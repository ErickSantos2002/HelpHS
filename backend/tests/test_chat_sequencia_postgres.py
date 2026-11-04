"""
Numeração do chat na ordem de commit (F1-B-04c), contra PostgreSQL.

O contrato, em uma frase: toda mensagem que um envio grava recebe `seq`, o
próximo número do chamado, no fim da transação — e número maior quer dizer
commit DEPOIS. É por isso que `GET ...?after_seq=k` acha a mensagem que
comitou tarde, coisa que nenhum cursor por `created_at` acha.

Nada aqui é mock de banco: a garantia é o bloqueio da linha do chamado, e
bloqueio só se prova no PostgreSQL, com conexões independentes. As corridas
são DETERMINÍSTICAS — cada transação é segurada num ponto conhecido e só é
solta quando o teste vê, no próprio banco, o estado que quer provar.

O servidor é o do `test_chat_historico_postgres.py` (pgserver, ou
`TEST_POSTGRES_URL`).
"""

import asyncio
import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from starlette.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import ChatMessage, LibraryFile, LibraryVisibility, Ticket, UserRole
from app.routers import chat as rota_do_chat
from app.services.chat_sequencia import numera_mensagens_do_chat, perdeu_a_concorrencia
from app.services.helo import FalaDaHelo
from tests import test_chat_historico_postgres as _base
from tests import test_chat_idempotencia_postgres as _idem
from tests.test_chat_historico_postgres import _arquivo, _grava, _mensagem, _usuario

# As fixtures de banco real são as do teste do histórico (ver o porquê da
# atribuição em `test_chat_idempotencia_postgres.py`).
url_do_banco = _base.url_do_banco
banco_real = _base.banco_real

_Cena = _idem._Cena
_rest = _idem._rest
_post = _idem._post
_rodar = _idem._rodar
_alguem_esperando_bloqueio = _idem._alguem_esperando_bloqueio
_UMA_VEZ = _idem._UMA_VEZ
_NADA = _idem._NADA


# ── Ambiente ──────────────────────────────────────────────────


class _HeloQueFala:
    """A Helô no lugar da de verdade: fala, e pode ser SEGURADA no meio — é o
    tempo do modelo de linguagem, com a transação do envio aberta.

    `porta` é `threading.Event` para servir também ao WebSocket, que roda o
    app noutra thread; a espera vai para `to_thread` e não trava o laço."""

    def __init__(self, *, segura: bool = False):
        self.entrou = threading.Event()
        self.porta = threading.Event()
        if not segura:
            self.porta.set()
        self.chamadas = 0

    async def __call__(self, db, ticket, cliente, texto):
        self.chamadas += 1
        self.entrou.set()
        await asyncio.to_thread(self.porta.wait, 30)
        fala = ChatMessage(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            sender_id=None,
            content="fala da Helô",
            is_system=False,
            is_ai=True,
            created_at=datetime.now(UTC),
        )
        db.add(fala)
        return FalaDaHelo(mensagem=fala, motivo=None)


async def _espera(evento: threading.Event, prazo: float = 10.0) -> None:
    assert await asyncio.to_thread(evento.wait, prazo), "a Helô não foi chamada"


async def _get(chamado_id, ator: str, **params):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(
            f"/api/v1/tickets/{chamado_id}/messages", params=params, headers={"x-ator": ator}
        )


async def _linhas(cena: _Cena, chamado_id=None) -> list[tuple]:
    """(conteúdo, seq, created_at) do chamado, na ordem da numeração."""
    alvo = chamado_id or cena.chamado.id
    async with cena.fabrica() as s:
        rs = await s.execute(
            select(ChatMessage.content, ChatMessage.seq, ChatMessage.created_at)
            .where(ChatMessage.ticket_id == alvo)
            .order_by(ChatMessage.seq.asc().nulls_first(), ChatMessage.created_at)
        )
        return [tuple(r) for r in rs.all()]


async def _contador(cena: _Cena, chamado_id=None) -> int:
    async with cena.fabrica() as s:
        return (
            await s.execute(
                select(Ticket.chat_seq).where(Ticket.id == (chamado_id or cena.chamado.id))
            )
        ).scalar_one()


