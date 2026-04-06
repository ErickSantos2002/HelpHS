"""
Dashboard statistics endpoint.

Permissões:
  GET /dashboard/stats   — admin, technician
  GET /dashboard/reports — admin, technician
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import authorize
from app.models.models import (
    SatisfactionSurvey,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
)
from app.schemas.dashboard import (
    CategoryCount,
    CSATDistributionItem,
    DailyCount,
    DashboardStats,
    ReportData,
    SLAComplianceItem,
    SlaStats,
    SurveyStats,
    TicketStats,
)

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


@router.get("/dashboard/reports", response_model=ReportData)
async def get_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    period: Annotated[int, Query(ge=7, le=365)] = 30,
) -> ReportData:
    since = datetime.now(UTC) - timedelta(days=period)

    # ── Total tickets in period ───────────────────────────────
    total = (
        await db.execute(select(func.count()).select_from(Ticket).where(Ticket.created_at >= since))
    ).scalar_one()

    # ── Tickets per day ───────────────────────────────────────
    rows = (
        await db.execute(
            select(
                func.date_trunc("day", Ticket.created_at).label("day"),
                func.count().label("cnt"),
            )
            .where(Ticket.created_at >= since)
            .group_by(func.date_trunc("day", Ticket.created_at))
            .order_by(func.date_trunc("day", Ticket.created_at))
        )
    ).all()
    # Fill every day in range so the chart has no gaps
    counts_by_day: dict[str, int] = {r.day.strftime("%Y-%m-%d"): r.cnt for r in rows}
    tickets_by_day = [
        DailyCount(
            date=(since + timedelta(days=i)).strftime("%Y-%m-%d"),
            count=counts_by_day.get((since + timedelta(days=i)).strftime("%Y-%m-%d"), 0),
        )
        for i in range(period + 1)
    ]

    # ── Tickets by category ───────────────────────────────────
    cat_rows = (
        await db.execute(
            select(Ticket.category, func.count().label("cnt"))
            .where(Ticket.created_at >= since)
            .group_by(Ticket.category)
            .order_by(func.count().desc())
        )
    ).all()
    tickets_by_category = [CategoryCount(category=r.category.value, count=r.cnt) for r in cat_rows]
    # Ensure all categories appear even if count is zero
    present = {c.category for c in tickets_by_category}
    for cat in TicketCategory:
        if cat.value not in present:
            tickets_by_category.append(CategoryCount(category=cat.value, count=0))

    # ── SLA compliance by priority ────────────────────────────
    sla_compliance: list[SLAComplianceItem] = []
    for priority in TicketPriority:
        p_total = (
            await db.execute(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.priority == priority, Ticket.created_at >= since)
            )
        ).scalar_one()
        p_breached = (
            await db.execute(
                select(func.count())
                .select_from(Ticket)
                .where(
                    Ticket.priority == priority,
                    Ticket.created_at >= since,
                    Ticket.sla_resolve_breach.is_(True),
                )
            )
        ).scalar_one()
        rate = round((1 - p_breached / p_total) * 100, 1) if p_total > 0 else 100.0
        sla_compliance.append(
            SLAComplianceItem(
                priority=priority.value,
                total=p_total,
                breached=p_breached,
                compliance_rate=rate,
            )
        )

    # ── CSAT distribution ─────────────────────────────────────
    csat_rows = (
        await db.execute(
            select(SatisfactionSurvey.rating, func.count().label("cnt"))
            .where(SatisfactionSurvey.created_at >= since)
            .group_by(SatisfactionSurvey.rating)
            .order_by(SatisfactionSurvey.rating)
        )
    ).all()
    counts_by_rating: dict[int, int] = {r.rating: r.cnt for r in csat_rows}
    csat_distribution = [
        CSATDistributionItem(rating=i, count=counts_by_rating.get(i, 0)) for i in range(1, 6)
    ]

    avg_raw = (
        await db.execute(
            select(func.avg(SatisfactionSurvey.rating)).where(
                SatisfactionSurvey.created_at >= since
            )
        )
    ).scalar_one()
    csat_average = round(float(avg_raw), 2) if avg_raw is not None else None

    return ReportData(
        period_days=period,
        total_tickets=total,
        tickets_by_day=tickets_by_day,
        tickets_by_category=tickets_by_category,
        sla_compliance=sla_compliance,
        csat_distribution=csat_distribution,
        csat_average=csat_average,
    )
