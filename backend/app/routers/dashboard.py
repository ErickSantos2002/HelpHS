"""
Dashboard statistics endpoint.

Permissões:
  GET /dashboard/stats          — admin, technician
  GET /dashboard/reports        — admin, technician
  GET /dashboard/reports/export/csv — admin, technician
  GET /dashboard/reports/export/pdf — admin, technician
"""

import csv
import io
import uuid
from datetime import UTC, date as DateType, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import extract, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import authorize, get_current_user
from app.models.models import (
    Product,
    SatisfactionSurvey,
    Ticket,
    TicketCategory,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.schemas.dashboard import (
    AvgFirstResponseItem,
    AvgResolutionItem,
    CategoryCount,
    CsatDailyItem,
    CSATDistributionItem,
    DailyCount,
    DashboardStats,
    HourlyCount,
    OldestTicketItem,
    ProductCount,
    ReportComparison,
    ReportData,
    SLAComplianceItem,
    SlaStats,
    SurveyStats,
    TechnicianDetailReport,
    TechnicianDistItem,
    TechnicianListReport,
    TechnicianSummary,
    TicketStats,
    WeekdayCount,
)

router = APIRouter(tags=["Dashboard"])

_STATS_CACHE_KEY = "dashboard:stats"
_STATS_CACHE_TTL = 60  # seconds


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
) -> DashboardStats:
    # ── Try Redis cache first ─────────────────────────────────
    try:
        redis = await get_redis()
        cached = await redis.get(_STATS_CACHE_KEY)
        if cached:
            return DashboardStats.model_validate_json(cached)
    except Exception:
        pass  # Redis unavailable — fall through to DB

    # ── Ticket counts — single GROUP BY query per dimension ───
    status_rows = (
        await db.execute(select(Ticket.status, func.count().label("cnt")).group_by(Ticket.status))
    ).all()
    by_status: dict[str, int] = {r.status.value: r.cnt for r in status_rows}

    priority_rows = (
        await db.execute(
            select(Ticket.priority, func.count().label("cnt")).group_by(Ticket.priority)
        )
    ).all()
    by_priority: dict[str, int] = {r.priority.value: r.cnt for r in priority_rows}

    total = sum(by_status.values())
    awaiting = by_status.get(TicketStatus.awaiting_client.value, 0) + by_status.get(
        TicketStatus.awaiting_technical.value, 0
    )

    # ── SLA breaches — single query with conditional aggregation
    sla_row = (
        await db.execute(
            select(
                func.count().filter(Ticket.sla_response_breach.is_(True)).label("resp"),
                func.count().filter(Ticket.sla_resolve_breach.is_(True)).label("resolve"),
            ).select_from(Ticket)
        )
    ).one()

    # ── Survey stats — single query ───────────────────────────
    survey_row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.avg(SatisfactionSurvey.rating).label("avg"),
            ).select_from(SatisfactionSurvey)
        )
    ).one()

    avg_rating = round(float(survey_row.avg), 2) if survey_row.avg is not None else None

    result = DashboardStats(
        tickets=TicketStats(
            total=total,
            open=by_status.get(TicketStatus.open.value, 0),
            in_progress=by_status.get(TicketStatus.in_progress.value, 0),
            awaiting=awaiting,
            resolved=by_status.get(TicketStatus.resolved.value, 0),
            closed=by_status.get(TicketStatus.closed.value, 0),
            cancelled=by_status.get(TicketStatus.cancelled.value, 0),
            by_priority_critical=by_priority.get(TicketPriority.critical.value, 0),
            by_priority_high=by_priority.get(TicketPriority.high.value, 0),
            by_priority_medium=by_priority.get(TicketPriority.medium.value, 0),
            by_priority_low=by_priority.get(TicketPriority.low.value, 0),
        ),
        surveys=SurveyStats(total=survey_row.total, average_rating=avg_rating),
        sla=SlaStats(response_breached=sla_row.resp, resolve_breached=sla_row.resolve),
    )

    # ── Populate cache ────────────────────────────────────────
    try:
        redis = await get_redis()
        await redis.setex(_STATS_CACHE_KEY, _STATS_CACHE_TTL, result.model_dump_json())
    except Exception:
        pass

    return result


