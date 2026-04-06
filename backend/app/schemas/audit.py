"""
Pydantic v2 schemas for Audit Log endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.models.models import AuditAction
from app.schemas.base import AppBaseModel


class AuditLogResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    action: AuditAction
    entity_type: str
    entity_id: uuid.UUID | None
    old_data: dict | None
    new_data: dict | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogListResponse(AppBaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int
