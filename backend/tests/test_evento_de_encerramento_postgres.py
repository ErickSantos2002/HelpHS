"""
A idempotência do evento de encerramento contra PostgreSQL real.

Por que este arquivo existe: a trava da primeira entrega não está na aplicação,
está na cláusula `AND hangup_event_received_at IS NULL` do `UPDATE`. Defesa de
banco só se prova contra um banco. A suíte mockada ao lado prova que o router
decide certo a partir de um `rowcount`; **só aqui** se prova que o `rowcount` vem
certo quando duas entregas disputam a mesma linha.

O que a suíte mockada não alcança e esta alcança:

* as quatro colunas existem depois da migration — e as proibidas não;
* a primeira entrega grava e a segunda **não sobrescreve** nenhum dos campos;
* duas entregas CONCORRENTES produzem uma única gravação efetiva;
* `upgrade → downgrade → upgrade` fecha o ciclo sem resíduo.

As fixtures são IMPORTADAS do `test_constraint_telefone_postgres.py`, mesmo
caminho do `test_ramal_api4com_postgres.py` — copiá-las criaria duas versões do
mesmo arranjo para divergirem depois. ⚠️ O `banco` nasce VAZIO: cada teste roda
o `upgrade` por conta, como os vizinhos fazem.
"""

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.test_constraint_telefone_postgres import (  # noqa: F401
    _alembic,
    _conecta,
    banco,
    servidor,
)

_ANTES = "c8b8d6994fae"
_DEPOIS = "k7f8g9h0i1j2"

_COLUNAS = (
    "duration_seconds",
    "hangup_cause",
    "recording_available",
    "hangup_event_received_at",
)


async def _semeia(url) -> uuid.UUID:
    """Um técnico, um chamado e uma tentativa `confirmed`, pelo ORM.

    Pelo ORM, e não por `INSERT` à mão, de propósito: os modelos já conhecem os
    defaults, e um `INSERT` textual quebraria em silêncio na próxima coluna
    obrigatória que alguém acrescentasse.
    """
    from app.models.models import Ticket, TicketCall, User, UserRole

    engine = await _conecta(url)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as sessao:
        # ⚠️ `technician`, e NÃO `client`. O default do modelo é `client`, e
        # `client + active` sem telefone bate na CheckConstraint da Fase 1C — foi
        # exatamente o que derrubou a primeira versão deste arquivo. O
        # `test_ramal_api4com_postgres.py` já avisava disso na docstring dele.
        ator = User(
            name="Tecnico",
            email=f"t{uuid.uuid4().hex[:8]}@exemplo.invalido",
            password="x",
            role=UserRole.technician,
        )
        sessao.add(ator)
        await sessao.flush()

        chamado = Ticket(
            protocol=f"P{uuid.uuid4().hex[:10]}",
            title="t",
            description="d",
            creator_id=ator.id,
        )
        sessao.add(chamado)
        await sessao.flush()

        tentativa = TicketCall(
            ticket_id=chamado.id,
            initiated_by_id=ator.id,
            provider_call_id=str(uuid.uuid4()),
            creation_status="confirmed",
            provider_http_status=200,
        )
        sessao.add(tentativa)
        await sessao.flush()
        tid = tentativa.id
        await sessao.commit()
    await engine.dispose()
    return tid


async def _le(url, tentativa: uuid.UUID) -> dict:
    from app.models.models import TicketCall

    engine = await _conecta(url)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as sessao:
        linha = await sessao.get(TicketCall, tentativa)
        valores = {c: getattr(linha, c) for c in _COLUNAS}
    await engine.dispose()
    return valores


async def _entrega(url, tentativa, *, duracao, causa, gravacao):
    """Uma entrega, em conexão PRÓPRIA — é isso que permite a disputa real."""
    from app.services import telefonia

    engine = await _conecta(url)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as sessao:
        r = await telefonia.registra_encerramento(
            sessao,
            ticket_call_id=tentativa,
            duration_seconds=duracao,
            hangup_cause=causa,
            recording_available=gravacao,
        )
        await sessao.commit()
    await engine.dispose()
    return r