async def _build_report(
    db: AsyncSession,
    period: int = 30,
    category: TicketCategory | None = None,
    priority: TicketPriority | None = None,
    start_date: DateType | None = None,
    end_date: DateType | None = None,
) -> ReportData:
    """Shared data collection used by JSON, CSV and PDF endpoints."""
    if start_date and end_date:
        since = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=UTC)
        until = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=UTC)
        actual_period = (end_date - start_date).days + 1
        date_cond = [Ticket.created_at >= since, Ticket.created_at <= until]
    else:
        since = datetime.now(UTC) - timedelta(days=period)
        until = datetime.now(UTC)
        actual_period = period
        date_cond = [Ticket.created_at >= since]

    extra: list = []
    if category:
        extra.append(Ticket.category == category)
    if priority:
        extra.append(Ticket.priority == priority)

    base = [*date_cond, *extra]

    total = (
        await db.execute(select(func.count()).select_from(Ticket).where(*base))
    ).scalar_one()

    rows = (
        await db.execute(
            select(
                func.date_trunc(text("'day'"), Ticket.created_at).label("day"),
                func.count().label("cnt"),
            )
            .where(*base)
            .group_by(func.date_trunc(text("'day'"), Ticket.created_at))
            .order_by(func.date_trunc(text("'day'"), Ticket.created_at))
        )
    ).all()
    counts_by_day: dict[str, int] = {r.day.strftime("%Y-%m-%d"): r.cnt for r in rows}
    tickets_by_day = [
        DailyCount(
            date=(since + timedelta(days=i)).strftime("%Y-%m-%d"),
            count=counts_by_day.get((since + timedelta(days=i)).strftime("%Y-%m-%d"), 0),
        )
        for i in range(actual_period + 1)
    ]

    cat_rows = (
        await db.execute(
            select(Ticket.category, func.count().label("cnt"))
            .where(*base)
            .group_by(Ticket.category)
            .order_by(func.count().desc())
        )
    ).all()
    tickets_by_category = [CategoryCount(category=r.category.value, count=r.cnt) for r in cat_rows]
    present = {c.category for c in tickets_by_category}
    for cat in TicketCategory:
        if cat.value not in present:
            tickets_by_category.append(CategoryCount(category=cat.value, count=0))

    sla_rows = (
        await db.execute(
            select(
                Ticket.priority,
                func.count().label("total"),
                func.count().filter(Ticket.sla_resolve_breach.is_(True)).label("breached"),
            )
            .where(*base)
            .group_by(Ticket.priority)
        )
    ).all()
    sla_by_priority: dict[str, tuple[int, int]] = {
        r.priority.value: (r.total, r.breached) for r in sla_rows
    }
    sla_compliance: list[SLAComplianceItem] = []
    priorities_iter = [priority] if priority else list(TicketPriority)
    for prio in priorities_iter:
        p_total, p_breached = sla_by_priority.get(prio.value, (0, 0))
        rate = round((1 - p_breached / p_total) * 100, 1) if p_total > 0 else 100.0
        sla_compliance.append(
            SLAComplianceItem(
                priority=prio.value,
                total=p_total,
                breached=p_breached,
                compliance_rate=rate,
            )
        )

    # CSAT — join with Ticket when category/priority filter is active
    csat_date_cond = (
        [SatisfactionSurvey.created_at >= since, SatisfactionSurvey.created_at <= until]
        if (start_date and end_date)
        else [SatisfactionSurvey.created_at >= since]
    )
    if extra:
        ticket_subq = select(Ticket.id).where(*date_cond, *extra).scalar_subquery()
        csat_cond = [*csat_date_cond, SatisfactionSurvey.ticket_id.in_(ticket_subq)]
    else:
        csat_cond = csat_date_cond

    csat_rows = (
        await db.execute(
            select(SatisfactionSurvey.rating, func.count().label("cnt"))
            .where(*csat_cond)
            .group_by(SatisfactionSurvey.rating)
            .order_by(SatisfactionSurvey.rating)
        )
    ).all()
    counts_by_rating: dict[int, int] = {r.rating: r.cnt for r in csat_rows}
    csat_distribution = [
        CSATDistributionItem(rating=i, count=counts_by_rating.get(i, 0)) for i in range(1, 6)
    ]

    avg_raw = (
        await db.execute(select(func.avg(SatisfactionSurvey.rating)).where(*csat_cond))
    ).scalar_one()
    csat_average = round(float(avg_raw), 2) if avg_raw is not None else None

    # ── Tempo médio de resolução por prioridade ───────────────
    resolution_rows = (
        await db.execute(
            select(
                Ticket.priority,
                func.avg(
                    extract("epoch", Ticket.closed_at - Ticket.created_at) / 3600
                ).label("avg_hours"),
            )
            .where(
                *base,
                Ticket.closed_at.is_not(None),
                Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed]),
            )
            .group_by(Ticket.priority)
        )
    ).all()
    resolution_map: dict[str, float | None] = {
        r.priority.value: round(float(r.avg_hours), 1) if r.avg_hours else None
        for r in resolution_rows
    }
    avg_resolution_by_priority = [
        AvgResolutionItem(
            priority=prio.value,
            avg_hours=resolution_map.get(prio.value),
        )
        for prio in ([priority] if priority else list(TicketPriority))
    ]

    # ── CSAT diário ───────────────────────────────────────────
    csat_day_rows = (
        await db.execute(
            select(
                func.date_trunc(text("'day'"), SatisfactionSurvey.created_at).label("day"),
                func.avg(SatisfactionSurvey.rating).label("avg_rating"),
                func.count().label("cnt"),
            )
            .where(*csat_cond)
            .group_by(func.date_trunc(text("'day'"), SatisfactionSurvey.created_at))
            .order_by(func.date_trunc(text("'day'"), SatisfactionSurvey.created_at))
        )
    ).all()
    csat_day_map: dict[str, tuple[float, int]] = {
        r.day.strftime("%Y-%m-%d"): (round(float(r.avg_rating), 2), r.cnt)
        for r in csat_day_rows
    }
    csat_by_day = [
        CsatDailyItem(
            date=(since + timedelta(days=i)).strftime("%Y-%m-%d"),
            avg_rating=csat_day_map[(since + timedelta(days=i)).strftime("%Y-%m-%d")][0]
            if (since + timedelta(days=i)).strftime("%Y-%m-%d") in csat_day_map else None,
            count=csat_day_map[(since + timedelta(days=i)).strftime("%Y-%m-%d")][1]
            if (since + timedelta(days=i)).strftime("%Y-%m-%d") in csat_day_map else 0,
        )
        for i in range(actual_period + 1)
    ]

    # ── Distribuição por dia da semana (ISO: 1=Seg … 7=Dom) ──
    weekday_rows = (
        await db.execute(
            select(
                extract("isodow", Ticket.created_at).label("dow"),
                func.count().label("cnt"),
            )
            .where(*base)
            .group_by(extract("isodow", Ticket.created_at))
            .order_by(extract("isodow", Ticket.created_at))
        )
    ).all()
    weekday_map: dict[int, int] = {int(r.dow): r.cnt for r in weekday_rows}
    tickets_by_weekday = [
        WeekdayCount(weekday=d, count=weekday_map.get(d, 0)) for d in range(1, 8)
    ]

    # ── Tempo médio de primeira resposta por prioridade ──────────
    first_resp_rows = (
        await db.execute(
            select(
                Ticket.priority,
                func.avg(
                    extract("epoch", Ticket.sla_first_response - Ticket.created_at) / 3600
                ).label("avg_hours"),
            )
            .where(*base, Ticket.sla_first_response.is_not(None))
            .group_by(Ticket.priority)
        )
    ).all()
    first_resp_map: dict[str, float | None] = {
        r.priority.value: round(float(r.avg_hours), 1) if r.avg_hours else None
        for r in first_resp_rows
    }
    avg_first_response_by_priority = [
        AvgFirstResponseItem(priority=prio.value, avg_hours=first_resp_map.get(prio.value))
        for prio in ([priority] if priority else list(TicketPriority))
    ]

    # ── Tickets por produto ───────────────────────────────────────
    product_rows = (
        await db.execute(
            select(Product.name.label("product_name"), func.count().label("cnt"))
            .join(Product, Ticket.product_id == Product.id)
            .where(*base)
            .group_by(Product.name)
            .order_by(func.count().desc())
            .limit(10)
        )
    ).all()
    tickets_by_product = [
        ProductCount(product_name=r.product_name, count=r.cnt) for r in product_rows
    ]

    # ── Distribuição por hora do dia ─────────────────────────────
    hour_rows = (
        await db.execute(
            select(
                extract("hour", Ticket.created_at).label("hr"),
                func.count().label("cnt"),
            )
            .where(*base)
            .group_by(extract("hour", Ticket.created_at))
            .order_by(extract("hour", Ticket.created_at))
        )
    ).all()
    hour_map: dict[int, int] = {int(r.hr): r.cnt for r in hour_rows}
    tickets_by_hour = [HourlyCount(hour=h, count=hour_map.get(h, 0)) for h in range(24)]

    # ── Tickets em aberto há mais tempo ──────────────────────────
    open_statuses = [
        TicketStatus.open,
        TicketStatus.in_progress,
        TicketStatus.awaiting_client,
        TicketStatus.awaiting_technical,
    ]
    oldest_rows = (
        await db.execute(
            select(
                Ticket.id,
                Ticket.protocol,
                Ticket.title,
                Ticket.priority,
                Ticket.category,
                Ticket.status,
                Ticket.created_at,
                Ticket.sla_resolve_breach,
                User.name.label("assignee_name"),
            )
            .outerjoin(User, Ticket.assignee_id == User.id)
            .where(Ticket.status.in_(open_statuses), *extra)
            .order_by(Ticket.created_at.asc())
            .limit(10)
        )
    ).all()
    now = datetime.now(UTC)
    oldest_open_tickets = [
        OldestTicketItem(
            ticket_id=str(r.id),
            protocol=r.protocol,
            title=r.title,
            priority=r.priority.value,
            category=r.category.value,
            status=r.status.value,
            age_hours=round((now - r.created_at).total_seconds() / 3600, 1),
            sla_breached=bool(r.sla_resolve_breach),
            assignee_name=r.assignee_name,
        )
        for r in oldest_rows
    ]

    # ── Distribuição de tickets por técnico ──────────────────────
    resolved_statuses = [TicketStatus.resolved, TicketStatus.closed]
    active_statuses = [
        TicketStatus.open,
        TicketStatus.in_progress,
        TicketStatus.awaiting_client,
        TicketStatus.awaiting_technical,
    ]
    tech_dist_rows = (
        await db.execute(
            select(
                User.name.label("tech_name"),
                func.count().label("total"),
                func.count().filter(Ticket.status.in_(resolved_statuses)).label("resolved"),
                func.count().filter(Ticket.status.in_(active_statuses)).label("open_count"),
            )
            .join(User, Ticket.assignee_id == User.id)
            .where(*base)
            .group_by(User.name)
            .order_by(func.count().desc())
            .limit(15)
        )
    ).all()
    technicians_dist = [
        TechnicianDistItem(
            technician_name=r.tech_name,
            total=r.total,
            resolved=r.resolved,
            open_count=r.open_count,
        )
        for r in tech_dist_rows
    ]

    # ── Taxa de reabertura ────────────────────────────────────────
    reopen_date_cond = (
        [TicketHistory.created_at >= since, TicketHistory.created_at <= until]
        if (start_date and end_date)
        else [TicketHistory.created_at >= since]
    )
    reopen_q = (
        select(func.count(func.distinct(TicketHistory.ticket_id)))
        .join(Ticket, TicketHistory.ticket_id == Ticket.id)
        .where(
            TicketHistory.field == "status",
            TicketHistory.old_value.in_(["resolved", "closed"]),
            TicketHistory.new_value.in_(["open", "in_progress"]),
            *reopen_date_cond,
            *extra,
        )
    )
    reopened_count: int = (await db.execute(reopen_q)).scalar_one() or 0
    reopen_rate = round(reopened_count / total * 100, 1) if total > 0 else 0.0

    comparison = await _build_comparison(db, since, actual_period, category, priority)

    return ReportData(
        period_days=actual_period,
        total_tickets=total,
        tickets_by_day=tickets_by_day,
        tickets_by_category=tickets_by_category,
        sla_compliance=sla_compliance,
        csat_distribution=csat_distribution,
        csat_average=csat_average,
        avg_resolution_by_priority=avg_resolution_by_priority,
        avg_first_response_by_priority=avg_first_response_by_priority,
        csat_by_day=csat_by_day,
        tickets_by_product=tickets_by_product,
        tickets_by_weekday=tickets_by_weekday,
        tickets_by_hour=tickets_by_hour,
        oldest_open_tickets=oldest_open_tickets,
        technicians_dist=technicians_dist,
        reopened_count=reopened_count,
        reopen_rate=reopen_rate,
        comparison=comparison,
    )


