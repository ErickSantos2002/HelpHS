"""
Dashboard statistics endpoint.

Permissões:
  GET /dashboard/stats — admin, technician
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import (
    SatisfactionSurvey,
    Ticket,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.dashboard import DashboardStats, SlaStats, SurveyStats, TicketStats

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> DashboardStats:
    # ── Ticket counts by status ───────────────────────────────
    async def count_tickets(**filters) -> int:
        q = select(func.count()).select_from(Ticket)
        for col, val in filters.items():
            q = q.where(getattr(Ticket, col) == val)
        return (await db.execute(q)).scalar_one()

    total = await count_tickets()
    open_ = await count_tickets(status=TicketStatus.open)
    in_progress = await count_tickets(status=TicketStatus.in_progress)
    awaiting = await count_tickets(status=TicketStatus.awaiting_client) + await count_tickets(
        status=TicketStatus.awaiting_technical
    )
    resolved = await count_tickets(status=TicketStatus.resolved)
    closed = await count_tickets(status=TicketStatus.closed)
    cancelled = await count_tickets(status=TicketStatus.cancelled)

    # ── Ticket counts by priority ─────────────────────────────
    p_critical = await count_tickets(priority=TicketPriority.critical)
    p_high = await count_tickets(priority=TicketPriority.high)
    p_medium = await count_tickets(priority=TicketPriority.medium)
    p_low = await count_tickets(priority=TicketPriority.low)

    # ── SLA breaches ──────────────────────────────────────────
    resp_breached = (
        await db.execute(
            select(func.count()).select_from(Ticket).where(Ticket.sla_response_breach.is_(True))
        )
    ).scalar_one()
    resolve_breached = (
        await db.execute(
            select(func.count()).select_from(Ticket).where(Ticket.sla_resolve_breach.is_(True))
        )
    ).scalar_one()

    # ── Survey stats ──────────────────────────────────────────
    survey_total = (
        await db.execute(select(func.count()).select_from(SatisfactionSurvey))
    ).scalar_one()
    avg_raw = (await db.execute(select(func.avg(SatisfactionSurvey.rating)))).scalar_one()
    avg_rating = round(float(avg_raw), 2) if avg_raw is not None else None

    return DashboardStats(
        tickets=TicketStats(
            total=total,
            open=open_,
            in_progress=in_progress,
            awaiting=awaiting,
            resolved=resolved,
            closed=closed,
            cancelled=cancelled,
            by_priority_critical=p_critical,
            by_priority_high=p_high,
            by_priority_medium=p_medium,
            by_priority_low=p_low,
        ),
        surveys=SurveyStats(total=survey_total, average_rating=avg_rating),
        sla=SlaStats(response_breached=resp_breached, resolve_breached=resolve_breached),
    )
