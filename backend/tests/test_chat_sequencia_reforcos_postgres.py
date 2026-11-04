"""
Reforços da numeração do chat (F1-B-04c), contra PostgreSQL:

- a Helô DE VERDADE (`responde_triagem` inteira, com o cliente do modelo
  atrasado), e não uma fala de mentira: o chamado fica livre enquanto o
  modelo pensa, inclusive no caminho da escalada, que altera o chamado;
- o script de recuperação concorrendo com envios no mesmo chamado;
- a ordem dos bloqueios entre chamados numa mesma transação;
- a guarda que avisa de mensagem indo para o commit sem número.

O servidor e as fixtures são os do `test_chat_historico_postgres.py`.
"""

import asyncio
import threading
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import event, select, text, update

from app.models.models import ChatMessage, Ticket
from app.services import helo
from app.services.chat_sequencia import numera_mensagens_do_chat
from scripts.numera_mensagens_sem_seq import numera
from tests import test_chat_historico_postgres as _base
from tests import test_chat_idempotencia_postgres as _idem
from tests.test_chat_historico_postgres import _grava, _mensagem
from tests.test_chat_sequencia_postgres import (
    _chamado_livre,
    _contador,
    _HeloQueFala,
    _linhas,
    _numera_gravando,
    _poe_o_marco,
)

url_do_banco = _base.url_do_banco
banco_real = _base.banco_real

_Cena = _idem._Cena
_rest = _idem._rest
_post = _idem._post
_rodar = _idem._rodar
_alguem_esperando_bloqueio = _idem._alguem_esperando_bloqueio


# ── A Helô de verdade, com o modelo atrasado ──────────────────


class _ModeloLento:
    """O cliente do modelo de linguagem (`responde_como_helo`), segurado na
    porta. Tudo antes e depois dele é a Helô real."""

    def __init__(self, resposta: str):
        self.entrou = threading.Event()
        self.porta = threading.Event()
        self.resposta = resposta

    async def __call__(self, sistema, contexto):
        self.entrou.set()
        await asyncio.to_thread(self.porta.wait, 30)
        return self.resposta


async def _chamado_para_a_helo(cena: _Cena) -> None:
    """Sem responsável (com responsável ela se cala), IA ligada nos dois
    níveis, e a saudação dela já feita — a mensagem número 1."""
    async with cena.fabrica() as s:
        await s.execute(
            update(Ticket)
            .where(Ticket.id == cena.chamado.id)
            .values(assignee_id=None, ai_enabled=True, helo_saiu=False)
        )
        await s.execute(
            text("UPDATE users SET ai_enabled = true WHERE id = :u"), {"u": cena.cliente.id}
        )
        await s.commit()
    await _numera_gravando(
        cena,
        ChatMessage(
            id=uuid.uuid4(),
            ticket_id=cena.chamado.id,
            sender_id=None,
            content="Oi! Sou a Helô.",
            is_system=False,
            is_ai=True,
            created_at=datetime.now(UTC) - timedelta(minutes=1),
        ),
    )