async def _build_comparison(
    db: AsyncSession,
    current_since: datetime,
    period: int,
    category: TicketCategory | None,
    priority: TicketPriority | None,
) -> ReportComparison:
    """Calcula as mesmas métricas para o período imediatamente anterior."""
    prev_until = current_since
    prev_since = current_since - timedelta(days=period)

    prev_date = [Ticket.created_at >= prev_since, Ticket.created_at < prev_until]
    prev_extra: list = []
    if category:
        prev_extra.append(Ticket.category == category)
    if priority:
        prev_extra.append(Ticket.priority == priority)
    prev_base = [*prev_date, *prev_extra]

    prev_total = (
        await db.execute(select(func.count()).select_from(Ticket).where(*prev_base))
    ).scalar_one()

    prev_sla_rows = (
        await db.execute(
            select(
                Ticket.priority,
                func.count().label("total"),
                func.count().filter(Ticket.sla_resolve_breach.is_(True)).label("breached"),
            )
            .where(*prev_base)
            .group_by(Ticket.priority)
        )
    ).all()
    prev_sla_map: dict[str, tuple[int, int]] = {
        r.priority.value: (r.total, r.breached) for r in prev_sla_rows
    }
    prev_sla: list[SLAComplianceItem] = []
    for prio in ([priority] if priority else list(TicketPriority)):
        t, b = prev_sla_map.get(prio.value, (0, 0))
        rate = round((1 - b / t) * 100, 1) if t > 0 else 100.0
        prev_sla.append(SLAComplianceItem(priority=prio.value, total=t, breached=b, compliance_rate=rate))

    prev_csat_date = [SatisfactionSurvey.created_at >= prev_since, SatisfactionSurvey.created_at < prev_until]
    if prev_extra:
        ticket_subq = select(Ticket.id).where(*prev_date, *prev_extra).scalar_subquery()
        prev_csat_cond = [*prev_csat_date, SatisfactionSurvey.ticket_id.in_(ticket_subq)]
    else:
        prev_csat_cond = prev_csat_date

    prev_avg_raw = (
        await db.execute(select(func.avg(SatisfactionSurvey.rating)).where(*prev_csat_cond))
    ).scalar_one()
    prev_csat = round(float(prev_avg_raw), 2) if prev_avg_raw is not None else None

    return ReportComparison(
        total_tickets=prev_total,
        csat_average=prev_csat,
        sla_compliance=prev_sla,
    )


