"""
Pydantic v2 schemas for SLA configuration endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import SLALevel
from app.schemas.base import AppBaseModel


class SLAConfigUpdate(AppBaseModel):
    response_time_hours: int | None = Field(default=None, ge=1, le=9999)
    resolve_time_hours: int | None = Field(default=None, ge=1, le=9999)
    warning_threshold: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None


class SLAConfigResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    level: SLALevel
    response_time_hours: int
    resolve_time_hours: int
    warning_threshold: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
