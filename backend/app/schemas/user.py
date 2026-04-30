"""
Pydantic v2 schemas for User endpoints.
"""

import uuid
from datetime import datetime

from pydantic import ConfigDict, EmailStr, Field, field_validator

from app.models.models import UserRole, UserStatus
from app.schemas.base import AppBaseModel


class UserCreate(AppBaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.client
    phone: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    lgpd_consent: bool = False

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("A senha deve conter ao menos um número")
        return v


class UserUpdate(AppBaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=500)
    role: UserRole | None = None


class PasswordChange(AppBaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("A senha deve conter ao menos um número")
        return v


class UserStatusUpdate(AppBaseModel):
    status: UserStatus


class LGPDConsentUpdate(AppBaseModel):
    lgpd_consent: bool


class OnboardingUpdate(AppBaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    cnpj: str | None = Field(default=None, max_length=18)
    company_city: str | None = Field(default=None, max_length=100)
    company_state: str | None = Field(default=None, max_length=2)


class UserResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    status: UserStatus
    phone: str | None
    department: str | None
    avatar_url: str | None
    last_login: datetime | None
    lgpd_consent: bool
    lgpd_consent_at: datetime | None
    company_name: str | None
    cnpj: str | None
    company_city: str | None
    company_state: str | None
    onboarding_completed: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(AppBaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int
