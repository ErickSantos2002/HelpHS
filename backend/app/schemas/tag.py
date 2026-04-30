"""
Pydantic v2 schemas for Tag endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import AppBaseModel


class TagCreate(AppBaseModel):
    name: str = Field(..., min_length=1, max_length=50, strip_whitespace=True)
    color: str = Field(default="#6366f1", pattern=r"^#[0-9a-fA-F]{6}$")


class TagUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50, strip_whitespace=True)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class TagResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str
    created_by: uuid.UUID | None
    created_at: datetime


class TagListResponse(AppBaseModel):
    items: list[TagResponse]
    total: int


class TicketTagsUpdate(AppBaseModel):
    tag_ids: list[uuid.UUID]
