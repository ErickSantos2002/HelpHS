"""
Pydantic schemas for authentication endpoints.
"""

from pydantic import EmailStr, field_validator

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
