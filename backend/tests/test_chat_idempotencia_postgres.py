"""
Idempotência do envio de mensagem no chat (D4, F1-B-04a), contra PostgreSQL.

O contrato: quem envia pode mandar um `client_message_id`. A mesma chave, da
mesma pessoa, no mesmo chamado, com o mesmo conteúdo, devolve a mensagem que já
foi gravada — sem gravar outra, sem notificar de novo, sem chamar a Helô de
novo e sem transmitir de novo para a sala. Com outro conteúdo, é conflito.

Nada aqui é mock de banco: a garantia final é o índice único parcial
`uq_chat_messages_envio`, e índice só se prova no PostgreSQL. As corridas são
DETERMINÍSTICAS: a primeira requisição é segurada depois de gravar e antes de
comitar, e o teste só a solta quando vê, em `pg_stat_activity`, a segunda
parada esperando o bloqueio do índice. Sem isso, "dois envios simultâneos"
passaria por sorte de escalonamento.

O servidor é o do `test_chat_historico_postgres.py` (pgserver com
`cleanup_mode="stop"`, ou `TEST_POSTGRES_URL`).
"""

import asyncio
import json
import threading
import time
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import (
    ChatMessage,
    LibraryFile,
    LibraryVisibility,
    Notification,
    NotificationType,
    Ticket,
    TicketHistory,
    TicketStatus,
    UserRole,
)
from app.routers import chat as rota_do_chat
from tests import test_chat_historico_postgres as _base
from tests.test_chat_historico_postgres import (
    _arquivo,
    _chamado,
    _grava,
    _usuario,
    _ws_ambiente,
)

# As fixtures de banco real são as do teste do histórico. Atribuídas, e não
# importadas pelo nome: o import direto faz o ruff ler cada parâmetro
# `banco_real` como redefinição (F811) — o mesmo arranjo do `test_anexos_zip.py`.
url_do_banco = _base.url_do_banco
banco_real = _base.banco_real

_TEXTO = "a impressora parou de novo"
_UMA_VEZ = {"mensagens": 1, "aviso_da_mensagem": 1, "aviso_de_status": 1, "status": 1}
_NADA = {"mensagens": 0, "aviso_da_mensagem": 0, "aviso_de_status": 0, "status": 0}


# ── Ambiente ──────────────────────────────────────────────────


class _Cena:
    """Pessoas e chamado gravados de verdade, e a contagem do que eles geraram."""

    def __init__(self, fabrica, criados):
        self.fabrica = fabrica
        self.criados = criados
        self.cliente = _usuario(UserRole.client)
        self.tecnico = _usuario(UserRole.technician)
        self.intruso = _usuario(UserRole.client)
        self.chamado = _chamado(self.cliente, self.tecnico)
        self.outro_chamado = _chamado(self.cliente, self.tecnico)
        self.do_intruso = _chamado(self.intruso, self.tecnico)

    async def grava(self) -> "_Cena":
        await _grava(self.fabrica, self.criados, self.cliente, self.tecnico, self.intruso)
        await _grava(self.fabrica, self.criados, self.chamado, self.outro_chamado, self.do_intruso)
        return self

    @property
    def atores(self):
        return {"cliente": self.cliente, "tecnico": self.tecnico, "intruso": self.intruso}

    async def contagem(self, chamado: Ticket | None = None) -> dict:
        """Cada efeito de um envio, contado no banco. Um envio só, com o chamado
        em andamento, dá `_UMA_VEZ`: a mensagem, o aviso dela, a mudança de
        status no histórico e o aviso dessa mudança."""
        alvo = (chamado or self.chamado).id

        def _avisos(tipo):
            return (
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.data["ticket_id"].astext == str(alvo), Notification.type == tipo
                )
            )

        async with self.fabrica() as s:
            mensagens = (
                await s.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.ticket_id == alvo)
                )
            ).scalar_one()
            aviso_da_mensagem = (
                await s.execute(_avisos(NotificationType.chat_message))
            ).scalar_one()
            aviso_de_status = (
                await s.execute(_avisos(NotificationType.ticket_updated))
            ).scalar_one()
            status = (
                await s.execute(
                    select(func.count())
                    .select_from(TicketHistory)
                    .where(TicketHistory.ticket_id == alvo, TicketHistory.field == "status")
                )
            ).scalar_one()
        return {
            "mensagens": mensagens,
            "aviso_da_mensagem": aviso_da_mensagem,
            "aviso_de_status": aviso_de_status,
            "status": status,
        }

    async def chamado_atual(self) -> Ticket:
        async with self.fabrica() as s:
            return (
                await s.execute(select(Ticket).where(Ticket.id == self.chamado.id))
            ).scalar_one()