async def _chamado_livre(cena: _Cena) -> bool:
    """Alguém segura a linha do chamado com UPDATE? `FOR NO KEY UPDATE NOWAIT`
    falha só nesse caso — o `FOR KEY SHARE` que cada INSERT de mensagem põe
    nela pela FK convive com ele."""
    async with cena.fabrica() as s:
        try:
            await s.execute(
                text("SELECT 1 FROM tickets WHERE id = :t FOR NO KEY UPDATE NOWAIT"),
                {"t": cena.chamado.id},
            )
            return True
        except DBAPIError as exc:
            assert getattr(exc.orig, "sqlstate", None) == "55P03", exc
            return False
        finally:
            await s.rollback()


async def _numera_gravando(cena: _Cena, *mensagens: ChatMessage) -> None:
    """Uma transação por mensagem, com a numeração do envio de verdade."""
    for m in mensagens:
        async with cena.fabrica() as s:
            s.add(m)
            await numera_mensagens_do_chat(s)
            await s.commit()


# ── A lacuna que motivou tudo ─────────────────────────────────


def test_commit_tardio_volta_por_after_seq_e_o_contador_nao_e_travado_durante_a_helo(banco_real):
    """O cliente escreve; a Helô "pensa" com a transação aberta. Nesse meio
    tempo o técnico escreve e comita. A mensagem do cliente tem `created_at`
    ANTERIOR à do técnico e comita DEPOIS: quem já tinha visto a do técnico
    a acha por `after_seq` — e a fala da Helô vem logo atrás, na ordem.

    Também prende a ordem dos bloqueios: durante a Helô a linha do chamado
    está LIVRE, e o técnico comita sem esperar por ela. Numerar antes da
    Helô (ou travar o chamado antes dela) derruba este teste."""

    async def _cena(cena: _Cena):
        helo = _HeloQueFala(segura=True)
        with _rest(cena), patch("app.routers.chat.responde_triagem", helo):
            lenta = asyncio.ensure_future(
                _post(cena.chamado.id, "cliente", "a lenta", chave=uuid.uuid4())
            )
            await _espera(helo.entrou)
            livre = await _chamado_livre(cena)
            rapida = await asyncio.wait_for(
                _post(cena.chamado.id, "tecnico", "a rápida", chave=uuid.uuid4()), 10
            )
            recente = await _get(cena.chamado.id, "cliente")
            ancora = recente.json()["ultima_seq"]
            antes = await _get(cena.chamado.id, "cliente", after_seq=ancora)
            helo.porta.set()
            lenta = await asyncio.wait_for(lenta, 15)
            depois = await _get(cena.chamado.id, "cliente", after_seq=ancora)
            return livre, rapida, ancora, antes, lenta, depois, await _linhas(cena)

    livre, rapida, ancora, antes, lenta, depois, linhas = _rodar(banco_real, _cena)

    assert livre, "a linha do chamado ficou travada durante a Helô"
    assert rapida.status_code == 201, rapida.text
    assert rapida.json()["seq"] == 1
    assert ancora == 1
    assert antes.json()["items"] == []
    assert (antes.json()["has_more"], antes.json()["next_after_seq"]) == (False, 1)

    assert lenta.status_code == 201, lenta.text
    assert lenta.json()["seq"] == 2
    corpo = depois.json()
    assert [(m["content"], m["seq"]) for m in corpo["items"]] == [
        ("a lenta", 2),
        ("fala da Helô", 3),
    ]
    assert (corpo["has_more"], corpo["next_after_seq"], corpo["ultima_seq"]) == (False, 3, 3)

    por_conteudo = {c: (s, quando) for c, s, quando in linhas}
    assert (
        por_conteudo["a lenta"][1] < por_conteudo["a rápida"][1]
    ), "o cenário precisa do created_at FORA da ordem de commit"
    assert [s for _, s, _ in linhas] == [1, 2, 3]


# ── Rollback e falha ──────────────────────────────────────────


