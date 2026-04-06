"""
Pydantic v2 schemas for Notification endpoints.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import ConfigDict

from app.models.models import NotificationType
from app.schemas.base import AppBaseModel


class NotificationResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: NotificationType
    title: str
    message: str
    data: dict[str, Any] | None
    read: bool
    read_at: datetime | None
    email_sent: bool
    created_at: datetime


class NotificationListResponse(AppBaseModel):
    items: list[NotificationResponse]
    total: int
    unread: int
    limit: int
    offset: int