@router.get("/dashboard/reports", response_model=ReportData)
async def get_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    period: Annotated[int, Query(ge=1, le=365)] = 30,
    category: TicketCategory | None = Query(default=None),
    priority: TicketPriority | None = Query(default=None),
    start_date: DateType | None = Query(default=None),
    end_date: DateType | None = Query(default=None),
) -> ReportData:
    return await _build_report(db, period, category, priority, start_date, end_date)


@router.get("/dashboard/reports/export/csv")
async def export_reports_csv(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    period: Annotated[int, Query(ge=1, le=365)] = 30,
    category: TicketCategory | None = Query(default=None),
    priority: TicketPriority | None = Query(default=None),
    start_date: DateType | None = Query(default=None),
    end_date: DateType | None = Query(default=None),
) -> StreamingResponse:
    data = await _build_report(db, period, category, priority, start_date, end_date)
    buf = io.StringIO()
    writer = csv.writer(buf)

    period_label = (
        f"{start_date} a {end_date}"
        if (start_date and end_date)
        else f"últimos {data.period_days} dias"
    )
    filter_parts = []
    if category:
        filter_parts.append(f"Categoria: {category.value}")
    if priority:
        filter_parts.append(f"Prioridade: {priority.value}")
    filter_label = " | ".join(filter_parts) if filter_parts else "Todos"

    writer.writerow([f"Relatório HelpHS — {period_label}"])
    writer.writerow([f"Filtros: {filter_label}"])
    writer.writerow([f"Gerado em: {datetime.now(UTC).strftime('%d/%m/%Y %H:%M')} UTC"])
    writer.writerow([])

    writer.writerow(["TICKETS POR DIA"])
    writer.writerow(["Data", "Quantidade"])
    for d in data.tickets_by_day:
        writer.writerow([d.date, d.count])
    writer.writerow([])

    writer.writerow(["TICKETS POR CATEGORIA"])
    writer.writerow(["Categoria", "Quantidade"])
    for c in sorted(data.tickets_by_category, key=lambda x: x.count, reverse=True):
        if c.count > 0:
            writer.writerow([c.category, c.count])
    writer.writerow([])

    writer.writerow(["CONFORMIDADE SLA POR PRIORIDADE"])
    writer.writerow(["Prioridade", "Total", "Violações", "Conformidade (%)"])
    for s in data.sla_compliance:
        writer.writerow([s.priority, s.total, s.breached, s.compliance_rate])
    writer.writerow([])

    writer.writerow(["DISTRIBUIÇÃO CSAT"])
    writer.writerow(["Nota", "Avaliações"])
    for c in data.csat_distribution:
        writer.writerow([c.rating, c.count])
    if data.csat_average is not None:
        writer.writerow(["Média", data.csat_average])

    buf.seek(0)
    suffix = f"_{category.value}" if category else ""
    suffix += f"_{priority.value}" if priority else ""
    filename = f"relatorio_helphs_{datetime.now(UTC).strftime('%Y%m%d')}_{data.period_days}d{suffix}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard/reports/export/pdf")
