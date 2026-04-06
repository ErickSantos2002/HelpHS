"""
Pydantic v2 schemas for Attachment endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import AppBaseModel


class AttachmentResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    uploaded_by: uuid.UUID
    original_name: str
    mime_type: str
    size_bytes: int
    virus_scanned: bool
    virus_clean: bool
    created_at: datetime


class AttachmentListResponse(AppBaseModel):
    items: list[AttachmentResponse]
    total: int


class AttachmentDownloadResponse(AppBaseModel):
    url: str
    expires_in: int = 3600