class _Helo:
    """A Helô no lugar da de verdade: conta as chamadas — efeito externo, a
    chamada ao modelo de linguagem, que rollback nenhum desfaz — e não fala."""

    def __init__(self):
        self.chamadas = 0

    async def __call__(self, *a, **k):
        self.chamadas += 1
        return None


@contextmanager
def _rest(cena: _Cena):
    """Uma sessão nova por requisição, como em produção; o ator vem do
    cabeçalho `x-ator`. A Helô é contada e o backplane fica sem rede."""

    async def _db():
        async with cena.fabrica() as s:
            yield s

    async def _ator(request: Request):
        return cena.atores[request.headers["x-ator"]]

    async def _sem_rede(*a, **k):
        return None

    helo = _Helo()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _ator
    try:
        with (
            patch("app.routers.chat.chat_backplane.publicar", _sem_rede),
            patch("app.routers.chat.responde_triagem", helo),
        ):
            yield helo
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _post(chamado_id, ator: str, conteudo: str = _TEXTO, chave=None, **extra):
    corpo: dict = {"content": conteudo, **extra}
    if chave is not None:
        corpo["client_message_id"] = str(chave)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.post(
            f"/api/v1/tickets/{chamado_id}/messages", json=corpo, headers={"x-ator": ator}
        )


async def _alguem_esperando_bloqueio(fabrica, prazo: float = 10.0) -> bool:
    """Alguma conexão deste banco parada esperando um bloqueio — a segunda
    gravação, presa no índice único enquanto a primeira não comita."""
    limite = time.monotonic() + prazo
    while time.monotonic() < limite:
        async with fabrica() as s:
            esperando = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                    )
                )
            ).scalar_one()
        if esperando:
            return True
        await asyncio.sleep(0.05)
    return False


def _rodar(banco_real, cena_async):
    fabrica, criados = banco_real

    async def _tudo():
        cena = await _Cena(fabrica, criados).grava()
        return await cena_async(cena)

    return asyncio.run(_tudo())


# ── REST: o reenvio ───────────────────────────────────────────


def test_reenvio_com_a_mesma_chave_devolve_a_original(banco_real):
    """201 na criação, 200 na repetição, o mesmo id, nada gravado de novo — e a
    mensagem continua no histórico como qualquer outra, com a chave."""
    chave = uuid.uuid4()

    async def _cena(cena: _Cena):
        with _rest(cena) as helo:
            primeira = await _post(cena.chamado.id, "cliente", chave=chave)
            depois_da_primeira = await cena.contagem()
            segunda = await _post(cena.chamado.id, "cliente", chave=chave)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                historico = await c.get(
                    f"/api/v1/tickets/{cena.chamado.id}/messages", headers={"x-ator": "cliente"}
                )
            return primeira, segunda, historico, depois_da_primeira, await cena.contagem(), helo

    primeira, segunda, historico, antes, depois, helo = _rodar(banco_real, _cena)

    assert primeira.status_code == 201, primeira.text
    assert segunda.status_code == 200, segunda.text
    assert segunda.json() == primeira.json()
    assert primeira.json()["client_message_id"] == str(chave)
    assert depois == antes == _UMA_VEZ
    assert helo.chamadas == 1
    assert [m["id"] for m in historico.json()["items"]] == [primeira.json()["id"]]
    assert historico.json()["items"][0]["client_message_id"] == str(chave)