def test_falha_depois_da_numeracao_desfaz_numero_e_mensagem_e_o_reenvio_grava(banco_real):
    """O número sai dentro da transação; ela morre antes do commit. Nada fica
    — nem a mensagem, nem o contador —, e o reenvio com a mesma chave grava
    com o MESMO número: rollback não deixa buraco."""
    chave = uuid.uuid4()
    visto: dict = {}

    async def _cena(cena: _Cena):
        async def _estoura(db):
            visto["contador"] = (
                await db.execute(
                    text("SELECT chat_seq FROM tickets WHERE id = :t"), {"t": cena.chamado.id}
                )
            ).scalar_one()
            visto["seq"] = (
                await db.execute(
                    text("SELECT seq FROM chat_messages WHERE client_message_id = :c"),
                    {"c": chave},
                )
            ).scalar_one()
            raise RuntimeError("falha simulada depois da numeração")

        with _rest(cena):
            with patch("app.routers.chat.commit_e_notificar", _estoura):
                with pytest.raises(RuntimeError):
                    await _post(cena.chamado.id, "cliente", chave=chave)
            sem_rastro = (await cena.contagem(), await _contador(cena))
            reenvio = await _post(cena.chamado.id, "cliente", chave=chave)
            return sem_rastro, reenvio, await cena.contagem(), await _contador(cena)

    sem_rastro, reenvio, depois, contador = _rodar(banco_real, _cena)

    assert visto == {"contador": 1, "seq": 1}, "a numeração tinha acontecido na transação"
    assert sem_rastro == (_NADA, 0)
    assert reenvio.status_code == 201, reenvio.text
    assert reenvio.json()["seq"] == 1
    assert (depois, contador) == (_UMA_VEZ, 1)


def test_envios_idempotentes_concorrentes_ganham_um_numero_so(banco_real):
    """Dois envios com a mesma chave ao mesmo tempo: a segunda espera no
    índice único, devolve a primeira — com o número dela — e não numera."""
    chave = uuid.uuid4()
    original = rota_do_chat._notify_other_party

    async def _cena(cena: _Cena):
        entrou, porta = asyncio.Event(), asyncio.Event()

        async def _segura(*a, **k):
            entrou.set()
            await porta.wait()
            return await original(*a, **k)

        with _rest(cena), patch("app.routers.chat._notify_other_party", _segura):
            tarefa = asyncio.ensure_future(
                asyncio.gather(
                    _post(cena.chamado.id, "tecnico", chave=chave),
                    _post(cena.chamado.id, "tecnico", chave=chave),
                )
            )
            await asyncio.wait_for(entrou.wait(), 10)
            viu_espera = await _alguem_esperando_bloqueio(cena.fabrica)
            porta.set()
            respostas = await tarefa
            return viu_espera, respostas, await _contador(cena), await cena.contagem()

    viu_espera, respostas, contador, depois = _rodar(banco_real, _cena)

    assert viu_espera
    assert sorted(r.status_code for r in respostas) == [200, 201]
    assert [r.json()["seq"] for r in respostas] == [1, 1]
    assert contador == 1
    assert depois == _UMA_VEZ


# ── Deadlock entre usuário e chamado ──────────────────────────


