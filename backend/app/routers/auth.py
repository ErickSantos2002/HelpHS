"""
Endpoints de autenticação: login, refresh, logout.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    bearer_scheme,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    delete_refresh_token,
    get_current_user,
    get_stored_refresh_token,
    hash_password,
    store_refresh_token,
    verify_password,
)
from app.models.models import AuditAction, AuditLog, User, UserRole, UserStatus
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()


def _audit(
    db: AsyncSession,
    action: AuditAction,
    user_id,
    request: Request,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type="user",
            entity_id=user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", ""),
        )
    )


# ── POST /auth/register ───────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    now = datetime.now(UTC)
    user = User(
        name=body.name,
        email=body.email,
        password=hash_password(body.password),
        role=UserRole.client,
        status=UserStatus.active,
        phone=body.phone,
        department=body.department,
        lgpd_consent=True,
        lgpd_consent_at=now,
    )
    db.add(user)
    await db.flush()

    _audit(db, AuditAction.create, user.id, request)
    await db.commit()
    await db.refresh(user)

    logger.info(f"New client registered: {user.email}")
    return UserResponse.model_validate(user)


# ── POST /auth/login ──────────────────────────────────────────


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password):
        logger.warning(f"Failed login attempt for email={body.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    access_token = create_access_token(user.id, user.role.value, user.email)
    refresh_token = create_refresh_token(user.id)

    await store_refresh_token(user.id, refresh_token)

    _audit(db, AuditAction.login, user.id, request)
    await db.commit()

    logger.info(f"User logged in: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expires_minutes * 60,
    )


# ── POST /auth/refresh ────────────────────────────────────────


@router.post("/refresh", response_model=AccessTokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise credentials_exc

    if payload.get("type") != "refresh":
        raise credentials_exc

    from uuid import UUID

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise credentials_exc

    stored = await get_stored_refresh_token(user_id)
    if stored != body.refresh_token:
        logger.warning(f"Refresh token mismatch for user_id={user_id}")
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None or user.status != UserStatus.active:
        raise credentials_exc

    new_access_token = create_access_token(user.id, user.role.value, user.email)

    return AccessTokenResponse(
        access_token=new_access_token,
        expires_in=settings.jwt_access_token_expires_minutes * 60,
    )


# ── POST /auth/logout ─────────────────────────────────────────


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    if credentials:
        token = credentials.credentials
        try:
            payload = decode_token(token)
            exp = payload.get("exp", 0)
            now = int(datetime.now(UTC).timestamp())
            ttl = max(exp - now, 1)
            await blacklist_token(token, ttl)
        except JWTError:
            pass

    await delete_refresh_token(current_user.id)

    _audit(db, AuditAction.logout, current_user.id, request)
    await db.commit()

    logger.info(f"User logged out: {current_user.email}")