def test_resposta_perdida_depois_do_commit_e_recuperada_sem_nova_transmissao(banco_real):
    """O commit voltou e a confirmação não chegou a quem enviou (aqui: a
    transmissão para a sala estoura depois do commit). O reenvio devolve a
    mensagem gravada e NÃO transmite de novo para a sala."""
    chave = uuid.uuid4()
    transmissoes: list[dict] = []

    async def _cai(_sala, _quadro):
        raise RuntimeError("a conexão caiu antes da resposta")

    async def _anota(_sala, quadro):
        transmissoes.append(quadro)

    async def _cena(cena: _Cena):
        with _rest(cena):
            with patch.object(rota_do_chat.manager, "broadcast", _cai):
                with pytest.raises(RuntimeError):
                    await _post(cena.chamado.id, "cliente", chave=chave)
            gravada = await cena.contagem()
            with patch.object(rota_do_chat.manager, "broadcast", _anota):
                reenvio = await _post(cena.chamado.id, "cliente", chave=chave)
            return gravada, reenvio, await cena.contagem()

    gravada, reenvio, depois = _rodar(banco_real, _cena)

    assert gravada["mensagens"] == 1, "o commit tinha voltado antes da queda"
    assert reenvio.status_code == 200, reenvio.text
    assert depois == gravada
    assert transmissoes == []


@pytest.mark.parametrize("onde", ["depois_de_gravar", "no_commit"])
def test_falha_antes_do_commit_nao_deixa_rastro_e_o_reenvio_grava(banco_real, onde):
    """A mensagem já foi ao banco (o INSERT sai antes da Helô) mas a transação
    não comitou: nada fica — nem a mensagem, nem o aviso —, e o reenvio com a
    mesma chave grava uma vez, como um envio novo."""
    chave = uuid.uuid4()
    alvo = {
        "depois_de_gravar": "app.routers.chat._notify_other_party",
        "no_commit": "app.routers.chat.commit_e_notificar",
    }[onde]

    async def _estoura(*a, **k):
        raise RuntimeError(f"falha simulada: {onde}")

    async def _cena(cena: _Cena):
        with _rest(cena):
            with patch(alvo, _estoura):
                with pytest.raises(RuntimeError):
                    await _post(cena.chamado.id, "cliente", chave=chave)
            sem_rastro = await cena.contagem()
            reenvio = await _post(cena.chamado.id, "cliente", chave=chave)
            return sem_rastro, reenvio, await cena.contagem()

    sem_rastro, reenvio, depois = _rodar(banco_real, _cena)

    assert sem_rastro == _NADA
    assert reenvio.status_code == 201, reenvio.text
    assert depois == _UMA_VEZ


@pytest.mark.parametrize("diferenca", ["texto", "arquivo"])
def test_mesma_chave_com_outro_conteudo_e_409(banco_real, diferenca):
    """A chave não torna duas mensagens iguais: a impressão do conteúdo
    pedido também precisa bater. A original fica intacta."""
    chave = uuid.uuid4()

    async def _cena(cena: _Cena):
        arquivo = _arquivo(cena.tecnico)
        await _grava(cena.fabrica, cena.criados, arquivo)
        with _rest(cena):
            primeira = await _post(cena.chamado.id, "tecnico", chave=chave)
            if diferenca == "texto":
                outra = await _post(cena.chamado.id, "tecnico", "outra coisa", chave=chave)
            else:
                outra = await _post(
                    cena.chamado.id, "tecnico", chave=chave, library_file_id=str(arquivo.id)
                )
            return primeira, outra, await cena.contagem()

    primeira, outra, depois = _rodar(banco_real, _cena)

    assert primeira.status_code == 201, primeira.text
    assert outra.status_code == 409, outra.text
    assert "client_message_id" in outra.json()["detail"]
    assert _TEXTO not in outra.text, "o 409 não devolve o conteúdo da original"
    assert depois["mensagens"] == 1


