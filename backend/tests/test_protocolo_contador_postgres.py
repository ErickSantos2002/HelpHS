"""
Contador durável de protocolo contra PostgreSQL de verdade.

O que o SQLite de `test_protocol.py` não prova:

* **Concorrência.** A garantia de "dois criadores, dois números" vem do lock de
  linha que o `ON CONFLICT DO UPDATE` toma em `ticket_protocol_counters` e
  segura até o commit. SQLite serializa o banco inteiro; só o Postgres mostra a
  espera de verdade.
* **A migration.** Ela semeia o contador a partir dos protocolos já emitidos,
  e é ela que garante que produção (0001..0026) siga em 0027 mesmo depois de
  `tickets` ser zerada. Roda pelo `alembic` como subprocesso, igual ao
  `start.sh`, e sobe/desce/sobe.

Como o banco aparece: `TEST_POSTGRES_URL` (CI), senão `pgserver`. Sem nenhum,
pula — mesma regra dos outros `*_postgres.py`.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.models import Ticket, TicketCategory, TicketStatus
from app.utils.protocol import generate_protocol
from tests.test_constraint_telefone_postgres import _alembic, servidor  # noqa: F401

# O pai da migration do contador — o head de produção em 07/10/2026.
_ANTES = "k7f8g9h0i1j2"
_CONTADOR = "0a17fd87823c"

_ANO = datetime.now(UTC).year


async def _banco_novo(servidor_url: str, nome: str) -> str:  # noqa: F811
    admin = create_async_engine(servidor_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{nome}"'))
    await admin.dispose()

    url = servidor_url.rsplit("/", 1)[0] + f"/{nome}"
    novo = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with novo.connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await novo.dispose()
    return url


@pytest_asyncio.fixture
async def banco(servidor):  # noqa: F811
    """Banco vazio, sem migration nenhuma — os testes de migration partem dele."""
    return await _banco_novo(servidor, "protocolo_contador_migracao")


@pytest_asyncio.fixture
async def migrado(servidor):  # noqa: F811
    """Banco no head, com um criador para satisfazer `tickets.creator_id`."""
    url = await _banco_novo(servidor, "protocolo_contador_concorrencia")
    r = _alembic(url, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    motor = create_async_engine(url, poolclass=NullPool)
    async with motor.begin() as conn:
        criador = await _insere_criador(conn)
    await motor.dispose()
    return url, criador


async def _insere_criador(conn) -> uuid.UUID:
    criador = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO users (id, name, email, password, role, status, lgpd_consent,"
            " onboarding_completed, email_verified, mfa_enabled, ai_enabled,"
            " created_at, updated_at)"
            " VALUES (:id, 'Equipe', :email, 'hash', 'admin', 'active', true,"
            " true, true, false, true, now(), now())"
        ),
        {"id": criador, "email": f"{criador}@exemplo.invalid"},
    )
    return criador


async def _insere_chamado(conn, criador: uuid.UUID, protocolo: str) -> None:
    await conn.execute(
        text(
            "INSERT INTO tickets (id, protocol, title, description, status, category,"
            " creator_id, sla_response_breach, sla_resolve_breach, sla_total_paused_ms,"
            " auto_closed, reopen_count, ai_enabled, helo_saiu,"
            " sla_resolve_extension_total_min, created_at, updated_at)"
            " VALUES (gen_random_uuid(), :p, 'titulo', 'corpo', 'open', 'general', :c,"
            " false, false, 0, false, 0, true, false, 0, now(), now())"
        ),
        {"p": protocolo, "c": criador},
    )


def _chamado(criador: uuid.UUID, protocolo: str) -> Ticket:
    agora = datetime.now(UTC)
    return Ticket(
        id=uuid.uuid4(),
        protocol=protocolo,
        title="titulo",
        description="corpo",
        category=TicketCategory.general,
        status=TicketStatus.open,
        creator_id=criador,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        sla_resolve_extension_total_min=0,
        ai_enabled=True,
        auto_closed=False,
        reopen_count=0,
        created_at=agora,
        updated_at=agora,
    )


async def _contadores(conn) -> dict[int, int]:
    linhas = await conn.execute(text("SELECT year, last_number FROM ticket_protocol_counters"))
    return {ano: n for ano, n in linhas.all()}


async def _retrato_dos_chamados(conn) -> list[tuple]:
    return (
        await conn.execute(
            text("SELECT id, protocol, created_at, updated_at FROM tickets ORDER BY id")
        )
    ).all()


# ── Concorrência ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_criadores_simultaneos_recebem_numeros_distintos(migrado):
    """
    Dez aberturas ao mesmo tempo, cada uma na sua conexão e segurando a
    transação aberta entre gerar e commitar — a janela em que `max()+1` dava o
    mesmo número a todas.
    """
    url, criador = migrado
    motor = create_async_engine(url, pool_size=12)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)

    async def _abre() -> str:
        async with fabrica() as sessao:
            protocolo = await generate_protocol(sessao)
            await asyncio.sleep(0.05)
            sessao.add(_chamado(criador, protocolo))
            await sessao.commit()
            return protocolo

    try:
        emitidos = await asyncio.gather(*(_abre() for _ in range(10)))
    finally:
        await motor.dispose()

    assert sorted(emitidos) == [f"HS-{_ANO}-{n:04d}" for n in range(1, 11)]


@pytest.mark.asyncio
async def test_o_segundo_espera_o_primeiro_e_herda_o_numero_revertido(migrado):
    """
    A transação que alocou segura a linha do ano. Quem chega depois ESPERA; se a
    primeira reverte, o número volta e o segundo o recebe — sem buraco e sem
    duplicata, porque o primeiro chamado nunca existiu.
    """
    url, criador = migrado
    motor = create_async_engine(url, pool_size=4)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    try:
        async with fabrica() as primeiro, fabrica() as segundo:
            numero_do_primeiro = await generate_protocol(primeiro)

            tarefa = asyncio.create_task(generate_protocol(segundo))
            await asyncio.sleep(0.3)
            assert not tarefa.done(), "o segundo não esperou o lock do primeiro"

            await primeiro.rollback()
            numero_do_segundo = await asyncio.wait_for(tarefa, timeout=5)
            segundo.add(_chamado(criador, numero_do_segundo))
            await segundo.commit()

        assert numero_do_segundo == numero_do_primeiro

        async with motor.connect() as conn:
            protocolos = (await conn.execute(text("SELECT protocol FROM tickets"))).scalars().all()
        assert protocolos == [numero_do_segundo]
    finally:
        await motor.dispose()


@pytest.mark.asyncio
async def test_commit_do_primeiro_faz_o_segundo_avancar(migrado):
    url, criador = migrado
    motor = create_async_engine(url, pool_size=4)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    try:
        async with fabrica() as primeiro, fabrica() as segundo:
            p1 = await generate_protocol(primeiro)
            tarefa = asyncio.create_task(generate_protocol(segundo))
            await asyncio.sleep(0.3)
            assert not tarefa.done()

            primeiro.add(_chamado(criador, p1))
            await primeiro.commit()
            p2 = await asyncio.wait_for(tarefa, timeout=5)
            segundo.add(_chamado(criador, p2))
            await segundo.commit()

        assert (p1, p2) == (f"HS-{_ANO}-0001", f"HS-{_ANO}-0002")
    finally:
        await motor.dispose()


# ── Migration ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_migration_semeia_a_partir_do_maior_protocolo_emitido(banco):
    """
    O estado de produção: 2026 de 0001 a 0026 com um buraco (um chamado já foi
    apagado), mais um ano anterior. O contador nasce no MAIOR emitido de cada
    ano, e os chamados não mudam uma vírgula.
    """
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr[-2000:]

    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        criador = await _insere_criador(conn)
        for n in range(1, 27):
            if n != 13:
                await _insere_chamado(conn, criador, f"HS-2026-{n:04d}")
        await _insere_chamado(conn, criador, "HS-2025-0003")
        # Protocolo fora do formato, gravado à mão: a migration não pode morrer
        # num CAST por causa dele.
        await _insere_chamado(conn, criador, "HS-2026-MANUAL")
        antes = await _retrato_dos_chamados(conn)
    await motor.dispose()

    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        assert await _contadores(conn) == {2025: 3, 2026: 26}
        assert await _retrato_dos_chamados(conn) == antes
    await motor.dispose()


@pytest.mark.asyncio
async def test_depois_da_migration_zerar_os_chamados_segue_em_0027(banco):
    """O cenário inteiro do piloto, no schema construído pela migration."""
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr[-2000:]
    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        criador = await _insere_criador(conn)
        for n in range(1, 27):
            await _insere_chamado(conn, criador, f"HS-{_ANO}-{n:04d}")
    await motor.dispose()

    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    motor = create_async_engine(banco, poolclass=NullPool)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    try:
        async with fabrica() as sessao:
            await sessao.execute(text("DELETE FROM tickets"))
            await sessao.commit()

            p = await generate_protocol(sessao)
            sessao.add(_chamado(criador, p))
            await sessao.commit()
            assert p == f"HS-{_ANO}-0027"

            await sessao.execute(text("DELETE FROM tickets"))
            await sessao.commit()
            assert await generate_protocol(sessao) == f"HS-{_ANO}-0028"
    finally:
        await motor.dispose()


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade(banco):
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr[-2000:]
    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        criador = await _insere_criador(conn)
        for n in (1, 2, 7):
            await _insere_chamado(conn, criador, f"HS-2026-{n:04d}")
        antes = await _retrato_dos_chamados(conn)
    await motor.dispose()

    for alvo, comando in (("head", "upgrade"), (_ANTES, "downgrade"), ("head", "upgrade")):
        r = _alembic(banco, comando, alvo)
        assert r.returncode == 0, f"{comando} {alvo}: {r.stderr[-2000:]}"

        motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        async with motor.connect() as conn:
            existe = (
                await conn.execute(text("SELECT to_regclass('public.ticket_protocol_counters')"))
            ).scalar_one()
            if comando == "downgrade":
                assert existe is None
            else:
                assert existe == "ticket_protocol_counters"
                assert await _contadores(conn) == {2026: 7}
            assert await _retrato_dos_chamados(conn) == antes
        await motor.dispose()


@pytest.mark.asyncio
async def test_migration_em_banco_sem_chamados_cria_tabela_vazia(banco):
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]
    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        assert await _contadores(conn) == {}
    await motor.dispose()


@pytest.mark.asyncio
async def test_contador_recusa_numero_negativo(banco):
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]
    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        with pytest.raises(Exception, match="ck_ticket_protocol_counters"):
            await conn.execute(
                text("INSERT INTO ticket_protocol_counters (year, last_number) VALUES (2026, -1)")
            )
    await motor.dispose()
