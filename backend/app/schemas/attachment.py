"""
Pydantic v2 schemas for Attachment endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.models.models import UserRole
from app.schemas.base import AppBaseModel


class AttachmentResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    uploaded_by: uuid.UUID
    # Preenchidos pelo router com o cadastro de quem enviou, lido na hora —
    # não são colunas do anexo.
    uploaded_by_name: str | None = None
    uploaded_by_role: UserRole | None = None
    original_name: str
    mime_type: str
    size_bytes: int
    virus_scanned: bool
    virus_clean: bool
    created_at: datetime


class AttachmentListResponse(AppBaseModel):
    items: list[AttachmentResponse]
    total: int


class AttachmentArchiveUnverified(AppBaseModel):
    id: uuid.UUID
    original_name: str


class AttachmentArchiveResponse(AppBaseModel):
    """O link do ZIP e o que a tela precisa avisar ANTES de baixar.

    `nao_verificados` sai da mesma lista congelada no token: o que foi avisado
    é exatamente o que vai no ZIP.
    """

    url: str
    expires_in: int
    total: int
    nao_verificados: list[AttachmentArchiveUnverified]


class AttachmentDownloadResponse(AppBaseModel):
    url: str
    expires_in: int = 3600