def test_mesma_chave_em_outro_chamado_e_outra_mensagem(banco_real):
    chave = uuid.uuid4()

    async def _cena(cena: _Cena):
        with _rest(cena):
            a = await _post(cena.chamado.id, "cliente", chave=chave)
            b = await _post(cena.outro_chamado.id, "cliente", chave=chave)
        return a, b

    a, b = _rodar(banco_real, _cena)

    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["id"] != b.json()["id"]


def test_mesma_chave_de_outro_remetente_e_outra_mensagem(banco_real):
    chave = uuid.uuid4()

    async def _cena(cena: _Cena):
        with _rest(cena):
            a = await _post(cena.chamado.id, "cliente", chave=chave)
            b = await _post(cena.chamado.id, "tecnico", chave=chave)
            return a, b, await cena.contagem()

    a, b, depois = _rodar(banco_real, _cena)

    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["id"] != b.json()["id"]
    assert depois["mensagens"] == 2


def test_cliente_sem_chave_continua_como_sempre(banco_real):
    """Cliente antigo: o mesmo texto duas vezes são duas mensagens, e a
    resposta traz a chave nula."""

    async def _cena(cena: _Cena):
        with _rest(cena):
            a = await _post(cena.chamado.id, "cliente")
            b = await _post(cena.chamado.id, "cliente")
            return a, b, await cena.contagem()

    a, b, depois = _rodar(banco_real, _cena)

    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["client_message_id"] is None
    assert depois["mensagens"] == 2


def test_chave_alheia_nao_revela_mensagem_de_outro_chamado(banco_real):
    """O intruso conhece a chave da vítima. No chamado dela: o mesmo 404 de
    sempre. No chamado DELE: uma mensagem nova, dele — nunca a da vítima."""
    chave = uuid.uuid4()

    async def _cena(cena: _Cena):
        with _rest(cena):
            da_vitima = await _post(cena.chamado.id, "cliente", "segredo da vítima", chave=chave)
            no_alheio = await _post(cena.chamado.id, "intruso", "segredo da vítima", chave=chave)
            sem_chave = await _post(cena.chamado.id, "intruso", "segredo da vítima")
            no_proprio = await _post(
                cena.do_intruso.id, "intruso", "segredo da vítima", chave=chave
            )
        return da_vitima, no_alheio, sem_chave, no_proprio, cena.do_intruso.id

    da_vitima, no_alheio, sem_chave, no_proprio, do_intruso = _rodar(banco_real, _cena)

    assert da_vitima.status_code == 201
    assert no_alheio.status_code == sem_chave.status_code == 404
    assert no_alheio.json() == sem_chave.json()
    assert no_proprio.status_code == 201
    assert no_proprio.json()["id"] != da_vitima.json()["id"]
    assert no_proprio.json()["ticket_id"] == str(do_intruso)


def test_reenvio_depois_de_o_arquivo_virar_interno_devolve_a_original(banco_real):
    """A repetição vem antes da conferência do arquivo: o que já foi aceito
    não vira erro porque o arquivo mudou depois."""
    chave = uuid.uuid4()

    async def _cena(cena: _Cena):
        arquivo = _arquivo(cena.tecnico)
        await _grava(cena.fabrica, cena.criados, arquivo)
        with _rest(cena):
            primeira = await _post(
                cena.chamado.id, "tecnico", chave=chave, library_file_id=str(arquivo.id)
            )
            async with cena.fabrica() as s:
                await s.execute(
                    update(LibraryFile)
                    .where(LibraryFile.id == arquivo.id)
                    .values(visibility=LibraryVisibility.internal)
                )
                await s.commit()
            reenvio = await _post(
                cena.chamado.id, "tecnico", chave=chave, library_file_id=str(arquivo.id)
            )
            return primeira, reenvio

    primeira, reenvio = _rodar(banco_real, _cena)

    assert primeira.status_code == 201, primeira.text
    assert reenvio.status_code == 200, reenvio.text
    assert reenvio.json()["id"] == primeira.json()["id"]
    assert reenvio.json()["library_file_name"] == "manual-do-equipamento.pdf"