@pytest.mark.parametrize(
    "resposta",
    ['{"resposta": "Tente religar o equipamento.", "escalar": false}', ""],
    ids=["responde", "escala_porque_o_modelo_ficou_mudo"],
)
def test_helo_real_com_modelo_lento_nao_trava_o_chamado(banco_real, resposta):
    modelo = _ModeloLento(resposta)

    async def _cena(cena: _Cena):
        await _chamado_para_a_helo(cena)
        with (
            _rest(cena),
            patch("app.routers.chat.responde_triagem", helo.responde_triagem),
            patch.object(
                helo, "get_settings", lambda: MagicMock(helo_enabled=True, helo_modo="completa")
            ),
            patch.object(helo, "embute_um", AsyncMock(return_value=None)),
            patch.object(helo, "responde_como_helo", modelo),
        ):
            do_cliente = asyncio.ensure_future(
                _post(cena.chamado.id, "cliente", "não liga", chave=uuid.uuid4())
            )
            assert await asyncio.to_thread(modelo.entrou.wait, 15), "o modelo não foi chamado"
            livre = await _chamado_livre(cena)
            do_tecnico = await asyncio.wait_for(
                _post(cena.chamado.id, "tecnico", "estou vendo", chave=uuid.uuid4()), 10
            )
            modelo.porta.set()
            do_cliente = await asyncio.wait_for(do_cliente, 20)
        async with cena.fabrica() as s:
            saiu = (
                await s.execute(select(Ticket.helo_saiu).where(Ticket.id == cena.chamado.id))
            ).scalar_one()
        return livre, do_tecnico, do_cliente, saiu, await _linhas(cena), await _contador(cena)

    livre, do_tecnico, do_cliente, saiu, linhas, contador = _rodar(banco_real, _cena)

    assert livre, "a linha do chamado ficou travada enquanto o modelo pensava"
    assert do_tecnico.status_code == 201, do_tecnico.text
    assert do_tecnico.json()["seq"] == 2
    assert do_cliente.status_code == 201, do_cliente.text
    assert do_cliente.json()["seq"] == 3
    seqs = [s for _, s, _ in linhas]
    assert seqs == [1, 2, 3, 4] and contador == 4
    assert linhas[3][0] != "não liga", "a fala dela vem logo depois da do cliente"
    assert saiu is (resposta == ""), "na escalada ela sai — e altera o chamado DEPOIS do modelo"


# ── O script de recuperação e os envios ───────────────────────


def test_script_espera_o_envio_que_segura_o_chamado_e_numera_depois(banco_real, url_do_banco):
    fabrica, criados = banco_real

    async def _cena(cena: _Cena):
        await _poe_o_marco(fabrica, datetime.now(UTC) - timedelta(minutes=1))
        await _grava(
            fabrica,
            criados,
            *(
                _mensagem(cena.chamado, cena.tecnico, datetime.now(UTC), texto=f"antiga {i}")
                for i in range(2)
            ),
        )
        envio = fabrica()
        try:
            envio.add(_mensagem(cena.chamado, cena.cliente, datetime.now(UTC), texto="envio"))
            await numera_mensagens_do_chat(envio)  # trava o chamado, ainda sem commit
            script = asyncio.ensure_future(numera(url_do_banco))
            esperou = await _alguem_esperando_bloqueio(fabrica)
            await envio.commit()
        finally:
            await envio.close()
        numeradas = await asyncio.wait_for(script, 20)
        await _poe_o_marco(fabrica)
        return esperou, numeradas, await _linhas(cena), await _contador(cena)

    esperou, numeradas, linhas, contador = _rodar(banco_real, _cena)

    assert esperou, "o script deveria esperar o envio que segura o chamado"
    assert sum(numeradas.values()) == 2
    por_conteudo = {c: s for c, s, _ in linhas}
    assert por_conteudo["envio"] == 1
    assert sorted(por_conteudo[f"antiga {i}"] for i in range(2)) == [2, 3]
    assert contador == 3


def test_script_e_envios_ao_mesmo_tempo_nao_repetem_nem_pulam_numero(banco_real, url_do_banco):
    fabrica, criados = banco_real

    async def _cena(cena: _Cena):
        await _poe_o_marco(fabrica, datetime.now(UTC) - timedelta(minutes=1))
        await _grava(
            fabrica,
            criados,
            *(
                _mensagem(cena.chamado, cena.tecnico, datetime.now(UTC), texto=f"antiga {i}")
                for i in range(5)
            ),
        )
        with _rest(cena):
            resultados = await asyncio.gather(
                numera(url_do_banco),
                *(_post(cena.chamado.id, "tecnico", f"nova {i}") for i in range(10)),
            )
        await _poe_o_marco(fabrica)
        return resultados, await _linhas(cena), await _contador(cena)

    resultados, linhas, contador = _rodar(banco_real, _cena)

    numeradas, *respostas = resultados
    assert all(r.status_code == 201 for r in respostas), [r.text for r in respostas]
    assert sum(numeradas.values()) == 5
    assert sorted(s for _, s, _ in linhas) == list(range(1, 16))
    assert contador == 15


