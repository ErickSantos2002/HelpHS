"""
SLA Engine — business-hours calculator and breach tracker.

Business hours: 08:00–18:00, Mon–Fri, America/Sao_Paulo (10 h/day).
Holidays are not modelled in this version.

Public API
----------
add_business_hours(start, hours)  → datetime
    Adds N working hours to `start`, skipping nights/weekends.

apply_sla_config(ticket, config, now)
    Stamps sla_config_id, sla_response_due_at, sla_resolve_due_at on a ticket.

pause_sla(ticket, now)
    Records that the SLA clock started pausing (awaiting_* states).

resume_sla(ticket, now)
    Accumulates elapsed pause time and restarts the clock.

check_breaches(ticket, now)
    Flips sla_response_breach / sla_resolve_breach if deadlines have passed.
"""

from datetime import UTC, datetime, timedelta

import pytz

from app.models.models import SLAConfig, Ticket, TicketStatus

# ── Constants ─────────────────────────────────────────────────

SP_TZ = pytz.timezone("America/Sao_Paulo")
_WORK_START = 8  # 08:00
_WORK_END = 18  # 18:00
_WORK_HOURS_PER_DAY = _WORK_END - _WORK_START  # 10 h

_PAUSE_STATUSES = frozenset({TicketStatus.awaiting_client, TicketStatus.awaiting_technical})
_TERMINAL_STATUSES = frozenset({TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled})


# ── Internal helpers ──────────────────────────────────────────


def _to_sp(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to America/Sao_Paulo."""
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(SP_TZ)


def _advance_to_business_hours(dt: datetime) -> datetime:
    """
    If `dt` is outside working hours, return the next moment that IS inside
    working hours (keeping the SP timezone).
    """
    dt = _to_sp(dt)

    # Skip weekends
    while dt.weekday() >= 5:
        dt = (dt + timedelta(days=1)).replace(hour=_WORK_START, minute=0, second=0, microsecond=0)

    if dt.hour < _WORK_START:
        return dt.replace(hour=_WORK_START, minute=0, second=0, microsecond=0)

    if dt.hour >= _WORK_END:
        # Move to next business day
        dt = (dt + timedelta(days=1)).replace(hour=_WORK_START, minute=0, second=0, microsecond=0)
        while dt.weekday() >= 5:
            dt = (dt + timedelta(days=1)).replace(
                hour=_WORK_START, minute=0, second=0, microsecond=0
            )

    return dt


# ── Public API ────────────────────────────────────────────────


def add_business_hours(start: datetime, hours: int) -> datetime:
    """
    Return a datetime that is exactly `hours` business hours after `start`.
    Result is in America/Sao_Paulo timezone.
    """
    current = _advance_to_business_hours(start)
    remaining: float = hours

    while remaining > 0:
        end_of_day = current.replace(hour=_WORK_END, minute=0, second=0, microsecond=0)
        hours_left_today = (end_of_day - current).total_seconds() / 3600

        if remaining <= hours_left_today:
            current = current + timedelta(hours=remaining)
            remaining = 0
        else:
            remaining -= hours_left_today
            # Jump to next business day start
            next_day = (current + timedelta(days=1)).replace(
                hour=_WORK_START, minute=0, second=0, microsecond=0
            )
            while next_day.weekday() >= 5:
                next_day = (next_day + timedelta(days=1)).replace(
                    hour=_WORK_START, minute=0, second=0, microsecond=0
                )
            current = next_day

    return current


def apply_sla_config(ticket: Ticket, config: SLAConfig, now: datetime) -> None:
    """Stamp SLA deadlines on a ticket at creation time."""
    ticket.sla_config_id = config.id
    ticket.sla_response_due_at = add_business_hours(now, config.response_time_hours)
    ticket.sla_resolve_due_at = add_business_hours(now, config.resolve_time_hours)


def pause_sla(ticket: Ticket, now: datetime) -> None:
    """
    Start the pause clock.  Safe to call even if already paused
    (subsequent calls are no-ops).
    """
    if ticket.sla_paused_at is None:
        ticket.sla_paused_at = now


def resume_sla(ticket: Ticket, now: datetime) -> None:
    """
    Stop the pause clock and accumulate the elapsed pause duration into
    sla_total_paused_ms.  The accumulated time will later be used to extend
    the effective deadlines.
    """
    if ticket.sla_paused_at is not None:
        paused_ms = int((now - ticket.sla_paused_at).total_seconds() * 1000)
        ticket.sla_total_paused_ms = (ticket.sla_total_paused_ms or 0) + paused_ms
        ticket.sla_paused_at = None


def check_breaches(ticket: Ticket, now: datetime) -> None:
    """
    Update sla_response_breach and sla_resolve_breach.
    The effective deadline = original_due_at + total_paused_ms,
    so pause time extends the deadlines proportionally.
    """
    offset = timedelta(milliseconds=ticket.sla_total_paused_ms or 0)

    if ticket.sla_response_due_at and ticket.sla_first_response is None:
        effective = ticket.sla_response_due_at + offset
        if now > effective:
            ticket.sla_response_breach = True

    if ticket.sla_resolve_due_at and ticket.status not in _TERMINAL_STATUSES:
        effective = ticket.sla_resolve_due_at + offset
        if now > effective:
            ticket.sla_resolve_breach = True
