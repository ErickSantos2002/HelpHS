"""
Pydantic v2 schemas for CSAT (Customer Satisfaction) Survey endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field, field_validator

from app.schemas.base import AppBaseModel


class SurveyCreate(AppBaseModel):
    rating: int = Field(..., ge=1, le=10, description="Avaliação de 1 (péssimo) a 10 (excelente)")
    # Opcional na API para não invalidar integrações que só enviam a nota do
    # atendimento; o formulário do sistema pede as duas.
    recommend_rating: int | None = Field(
        default=None, ge=1, le=10, description="O quanto recomendaria a empresa, de 1 a 10"
    )
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("rating")
    @classmethod
    def rating_must_be_valid(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("A avaliação deve ser entre 1 e 10")
        return v

    @field_validator("recommend_rating")
    @classmethod
    def recommend_must_be_valid(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 10:
            raise ValueError("A nota de recomendação deve ser entre 1 e 10")
        return v


class SurveyResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    user_id: uuid.UUID
    rating: int
    recommend_rating: int | None = None
    comment: str | None
    created_at: datetime


class SurveyListResponse(AppBaseModel):
    items: list[SurveyResponse]
    total: int
    average_rating: float | None
    # Média só das avaliações que responderam a pergunta — as anteriores à
    # coluna ficam de fora em vez de entrar como zero e puxar o número.
    average_recommend: float | None = None
    limit: int
    offset: int