# ── REST: a corrida ───────────────────────────────────────────


@pytest.mark.parametrize("quem", ["cliente", "tecnico"])
def test_dois_envios_simultaneos_gravam_e_produzem_efeitos_uma_vez(banco_real, quem):
    """A primeira requisição grava e é segurada antes de comitar. A segunda,
    com a mesma chave, passa pela consulta prévia (a primeira ainda não é
    visível) e PARA no índice único — o teste só solta a primeira depois de
    ver essa espera no banco. Resultado: uma linha, um aviso, uma mudança de
    status, uma primeira resposta de SLA e uma Helô."""
    chave = uuid.uuid4()
    original = rota_do_chat._notify_other_party

    async def _cena(cena: _Cena):
        entrou, porta = asyncio.Event(), asyncio.Event()

        async def _segura(*a, **k):
            entrou.set()
            await porta.wait()
            return await original(*a, **k)

        with _rest(cena) as helo, patch("app.routers.chat._notify_other_party", _segura):
            corrida = asyncio.gather(
                _post(cena.chamado.id, quem, chave=chave),
                _post(cena.chamado.id, quem, chave=chave),
            )
            tarefa = asyncio.ensure_future(corrida)
            await asyncio.wait_for(entrou.wait(), 10)
            viu_espera = await _alguem_esperando_bloqueio(cena.fabrica)
            porta.set()
            respostas = await tarefa
            return respostas, viu_espera, await cena.contagem(), helo, await cena.chamado_atual()

    respostas, viu_espera, depois, helo, chamado = _rodar(banco_real, _cena)

    assert viu_espera, "a segunda gravação não ficou presa no índice único"
    assert sorted(r.status_code for r in respostas) == [200, 201], [r.text for r in respostas]
    assert respostas[0].json()["id"] == respostas[1].json()["id"]
    assert depois == _UMA_VEZ
    assert helo.chamadas == (1 if quem == "cliente" else 0)
    if quem == "tecnico":
        assert chamado.status is TicketStatus.awaiting_client
        assert chamado.sla_first_response is not None
    else:
        assert chamado.status is TicketStatus.awaiting_technical


def test_corrida_com_a_mesma_chave_e_outro_conteudo_da_409_para_quem_perde(banco_real):
    """A mesma corrida, mas com conteúdos diferentes: quem para no índice não
    é reenvio, é chave reaproveitada. Um 201, um 409, e a linha que ficou é a
    de quem venceu."""
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
                    _post(cena.chamado.id, "tecnico", "versão A", chave=chave),
                    _post(cena.chamado.id, "tecnico", "versão B", chave=chave),
                )
            )
            await asyncio.wait_for(entrou.wait(), 10)
            viu_espera = await _alguem_esperando_bloqueio(cena.fabrica)
            porta.set()
            respostas = await tarefa
        async with cena.fabrica() as s:
            gravado = (
                await s.execute(
                    select(ChatMessage.content).where(ChatMessage.ticket_id == cena.chamado.id)
                )
            ).scalar_one()
        return respostas, viu_espera, gravado

    respostas, viu_espera, gravado = _rodar(banco_real, _cena)

    assert viu_espera
    assert sorted(r.status_code for r in respostas) == [201, 409], [r.text for r in respostas]
    vencedora = next(r for r in respostas if r.status_code == 201)
    assert gravado == vencedora.json()["content"]


@pytest.mark.parametrize("remetente", ["pessoa", "ninguem"])
def test_violacao_que_nao_e_da_chave_continua_subindo(banco_real, remetente):
    """`_grava_uma_vez` só transforma em repetição a violação da CHAVE. Outra
    regra do banco — aqui, um chamado que não existe — sobe como sempre subiu,
    em vez de virar um 200 com a mensagem de outra pessoa ou um None calado."""

    async def _cena(cena: _Cena):
        msg = ChatMessage(
            id=uuid.uuid4(),
            ticket_id=uuid.uuid4(),  # FK quebrada de propósito
            sender_id=cena.cliente.id if remetente == "pessoa" else None,
            content="oi",
            is_system=False,
            is_ai=False,
            client_message_id=uuid.uuid4(),
            client_message_fingerprint="f" * 64,
        )
        async with cena.fabrica() as s:
            with pytest.raises(IntegrityError, match="ticket_id"):
                await rota_do_chat._grava_uma_vez(s, msg)

    _rodar(banco_real, _cena)


