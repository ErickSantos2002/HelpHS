"""
As agregações do dashboard, executadas contra PostgreSQL de verdade.

Por que este arquivo existe
---------------------------
O `dashboard.py` monta 26 construções que só o PostgreSQL entende —
`date_trunc`, `extract('isodow')`, `count(...).filter(...)` — e nenhuma delas
era executada contra banco nenhum: os nove testes do `test_dashboard.py` são
inteiramente mockados, e mock não valida SQL. Um erro de dialeto ali só
apareceria em produção, na tela do administrador.

O que se compra aqui é proteção contra regressão, não conserto de bug vivo: as
agregações estão no ar e funcionando. O caso mais arriscado é o
`_resumos_de_tecnicos`, reescrito na rodada do N+1 para agregar com `GROUP BY`
— SQL novo que nunca tinha tocado um Postgres.

Como o banco aparece
--------------------
`TEST_POSTGRES_URL` quando existe (é o que o CI passa, do serviço `postgres`),
senão um Postgres efêmero via `pgserver` (Rota B do desenvolvimento-local.md,
sem Docker). Sem nenhum dos dois, os testes são pulados em vez de falhar —
quem não tem Postgres à mão continua rodando a suíte inteira.

O schema sai do `create_all` dos próprios modelos, e no Postgres isso vale para
as 24 tabelas: o subconjunto que o `test_groups.py` precisou é limitação do
SQLite (coluna ARRAY em `kb_articles`), não daqui.

Cada teste roda numa transação revertida no fim — 2 ms, contra ~730 ms de um
TRUNCATE do subconjunto. Nenhum teste enxerga o dado do outro.
"""

import asyncio
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    SatisfactionSurvey,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.routers.dashboard import (
    _build_report,
    _resumos_de_tecnicos,
    _technician_summary,
    get_dashboard_stats,
)

_AGORA = datetime.now(UTC)


def _sobe_postgres() -> tuple[str, object] | tuple[None, None]:
    """Devolve (url, recurso_para_encerrar). Recurso é None quando veio do CI."""
    do_ambiente = os.environ.get("TEST_POSTGRES_URL")
    if do_ambiente:
        return do_ambiente.replace("postgresql://", "postgresql+asyncpg://"), None

    try:
        import pgserver
    except ImportError:
        return None, None

    pasta = tempfile.mkdtemp(prefix="helphs-testes-pg-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    servidor.psql("CREATE DATABASE dashboard_testes;")
    url = servidor.get_uri(database="dashboard_testes")
    return url.replace("postgresql://", "postgresql+asyncpg://"), (servidor, pasta)


@pytest.fixture(scope="module")
def url_do_banco():
    """
    SÍNCRONA de propósito. Subir o servidor e montar o schema não pode viver
    numa fixture async de escopo de módulo: o pytest-asyncio dá um laço de
    evento por teste, e a conexão criada no laço do módulo morre no primeiro
    uso ("transaction already deassociated from connection").

    Aqui o custo grande — servidor (~13 s) e create_all (~1 s) — acontece uma
    vez, num laço próprio, e cada teste abre a sua conexão no laço dele.
    """
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    asyncio.run(_monta())

    yield url

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def db(url_do_banco):
    """Sessão numa transação revertida no fim — isolamento por teste, ~2 ms."""
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        async with async_sessionmaker(bind=conn, expire_on_commit=False)() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


# ── Dados sintéticos ──────────────────────────────────────────


def _usuario(papel: UserRole, nome: str) -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        password="x",
        role=papel,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _chamado(
    criador: User,
    responsavel: User | None = None,
    status: TicketStatus = TicketStatus.open,
    dias_atras: int = 1,
    horas_ate_resolver: float | None = None,
) -> Ticket:
    aberto_em = _AGORA - timedelta(days=dias_atras)
    resolvido_em = (
        aberto_em + timedelta(hours=horas_ate_resolver) if horas_ate_resolver is not None else None
    )
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-TEST-{uuid.uuid4().hex[:10]}",
        title="Chamado sintético",
        description="corpo",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=status,
        creator_id=criador.id,
        assignee_id=responsavel.id if responsavel else None,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        auto_closed=False,
        reopen_count=0,
        created_at=aberto_em,
        updated_at=aberto_em,
        resolved_at=resolvido_em,
        closed_at=resolvido_em,
    )


# ── Testes ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resumo_de_tecnicos_em_lote_agrega_no_postgres(db):
    """
    O caso mais arriscado: SQL reescrito para agregar com `GROUP BY`, com
    `count(...).filter(...)` e `avg(extract('epoch', ...))`, que nunca tinha
    sido executado contra um Postgres.

    Inclui um técnico SEM chamado nenhum de propósito — ele não volta do
    `GROUP BY`, e é o caso que o código trata com `.get(id, 0)`.
    """
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario(UserRole.technician, "Ana")
    ocioso = _usuario(UserRole.technician, "Bruno")
    db.add_all([cliente, tecnico, ocioso])
    await db.flush()

    db.add_all(
        [
            _chamado(cliente, tecnico, TicketStatus.resolved, dias_atras=2, horas_ate_resolver=4),
            _chamado(cliente, tecnico, TicketStatus.open, dias_atras=1),
        ]
    )
    await db.flush()

    linhas = [
        type("L", (), {"id": tecnico.id, "name": tecnico.name})(),
        type("L", (), {"id": ocioso.id, "name": ocioso.name})(),
    ]
    resumos = await _resumos_de_tecnicos(db, linhas, _AGORA - timedelta(days=30))

    por_nome = {r.technician_name: r for r in resumos}
    assert por_nome["Ana"].total_assigned == 2
    assert por_nome["Ana"].resolved == 1
    assert por_nome["Ana"].open_count == 1
    assert por_nome["Ana"].avg_resolution_hours == pytest.approx(4.0, abs=0.2)

    # Técnico sem chamado precisa aparecer zerado, não sumir da lista
    assert por_nome["Bruno"].total_assigned == 0
    assert por_nome["Bruno"].avg_resolution_hours is None
    assert por_nome["Bruno"].sla_compliance_rate == 100.0


