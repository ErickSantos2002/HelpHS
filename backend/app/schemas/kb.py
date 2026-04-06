"""
Pydantic v2 schemas for Knowledge Base endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import KBArticleStatus, TicketCategory
from app.schemas.base import AppBaseModel


class KBArticleCreate(AppBaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    category: TicketCategory = TicketCategory.general
    tags: list[str] = Field(default_factory=list)
    status: KBArticleStatus = KBArticleStatus.draft


class KBArticleUpdate(AppBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    category: TicketCategory | None = None
    tags: list[str] | None = None
    status: KBArticleStatus | None = None


class KBArticleResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    slug: str
    category: TicketCategory
    tags: list[str]
    status: KBArticleStatus
    author_id: uuid.UUID
    author_name: str = ""
    view_count: int
    helpful: int
    not_helpful: int
    created_at: datetime
    updated_at: datetime


class KBArticleListResponse(AppBaseModel):
    items: list[KBArticleResponse]
    total: int
    limit: int
    offset: int


class KBFeedbackPayload(AppBaseModel):
    helpful: bool
