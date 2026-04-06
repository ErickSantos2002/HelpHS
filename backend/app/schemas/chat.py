"""
Pydantic v2 schemas for Chat endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict

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
    content: str


class SuggestReplyResponse(AppBaseModel):
    suggestion: str


class ConversationSummaryResponse(AppBaseModel):
    summary: str