@pytest.mark.asyncio
async def test_resumo_em_lote_bate_com_o_individual(db):
    """
    O contrato do refatoramento do N+1: a versão em lote tem de produzir os
    mesmos números da individual, que continua servindo o relatório de UM
    técnico. Se as duas divergirem, uma das telas mente.
    """
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario(UserRole.technician, "Ana")
    db.add_all([cliente, tecnico])
    await db.flush()

    db.add_all(
        [
            _chamado(cliente, tecnico, TicketStatus.resolved, dias_atras=3, horas_ate_resolver=6),
            _chamado(cliente, tecnico, TicketStatus.closed, dias_atras=2, horas_ate_resolver=2),
            _chamado(cliente, tecnico, TicketStatus.in_progress, dias_atras=1),
        ]
    )
    await db.flush()

    desde = _AGORA - timedelta(days=30)
    linha = type("L", (), {"id": tecnico.id, "name": tecnico.name})()

    em_lote = (await _resumos_de_tecnicos(db, [linha], desde))[0]
    individual = await _technician_summary(db, tecnico.id, tecnico.name, desde)

    assert em_lote.total_assigned == individual.total_assigned
    assert em_lote.resolved == individual.resolved
    assert em_lote.open_count == individual.open_count
    assert em_lote.sla_breached == individual.sla_breached
    assert em_lote.sla_compliance_rate == individual.sla_compliance_rate
    assert em_lote.avg_resolution_hours == individual.avg_resolution_hours
    assert em_lote.csat_average == individual.csat_average
    assert em_lote.csat_count == individual.csat_count


@pytest.mark.asyncio
async def test_relatorio_completo_roda_com_date_trunc_e_isodow(db):
    """
    O `_build_report` concentra 6 `date_trunc` e 8 `extract` — inclusive
    `isodow`, que não existe fora do Postgres. É o que mais tem a perder num
    erro de dialeto.
    """
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario(UserRole.technician, "Ana")
    db.add_all([cliente, tecnico])
    await db.flush()

    db.add_all(
        [
            _chamado(cliente, tecnico, TicketStatus.resolved, dias_atras=d, horas_ate_resolver=3)
            for d in (1, 2, 3, 8, 9)
        ]
    )
    await db.flush()

    relatorio = await _build_report(db, period=30)

    assert relatorio.period_days == 30
    assert relatorio.total_tickets == 5

    # As séries por dia (date_trunc) e por dia da semana (isodow) são as que
    # dependem do dialeto: precisam vir preenchidas e somar o que existe.
    assert relatorio.tickets_by_day, "a série por dia veio vazia"
    assert sum(item.count for item in relatorio.tickets_by_day) == 5

    assert relatorio.tickets_by_weekday, "a série por dia da semana veio vazia"
    assert sum(item.count for item in relatorio.tickets_by_weekday) == 5

    # tickets_by_hour usa extract('hour'); a de produto, um LEFT JOIN agregado.
    assert sum(item.count for item in relatorio.tickets_by_hour) == 5


@pytest.mark.asyncio
async def test_estatisticas_do_painel_contam_com_filter(db):
    """As contagens do painel usam `count(...).filter(...)` por status."""
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario(UserRole.technician, "Ana")
    db.add_all([cliente, tecnico])
    await db.flush()

    db.add_all(
        [
            _chamado(cliente, tecnico, TicketStatus.open, dias_atras=1),
            _chamado(cliente, tecnico, TicketStatus.open, dias_atras=2),
            _chamado(cliente, tecnico, TicketStatus.resolved, dias_atras=3, horas_ate_resolver=1),
        ]
    )
    await db.flush()

    stats = await get_dashboard_stats(db, tecnico)

    assert stats.tickets.total == 3
    assert stats.tickets.open == 2
    assert stats.tickets.resolved == 1


@pytest.mark.asyncio
async def test_csat_medio_vem_do_join_com_a_pesquisa(db):
    """A média de CSAT junta pesquisa e chamado — outro caminho agregado."""
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario(UserRole.technician, "Ana")
    db.add_all([cliente, tecnico])
    await db.flush()

    chamados = [
        _chamado(cliente, tecnico, TicketStatus.closed, dias_atras=2, horas_ate_resolver=1),
        _chamado(cliente, tecnico, TicketStatus.closed, dias_atras=3, horas_ate_resolver=1),
    ]
    db.add_all(chamados)
    await db.flush()

    db.add_all(
        [
            SatisfactionSurvey(
                id=uuid.uuid4(),
                ticket_id=c.id,
                user_id=cliente.id,
                rating=nota,
                created_at=_AGORA - timedelta(days=1),
            )
            for c, nota in zip(chamados, (8, 10), strict=True)
        ]
    )
    await db.flush()

    resumo = await _technician_summary(db, tecnico.id, tecnico.name, _AGORA - timedelta(days=30))

    assert resumo.csat_count == 2
    assert resumo.csat_average == pytest.approx(9.0, abs=0.01)
