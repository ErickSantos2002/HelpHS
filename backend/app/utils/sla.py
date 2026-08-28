"""
SLA Engine — business-hours calculator and breach tracker.

Business hours: 08:00–17:00, Mon–Fri, America/Sao_Paulo (9 h/day).
Holidays are not modelled in this version.

Public API
----------
add_business_hours(start, hours)  → datetime
    Adds N working hours to `start`, skipping nights/weekends.

add_business_days(start, days)  → datetime
    Same thing in units of whole working days (9 h each).

apply_sla_config(ticket, config, now)
    Stamps sla_config_id, sla_response_due_at, sla_resolve_due_at on a ticket.

pause_sla(ticket, now)
    Records that the SLA clock started pausing (awaiting_* states).

resume_sla(ticket, now)
    Accumulates elapsed pause time and restarts the clock.

check_breaches(ticket, now)
    Flips sla_response_breach / sla_resolve_breach if deadlines have passed.

register_first_response(ticket, now, responder_id=..., is_ai=..., is_system=...)
    Stamps sla_first_response when someone other than the ticket's author
    speaks to the client for the first time.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytz

from app.models.models import SLAConfig, Ticket, TicketStatus

# ── Constants ─────────────────────────────────────────────────

# Jornada e fuso são CONSTANTES de propósito, não configuração.
#
# 08:00–17:00 (9 h/dia) foi confirmado com o cliente em 05/08/2026 e é o que o
# RN-013 sempre disse — ver "SLA" em docs/decisoes-e-regras.md.
#
# Existiu um bloco SLA_* no config.py que ninguém lia e que dizia 18:00. Ligar
# aquilo aqui para "corrigir a divergência" mudaria o prazo de TODOS os chamados
# de uma vez, sem ninguém perceber. Se o horário precisar mudar um dia, muda
# aqui — e a decisão vai para o documento antes do código.
SP_TZ = pytz.timezone("America/Sao_Paulo")
_WORK_START = 8  # 08:00
_WORK_END = 17  # 17:00
_WORK_HOURS_PER_DAY = _WORK_END - _WORK_START  # 9 h

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


def add_business_days(start: datetime, days: int) -> datetime:
    """
    Return a datetime that is exactly `days` business days after `start`.

    A business day is the 9 h journey itself, so this is just a convenience
    wrapper over add_business_hours — a deadline set on Friday afternoon lands
    on the middle of the following week, not on Monday morning.
    """
    return add_business_hours(start, days * _WORK_HOURS_PER_DAY)


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


def register_first_response(
    ticket: Ticket,
    now: datetime,
    *,
    responder_id: uuid.UUID | None,
    is_ai: bool = False,
    is_system: bool = False,
) -> bool:
    """
    Carimba a primeira resposta do SLA. Devolve True se carimbou agora.

    Primeira resposta é a primeira fala dirigida ao cliente por alguém que não
    é o autor do chamado — não é "o chamado saiu do estado inicial". A regra
    não olha para status nenhum, de propósito: assumir, atribuir ou cancelar
    um chamado marcava resposta sem uma palavra ter sido dita, e chamado que
    nasce fora de `open` (a Helô) nunca marcava.

    O critério de "não é o autor" é o mesmo que o chat já usa para decidir a
    quem notificar (`_notify_other_party`) — mesma pergunta, uma só resposta.
    Vale também na resolução: quando quem abre e quem resolve são a mesma
    pessoa, não houve ninguém do outro lado esperando, e um tempo de resposta
    de zero segundo só sujaria a média de uma conversa que não existiu.

    **A fala da Helô CARIMBA** — decisão do cliente em 28/08/2026, revertendo
    o desenho original. O argumento dele: quando ela responde, o atendimento
    começou de fato, e mostrar "aguardando primeira resposta" para um cliente
    que acabou de ser respondido é o indicador mentindo para o lado contrário.

    O preço está registrado aqui porque ele é real e não aparece sozinho: com
    a Helô ligada, todo chamado passa a ter primeira resposta em segundos, e
    este indicador vira ~100% permanente. Ele deixa de medir a equipe e passa
    a medir o robô, que é sempre rápido. Se um dia fizer falta saber quanto o
    cliente esperou por um HUMANO, esse número não existe mais — seria uma
    coluna nova, não um filtro sobre esta.

    `is_system` continua sem carimbar: mensagem automática de mudança de
    status não é alguém falando com o cliente.

    A violação é avaliada ANTES do carimbo porque `check_breaches` só olha o
    prazo enquanto `sla_first_response` é nulo — na ordem inversa, a resposta
    atrasada apagava a própria violação.
    """
    if ticket.sla_first_response is not None:
        return False
    if is_system:
        return False
    # A Helô não tem `responder_id` — ela fala com remetente nulo. A checagem
    # de autor abaixo existe para gente, e sem esta saída ela recusaria o
    # carimbo justamente no caso que o cliente pediu.
    if not is_ai and (responder_id is None or responder_id == ticket.creator_id):
        return False

    offset = timedelta(milliseconds=ticket.sla_total_paused_ms or 0)
    if ticket.sla_response_due_at and now > ticket.sla_response_due_at + offset:
        ticket.sla_response_breach = True

    ticket.sla_first_response = now
    return True
