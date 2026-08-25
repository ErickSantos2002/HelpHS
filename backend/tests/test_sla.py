"""
Tests for the SLA engine (app/utils/sla.py).

All tests use deterministic datetimes in America/Sao_Paulo to ensure
business-hours logic is verified precisely.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.models import SLAConfig, TicketStatus
from app.utils.sla import (
    _PAUSE_STATUSES,
    SP_TZ,
    add_business_hours,
    apply_sla_config,
    check_breaches,
    pause_sla,
    register_first_response,
    resume_sla,
)

# ── Helpers ───────────────────────────────────────────────────

_AUTOR_ID = uuid.uuid4()
_TECNICO_ID = uuid.uuid4()


def _sp(year, month, day, hour=0, minute=0):
    """Return a timezone-aware datetime in America/Sao_Paulo."""
    return SP_TZ.localize(__import__("datetime").datetime(year, month, day, hour, minute))


def _mock_ticket(
    status=TicketStatus.open,
    creator_id=None,
    sla_paused_at=None,
    sla_total_paused_ms=0,
    sla_response_due_at=None,
    sla_resolve_due_at=None,
    sla_first_response=None,
    sla_response_breach=False,
    sla_resolve_breach=False,
):
    t = MagicMock()
    t.status = status
    t.creator_id = creator_id or _AUTOR_ID
    t.sla_paused_at = sla_paused_at
    t.sla_total_paused_ms = sla_total_paused_ms
    t.sla_response_due_at = sla_response_due_at
    t.sla_resolve_due_at = sla_resolve_due_at
    t.sla_first_response = sla_first_response
    t.sla_response_breach = sla_response_breach
    t.sla_resolve_breach = sla_resolve_breach
    return t


# ═══════════════════════════════════════════════════════════════
# add_business_hours
# ═══════════════════════════════════════════════════════════════


def test_add_hours_same_day():
    """2h from 09:00 Mon → 11:00 same day."""
    start = _sp(2026, 4, 6, 9, 0)  # Monday 09:00
    result = add_business_hours(start, 2)
    assert result.hour == 11
    assert result.date() == start.date()


def test_add_hours_crosses_end_of_day():
    """8h from 14:00 Mon: 3h left today → ends at 17:00, then 5h Tue → 13:00 Tue."""
    start = _sp(2026, 4, 6, 14, 0)  # Monday 14:00
    result = add_business_hours(start, 8)
    assert result.weekday() == 1  # Tuesday
    assert result.hour == 13


def test_add_hours_crosses_weekend():
    """4h from Friday 16:00 (1h left today) → Monday 11:00."""
    start = _sp(2026, 4, 10, 16, 0)  # Friday 16:00
    result = add_business_hours(start, 4)
    assert result.weekday() == 0  # Monday
    assert result.hour == 11


def test_add_hours_start_before_work():
    """Starting before 08:00 is treated as starting at 08:00."""
    start = _sp(2026, 4, 6, 6, 0)  # Monday 06:00
    result = add_business_hours(start, 2)
    assert result.hour == 10
    assert result.date() == start.date()


def test_add_hours_start_after_work():
    """Starting after 17:00 advances to next business day 08:00."""
    start = _sp(2026, 4, 6, 19, 0)  # Monday 19:00
    result = add_business_hours(start, 2)
    assert result.weekday() == 1  # Tuesday
    assert result.hour == 10


def test_add_hours_start_on_saturday():
    """Starting on Saturday advances to Monday."""
    start = _sp(2026, 4, 11, 10, 0)  # Saturday 10:00
    result = add_business_hours(start, 1)
    assert result.weekday() == 0  # Monday
    assert result.hour == 9


def test_add_hours_multiple_days():
    """24 horas úteis = 2 dias cheios + 6h (24 = 9+9+6)."""
    start = _sp(2026, 4, 6, 8, 0)  # Monday 08:00
    result = add_business_hours(start, 24)
    # 9h Mon + 9h Tue + 6h Wed = Wednesday 14:00
    assert result.weekday() == 2  # Wednesday
    assert result.hour == 14


def test_add_zero_hours():
    """0 business hours returns the (advanced) start time."""
    start = _sp(2026, 4, 6, 10, 0)
    result = add_business_hours(start, 0)
    assert result.hour == 10
    assert result.date() == start.date()


# ═══════════════════════════════════════════════════════════════
# apply_sla_config
# ═══════════════════════════════════════════════════════════════


def test_apply_sla_config_sets_deadlines():
    ticket = _mock_ticket()
    config = MagicMock(spec=SLAConfig)
    config.id = __import__("uuid").uuid4()
    config.response_time_hours = 2
    config.resolve_time_hours = 8

    now = _sp(2026, 4, 6, 9, 0)  # Monday 09:00
    apply_sla_config(ticket, config, now)

    assert ticket.sla_config_id == config.id
    assert ticket.sla_response_due_at.hour == 11  # 09:00 + 2h
    assert ticket.sla_resolve_due_at.hour == 17  # 09:00 + 8h


# ═══════════════════════════════════════════════════════════════
# pause_sla / resume_sla
# ═══════════════════════════════════════════════════════════════


def test_pause_sla_sets_paused_at():
    ticket = _mock_ticket()
    now = _sp(2026, 4, 6, 10, 0)
    pause_sla(ticket, now)
    assert ticket.sla_paused_at == now


def test_pause_sla_no_op_if_already_paused():
    first_pause = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(sla_paused_at=first_pause)
    second_pause = _sp(2026, 4, 6, 11, 0)
    pause_sla(ticket, second_pause)
    assert ticket.sla_paused_at == first_pause  # unchanged


def test_resume_sla_accumulates_ms():
    paused_at = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(sla_paused_at=paused_at, sla_total_paused_ms=0)
    resume_at = paused_at + timedelta(hours=2)
    resume_sla(ticket, resume_at)

    assert ticket.sla_paused_at is None
    assert ticket.sla_total_paused_ms == 2 * 3600 * 1000  # 2h in ms


def test_resume_sla_adds_to_existing_paused_ms():
    paused_at = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(sla_paused_at=paused_at, sla_total_paused_ms=3_600_000)  # 1h already
    resume_at = paused_at + timedelta(hours=1)
    resume_sla(ticket, resume_at)
    assert ticket.sla_total_paused_ms == 2 * 3600 * 1000  # 2h total


def test_resume_sla_no_op_if_not_paused():
    ticket = _mock_ticket(sla_paused_at=None, sla_total_paused_ms=0)
    resume_sla(ticket, _sp(2026, 4, 6, 12, 0))
    assert ticket.sla_total_paused_ms == 0


# ═══════════════════════════════════════════════════════════════
# check_breaches
# ═══════════════════════════════════════════════════════════════


def test_check_breaches_no_breach_within_deadline():
    due = _sp(2026, 4, 6, 17, 0)
    ticket = _mock_ticket(
        sla_response_due_at=due,
        sla_resolve_due_at=due,
    )
    now = _sp(2026, 4, 6, 16, 0)  # 1h before deadline
    check_breaches(ticket, now)
    assert ticket.sla_response_breach is False
    assert ticket.sla_resolve_breach is False


def test_check_breaches_response_breach():
    due = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(sla_response_due_at=due, sla_first_response=None)
    now = _sp(2026, 4, 6, 11, 0)  # 1h past due
    check_breaches(ticket, now)
    assert ticket.sla_response_breach is True


def test_check_breaches_no_response_breach_if_already_responded():
    due = _sp(2026, 4, 6, 10, 0)
    first_response = _sp(2026, 4, 6, 9, 0)  # responded before due
    ticket = _mock_ticket(sla_response_due_at=due, sla_first_response=first_response)
    now = _sp(2026, 4, 6, 11, 0)
    check_breaches(ticket, now)
    assert ticket.sla_response_breach is False


def test_check_breaches_resolve_breach():
    due = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(
        status=TicketStatus.in_progress,
        sla_resolve_due_at=due,
    )
    now = _sp(2026, 4, 6, 12, 0)
    check_breaches(ticket, now)
    assert ticket.sla_resolve_breach is True


def test_check_breaches_no_resolve_breach_if_resolved():
    due = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(
        status=TicketStatus.resolved,
        sla_resolve_due_at=due,
    )
    now = _sp(2026, 4, 6, 12, 0)
    check_breaches(ticket, now)
    assert ticket.sla_resolve_breach is False


def test_check_breaches_pause_extends_deadline():
    """2h of pause time should push back the effective deadline by 2h."""
    due = _sp(2026, 4, 6, 10, 0)
    paused_ms = 2 * 3600 * 1000  # 2h paused
    ticket = _mock_ticket(
        sla_resolve_due_at=due,
        sla_total_paused_ms=paused_ms,
        status=TicketStatus.in_progress,
    )
    # now = 11:00 — past original due (10:00) but within extended deadline (12:00)
    now = _sp(2026, 4, 6, 11, 0)
    check_breaches(ticket, now)
    assert ticket.sla_resolve_breach is False


# ═══════════════════════════════════════════════════════════════
# Pause statuses constant
# ═══════════════════════════════════════════════════════════════


def test_pause_statuses_set():
    assert TicketStatus.awaiting_client in _PAUSE_STATUSES
    assert TicketStatus.awaiting_technical in _PAUSE_STATUSES
    assert TicketStatus.in_progress not in _PAUSE_STATUSES


# ═══════════════════════════════════════════════════════════════
# register_first_response — quem "respondeu" ao cliente
# ═══════════════════════════════════════════════════════════════


def test_first_response_marca_quando_nao_autor_responde():
    """Técnico falando no chamado é a primeira resposta."""
    ticket = _mock_ticket()
    now = _sp(2026, 4, 6, 9, 30)

    marcou = register_first_response(ticket, now, responder_id=_TECNICO_ID)

    assert marcou is True
    assert ticket.sla_first_response == now


def test_first_response_ignora_o_autor_do_chamado():
    """Cliente escrevendo no próprio chamado não responde a si mesmo."""
    ticket = _mock_ticket()

    marcou = register_first_response(ticket, _sp(2026, 4, 6, 9, 30), responder_id=_AUTOR_ID)

    assert marcou is False
    assert ticket.sla_first_response is None


def test_first_response_e_idempotente():
    """A segunda mensagem do técnico não desloca o carimbo da primeira."""
    primeira = _sp(2026, 4, 6, 9, 30)
    ticket = _mock_ticket(sla_first_response=primeira)

    marcou = register_first_response(ticket, _sp(2026, 4, 6, 11, 0), responder_id=_TECNICO_ID)

    assert marcou is False
    assert ticket.sla_first_response == primeira


def test_first_response_ignora_mensagem_da_ia():
    """A Helô não zera o relógio — o SLA espera um humano."""
    ticket = _mock_ticket()

    marcou = register_first_response(
        ticket, _sp(2026, 4, 6, 9, 30), responder_id=_TECNICO_ID, is_ai=True
    )

    assert marcou is False
    assert ticket.sla_first_response is None


def test_first_response_ignora_mensagem_do_sistema():
    ticket = _mock_ticket()

    marcou = register_first_response(
        ticket, _sp(2026, 4, 6, 9, 30), responder_id=_TECNICO_ID, is_system=True
    )

    assert marcou is False
    assert ticket.sla_first_response is None


def test_first_response_ignora_remetente_nulo():
    """Remetente nulo é ação do sistema — blinda a Helô antes de ela existir."""
    ticket = _mock_ticket()

    marcou = register_first_response(ticket, _sp(2026, 4, 6, 9, 30), responder_id=None)

    assert marcou is False
    assert ticket.sla_first_response is None


def test_first_response_atrasada_preserva_a_violacao():
    """Responder depois do prazo carimba a resposta E registra a violação.

    Regressão do bug em que carimbar antes de check_breaches apagava a
    violação: o chamado atendido com atraso saía do relatório limpo.
    """
    due = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(sla_response_due_at=due)
    now = _sp(2026, 4, 6, 12, 0)

    register_first_response(ticket, now, responder_id=_TECNICO_ID)

    assert ticket.sla_first_response == now
    assert ticket.sla_response_breach is True


def test_first_response_dentro_do_prazo_nao_marca_violacao():
    due = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(sla_response_due_at=due)

    register_first_response(ticket, _sp(2026, 4, 6, 9, 0), responder_id=_TECNICO_ID)

    assert ticket.sla_response_breach is False


def test_first_response_conta_a_pausa_no_prazo():
    """2h de pausa esticam o prazo: 11:00 ainda está dentro de um prazo de 10:00."""
    due = _sp(2026, 4, 6, 10, 0)
    ticket = _mock_ticket(sla_response_due_at=due, sla_total_paused_ms=2 * 3600 * 1000)

    register_first_response(ticket, _sp(2026, 4, 6, 11, 0), responder_id=_TECNICO_ID)

    assert ticket.sla_response_breach is False


def test_first_response_sem_prazo_configurado_apenas_carimba():
    """Chamado sem SLA aplicado registra a resposta sem inventar violação."""
    ticket = _mock_ticket(sla_response_due_at=None)
    now = _sp(2026, 4, 6, 9, 30)

    register_first_response(ticket, now, responder_id=_TECNICO_ID)

    assert ticket.sla_first_response == now
    assert ticket.sla_response_breach is False


# ═══════════════════════════════════════════════════════════════
# PATCH /sla-configs/{id} — a rede que faltava
# ═══════════════════════════════════════════════════════════════
#
# Este arquivo tinha 30 testes do motor de SLA e NENHUM que batesse no
# endpoint. Por isso três kwargs errados na linha de auditoria sobreviveram:
# o PATCH devolvia 500 em 100% das chamadas — configurar prazo de SLA pela
# interface nunca funcionou — e nada na suíte percebia.
#
# O mypy também não pega: modelo declarativo do SQLAlchemy não tem __init__
# conferido. A rede que faltava era teste de endpoint, e é o que entra aqui.


def _config_falsa():
    c = MagicMock()
    c.id = uuid.uuid4()
    c.level = "critical"
    c.response_time_hours = 1
    c.resolve_time_hours = 4
    c.warning_threshold = 80
    c.is_active = True
    c.created_at = datetime.now(UTC)
    c.updated_at = datetime.now(UTC)
    return c


def _db_com(config):
    """Sessão que devolve `config` e guarda o que foi adicionado."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = config

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return session, _gen


