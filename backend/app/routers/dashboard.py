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
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
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


async def _build_report(db: AsyncSession, period: int) -> ReportData:
    """Shared data collection used by JSON, CSV and PDF endpoints."""
    since = datetime.now(UTC) - timedelta(days=period)

    total = (
        await db.execute(select(func.count()).select_from(Ticket).where(Ticket.created_at >= since))
    ).scalar_one()

    rows = (
        await db.execute(
            select(
                func.date_trunc(literal("day"), Ticket.created_at).label("day"),
                func.count().label("cnt"),
            )
            .where(Ticket.created_at >= since)
            .group_by(func.date_trunc(literal("day"), Ticket.created_at))
            .order_by(func.date_trunc(literal("day"), Ticket.created_at))
        )
    ).all()
    counts_by_day: dict[str, int] = {r.day.strftime("%Y-%m-%d"): r.cnt for r in rows}
    tickets_by_day = [
        DailyCount(
            date=(since + timedelta(days=i)).strftime("%Y-%m-%d"),
            count=counts_by_day.get((since + timedelta(days=i)).strftime("%Y-%m-%d"), 0),
        )
        for i in range(period + 1)
    ]

    cat_rows = (
        await db.execute(
            select(Ticket.category, func.count().label("cnt"))
            .where(Ticket.created_at >= since)
            .group_by(Ticket.category)
            .order_by(func.count().desc())
        )
    ).all()
    tickets_by_category = [CategoryCount(category=r.category.value, count=r.cnt) for r in cat_rows]
    present = {c.category for c in tickets_by_category}
    for cat in TicketCategory:
        if cat.value not in present:
            tickets_by_category.append(CategoryCount(category=cat.value, count=0))

    # ── SLA compliance — single query with conditional aggregation
    sla_rows = (
        await db.execute(
            select(
                Ticket.priority,
                func.count().label("total"),
                func.count().filter(Ticket.sla_resolve_breach.is_(True)).label("breached"),
            )
            .where(Ticket.created_at >= since)
            .group_by(Ticket.priority)
        )
    ).all()
    sla_by_priority: dict[str, tuple[int, int]] = {
        r.priority.value: (r.total, r.breached) for r in sla_rows
    }
    sla_compliance: list[SLAComplianceItem] = []
    for priority in TicketPriority:
        p_total, p_breached = sla_by_priority.get(priority.value, (0, 0))
        rate = round((1 - p_breached / p_total) * 100, 1) if p_total > 0 else 100.0
        sla_compliance.append(
            SLAComplianceItem(
                priority=priority.value,
                total=p_total,
                breached=p_breached,
                compliance_rate=rate,
            )
        )

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


@router.get("/dashboard/reports", response_model=ReportData)
async def get_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    period: Annotated[int, Query(ge=7, le=365)] = 30,
) -> ReportData:
    return await _build_report(db, period)


@router.get("/dashboard/reports/export/csv")
async def export_reports_csv(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    period: Annotated[int, Query(ge=7, le=365)] = 30,
) -> StreamingResponse:
    data = await _build_report(db, period)
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow([f"Relatório HelpHS — últimos {period} dias"])
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
    filename = f"relatorio_helphs_{datetime.now(UTC).strftime('%Y%m%d')}_{period}d.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard/reports/export/pdf")
async def export_reports_pdf(
    db: Annotated[AsyncSession, Depends(get_db)],
    _actor: Annotated[User, Depends(authorize(UserRole.admin, UserRole.technician))],
    period: Annotated[int, Query(ge=7, le=365)] = 30,
) -> StreamingResponse:
    data = await _build_report(db, period)
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm)

    story = []
    title_style = styles["Title"]
    h2_style = styles["Heading2"]
    normal_style = styles["Normal"]

    story.append(Paragraph("Relatório HelpHS", title_style))
    story.append(
        Paragraph(
            f"Período: últimos {period} dias &nbsp;·&nbsp; "
            f"Gerado em {datetime.now(UTC).strftime('%d/%m/%Y %H:%M')} UTC",
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
    filename = f"relatorio_helphs_{datetime.now(UTC).strftime('%Y%m%d')}_{period}d.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
