"""
Os períodos dos relatórios contra PostgreSQL de verdade (F1-B-03a).

O que só o banco prova: o agrupamento por dia, dia da semana e hora em
`America/Recife` (`timezone()` + `date_trunc`/`extract`), as bordas
`[início, fim)` comparadas com `timestamptz`, e a linha `NULL` do
`GROUP BY priority` na comparação — que derrubava o relatório com 500.

As chamadas HTTP passam pela sessão do teste, então os endpoints enxergam os
dados do teste e a transação continua sendo revertida no fim.
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import (
    SatisfactionSurvey,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.routers.dashboard import _build_report, _resumos_de_tecnicos, _technician_summary
from app.utils.periodo_relatorio import dia_local, meia_noite_local, resolve_janela
from tests import test_dashboard_postgres as _base
from tests.test_dashboard_postgres import _usuario

# O mesmo Postgres descartável e a mesma transação revertida por teste.
url_do_banco = _base.url_do_banco
db = _base.db

# 29/10/2026, 12:00 em Recife.
AGORA = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
HOJE = date(2026, 10, 29)
ONTEM = date(2026, 10, 28)


def _janela(inicio: date, fim: date):
    return resolve_janela(30, inicio, fim, agora=AGORA)


def _chamado_em(
    criador: User,
    quando: datetime,
    responsavel: User | None = None,
    prioridade: TicketPriority | None = TicketPriority.medium,
    status: TicketStatus = TicketStatus.open,
    resolvido_em: datetime | None = None,
    primeira_resposta: datetime | None = None,
    justificativa: str | None = None,
) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-PER-{uuid.uuid4().hex[:10]}",
        title="Chamado do período",
        description="corpo",
        priority=prioridade,
        category=TicketCategory.hardware,
        status=status,
        creator_id=criador.id,
        assignee_id=responsavel.id if responsavel else None,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        sla_first_response=primeira_resposta,
        sla_breach_justification=justificativa,
        auto_closed=False,
        reopen_count=0,
        created_at=quando,
        updated_at=quando,
        resolved_at=resolvido_em,
        closed_at=resolvido_em,
    )


async def _pessoas(db):
    cliente = _usuario(UserRole.client, "Cliente")
    tecnico = _usuario(UserRole.technician, "Ana")
    db.add_all([cliente, tecnico])
    await db.flush()
    return cliente, tecnico


# ── Hoje, Ontem, 7 dias, mês passado ──────────────────────────


@pytest.mark.asyncio
async def test_hoje_e_ontem_se_separam_na_meia_noite_de_recife(db):
    cliente, tecnico = await _pessoas(db)
    meia_noite = meia_noite_local(HOJE)  # 29/10 03:00Z
    db.add_all(
        [
            _chamado_em(cliente, meia_noite, tecnico),  # 00:00 de hoje: é de hoje
            _chamado_em(cliente, meia_noite - timedelta(microseconds=1), tecnico),  # ontem
            _chamado_em(cliente, meia_noite - timedelta(hours=1), tecnico),  # ontem, 23:00
        ]
    )
    await db.flush()

    hoje = await _build_report(db, janela=_janela(HOJE, HOJE))
    ontem = await _build_report(db, janela=_janela(ONTEM, ONTEM))

    assert hoje.total_tickets == 1
    assert ontem.total_tickets == 2
    assert [d.date for d in hoje.tickets_by_day] == ["2026-10-29"]
    assert [d.date for d in ontem.tickets_by_day] == ["2026-10-28"]
    assert ontem.tickets_by_day[0].count == 2
    # A comparação de "Hoje" é o dia de ontem inteiro.
    assert hoje.comparison is not None
    assert hoje.comparison.total_tickets == 2


@pytest.mark.asyncio
async def test_ultimos_7_dias_tem_sete_barras_e_comecam_na_meia_noite_local(db):
    cliente, tecnico = await _pessoas(db)
    primeiro = HOJE - timedelta(days=6)
    db.add_all(
        [
            _chamado_em(cliente, meia_noite_local(primeiro), tecnico),
            _chamado_em(cliente, meia_noite_local(primeiro) - timedelta(seconds=1), tecnico),
            _chamado_em(cliente, AGORA - timedelta(hours=1), tecnico),
        ]
    )
    await db.flush()

    r = await _build_report(db, janela=_janela(primeiro, HOJE))

    assert r.period_days == 7
    assert r.total_tickets == 2
    assert len(r.tickets_by_day) == 7
    assert r.tickets_by_day[0].date == "2026-10-23"
    assert r.tickets_by_day[-1].date == "2026-10-29"
    assert sum(d.count for d in r.tickets_by_day) == r.total_tickets
    assert r.comparison is not None
    assert r.comparison.total_tickets == 1


@pytest.mark.asyncio
async def test_mes_passado_compara_com_o_mes_civil_anterior(db):
    """31/08 às 22:00 em Recife é 01/09 01:00Z: pertence a AGOSTO."""
    cliente, tecnico = await _pessoas(db)
    db.add_all(
        [
            _chamado_em(cliente, datetime(2026, 9, 1, 1, 0, tzinfo=UTC), tecnico),  # 31/08
            _chamado_em(cliente, datetime(2026, 8, 1, 3, 0, tzinfo=UTC), tecnico),  # 01/08
            _chamado_em(cliente, datetime(2026, 9, 15, 12, 0, tzinfo=UTC), tecnico),
            _chamado_em(cliente, datetime(2026, 10, 1, 2, 59, tzinfo=UTC), tecnico),  # 30/09
        ]
    )
    await db.flush()

    r = await _build_report(db, janela=_janela(date(2026, 9, 1), date(2026, 9, 30)))

    assert r.total_tickets == 2
    assert len(r.tickets_by_day) == 30
    assert r.start_date == date(2026, 9, 1)
    assert r.end_date == date(2026, 9, 30)
    assert r.comparison is not None
    assert r.comparison.start_date == date(2026, 8, 1)
    assert r.comparison.end_date == date(2026, 8, 31)
    assert r.comparison.total_tickets == 2


@pytest.mark.asyncio
async def test_virada_de_ano_a_noite_de_31_de_dezembro_fica_em_dezembro(db):
    cliente, tecnico = await _pessoas(db)
    # 01/01/2026 02:00Z = 31/12/2025 23:00 em Recife.
    db.add(_chamado_em(cliente, datetime(2026, 1, 1, 2, 0, tzinfo=UTC), tecnico))
    await db.flush()

    dezembro = await _build_report(db, janela=_janela(date(2025, 12, 1), date(2025, 12, 31)))
    janeiro = await _build_report(db, janela=_janela(date(2026, 1, 1), date(2026, 1, 31)))

    assert dezembro.total_tickets == 1
    assert dezembro.tickets_by_day[-1].date == "2025-12-31"
    assert dezembro.tickets_by_day[-1].count == 1
    assert janeiro.total_tickets == 0
    assert janeiro.comparison is not None
    assert janeiro.comparison.total_tickets == 1


# ── Bordas e agrupamento em Recife ────────────────────────────


@pytest.mark.asyncio
async def test_inicio_incluido_e_fim_excluido(db):
    """O antigo 23:59:59 perdia o último segundo do dia."""
    cliente, tecnico = await _pessoas(db)
    inicio, fim = date(2026, 10, 1), date(2026, 10, 15)
    proxima_meia_noite = meia_noite_local(fim + timedelta(days=1))
    db.add_all(
        [
            _chamado_em(cliente, meia_noite_local(inicio), tecnico),
            _chamado_em(cliente, proxima_meia_noite - timedelta(microseconds=1), tecnico),
            _chamado_em(cliente, proxima_meia_noite, tecnico),
        ]
    )
    await db.flush()

    r = await _build_report(db, janela=_janela(inicio, fim))

    assert r.total_tickets == 2
    assert len(r.tickets_by_day) == 15, "uma barra por dia escolhido, sem a barra extra"
    assert r.tickets_by_day[-1].date == "2026-10-15"
    assert r.tickets_by_day[-1].count == 1


@pytest.mark.asyncio
async def test_dia_hora_e_dia_da_semana_saem_no_fuso_de_recife(db):
    cliente, tecnico = await _pessoas(db)
    # 15/10/2026 02:30Z = quarta 14/10, 23:30 em Recife.
    db.add(_chamado_em(cliente, datetime(2026, 10, 15, 2, 30, tzinfo=UTC), tecnico))
    await db.flush()

    r = await _build_report(db, janela=_janela(date(2026, 10, 14), date(2026, 10, 15)))

    por_dia = {d.date: d.count for d in r.tickets_by_day}
    assert por_dia == {"2026-10-14": 1, "2026-10-15": 0}
    por_hora = {h.hour: h.count for h in r.tickets_by_hour}
    assert por_hora[23] == 1 and por_hora[2] == 0
    por_semana = {w.weekday: w.count for w in r.tickets_by_weekday}
    assert por_semana[3] == 1  # ISO: 3 = quarta


@pytest.mark.asyncio
async def test_csat_por_dia_tambem_no_fuso_de_recife(db):
    cliente, tecnico = await _pessoas(db)
    chamado = _chamado_em(cliente, datetime(2026, 10, 10, 12, tzinfo=UTC), tecnico)
    db.add(chamado)
    await db.flush()
    db.add(
        SatisfactionSurvey(
            id=uuid.uuid4(),
            ticket_id=chamado.id,
            user_id=cliente.id,
            rating=9,
            created_at=datetime(2026, 10, 15, 2, 30, tzinfo=UTC),  # 14/10 em Recife
        )
    )
    await db.flush()

    r = await _build_report(db, janela=_janela(date(2026, 10, 14), date(2026, 10, 15)))

    por_dia = {d.date: d for d in r.csat_by_day}
    assert len(r.csat_by_day) == 2
    assert por_dia["2026-10-14"].count == 1
    assert por_dia["2026-10-14"].avg_rating == pytest.approx(9.0)
    assert por_dia["2026-10-15"].avg_rating is None


@pytest.mark.asyncio
async def test_justificativas_respeitam_o_fim_do_periodo(db):
    cliente, tecnico = await _pessoas(db)
    dentro = datetime(2026, 10, 5, 15, tzinfo=UTC)
    depois = datetime(2026, 10, 20, 15, tzinfo=UTC)
    db.add_all(
        [
            _chamado_em(
                cliente,
                dentro - timedelta(days=1),
                tecnico,
                status=TicketStatus.resolved,
                resolvido_em=dentro,
                justificativa="dentro",
            ),
            _chamado_em(
                cliente,
                depois - timedelta(days=1),
                tecnico,
                status=TicketStatus.resolved,
                resolvido_em=depois,
                justificativa="depois",
            ),
        ]
    )
    await db.flush()

    r = await _build_report(db, janela=_janela(date(2026, 10, 1), date(2026, 10, 10)))

    assert [j.justification for j in r.sla_justifications] == ["dentro"]


# ── Vazio, prioridade nula, médias ────────────────────────────


@pytest.mark.asyncio
async def test_periodo_vazio_responde_sem_erro_e_sem_dado_inventado(db):
    r = await _build_report(db, janela=_janela(date(2026, 10, 1), date(2026, 10, 3)))

    assert r.total_tickets == 0
    assert len(r.tickets_by_day) == 3
    assert all(d.count == 0 for d in r.tickets_by_day)
    assert all(s.total == 0 for s in r.sla_compliance)
    assert all(a.avg_hours is None for a in r.avg_resolution_by_priority)
    assert r.csat_average is None


@pytest.mark.asyncio
async def test_prioridade_nula_no_periodo_anterior_nao_derruba_o_relatorio(db):
    """Regressão do 500: a comparação não tinha a guarda do período atual."""
    cliente, tecnico = await _pessoas(db)
    db.add_all(
        [
            _chamado_em(cliente, meia_noite_local(ONTEM) + timedelta(hours=10), prioridade=None),
            _chamado_em(
                cliente,
                meia_noite_local(ONTEM) + timedelta(hours=11),
                tecnico,
                prioridade=TicketPriority.high,
            ),
        ]
    )
    await db.flush()

    r = await _build_report(db, janela=_janela(HOJE, HOJE))

    assert r.comparison is not None
    assert r.comparison.total_tickets == 2
    por_nivel = {s.priority: s for s in r.comparison.sla_compliance}
    assert set(por_nivel) == {"critical", "high", "medium", "low"}
    assert sum(s.total for s in r.comparison.sla_compliance) == 1


@pytest.mark.asyncio
async def test_media_zero_e_zero_e_nao_ausencia_de_dado(db):
    """Resolvido no mesmo instante em que foi aberto: média 0,0 horas."""
    cliente, tecnico = await _pessoas(db)
    quando = datetime(2026, 10, 10, 12, tzinfo=UTC)
    db.add(
        _chamado_em(
            cliente,
            quando,
            tecnico,
            prioridade=TicketPriority.low,
            status=TicketStatus.resolved,
            resolvido_em=quando,
            primeira_resposta=quando,
        )
    )
    await db.flush()
    janela = _janela(date(2026, 10, 10), date(2026, 10, 10))

    r = await _build_report(db, janela=janela)
    resolucao = {a.priority: a.avg_hours for a in r.avg_resolution_by_priority}
    resposta = {a.priority: a.avg_hours for a in r.avg_first_response_by_priority}
    assert resolucao["low"] == 0.0
    assert resposta["low"] == 0.0
    assert resolucao["high"] is None

    individual = await _technician_summary(db, tecnico.id, tecnico.name, janela.inicio, janela.fim)
    linha = type("L", (), {"id": tecnico.id, "name": tecnico.name})()
    em_lote = (await _resumos_de_tecnicos(db, [linha], janela.inicio, janela.fim))[0]
    assert individual.avg_resolution_hours == 0.0
    assert em_lote.avg_resolution_hours == 0.0


@pytest.mark.asyncio
async def test_resumo_de_tecnicos_respeita_o_fim_do_periodo(db):
    cliente, tecnico = await _pessoas(db)
    db.add_all(
        [
            _chamado_em(cliente, datetime(2026, 10, 5, 12, tzinfo=UTC), tecnico),
            _chamado_em(cliente, datetime(2026, 10, 20, 12, tzinfo=UTC), tecnico),
        ]
    )
    await db.flush()
    janela = _janela(date(2026, 10, 1), date(2026, 10, 10))
    linha = type("L", (), {"id": tecnico.id, "name": tecnico.name})()

    em_lote = (await _resumos_de_tecnicos(db, [linha], janela.inicio, janela.fim))[0]
    individual = await _technician_summary(db, tecnico.id, tecnico.name, janela.inicio, janela.fim)

    assert em_lote.total_assigned == individual.total_assigned == 1


# ── `period` legado ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_period_legado_continua_contando_de_agora_para_tras(db):
    cliente, tecnico = await _pessoas(db)
    agora = datetime.now(UTC)
    db.add_all(
        [
            _chamado_em(cliente, agora - timedelta(days=6, hours=23), tecnico),
            _chamado_em(cliente, agora - timedelta(days=7, hours=1), tecnico),
        ]
    )
    await db.flush()

    r = await _build_report(db, period=7)

    assert r.period_days == 7
    assert r.total_tickets == 1
    assert r.end_date == dia_local(datetime.now(UTC))
    assert r.start_date == dia_local(datetime.now(UTC) - timedelta(days=7))
    assert sum(d.count for d in r.tickets_by_day) == 1


# ── HTTP: contrato, permissões, consistência ──────────────────


def _cliente_http(db, ator: User):
    from app.core.database import get_db
    from app.core.security import get_current_user

    async def _db():
        yield db

    async def _ator():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _ator
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


_RELATORIOS = [
    "/api/v1/dashboard/reports",
    "/api/v1/dashboard/reports/technicians",
    "/api/v1/dashboard/reports/export/csv",
    "/api/v1/dashboard/reports/export/pdf",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("periodo", [1, 2])
async def test_endpoints_de_tecnico_aceitam_hoje_e_ontem(db, periodo):
    """Regressão do 422: `period` 1 e 2 são o que a tela no ar manda."""
    admin = _usuario(UserRole.admin, "Admin")
    _, tecnico = await _pessoas(db)
    db.add(admin)
    await db.flush()

    async with _cliente_http(db, admin) as c:
        lista = await c.get("/api/v1/dashboard/reports/technicians", params={"period": periodo})
        detalhe = await c.get(
            "/api/v1/dashboard/reports/technician",
            params={"period": periodo, "technician_id": str(tecnico.id)},
        )

    assert lista.status_code == 200, lista.text
    assert lista.json()["period_days"] == periodo
    assert detalhe.status_code == 200, detalhe.text
    assert detalhe.json()["period_days"] == periodo


@pytest.mark.asyncio
async def test_endpoints_de_tecnico_aceitam_datas(db):
    admin = _usuario(UserRole.admin, "Admin")
    cliente, tecnico = await _pessoas(db)
    db.add(admin)
    db.add_all(
        [
            _chamado_em(cliente, datetime(2026, 10, 5, 12, tzinfo=UTC), tecnico),
            _chamado_em(cliente, datetime(2026, 10, 20, 12, tzinfo=UTC), tecnico),
        ]
    )
    await db.flush()
    datas = {"start_date": "2026-10-01", "end_date": "2026-10-10"}

    async with _cliente_http(db, admin) as c:
        lista = await c.get("/api/v1/dashboard/reports/technicians", params=datas)
        detalhe = await c.get(
            "/api/v1/dashboard/reports/technician",
            params={**datas, "technician_id": str(tecnico.id)},
        )

    assert lista.status_code == 200, lista.text
    ana = next(t for t in lista.json()["technicians"] if t["technician_id"] == str(tecnico.id))
    assert ana["total_assigned"] == 1
    corpo = detalhe.json()
    assert corpo["total_assigned"] == 1
    assert corpo["period_days"] == 10
    assert corpo["start_date"] == "2026-10-01"
    assert corpo["end_date"] == "2026-10-10"
    assert corpo["timezone"] == "America/Recife"
    assert len(corpo["tickets_by_day"]) == 10
    assert sum(d["count"] for d in corpo["tickets_by_day"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params, trecho",
    [
        ({"start_date": "2026-10-01"}, "data inicial e a data final"),
        ({"end_date": "2026-10-01"}, "data inicial e a data final"),
        ({"start_date": "2026-10-10", "end_date": "2026-10-01"}, "posterior"),
        ({"start_date": "2025-01-01", "end_date": "2026-01-02"}, "366"),
        ({"start_date": "2020-01-01", "end_date": "2099-01-01"}, "futuro"),
    ],
)
async def test_datas_invalidas_dao_422_com_mensagem_em_todos_os_relatorios(db, params, trecho):
    admin = _usuario(UserRole.admin, "Admin")
    _, tecnico = await _pessoas(db)
    db.add(admin)
    await db.flush()

    async with _cliente_http(db, admin) as c:
        respostas = [await c.get(url, params=params) for url in _RELATORIOS]
        respostas.append(
            await c.get(
                "/api/v1/dashboard/reports/technician",
                params={**params, "technician_id": str(tecnico.id)},
            )
        )

    for resp in respostas:
        assert resp.status_code == 422, (resp.url, resp.text)
        assert trecho in resp.json()["detail"]


@pytest.mark.asyncio
async def test_prioridade_nula_no_periodo_anterior_responde_200_pela_api(db):
    admin = _usuario(UserRole.admin, "Admin")
    cliente, _ = await _pessoas(db)
    db.add(admin)
    db.add(_chamado_em(cliente, datetime(2026, 10, 9, 12, tzinfo=UTC), prioridade=None))
    await db.flush()

    async with _cliente_http(db, admin) as c:
        resp = await c.get(
            "/api/v1/dashboard/reports",
            params={"start_date": "2026-10-10", "end_date": "2026-10-10"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["comparison"]["total_tickets"] == 1


@pytest.mark.asyncio
async def test_cliente_nao_acessa_nenhum_relatorio(db):
    cliente, tecnico = await _pessoas(db)
    datas = {"start_date": "2026-10-01", "end_date": "2026-10-10"}

    async with _cliente_http(db, cliente) as c:
        respostas = [await c.get(url, params=datas) for url in _RELATORIOS]
        respostas.append(
            await c.get(
                "/api/v1/dashboard/reports/technician",
                params={**datas, "technician_id": str(tecnico.id)},
            )
        )

    assert [r.status_code for r in respostas] == [403] * 5


@pytest.mark.asyncio
async def test_tecnico_nao_ve_a_lista_e_ve_so_o_proprio_detalhe(db):
    cliente, tecnico = await _pessoas(db)
    outro = _usuario(UserRole.technician, "Bruno")
    db.add(outro)
    db.add(_chamado_em(cliente, datetime(2026, 10, 5, 12, tzinfo=UTC), outro))
    await db.flush()
    datas = {"start_date": "2026-10-01", "end_date": "2026-10-10"}

    async with _cliente_http(db, tecnico) as c:
        lista = await c.get("/api/v1/dashboard/reports/technicians", params=datas)
        detalhe = await c.get(
            "/api/v1/dashboard/reports/technician",
            params={**datas, "technician_id": str(outro.id)},
        )
        geral = await c.get("/api/v1/dashboard/reports", params=datas)

    assert lista.status_code == 403
    assert detalhe.status_code == 200
    assert detalhe.json()["technician_id"] == str(tecnico.id)
    assert detalhe.json()["total_assigned"] == 0
    assert geral.status_code == 200


@pytest.mark.asyncio
async def test_relatorio_tecnicos_e_exportacoes_contam_o_mesmo_periodo(db):
    admin = _usuario(UserRole.admin, "Admin")
    cliente, tecnico = await _pessoas(db)
    outro = _usuario(UserRole.technician, "Bruno")
    db.add_all([admin, outro])
    await db.flush()
    db.add_all(
        [
            _chamado_em(cliente, datetime(2026, 10, 1, 3, tzinfo=UTC), tecnico),  # 1º, 00:00
            _chamado_em(cliente, datetime(2026, 10, 4, 12, tzinfo=UTC), outro),
            _chamado_em(cliente, datetime(2026, 10, 11, 2, 59, tzinfo=UTC), outro),  # 10, 23:59
            _chamado_em(cliente, datetime(2026, 10, 11, 3, tzinfo=UTC), tecnico),  # fora
            _chamado_em(cliente, datetime(2026, 10, 1, 2, 59, tzinfo=UTC), tecnico),  # fora
        ]
    )
    await db.flush()
    datas = {"start_date": "2026-10-01", "end_date": "2026-10-10"}

    async with _cliente_http(db, admin) as c:
        geral = (await c.get("/api/v1/dashboard/reports", params=datas)).json()
        tecnicos = (await c.get("/api/v1/dashboard/reports/technicians", params=datas)).json()
        planilha = await c.get("/api/v1/dashboard/reports/export/csv", params=datas)
        pdf = await c.get("/api/v1/dashboard/reports/export/pdf", params=datas)

    assert geral["total_tickets"] == 3
    assert geral["timezone"] == "America/Recife"
    assert sum(t["total_assigned"] for t in tecnicos["technicians"]) == 3
    assert tecnicos["start_date"] == "2026-10-01"

    linhas = list(csv.reader(io.StringIO(planilha.text)))
    inicio = linhas.index(["Data", "Quantidade"]) + 1
    por_dia = []
    for linha in linhas[inicio:]:
        if not linha:
            break
        por_dia.append(linha)
    assert len(por_dia) == 10
    assert sum(int(q) for _, q in por_dia) == 3
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_period_legado_pela_api_continua_igual(db):
    admin = _usuario(UserRole.admin, "Admin")
    db.add(admin)
    await db.flush()

    async with _cliente_http(db, admin) as c:
        resp = await c.get("/api/v1/dashboard/reports", params={"period": 30})

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["period_days"] == 30
    assert corpo["start_date"] is not None and corpo["end_date"] is not None
