"""
Pydantic v2 schemas for CSAT (Customer Satisfaction) Survey endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field, field_validator

from app.schemas.base import AppBaseModel


class SurveyCreate(AppBaseModel):
    rating: int = Field(..., ge=1, le=5, description="Avaliação de 1 (péssimo) a 5 (excelente)")
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("rating")
    @classmethod
    def rating_must_be_valid(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("A avaliação deve ser entre 1 e 5")
        return v


class SurveyResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    user_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime


class SurveyListResponse(AppBaseModel):
    items: list[SurveyResponse]
    total: int
    average_rating: float | None
    limit: int
    offset: int
