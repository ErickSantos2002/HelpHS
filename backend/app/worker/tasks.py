import asyncio
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.models import Ticket, TicketStatus
from app.utils.sla import check_breaches
from app.worker.celery_app import celery_app

# ── SLA breach checker ────────────────────────────────────────

_TERMINAL = {TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled}


async def _run_sla_check() -> dict:
    now = datetime.now(UTC)
    updated = 0
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Ticket).where(
                    Ticket.status.not_in(list(_TERMINAL)),
                    Ticket.sla_resolve_due_at.is_not(None),
                )
            )
        ).scalars().all()

        for ticket in rows:
            before_resp    = ticket.sla_response_breach
            before_resolve = ticket.sla_resolve_breach
            check_breaches(ticket, now)
            if ticket.sla_response_breach != before_resp or ticket.sla_resolve_breach != before_resolve:
                updated += 1

        await db.commit()
    return {"checked": len(rows), "updated": updated}


@celery_app.task(bind=True, name="tasks.send_notification_email", max_retries=3)
def send_notification_email(self, user_id: str, subject: str, body: str) -> dict:
    """Envia email de notificacao de forma assincrona."""
    try:
        logger.info(f"Sending notification email to user {user_id}: {subject}")
        # Implementacao real sera adicionada na task de email (Sprint 3)
        return {"status": "queued", "user_id": user_id, "subject": subject}
    except Exception as exc:
        logger.error(f"Email task failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="tasks.classify_ticket", max_retries=2)
def classify_ticket(self, ticket_id: str, title: str, description: str) -> dict:
    """Classifica ticket via IA de forma assincrona."""
    try:
        logger.info(f"Classifying ticket {ticket_id}")
        # Implementacao real sera adicionada na task de IA (Sprint 6)
        return {"status": "queued", "ticket_id": ticket_id}
    except Exception as exc:
        logger.error(f"Classification task failed: {exc}")
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.health_check")
def health_check() -> dict:
    """Task de verificacao de saude do worker."""
    logger.info("Celery worker health check OK")
    return {"status": "ok"}


@celery_app.task(name="tasks.check_sla_breaches")
def check_sla_breaches() -> dict:
    """Varre todos os tickets ativos e marca SLA vencido quando o prazo passou."""
    result = asyncio.run(_run_sla_check())
    logger.info(
        "SLA breach check — {} tickets verificados, {} atualizados",
        result["checked"],
        result["updated"],
    )
    return result
