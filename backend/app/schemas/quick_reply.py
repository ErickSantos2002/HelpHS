"""
Schemas das respostas rápidas do chat.
"""

import re
import uuid
from datetime import datetime

from pydantic import ConfigDict, Field, field_validator

from app.schemas.base import AppBaseModel

_SHORTCUT_RE = re.compile(r"^[a-z0-9_-]+$")
_SHORTCUT_ERRO = (
    "O atalho deve ter apenas letras minúsculas, números, hífen ou underline, sem espaços."
)


def _normalize_shortcut(value: str) -> str:
    """Remove a barra inicial e padroniza em minúsculas."""
    normalized = value.strip().lstrip("/").lower()
    if not _SHORTCUT_RE.match(normalized):
        raise ValueError(_SHORTCUT_ERRO)
    return normalized


class QuickReplyCreate(AppBaseModel):
    shortcut: str = Field(..., min_length=2, max_length=50)
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1, max_length=4000)
    is_active: bool = True

    @field_validator("shortcut")
    @classmethod
    def shortcut_format(cls, v: str) -> str:
        return _normalize_shortcut(v)


class QuickReplyUpdate(AppBaseModel):
    shortcut: str | None = Field(default=None, min_length=2, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    is_active: bool | None = None

    @field_validator("shortcut")
    @classmethod
    def shortcut_format(cls, v: str | None) -> str | None:
        return _normalize_shortcut(v) if v is not None else None


class QuickReplyResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shortcut: str
    title: str
    content: str
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class QuickReplyListResponse(AppBaseModel):
    items: list[QuickReplyResponse]
    total: int
