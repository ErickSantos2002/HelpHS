"""
Pydantic v2 schemas for Knowledge Base endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import KBArticleStatus, TicketCategory
from app.schemas.base import AppBaseModel


class KBArticleProduct(AppBaseModel):
    """Produto vinculado a um artigo."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class KBArticleCreate(AppBaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    category: TicketCategory = TicketCategory.general
    tags: list[str] = Field(default_factory=list)
    status: KBArticleStatus = KBArticleStatus.draft
    # Lista vazia = artigo vale para todos os produtos
    product_ids: list[uuid.UUID] = Field(default_factory=list)


class KBArticleUpdate(AppBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    category: TicketCategory | None = None
    tags: list[str] | None = None
    status: KBArticleStatus | None = None
    product_ids: list[uuid.UUID] | None = None


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
    products: list[KBArticleProduct] = []
    """Vazio significa que o artigo vale para todos os produtos."""


class KBArticleListResponse(AppBaseModel):
    items: list[KBArticleResponse]
    total: int
    limit: int
    offset: int


class KBFeedbackPayload(AppBaseModel):
    helpful: bool


class KBCommentCreate(AppBaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    parent_id: uuid.UUID | None = None


class KBCommentResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    article_id: uuid.UUID
    author_id: uuid.UUID | None
    author_name: str = ""
    author_role: str = ""
    content: str
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    replies: list["KBCommentResponse"] = []


KBCommentResponse.model_rebuild()


class KBCommentListResponse(AppBaseModel):
    items: list[KBCommentResponse]
    total: int
