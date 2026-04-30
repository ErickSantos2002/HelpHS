"""
Pydantic v2 schemas for Chat endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import AppBaseModel


class ChatSenderInfo(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str


class ChatMessageResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_id: uuid.UUID
    content: str
    is_system: bool
    is_ai: bool
    read_at: datetime | None
    created_at: datetime

    # Flattened sender fields (populated manually)
    sender_name: str = ""
    sender_role: str = ""


class ChatMessageListResponse(AppBaseModel):
    items: list[ChatMessageResponse]
    total: int
    limit: int
    offset: int


class ChatMessageCreate(AppBaseModel):
    content: str = Field(..., min_length=1)


class SuggestReplyResponse(AppBaseModel):
    suggestion: str


class ConversationSummaryResponse(AppBaseModel):
    summary: str


class ImproveMessageRequest(AppBaseModel):
    draft: str = Field(..., min_length=1, max_length=4000)


class ImproveMessageResponse(AppBaseModel):
    improved: str