@pytest.mark.asyncio
async def test_patch_de_sla_responde_200_e_persiste():
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.main import app
    from app.models.models import UserRole

    config = _config_falsa()
    session, override = _db_com(config)

    admin = MagicMock()
    admin.id = uuid.uuid4()
    admin.role = UserRole.admin

    async def _admin():
        return admin

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_current_user] = _admin
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.patch(
                f"/api/v1/sla-configs/{config.id}", json={"response_time_hours": 3}
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    assert config.response_time_hours == 3, "o valor não chegou no objeto"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_patch_de_sla_registra_auditoria_com_os_campos_do_modelo():
    """
    Os três kwargs errados (resource_type/resource_id/new_values) só aparecem
    quando alguém constrói o AuditLog de verdade — daí o teste afirmar os
    nomes que o modelo tem, e não só o 200.
    """
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.main import app
    from app.models.models import AuditLog, UserRole

    config = _config_falsa()
    session, override = _db_com(config)

    admin = MagicMock()
    admin.id = uuid.uuid4()
    admin.role = UserRole.admin

    async def _admin():
        return admin

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_current_user] = _admin
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.patch(f"/api/v1/sla-configs/{config.id}", json={"resolve_time_hours": 8})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text

    logs = [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], AuditLog)]
    assert logs, "nenhuma linha de auditoria foi adicionada"
    log = logs[0]
    assert log.entity_type == "sla_config"
    assert log.entity_id == config.id, "entity_id é UUID no modelo, não string"
    assert log.new_data == {"resolve_time_hours": 8}