# ── O índice ──────────────────────────────────────────────────

# `pg_get_constraintdef` do CHECK, como o PostgreSQL o devolve. O mesmo texto é
# conferido depois da migration (`test_migrations_postgres.py`): é assim que o
# model e a migration provam que declaram a mesma regra.
REGRA_CHAVE_COM_IMPRESSAO = (
    "CHECK (((client_message_id IS NULL) = (client_message_fingerprint IS NULL)))"
)


def test_o_indice_unico_e_a_garantia_e_a_regra_vale_no_banco(banco_real):
    """Sem passar pelo código: o banco recusa a segunda linha com a mesma
    (chamado, remetente, chave), aceita quantas linhas sem chave houver, e
    recusa chave sem impressão."""
    chave = uuid.uuid4()

    async def _insere(cena: _Cena, s, chave_da_vez, impressao="x" * 64):
        await s.execute(
            text(
                "INSERT INTO chat_messages (id, ticket_id, sender_id, content, is_system, "
                "is_ai, client_message_id, client_message_fingerprint) "
                "VALUES (:id, :t, :s, 'oi', false, false, :k, :f)"
            ),
            {
                "id": uuid.uuid4(),
                "t": cena.chamado.id,
                "s": cena.cliente.id,
                "k": chave_da_vez,
                "f": impressao if chave_da_vez else None,
            },
        )

    async def _cena(cena: _Cena):
        resultados = {}
        async with cena.fabrica() as s:
            await _insere(cena, s, chave)
            await _insere(cena, s, None)
            await _insere(cena, s, None)
            await s.commit()
        async with cena.fabrica() as s:
            try:
                await _insere(cena, s, chave)
                await s.commit()
                resultados["repetida"] = "gravou"
            except IntegrityError as e:
                resultados["repetida"] = str(e.orig)
        async with cena.fabrica() as s:
            try:
                await s.execute(
                    text(
                        "INSERT INTO chat_messages (id, ticket_id, sender_id, content, "
                        "is_system, is_ai, client_message_id) "
                        "VALUES (:id, :t, :s, 'oi', false, false, :k)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "t": cena.chamado.id,
                        "s": cena.cliente.id,
                        "k": uuid.uuid4(),
                    },
                )
                await s.commit()
                resultados["sem_impressao"] = "gravou"
            except IntegrityError as e:
                resultados["sem_impressao"] = str(e.orig)
        async with cena.fabrica() as s:
            resultados["regra"] = (
                await s.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conname = 'ck_chat_messages_chave_com_impressao'"
                    )
                )
            ).scalar_one()
        resultados["contagem"] = await cena.contagem()
        return resultados

    r = _rodar(banco_real, _cena)

    assert "uq_chat_messages_envio" in r["repetida"]
    assert "ck_chat_messages_chave_com_impressao" in r["sem_impressao"]
    assert r["regra"] == REGRA_CHAVE_COM_IMPRESSAO
    assert r["contagem"]["mensagens"] == 3


# ── WebSocket ─────────────────────────────────────────────────


def _ate(ws, tipo: str, limite: int = 20) -> list[dict]:
    """Lê quadros até chegar um do tipo pedido; devolve todos os lidos."""
    lidos = []
    for _ in range(limite):
        quadro = ws.receive_json()
        lidos.append(quadro)
        if quadro["type"] == tipo:
            return lidos
    raise AssertionError(f"nenhum quadro {tipo!r} em {lidos}")