async def export_reports_pdf(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    period: Annotated[int, Query(ge=1, le=365)] = 30,
    category: TicketCategory | None = Query(default=None),
    priority: TicketPriority | None = Query(default=None),
    start_date: DateType | None = Query(default=None),
    end_date: DateType | None = Query(default=None),
) -> StreamingResponse:
    data = await _build_report(db, period, category, priority, start_date, end_date)
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm)

    story = []
    title_style = styles["Title"]
    h2_style = styles["Heading2"]
    normal_style = styles["Normal"]

    period_label = (
        f"{start_date} a {end_date}"
        if (start_date and end_date)
        else f"últimos {data.period_days} dias"
    )
    filter_parts = []
    if category:
        filter_parts.append(f"Categoria: {category.value}")
    if priority:
        filter_parts.append(f"Prioridade: {priority.value}")
    filter_str = " · ".join(filter_parts)

    story.append(Paragraph("Relatório HelpHS", title_style))
    story.append(
        Paragraph(
            f"Período: {period_label}"
            + (f" &nbsp;·&nbsp; {filter_str}" if filter_str else "")
            + f" &nbsp;·&nbsp; Gerado em {datetime.now(UTC).strftime('%d/%m/%Y %H:%M')} UTC",
            normal_style,
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    def _table(header: list[str], rows: list[list]) -> Table:
        table_data = [header] + rows
        t = Table(table_data, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f1f5f9")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return t

    # Summary
    story.append(Paragraph("Resumo", h2_style))
    story.append(
        _table(
            ["Métrica", "Valor"],
            [
                ["Total de tickets no período", str(data.total_tickets)],
                ["Média CSAT", str(data.csat_average) if data.csat_average else "—"],
            ],
        )
    )
    story.append(Spacer(1, 0.5 * cm))

    # Tickets por categoria
    story.append(Paragraph("Tickets por Categoria", h2_style))
    cat_rows = [
        [c.category.capitalize(), str(c.count)]
        for c in sorted(data.tickets_by_category, key=lambda x: x.count, reverse=True)
        if c.count > 0
    ]
    if cat_rows:
        story.append(_table(["Categoria", "Quantidade"], cat_rows))
    story.append(Spacer(1, 0.5 * cm))

    # SLA compliance
    story.append(Paragraph("Conformidade SLA por Prioridade", h2_style))
    story.append(
        _table(
            ["Prioridade", "Total", "Violações", "Conformidade"],
            [
                [s.priority.capitalize(), str(s.total), str(s.breached), f"{s.compliance_rate}%"]
                for s in data.sla_compliance
            ],
        )
    )
    story.append(Spacer(1, 0.5 * cm))

    # CSAT
    story.append(Paragraph("Distribuição CSAT", h2_style))
    story.append(
        _table(
            ["Nota", "Avaliações"],
            [[f"{'★' * c.rating}", str(c.count)] for c in data.csat_distribution],
        )
    )

    doc.build(story)
    buf.seek(0)
    suffix = f"_{category.value}" if category else ""
    suffix += f"_{priority.value}" if priority else ""
    filename = f"relatorio_helphs_{datetime.now(UTC).strftime('%Y%m%d')}_{data.period_days}d{suffix}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Technician reports ────────────────────────────────────────


async def _technician_summary(
    db: AsyncSession, tech_id: uuid.UUID, tech_name: str, since: datetime
) -> TechnicianSummary:
    """Compute aggregated metrics for a single technician."""
    ticket_row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count()
                .filter(Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed]))
                .label("resolved"),
                func.count()
                .filter(
                    Ticket.status.in_(
                        [
                            TicketStatus.open,
                            TicketStatus.in_progress,
                            TicketStatus.awaiting_client,
                            TicketStatus.awaiting_technical,
                        ]
                    )
                )
                .label("open_count"),
                func.count().filter(Ticket.sla_resolve_breach.is_(True)).label("breached"),
                func.avg(extract("epoch", Ticket.closed_at - Ticket.created_at) / 3600)
                .filter(Ticket.closed_at.is_not(None))
                .label("avg_hours"),
            ).where(Ticket.assignee_id == tech_id, Ticket.created_at >= since)
        )
    ).one()

    csat_row = (
        await db.execute(
            select(
                func.avg(SatisfactionSurvey.rating).label("avg"),
                func.count(SatisfactionSurvey.id).label("cnt"),
            )
            .join(Ticket, SatisfactionSurvey.ticket_id == Ticket.id)
            .where(Ticket.assignee_id == tech_id, SatisfactionSurvey.created_at >= since)
        )
    ).one()

    total = ticket_row.total or 0
    breached = ticket_row.breached or 0
    compliance = round((1 - breached / total) * 100, 1) if total > 0 else 100.0

    return TechnicianSummary(
        technician_id=str(tech_id),
        technician_name=tech_name,
        total_assigned=total,
        resolved=ticket_row.resolved or 0,
        open_count=ticket_row.open_count or 0,
        sla_breached=breached,
        sla_compliance_rate=compliance,
        avg_resolution_hours=(
            round(float(ticket_row.avg_hours), 1) if ticket_row.avg_hours else None
        ),
        csat_average=round(float(csat_row.avg), 2) if csat_row.avg else None,
        csat_count=csat_row.cnt or 0,
    )


