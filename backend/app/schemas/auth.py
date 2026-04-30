"""
Pydantic schemas for authentication endpoints.
"""

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import AppBaseModel


class LoginRequest(AppBaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Senha não pode estar vazia")
        return v


class RegisterRequest(AppBaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    lgpd_consent: bool

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("A senha deve conter ao menos uma letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("A senha deve conter ao menos um número")
        return v

    @field_validator("lgpd_consent")
    @classmethod
    def must_accept_lgpd(cls, v: bool) -> bool:
        if not v:
            raise ValueError("O consentimento LGPD é obrigatório para criar uma conta")
        return v


class TokenResponse(AppBaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token TTL in seconds


class RefreshRequest(AppBaseModel):
    refresh_token: str


class AccessTokenResponse(AppBaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
