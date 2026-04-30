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


class ReportData(AppBaseModel):
    period_days: int
    total_tickets: int
    tickets_by_day: list[DailyCount]
    tickets_by_category: list[CategoryCount]
    sla_compliance: list[SLAComplianceItem]
    csat_distribution: list[CSATDistributionItem]
    csat_average: float | None


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