@pytest.mark.parametrize("quem_perde", ["o_envio", "a_outra"])
def test_ciclo_chamado_usuario_quem_perde_sai_inteiro_e_nada_e_repetido(banco_real, quem_perde):
    """O ciclo da prova de conceito, reproduzido com o envio de verdade.

    O envio do cliente segura `FOR KEY SHARE` no próprio usuário (FK do
    remetente) desde o INSERT. Outra transação trava o CHAMADO e depois pede
    o USUÁRIO com `FOR UPDATE` — a ordem que a regra proíbe. O envio, no fim,
    pede o chamado: ciclo. O PostgreSQL desfaz uma das duas.

    Quem perde é escolhido pelo `deadlock_timeout` de cada conexão: quem
    detecta primeiro é a vítima. As duas saídas são provadas:

    - o envio perde → 503, NADA gravado (mensagem, aviso, status, número), a
      Helô NÃO é chamada de novo pelo servidor, e o reenvio de quem enviou
      grava com o número 1;
    - a outra perde → o envio comita normalmente, com o número 1.
    """
    chave = uuid.uuid4()
    espera_da_outra = "30s" if quem_perde == "o_envio" else "50ms"

    async def _cena(cena: _Cena):
        helo = _HeloQueFala(segura=True)
        outra = cena.fabrica()
        try:
            await outra.execute(text(f"SET deadlock_timeout = '{espera_da_outra}'"))
        except DBAPIError:
            await outra.close()
            pytest.skip("o usuário do banco de testes não pode mudar deadlock_timeout")
        with _rest(cena), patch("app.routers.chat.responde_triagem", helo):
            envio = asyncio.ensure_future(
                _post(cena.chamado.id, "cliente", "no meio do ciclo", chave=chave)
            )
            await _espera(helo.entrou)
            await outra.execute(
                text("UPDATE tickets SET updated_at = now() WHERE id = :t"),
                {"t": cena.chamado.id},
            )
            helo.porta.set()
            assert await _alguem_esperando_bloqueio(cena.fabrica), "o envio não esperou o chamado"

            async def _pede_o_usuario():
                try:
                    await outra.execute(
                        text("SELECT 1 FROM users WHERE id = :u FOR UPDATE"),
                        {"u": cena.cliente.id},
                    )
                    await outra.commit()
                    return "comitou"
                except DBAPIError as exc:
                    await outra.rollback()
                    return "perdeu" if perdeu_a_concorrencia(exc) else f"erro: {exc}"

            resultado_da_outra, resposta = await asyncio.gather(_pede_o_usuario(), envio)
            await outra.close()
            chamadas_antes_do_reenvio = helo.chamadas
            depois_do_ciclo = (await cena.contagem(), await _contador(cena))
            reenvio = None
            if quem_perde == "o_envio":
                reenvio = await _post(cena.chamado.id, "cliente", "no meio do ciclo", chave=chave)
            return (
                resultado_da_outra,
                resposta,
                chamadas_antes_do_reenvio,
                depois_do_ciclo,
                reenvio,
                await cena.contagem(),
                await _linhas(cena),
            )

    outra, resposta, chamadas, depois_do_ciclo, reenvio, depois, linhas = _rodar(banco_real, _cena)

    if quem_perde == "o_envio":
        assert outra == "comitou"
        assert resposta.status_code == 503, resposta.text
        assert resposta.json()["detail"] == rota_do_chat._ENVIO_NAO_GRAVADO
        assert resposta.headers.get("retry-after") == "1"
        assert chamadas == 1, "o servidor não repete a Helô sozinho"
        assert depois_do_ciclo == (_NADA, 0)
        assert reenvio.status_code == 201, reenvio.text
        assert reenvio.json()["seq"] == 1
    else:
        assert outra == "perdeu"
        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["seq"] == 1
    assert depois == {**_UMA_VEZ, "mensagens": 2}, "a do cliente e a fala da Helô"
    assert [(c, s) for c, s, _ in linhas] == [("no meio do ciclo", 1), ("fala da Helô", 2)]


def test_usuario_antes_do_chamado_so_espera_e_ninguem_perde(banco_real):
    """A ordem da regra: quem trava o usuário PRIMEIRO e o chamado depois
    só espera o envio terminar — sem ciclo, sem vítima."""

    async def _cena(cena: _Cena):
        helo = _HeloQueFala(segura=True)
        outra = cena.fabrica()
        with _rest(cena), patch("app.routers.chat.responde_triagem", helo):
            envio = asyncio.ensure_future(_post(cena.chamado.id, "cliente", chave=uuid.uuid4()))
            await _espera(helo.entrou)

            async def _usuario_e_depois_chamado():
                await outra.execute(
                    text("SELECT 1 FROM users WHERE id = :u FOR UPDATE"), {"u": cena.cliente.id}
                )
                await outra.execute(
                    text("UPDATE tickets SET updated_at = now() WHERE id = :t"),
                    {"t": cena.chamado.id},
                )
                await outra.commit()
                return "comitou"

            tarefa = asyncio.ensure_future(_usuario_e_depois_chamado())
            assert await _alguem_esperando_bloqueio(cena.fabrica), "a outra não esperou o envio"
            helo.porta.set()
            resposta, resultado = await asyncio.wait_for(asyncio.gather(envio, tarefa), 15)
            await outra.close()
            return resposta, resultado

    resposta, resultado = _rodar(banco_real, _cena)

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["seq"] == 1
    assert resultado == "comitou"