@pytest.mark.asyncio
async def test_a_migration_cria_as_quatro_e_nenhuma_proibida(banco):  # noqa: F811
    from sqlalchemy import text

    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        presentes = {
            linha[0]
            for linha in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'ticket_calls'"
                    )
                )
            ).all()
        }
    await engine.dispose()

    for coluna in _COLUNAS:
        assert coluna in presentes, f"a migration não criou {coluna}"
    for proibida in ("record_url", "recording_url", "caller", "called", "metadata"):
        assert proibida not in presentes, f"{proibida} entrou no banco"


@pytest.mark.asyncio
async def test_a_primeira_entrega_vence_e_a_duplicada_nao_sobrescreve(banco):  # noqa: F811
    from app.services.telefonia import ResultadoDoEncerramento as R

    assert _alembic(banco, "upgrade", "head").returncode == 0
    tentativa = await _semeia(banco)

    primeiro = await _entrega(banco, tentativa, duracao=9, causa="NORMAL_CLEARING", gravacao=True)
    assert primeiro is R.registrado

    gravado = await _le(banco, tentativa)
    assert gravado["duration_seconds"] == 9
    assert gravado["hangup_cause"] == "NORMAL_CLEARING"
    assert gravado["recording_available"] is True
    assert gravado["hangup_event_received_at"] is not None

    # Segunda entrega com valores DIFERENTES: se algum aparecer no banco, a trava
    # não travou.
    segundo = await _entrega(
        banco, tentativa, duracao=999, causa="ORIGINATOR_CANCEL", gravacao=False
    )
    assert segundo is R.duplicado

    assert await _le(banco, tentativa) == gravado, "a duplicada sobrescreveu a primeira"


@pytest.mark.asyncio
async def test_duas_entregas_concorrentes_gravam_uma_vez_so(banco):  # noqa: F811
    """A corrida que um `SELECT` seguido de `if` reabriria.

    Duas conexões independentes, disparadas juntas. Com a condição dentro do
    `UPDATE`, o PostgreSQL serializa as escritas na mesma linha e exatamente uma
    encontra `hangup_event_received_at` nulo.
    """
    assert _alembic(banco, "upgrade", "head").returncode == 0
    tentativa = await _semeia(banco)

    resultados = await asyncio.gather(
        _entrega(banco, tentativa, duracao=9, causa="NORMAL_CLEARING", gravacao=True),
        _entrega(banco, tentativa, duracao=999, causa="ORIGINATOR_CANCEL", gravacao=False),
    )

    assert sorted(r.value for r in resultados) == [
        "duplicado",
        "registrado",
    ], f"as entregas não se excluíram: {[r.value for r in resultados]}"

    final = await _le(banco, tentativa)
    # Qual das duas venceu não importa; a coerência entre os campos importa:
    # nunca a duração de uma com a causa da outra.
    assert (final["duration_seconds"], final["hangup_cause"], final["recording_available"]) in {
        (9, "NORMAL_CLEARING", True),
        (999, "ORIGINATOR_CANCEL", False),
    }


@pytest.mark.asyncio
async def test_linha_inexistente_nao_e_confundida_com_duplicada(banco):  # noqa: F811
    from app.services.telefonia import ResultadoDoEncerramento as R

    assert _alembic(banco, "upgrade", "head").returncode == 0

    r = await _entrega(banco, uuid.uuid4(), duracao=9, causa="NORMAL_CLEARING", gravacao=True)
    assert r is R.inexistente


@pytest.mark.asyncio
async def test_o_ciclo_da_migration_fecha_sem_residuo(banco):  # noqa: F811
    """`upgrade → downgrade → upgrade`: o downgrade remove as quatro, e só elas."""
    from sqlalchemy import text

    assert _alembic(banco, "upgrade", _DEPOIS).returncode == 0
    assert _alembic(banco, "downgrade", _ANTES).returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        depois_do_downgrade = {
            linha[0]
            for linha in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'ticket_calls'"
                    )
                )
            ).all()
        }
    await engine.dispose()

    for coluna in _COLUNAS:
        assert coluna not in depois_do_downgrade, f"o downgrade deixou {coluna}"
    # E não levou nada que não era dele.
    for antiga in ("id", "ticket_id", "provider_call_id", "creation_status"):
        assert antiga in depois_do_downgrade, f"o downgrade removeu {antiga}"

    assert _alembic(banco, "upgrade", _DEPOIS).returncode == 0
