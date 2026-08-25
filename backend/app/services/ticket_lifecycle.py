"""
Encerramento do chamado — fechamento automático (RN-005) e prazo de reabertura
(RN-006).

Por que roda dentro da API, e não numa fila
-------------------------------------------
**É deliberado.** O ambiente sobe um processo só — o `start.sh` executa apenas
o uvicorn — e uma rodada de hora em hora não paga o custo de operar um segundo
serviço só para ela. Um pacote Celery chegou a existir aqui sem nunca executar
nada; foi removido em 25/08/2026 (ver docs/decisoes-e-regras.md).

A rotina roda então como uma task asyncio do próprio processo da API. Como o
uvicorn sobe com `--workers 2`, os dois processos acordariam juntos: um lock no
Redis garante que só um deles trabalha por rodada. Sem Redis a rodada é pulada
— fechar o mesmo chamado duas vezes geraria histórico e notificação duplicados.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.models import (
    AuditAction,
    AuditLog,
    NotificationType,
    Ticket,
    TicketHistory,
    TicketStatus,
)
from app.services.notifications import notify
from app.utils.sla import add_business_days

_LOCK_KEY = "helphs:lock:ticket-auto-close"
_BATCH_LIMIT = 200


# ── Prazos ────────────────────────────────────────────────────


def resolution_reference(ticket: Ticket) -> datetime | None:
    """
    Data a partir da qual os dois prazos são contados.

    É o `resolved_at`, mas chamados encerrados antes da v1.4.0 podem não
    tê-lo: a migration faz o backfill a partir do `closed_at`, e o mesmo
    fallback vale aqui para qualquer base onde ele não tenha rodado. Sem isso
    o chamado antigo ficaria sem prazo nenhum — nem fecha, nem reabre.
    """
    return ticket.resolved_at or ticket.closed_at


def auto_close_deadline(resolved_at: datetime, settings: Settings) -> datetime:
    """Quando o chamado resolvido passa sozinho para Fechado."""
    return add_business_days(resolved_at, settings.ticket_auto_close_business_days)


def reopen_deadline(resolved_at: datetime, settings: Settings) -> datetime:
    """Até quando o cliente ainda pode reabrir o chamado."""
    return add_business_days(resolved_at, settings.ticket_reopen_business_days)


def can_client_reopen(ticket: Ticket, settings: Settings, now: datetime | None = None) -> bool:
    if ticket.status not in (TicketStatus.resolved, TicketStatus.closed):
        return False
    referencia = resolution_reference(ticket)
    if referencia is None:
        return False
    now = now or datetime.now(UTC)
    return now <= reopen_deadline(referencia, settings)


# ── Fechamento automático ─────────────────────────────────────


async def close_expired_tickets(db: AsyncSession, settings: Settings) -> int:
    """
    Fecha os chamados resolvidos que passaram do prazo. Devolve quantos foram
    fechados. O commit é feito aqui — esta rotina não tem um handler HTTP dono
    da transação.
    """
    now = datetime.now(UTC)

    referencia_sql = func.coalesce(Ticket.resolved_at, Ticket.closed_at)
    rows = await db.execute(
        select(Ticket)
        .where(Ticket.status == TicketStatus.resolved, referencia_sql.is_not(None))
        .order_by(referencia_sql)
        .limit(_BATCH_LIMIT)
    )
    candidates = rows.scalars().all()

    closed = 0
    for ticket in candidates:
        referencia = resolution_reference(ticket)
        if referencia is None or now < auto_close_deadline(referencia, settings):
            continue

        ticket.status = TicketStatus.closed
        ticket.closed_at = now
        ticket.updated_at = now
        ticket.auto_closed = True

        db.add(
            TicketHistory(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                user_id=None,  # ação do sistema, sem autor humano
                field="status",
                old_value=TicketStatus.resolved.value,
                new_value=TicketStatus.closed.value,
                comment=(
                    f"Fechado automaticamente após "
                    f"{settings.ticket_auto_close_business_days} dias úteis "
                    f"sem manifestação do cliente."
                ),
            )
        )
        db.add(
            AuditLog(
                user_id=None,
                action=AuditAction.status_change,
                entity_type="ticket",
                entity_id=ticket.id,
            )
        )
        await notify(
            db,
            ticket.creator_id,
            NotificationType.ticket_closed,
            "Chamado fechado automaticamente",
            (
                f"O ticket {ticket.protocol} foi fechado por falta de manifestação. "
                f"Se o problema voltar, você ainda pode reabri-lo."
            ),
            data={"ticket_id": str(ticket.id), "protocol": ticket.protocol},
            settings=settings,
        )
        closed += 1

    if closed:
        await db.commit()
        logger.info(f"Fechamento automático: {closed} chamado(s) movidos para Fechado")

    return closed


async def _run_once() -> None:
    """Uma rodada, protegida por lock para não repetir entre os workers."""
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis

    settings = get_settings()
    ttl = max(60, settings.ticket_auto_close_interval_seconds - 60)

    try:
        redis = await get_redis()
        got_lock = await redis.set(_LOCK_KEY, "1", nx=True, ex=ttl)
    except Exception as exc:  # noqa: BLE001 — Redis fora do ar não pode derrubar a API
        logger.warning(f"Fechamento automático pulado (Redis indisponível): {exc}")
        return

    if not got_lock:
        return  # outro worker já está cuidando desta rodada

    try:
        async with AsyncSessionLocal() as db:
            await close_expired_tickets(db, settings)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Falha na rotina de fechamento automático: {exc}")


async def auto_close_loop() -> None:
    settings = get_settings()
    interval = settings.ticket_auto_close_interval_seconds

    # Um respiro depois do boot: migrations e seeds ainda podem estar rodando.
    await asyncio.sleep(min(60, interval))

    while True:
        await _run_once()
        await asyncio.sleep(interval)


def start_auto_close_worker() -> asyncio.Task | None:
    """Sobe o laço em background. Devolve None quando a rotina está desligada."""
    settings = get_settings()
    if settings.ticket_auto_close_interval_seconds <= 0:
        logger.info("Fechamento automático desligado (intervalo = 0)")
        return None

    logger.info(
        f"Fechamento automático ativo: {settings.ticket_auto_close_business_days} dias úteis, "
        f"verificando a cada {settings.ticket_auto_close_interval_seconds}s"
    )
    return asyncio.create_task(auto_close_loop(), name="ticket-auto-close")