# ── Concorrência entre chamados ───────────────────────────────


def test_dois_chamados_ao_mesmo_tempo_numeram_cada_um_do_seu_jeito(banco_real):
    async def _cena(cena: _Cena):
        with _rest(cena):
            alvos = [cena.chamado.id if i % 2 == 0 else cena.outro_chamado.id for i in range(12)]
            quem = ["cliente" if i % 3 == 0 else "tecnico" for i in range(12)]
            respostas = await asyncio.gather(
                *(_post(a, q, f"m{i}") for i, (a, q) in enumerate(zip(alvos, quem, strict=True)))
            )
            return (
                respostas,
                await _linhas(cena),
                await _linhas(cena, cena.outro_chamado.id),
                await _contador(cena),
                await _contador(cena, cena.outro_chamado.id),
            )

    respostas, um, outro, contador_um, contador_outro = _rodar(banco_real, _cena)

    assert all(r.status_code == 201 for r in respostas), [r.text for r in respostas]
    assert [s for _, s, _ in um] == list(range(1, 7))
    assert [s for _, s, _ in outro] == list(range(1, 7))
    assert (contador_um, contador_outro) == (6, 6)


# ── Consulta incremental ──────────────────────────────────────


def test_after_seq_pagina_mais_de_cem_sem_teto_silencioso(banco_real):
    """250 mensagens, uma transação cada: 100 + 100 + 50, com `has_more`
    verdadeiro enquanto houver página, e `next_after_seq` encadeando."""

    async def _cena(cena: _Cena):
        base = datetime.now(UTC) - timedelta(hours=1)
        await _numera_gravando(
            cena,
            *(
                _mensagem(cena.chamado, cena.tecnico, base + timedelta(seconds=i), texto=f"n{i}")
                for i in range(250)
            ),
        )
        paginas = []
        ancora = 0
        with _rest(cena):
            while True:
                r = await _get(cena.chamado.id, "cliente", after_seq=ancora)
                assert r.status_code == 200, r.text
                paginas.append(r.json())
                ancora = r.json()["next_after_seq"]
                if not r.json()["has_more"]:
                    break
        return paginas

    paginas = _rodar(banco_real, _cena)

    assert [len(p["items"]) for p in paginas] == [100, 100, 50]
    assert [p["has_more"] for p in paginas] == [True, True, False]
    assert [p["next_after_seq"] for p in paginas] == [100, 200, 250]
    seqs = [m["seq"] for p in paginas for m in p["items"]]
    assert seqs == list(range(1, 251))


def test_reconexao_prolongada_recupera_tudo_inclusive_a_tardia(banco_real):
    """A tela parou na 37. Enquanto esteve fora, comitaram mais 150 — a última
    delas carimbada ANTES de todas. Seguindo `next_after_seq` até o fim, ela
    acha as 150, sem repetir nenhuma."""

    async def _cena(cena: _Cena):
        base = datetime.now(UTC) - timedelta(hours=2)
        await _numera_gravando(
            cena,
            *(
                _mensagem(cena.chamado, cena.tecnico, base + timedelta(seconds=i), texto=f"a{i}")
                for i in range(37)
            ),
        )
        depois = [
            _mensagem(cena.chamado, cena.cliente, base + timedelta(minutes=10, seconds=i))
            for i in range(149)
        ]
        tardia = _mensagem(cena.chamado, cena.cliente, base - timedelta(hours=1), texto="tardia")
        await _numera_gravando(cena, *depois, tardia)
        vistas, ancora = [], 37
        with _rest(cena):
            while True:
                r = (await _get(cena.chamado.id, "cliente", after_seq=ancora)).json()
                vistas += r["items"]
                ancora = r["next_after_seq"]
                if not r["has_more"]:
                    break
        return vistas

    vistas = _rodar(banco_real, _cena)

    assert len(vistas) == 150
    assert len({m["id"] for m in vistas}) == 150
    assert vistas[-1]["content"] == "tardia"
    assert [m["seq"] for m in vistas] == list(range(38, 188))