def _nada_mais_chegou(ws) -> list[dict]:
    """Manda uma sonda e devolve o que chegou ANTES da resposta dela. Os
    quadros de um socket chegam em ordem: vazio prova que nada ficou no meio."""
    ws.send_text("sonda: isto não é json")
    return _ate(ws, "error")[:-1]


def _url(chamado_id, pessoa) -> str:
    return f"/api/v1/ws/tickets/{chamado_id}?token={pessoa.id}"


def _ws(banco_real):
    fabrica, criados = banco_real
    cena = asyncio.run(_Cena(fabrica, criados).grava())
    return cena, _ws_ambiente(fabrica)


def test_ws_ecoa_a_chave_e_o_reenvio_so_confirma_para_quem_enviou(banco_real):
    cena, (p1, p2, p3) = _ws(banco_real)
    chave = str(uuid.uuid4())
    helo = _Helo()

    with p1, p2, p3, patch("app.routers.chat.responde_triagem", helo):
        tc = TestClient(app)
        with (
            tc.websocket_connect(_url(cena.chamado.id, cena.cliente)) as quem_envia,
            tc.websocket_connect(_url(cena.chamado.id, cena.tecnico)) as quem_assiste,
        ):
            quem_envia.send_text(json.dumps({"content": _TEXTO, "client_message_id": chave}))
            primeira = _ate(quem_envia, "ack")
            # Tudo o que o primeiro envio mandou à sala (mensagem e status).
            na_sala = _nada_mais_chegou(quem_assiste)

            quem_envia.send_text(json.dumps({"content": _TEXTO, "client_message_id": chave}))
            reenvio = _ate(quem_envia, "ack")
            para_a_sala = _nada_mais_chegou(quem_assiste)

    mensagem = next(q for q in primeira if q["type"] == "message")["data"]
    confirmacao = primeira[-1]
    assert mensagem["client_message_id"] == chave
    assert confirmacao["client_message_id"] == chave
    assert confirmacao["duplicate"] is False
    assert confirmacao["data"]["id"] == mensagem["id"]
    assert [q["type"] for q in na_sala] == ["message", "status_update"]
    assert na_sala[0]["data"]["id"] == mensagem["id"]
    assert na_sala[0]["data"]["client_message_id"] == chave

    assert [q["type"] for q in reenvio] == ["ack"], "o reenvio não transmite de novo"
    assert reenvio[0]["duplicate"] is True
    assert reenvio[0]["data"]["id"] == mensagem["id"]
    assert para_a_sala == []
    assert asyncio.run(cena.contagem())["mensagens"] == 1
    assert helo.chamadas == 1


def test_ws_mesma_chave_com_outro_conteudo_e_erro_de_conflito(banco_real):
    cena, (p1, p2, p3) = _ws(banco_real)
    chave = str(uuid.uuid4())

    with p1, p2, p3, patch("app.routers.chat.responde_triagem", _Helo()):
        with TestClient(app).websocket_connect(_url(cena.chamado.id, cena.tecnico)) as ws:
            ws.send_text(json.dumps({"content": _TEXTO, "client_message_id": chave}))
            _ate(ws, "ack")
            ws.send_text(json.dumps({"content": "outra coisa", "client_message_id": chave}))
            conflito = _ate(ws, "error")

    assert [q["type"] for q in conflito] == ["error"]
    assert conflito[0]["code"] == "client_message_id_conflict"
    assert conflito[0]["client_message_id"] == chave
    assert asyncio.run(cena.contagem())["mensagens"] == 1


@pytest.mark.parametrize("chave", ["nao-e-uuid", 123, ""])
def test_ws_chave_invalida_e_recusada_sem_gravar(banco_real, chave):
    cena, (p1, p2, p3) = _ws(banco_real)

    with p1, p2, p3:
        with TestClient(app).websocket_connect(_url(cena.chamado.id, cena.tecnico)) as ws:
            ws.send_text(json.dumps({"content": _TEXTO, "client_message_id": chave}))
            # A sonda logo atrás garante um erro na fila mesmo se a recusa não
            # vier: o teste falha em vez de ficar esperando para sempre.
            ws.send_text("sonda: isto não é json")
            recusa = _ate(ws, "error")

    assert [q["type"] for q in recusa] == ["error"]
    assert "client_message_id" in recusa[0]["detail"]
    assert asyncio.run(cena.contagem())["mensagens"] == 0


