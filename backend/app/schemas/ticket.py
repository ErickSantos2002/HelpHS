"""
Pydantic v2 schemas for Ticket endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import TicketCategory, TicketPriority, TicketStatus
from app.schemas.base import AppBaseModel


class TicketCreate(AppBaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    priority: TicketPriority = TicketPriority.medium
    category: TicketCategory = TicketCategory.general
    product_id: uuid.UUID | None = None
    equipment_id: uuid.UUID | None = None


class TicketUpdate(AppBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    priority: TicketPriority | None = None
    category: TicketCategory | None = None
    product_id: uuid.UUID | None = None
    equipment_id: uuid.UUID | None = None


class TicketStatusUpdate(AppBaseModel):
    status: TicketStatus
    comment: str | None = Field(default=None, max_length=1000)


class TicketAssign(AppBaseModel):
    assignee_id: uuid.UUID | None = None


class TicketResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    protocol: str
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: TicketCategory
    creator_id: uuid.UUID
    assignee_id: uuid.UUID | None
    product_id: uuid.UUID | None
    equipment_id: uuid.UUID | None
    sla_response_due_at: datetime | None
    sla_resolve_due_at: datetime | None
    sla_response_breach: bool
    sla_resolve_breach: bool
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    ai_classification: str | None = None
    ai_confidence: float | None = None
    ai_summary: str | None = None
    ai_conversation_summary: str | None = None


class TicketListResponse(AppBaseModel):
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


class TicketHistoryResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    user_id: uuid.UUID
    field: str
    old_value: str | None
    new_value: str | None
    comment: str | None
    created_at: datetime


class TicketHistoryListResponse(AppBaseModel):
    items: list[TicketHistoryResponse]
    total: int
    limit: int
    offset: int