# ── Legado e a primeira âncora ────────────────────────────────


def test_legado_sem_numero_continua_no_historico_e_fica_fora_do_incremental(banco_real):
    async def _cena(cena: _Cena):
        base = datetime.now(UTC) - timedelta(days=3)
        legado = [
            _mensagem(cena.chamado, cena.tecnico, base + timedelta(minutes=i), texto=f"antiga {i}")
            for i in range(3)
        ]
        await _grava(cena.fabrica, cena.criados, *legado)  # sem numerar: o passado
        with _rest(cena):
            novas = [await _post(cena.chamado.id, "cliente", f"nova {i}") for i in range(2)]
            recente = await _get(cena.chamado.id, "cliente")
            incremental = await _get(cena.chamado.id, "cliente", after_seq=0)
            por_cursor = await _get(cena.chamado.id, "cliente", limit=2)
            anterior = await _get(
                cena.chamado.id, "cliente", limit=50, before=por_cursor.json()["next_before"]
            )
        return novas, recente.json(), incremental.json(), anterior.json()

    novas, recente, incremental, anterior = _rodar(banco_real, _cena)

    assert [r.status_code for r in novas] == [201, 201]
    assert [(m["content"], m["seq"]) for m in recente["items"]] == [
        ("antiga 0", None),
        ("antiga 1", None),
        ("antiga 2", None),
        ("nova 0", 1),
        ("nova 1", 2),
    ]
    assert recente["ultima_seq"] == 2
    assert [m["content"] for m in incremental["items"]] == ["nova 0", "nova 1"]
    assert [m["content"] for m in anterior["items"]] == ["antiga 0", "antiga 1", "antiga 2"]


def test_a_primeira_ancora_nao_perde_o_que_comita_entre_o_contador_e_a_pagina(banco_real):
    """A tela abre (página recente, sem `after_seq`), guarda `ultima_seq` como
    âncora e depois segue por `after_seq`. Um commit no MEIO da leitura da
    página não pode cair entre as duas — ou está na página, ou volta pelo
    incremental. Prende a ordem: contador ANTES das mensagens."""
    original = rota_do_chat._ultima_seq

    async def _cena(cena: _Cena):
        await _numera_gravando(
            cena, _mensagem(cena.chamado, cena.tecnico, datetime.now(UTC), texto="primeira")
        )

        async def _com_commit_no_meio(db, ticket_id):
            # O commit acontece AQUI, colado na leitura do contador: com o
            # contador lido depois da página, a página não veria a mensagem e
            # o contador já a contaria — a âncora pularia por cima dela.
            await _numera_gravando(
                cena,
                _mensagem(cena.chamado, cena.cliente, datetime.now(UTC), texto="no meio"),
            )
            return await original(db, ticket_id)

        with _rest(cena):
            with patch("app.routers.chat._ultima_seq", _com_commit_no_meio):
                pagina = (await _get(cena.chamado.id, "cliente")).json()
            seguinte = (
                await _get(cena.chamado.id, "cliente", after_seq=pagina["ultima_seq"])
            ).json()
        return pagina, seguinte

    pagina, seguinte = _rodar(banco_real, _cena)

    vistas = {m["content"] for m in pagina["items"]} | {m["content"] for m in seguinte["items"]}
    assert "no meio" in vistas
    assert {"primeira", "no meio"} <= vistas


# ── Acesso, anexos internos e contrato ────────────────────────