def test_ws_sem_chave_continua_como_sempre(banco_real):
    """Cliente antigo: recebe a mensagem pela sala, com a chave nula, e
    nenhuma confirmação a mais."""
    cena, (p1, p2, p3) = _ws(banco_real)

    with p1, p2, p3:
        with TestClient(app).websocket_connect(_url(cena.chamado.id, cena.tecnico)) as ws:
            ws.send_text(json.dumps({"content": _TEXTO}))
            chegou = _ate(ws, "message")
            depois = _nada_mais_chegou(ws)

    assert [q["type"] for q in chegou] == ["message"]
    assert chegou[0]["data"]["client_message_id"] is None
    assert [q["type"] for q in depois] == ["status_update"], "nenhuma confirmação a mais"


def test_rest_e_websocket_simultaneos_com_a_mesma_chave(banco_real):
    """O POST grava e é segurado antes de comitar; o mesmo envio chega pelo
    socket e para no índice. Solto o POST: ele cria (201) e transmite; o
    socket recebe a transmissão uma vez e, para o seu envio, só a
    confirmação de repetição — com o id que o POST gravou."""
    fabrica, _ = banco_real
    cena, (p1, p2, p3) = _ws(banco_real)
    chave = str(uuid.uuid4())
    original = rota_do_chat._notify_other_party
    entrou, porta = threading.Event(), threading.Event()
    primeira_vez = threading.Lock()

    async def _segura_so_o_primeiro(*a, **k):
        if primeira_vez.acquire(blocking=False):
            entrou.set()
            await asyncio.to_thread(porta.wait, 20)
        return await original(*a, **k)

    async def _db():
        async with fabrica() as s:
            yield s

    async def _cliente():
        return cena.cliente

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _cliente
    resposta: dict = {}
    try:
        with (
            p1,
            p2,
            p3,
            patch("app.routers.chat.responde_triagem", _Helo()),
            patch("app.routers.chat._notify_other_party", _segura_so_o_primeiro),
        ):
            tc = TestClient(app)
            with tc.websocket_connect(_url(cena.chamado.id, cena.cliente)) as ws:

                def _post_em_paralelo():
                    resposta["r"] = tc.post(
                        f"/api/v1/tickets/{cena.chamado.id}/messages",
                        json={"content": _TEXTO, "client_message_id": chave},
                    )

                fio = threading.Thread(target=_post_em_paralelo)
                fio.start()
                assert entrou.wait(20), "o POST não chegou a gravar"
                ws.send_text(json.dumps({"content": _TEXTO, "client_message_id": chave}))
                viu_espera = asyncio.run(_alguem_esperando_bloqueio(fabrica))
                porta.set()
                fio.join(30)
                quadros = _ate(ws, "ack")
                depois = _nada_mais_chegou(ws)
    finally:
        porta.set()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    r = resposta["r"]
    assert viu_espera, "o envio pelo socket não ficou preso no índice único"
    assert r.status_code == 201, r.text
    # O POST já tinha terminado (`join`) antes da leitura: tudo o que ele
    # transmitiu está na fila. A ordem entre a confirmação do socket e a
    # transmissão do POST é da corrida; a CONTAGEM não é.
    todos = quadros + depois
    assert sorted(q["type"] for q in todos) == ["ack", "message", "status_update"]
    mensagem = next(q for q in todos if q["type"] == "message")
    confirmacao = next(q for q in todos if q["type"] == "ack")
    assert mensagem["data"]["id"] == r.json()["id"]
    assert confirmacao["duplicate"] is True
    assert confirmacao["data"]["id"] == r.json()["id"]
    assert asyncio.run(cena.contagem()) == _UMA_VEZ
