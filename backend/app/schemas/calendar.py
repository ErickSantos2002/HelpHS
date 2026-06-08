"""
Pydantic schemas for Calendar endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import CalendarEventType
from app.schemas.base import AppBaseModel


class CalendarEventCreate(AppBaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    event_type: CalendarEventType = CalendarEventType.event
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")
    start_date: datetime
    end_date: datetime


class CalendarEventUpdate(AppBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    event_type: CalendarEventType | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    start_date: datetime | None = None
    end_date: datetime | None = None


class CalendarEventResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    event_type: CalendarEventType
    color: str
    start_date: datetime
    end_date: datetime
    created_by: uuid.UUID | None
    creator_name: str | None = None
    created_at: datetime
    updated_at: datetime


class CalendarEventListResponse(AppBaseModel):
    items: list[CalendarEventResponse]
    total: int