# ── A ordem entre chamados ────────────────────────────────────


def test_varios_chamados_na_mesma_transacao_travam_em_ordem_de_id(banco_real):
    """Hoje nenhuma transação grava em mais de um chamado; a regra existe para
    a primeira que vier. As mensagens entram na ordem INVERSA à do id, e os
    UPDATE do contador saem na ordem do id — é o `sorted` que evita duas
    transações dessas travarem os mesmos chamados em ordens opostas."""

    async def _cena(cena: _Cena):
        chamados = sorted(
            [cena.chamado, cena.outro_chamado, cena.do_intruso], key=lambda c: c.id, reverse=True
        )
        travados: list[uuid.UUID] = []

        def _anota(conn, cursor, comando, parametros, contexto, varios):
            if comando.startswith("UPDATE tickets SET chat_seq"):
                travados.extend(p for p in parametros if isinstance(p, uuid.UUID))

        async with cena.fabrica() as s:
            motor = s.bind.sync_engine
            event.listen(motor, "before_cursor_execute", _anota)
            try:
                for c in chamados:
                    s.add(_mensagem(c, cena.tecnico, datetime.now(UTC)))
                await numera_mensagens_do_chat(s)
                await s.commit()
            finally:
                event.remove(motor, "before_cursor_execute", _anota)
        return [c.id for c in chamados], travados

    inseridos, travados = _rodar(banco_real, _cena)

    assert inseridos != sorted(inseridos), "o cenário precisa da inserção fora de ordem"
    assert travados == sorted(inseridos)


# ── A guarda do commit ────────────────────────────────────────


def test_guarda_avisa_da_mensagem_montada_depois_da_numeracao(banco_real):
    async def _cena(cena: _Cena):
        antes = _mensagem(cena.chamado, cena.tecnico, datetime.now(UTC), texto="numerada")
        depois = _mensagem(cena.chamado, cena.tecnico, datetime.now(UTC), texto="esquecida")
        with patch("app.services.chat_sequencia.logger") as registro:
            async with cena.fabrica() as s:
                s.add(antes)
                await numera_mensagens_do_chat(s)
                s.add(depois)  # o defeito: depois da numeração, antes do commit
                await s.commit()
        return antes.id, depois.id, registro.error.call_args_list, await _linhas(cena)

    antes_id, depois_id, chamadas, linhas = _rodar(banco_real, _cena)

    assert len(chamadas) == 1
    texto = " ".join(str(a) for a in chamadas[0].args)
    assert str(depois_id) in texto and str(antes_id) not in texto
    # Só avisa: não barra o commit e não numera.
    assert {c: s for c, s, _ in linhas} == {"numerada": 1, "esquecida": None}


def test_guarda_fica_quieta_nos_escritores_de_verdade(banco_real):
    """O envio do cliente com a fala da Helô, o reenvio que para no índice
    único (SAVEPOINT desfeito) e o envio do técnico: nenhum aviso. O
    `before_commit` do SAVEPOINT de `_grava_uma_vez` — onde a mensagem ainda
    não foi numerada — não pode contar."""
    chave = uuid.uuid4()

    async def _cena(cena: _Cena):
        with (
            patch("app.services.chat_sequencia.logger") as registro,
            _rest(cena),
            patch("app.routers.chat.responde_triagem", _HeloQueFala()),
        ):
            respostas = [
                await _post(cena.chamado.id, "cliente", chave=chave),
                await _post(cena.chamado.id, "cliente", chave=chave),
                await _post(cena.chamado.id, "tecnico"),
            ]
        return respostas, registro.error.call_args_list

    respostas, avisos = _rodar(banco_real, _cena)

    assert [r.status_code for r in respostas] == [201, 200, 201]
    assert avisos == []