def test_after_seq_respeita_o_acesso_e_o_arquivo_interno(banco_real):
    async def _cena(cena: _Cena):
        arquivo = _arquivo(cena.tecnico)
        await _grava(cena.fabrica, cena.criados, arquivo)
        with _rest(cena):
            enviada = await _post(
                cena.chamado.id, "tecnico", "segue o manual", library_file_id=str(arquivo.id)
            )
            async with cena.fabrica() as s:
                await s.execute(
                    update(LibraryFile)
                    .where(LibraryFile.id == arquivo.id)
                    .values(visibility=LibraryVisibility.internal)
                )
                await s.commit()
            do_cliente = await _get(cena.chamado.id, "cliente", after_seq=0)
            da_equipe = await _get(cena.chamado.id, "tecnico", after_seq=0)
            alheio = await _get(cena.chamado.id, "intruso", after_seq=0)
            alheio_sem = await _get(cena.chamado.id, "intruso")
        return enviada, do_cliente, da_equipe, alheio, alheio_sem

    enviada, do_cliente, da_equipe, alheio, alheio_sem = _rodar(banco_real, _cena)

    assert enviada.status_code == 201, enviada.text
    m = do_cliente.json()["items"][0]
    assert m["library_file_unavailable"] is True
    assert m["library_file_name"] is None and m["library_file_id"] is None
    assert da_equipe.json()["items"][0]["library_file_name"] == "manual-do-equipamento.pdf"
    assert alheio.status_code == alheio_sem.status_code == 404
    assert alheio.json() == alheio_sem.json()


def test_after_seq_recusa_combinacao_e_ancora_maior_que_o_contador(banco_real):
    async def _cena(cena: _Cena):
        with _rest(cena):
            await _post(cena.chamado.id, "cliente")
            com_offset = await _get(cena.chamado.id, "cliente", after_seq=0, offset=0)
            pagina = await _get(cena.chamado.id, "cliente", limit=1)
            com_before = await _get(cena.chamado.id, "cliente", after_seq=0, before="x")
            negativo = await _get(cena.chamado.id, "cliente", after_seq=-1)
            alem = await _get(cena.chamado.id, "cliente", after_seq=2)
            igual = await _get(cena.chamado.id, "cliente", after_seq=1)
        return com_offset, pagina, com_before, negativo, alem, igual

    com_offset, pagina, com_before, negativo, alem, igual = _rodar(banco_real, _cena)

    assert com_offset.status_code == com_before.status_code == negativo.status_code == 422
    assert pagina.json()["next_after_seq"] is None, "fora do modo incremental"
    assert alem.status_code == 409, alem.text
    assert alem.json()["detail"]["code"] == "ressincronizar"
    assert alem.json()["detail"]["ultima_seq"] == 1
    assert igual.status_code == 200
    assert (igual.json()["items"], igual.json()["next_after_seq"]) == ([], 1)


# ── WebSocket ─────────────────────────────────────────────────


def test_ws_quadros_e_confirmacao_levam_o_numero_e_a_helo_vem_depois(banco_real):
    cena, (p1, p2, p3) = _idem._ws(banco_real)
    chave = str(uuid.uuid4())
    helo = _HeloQueFala()

    with p1, p2, p3, patch("app.routers.chat.responde_triagem", helo):
        with TestClient(app).websocket_connect(_idem._url(cena.chamado.id, cena.cliente)) as ws:
            ws.send_text(json.dumps({"content": "pelo socket", "client_message_id": chave}))
            quadros = _idem._ate(ws, "ack")

    mensagens = [q["data"] for q in quadros if q["type"] == "message"]
    assert [(m["content"], m["seq"]) for m in mensagens] == [
        ("pelo socket", 1),
        ("fala da Helô", 2),
    ]
    assert quadros[-1]["data"]["seq"] == 1
    assert asyncio.run(cena.contagem()) == {**_UMA_VEZ, "mensagens": 2}


