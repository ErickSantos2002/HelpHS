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
