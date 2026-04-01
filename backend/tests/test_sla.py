"""
Tests for the SLA engine (app/utils/sla.py).

All tests use deterministic datetimes in America/Sao_Paulo to ensure
business-hours logic is verified precisely.
"""

from datetime import timedelta
from unittest.mock import MagicMock

from app.models.models import SLAConfig, TicketStatus
from app.utils.sla import (
    _PAUSE_STATUSES,
    SP_TZ,
    add_business_hours,
    apply_sla_config,
    check_breaches,
    pause_sla,
    resume_sla,
)

# ── Helpers ───────────────────────────────────────────────────


def _sp(year, month, day, hour=0, minute=0):
    """Return a timezone-aware datetime in America/Sao_Paulo."""
    return SP_TZ.localize(__import__("datetime").datetime(year, month, day, hour, minute))


def _mock_ticket(
    status=TicketStatus.open,
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
    """8h from 14:00 Mon: 4h left today → ends at 18:00, then 4h Tue → 12:00 Tue."""
    start = _sp(2026, 4, 6, 14, 0)  # Monday 14:00
    result = add_business_hours(start, 8)
    assert result.weekday() == 1  # Tuesday
    assert result.hour == 12


def test_add_hours_crosses_weekend():
    """4h from Friday 16:00 (2h left today) → Monday 10:00."""
    start = _sp(2026, 4, 10, 16, 0)  # Friday 16:00
    result = add_business_hours(start, 4)
    assert result.weekday() == 0  # Monday
    assert result.hour == 10


def test_add_hours_start_before_work():
    """Starting before 08:00 is treated as starting at 08:00."""
    start = _sp(2026, 4, 6, 6, 0)  # Monday 06:00
    result = add_business_hours(start, 2)
    assert result.hour == 10
    assert result.date() == start.date()


def test_add_hours_start_after_work():
    """Starting after 18:00 advances to next business day 08:00."""
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
    """24 business hours = 2 full working days + 4h (24 = 10+10+4)."""
    start = _sp(2026, 4, 6, 8, 0)  # Monday 08:00
    result = add_business_hours(start, 24)
    # 10h Mon + 10h Tue + 4h Wed = Wednesday 12:00
    assert result.weekday() == 2  # Wednesday
    assert result.hour == 12


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