def test_ws_envio_que_perde_o_deadlock_volta_como_erro_e_o_socket_segue(banco_real):
    """Mesmo ciclo do REST, pelo socket. O envio perde: chega um `error` com a
    chave e o código `envio_nao_gravado`, nada fica gravado, e o MESMO socket
    aceita o reenvio, que grava com o número 1."""
    cena, (p1, p2, p3) = _idem._ws(banco_real)
    chave = str(uuid.uuid4())
    helo = _HeloQueFala(segura=True)
    laco = asyncio.new_event_loop()
    outra = cena.fabrica()
    try:
        try:
            laco.run_until_complete(outra.execute(text("SET deadlock_timeout = '30s'")))
        except DBAPIError:
            pytest.skip("o usuário do banco de testes não pode mudar deadlock_timeout")

        with p1, p2, p3, patch("app.routers.chat.responde_triagem", helo):
            with TestClient(app).websocket_connect(_idem._url(cena.chamado.id, cena.cliente)) as ws:
                ws.send_text(json.dumps({"content": "pelo socket", "client_message_id": chave}))
                assert helo.entrou.wait(10)
                laco.run_until_complete(
                    outra.execute(
                        text("UPDATE tickets SET updated_at = now() WHERE id = :t"),
                        {"t": cena.chamado.id},
                    )
                )
                helo.porta.set()
                assert laco.run_until_complete(_alguem_esperando_bloqueio(cena.fabrica))
                laco.run_until_complete(
                    outra.execute(
                        text("SELECT 1 FROM users WHERE id = :u FOR UPDATE"),
                        {"u": cena.cliente.id},
                    )
                )
                laco.run_until_complete(outra.commit())
                recusa = _idem._ate(ws, "error")
                depois_da_recusa = asyncio.run(cena.contagem())

                ws.send_text(json.dumps({"content": "pelo socket", "client_message_id": chave}))
                aceito = _idem._ate(ws, "ack")
    finally:
        laco.run_until_complete(outra.close())
        laco.close()

    erro = recusa[-1]
    assert erro["code"] == "envio_nao_gravado"
    assert erro["client_message_id"] == chave
    assert erro["detail"] == rota_do_chat._ENVIO_NAO_GRAVADO
    assert [q for q in recusa if q["type"] == "message"] == [], "nada foi para a sala"
    assert depois_da_recusa == _NADA
    assert aceito[-1]["duplicate"] is False
    assert aceito[-1]["data"]["seq"] == 1
    assert helo.chamadas == 2, "uma pelo envio, outra pelo REENVIO de quem enviou"


# ── A saudação da abertura ────────────────────────────────────


def test_a_saudacao_da_helo_na_abertura_e_a_mensagem_1_do_chamado(banco_real):
    """O quarto escritor: `abre_triagem`, dentro do `create_ticket`. A
    saudação nasce no commit do chamado, com o número 1."""
    fabrica, criados = banco_real

    async def _cena():
        cliente = _usuario(UserRole.client)
        await _grava(fabrica, criados, cliente)

        async def _db():
            async with fabrica() as s:
                yield s

        async def _ator():
            return cliente

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _ator
        try:
            with (
                patch(
                    "app.services.helo.get_settings",
                    lambda: MagicMock(helo_enabled=True, helo_modo="triagem"),
                ),
                patch("app.routers.tickets._classify_ticket_async", AsyncMock()),
            ):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                    r = await c.post(
                        "/api/v1/tickets",
                        json={
                            "title": "Impressora",
                            "description": "parou",
                            "category": "hardware",
                        },
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
        assert r.status_code == 201, r.text
        chamado_id = uuid.UUID(r.json()["id"])
        criados["tickets"].add(chamado_id)
        async with fabrica() as s:
            linhas = (
                await s.execute(
                    select(ChatMessage.is_ai, ChatMessage.seq).where(
                        ChatMessage.ticket_id == chamado_id
                    )
                )
            ).all()
            contador = (
                await s.execute(select(Ticket.chat_seq).where(Ticket.id == chamado_id))
            ).scalar_one()
        return [tuple(x) for x in linhas], contador

    linhas, contador = asyncio.run(_cena())

    assert linhas == [(True, 1)]
    assert contador == 1
