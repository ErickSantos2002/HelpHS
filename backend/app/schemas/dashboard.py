"""
Schemas for dashboard statistics endpoint.
"""

from pydantic import ConfigDict

from app.schemas.base import AppBaseModel


class TicketStats(AppBaseModel):
    total: int
    open: int
    in_progress: int
    awaiting: int
    resolved: int
    closed: int
    cancelled: int
    by_priority_critical: int
    by_priority_high: int
    by_priority_medium: int
    by_priority_low: int


class SurveyStats(AppBaseModel):
    total: int
    average_rating: float | None


class SlaStats(AppBaseModel):
    response_breached: int
    resolve_breached: int


class DashboardStats(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    tickets: TicketStats
    surveys: SurveyStats
    sla: SlaStats


# ── Report schemas ────────────────────────────────────────────


class DailyCount(AppBaseModel):
    date: str  # YYYY-MM-DD
    count: int


class CategoryCount(AppBaseModel):
    category: str
    count: int


class SLAComplianceItem(AppBaseModel):
    priority: str
    total: int
    breached: int
    compliance_rate: float  # 0–100


class CSATDistributionItem(AppBaseModel):
    rating: int  # 1–5
    count: int


class AvgResolutionItem(AppBaseModel):
    priority: str
    avg_hours: float | None


class CsatDailyItem(AppBaseModel):
    date: str        # YYYY-MM-DD
    avg_rating: float | None
    count: int


class WeekdayCount(AppBaseModel):
    weekday: int   # 1 = Segunda … 7 = Domingo (ISO)
    count: int


class AvgFirstResponseItem(AppBaseModel):
    priority: str
    avg_hours: float | None


class ProductCount(AppBaseModel):
    product_name: str
    count: int


class HourlyCount(AppBaseModel):
    hour: int   # 0–23
    count: int


class TechnicianDistItem(AppBaseModel):
    technician_name: str
    total: int
    resolved: int
    open_count: int


class OldestTicketItem(AppBaseModel):
    ticket_id: str
    protocol: str
    title: str
    priority: str
    category: str
    status: str
    age_hours: float
    sla_breached: bool
    assignee_name: str | None


class ReportComparison(AppBaseModel):
    total_tickets: int
    csat_average: float | None
    sla_compliance: list[SLAComplianceItem]


class ReportData(AppBaseModel):
    period_days: int
    total_tickets: int
    tickets_by_day: list[DailyCount]
    tickets_by_category: list[CategoryCount]
    sla_compliance: list[SLAComplianceItem]
    csat_distribution: list[CSATDistributionItem]
    csat_average: float | None
    avg_resolution_by_priority: list[AvgResolutionItem] = []
    avg_first_response_by_priority: list[AvgFirstResponseItem] = []
    csat_by_day: list[CsatDailyItem] = []
    tickets_by_product: list[ProductCount] = []
    tickets_by_weekday: list[WeekdayCount] = []
    tickets_by_hour: list[HourlyCount] = []
    oldest_open_tickets: list[OldestTicketItem] = []
    technicians_dist: list[TechnicianDistItem] = []
    reopened_count: int = 0
    reopen_rate: float = 0.0
    comparison: ReportComparison | None = None


# ── Technician report schemas ─────────────────────────────────


class TechnicianSummary(AppBaseModel):
    technician_id: str
    technician_name: str
    total_assigned: int
    resolved: int
    open_count: int
    sla_breached: int
    sla_compliance_rate: float  # 0–100
    avg_resolution_hours: float | None
    csat_average: float | None
    csat_count: int


class TechnicianListReport(AppBaseModel):
    period_days: int
    technicians: list[TechnicianSummary]


class TechnicianDetailReport(AppBaseModel):
    period_days: int
    technician_id: str
    technician_name: str
    total_assigned: int
    resolved: int
    in_progress: int
    open_count: int
    sla_breached: int
    sla_compliance_rate: float
    avg_resolution_hours: float | None
    csat_average: float | None
    csat_count: int
    tickets_by_day: list[DailyCount]