@router.get("/dashboard/reports/technicians", response_model=TechnicianListReport)
async def get_technician_list_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin))],
    period: Annotated[int, Query(ge=7, le=365)] = 30,
) -> TechnicianListReport:
    """Admin-only: returns summary metrics for every active technician."""
    since = datetime.now(UTC) - timedelta(days=period)

    tech_rows = (
        await db.execute(
            select(User.id, User.name)
            .where(User.role == UserRole.technician, User.status == UserStatus.active)
            .order_by(User.name)
        )
    ).all()

    summaries = [await _technician_summary(db, row.id, row.name, since) for row in tech_rows]

    return TechnicianListReport(period_days=period, technicians=summaries)


@router.get("/dashboard/reports/technician", response_model=TechnicianDetailReport)
async def get_technician_detail_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[User, Depends(get_current_user)],
    period: Annotated[int, Query(ge=7, le=365)] = 30,
    technician_id: uuid.UUID | None = Query(default=None),
) -> TechnicianDetailReport:
    """
    Detailed metrics for a single technician.
    - Admin: can request any technician via ?technician_id=...
    - Technician: always sees own data (technician_id param ignored)
    """
    is_admin = actor.role == UserRole.admin
    is_tech = actor.role == UserRole.technician

    if not is_admin and not is_tech:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if is_tech:
        tech_id = actor.id
        tech_name = actor.name
    else:
        if technician_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="technician_id is required for admin",
            )
        tech_row = (
            await db.execute(
                select(User).where(User.id == technician_id, User.role == UserRole.technician)
            )
        ).scalar_one_or_none()
        if tech_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Technician not found"
            )
        tech_id = tech_row.id
        tech_name = tech_row.name

    since = datetime.now(UTC) - timedelta(days=period)

    summary = await _technician_summary(db, tech_id, tech_name, since)

    # In-progress count (not in resolved/closed/open)
    in_progress_row = (
        await db.execute(
            select(func.count()).where(
                Ticket.assignee_id == tech_id,
                Ticket.created_at >= since,
                Ticket.status == TicketStatus.in_progress,
            )
        )
    ).scalar_one()

    # Daily ticket volume for this technician
    day_rows = (
        await db.execute(
            select(
                func.date_trunc(text("'day'"), Ticket.created_at).label("day"),
                func.count().label("cnt"),
            )
            .where(Ticket.assignee_id == tech_id, Ticket.created_at >= since)
            .group_by(func.date_trunc(text("'day'"), Ticket.created_at))
            .order_by(func.date_trunc(text("'day'"), Ticket.created_at))
        )
    ).all()
    counts_by_day: dict[str, int] = {r.day.strftime("%Y-%m-%d"): r.cnt for r in day_rows}
    tickets_by_day = [
        DailyCount(
            date=(since + timedelta(days=i)).strftime("%Y-%m-%d"),
            count=counts_by_day.get((since + timedelta(days=i)).strftime("%Y-%m-%d"), 0),
        )
        for i in range(period + 1)
    ]

    return TechnicianDetailReport(
        period_days=period,
        technician_id=str(tech_id),
        technician_name=tech_name,
        total_assigned=summary.total_assigned,
        resolved=summary.resolved,
        in_progress=in_progress_row,
        open_count=summary.open_count,
        sla_breached=summary.sla_breached,
        sla_compliance_rate=summary.sla_compliance_rate,
        avg_resolution_hours=summary.avg_resolution_hours,
        csat_average=summary.csat_average,
        csat_count=summary.csat_count,
        tickets_by_day=tickets_by_day,
    )
