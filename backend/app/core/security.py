"""
JWT RS256 token creation, validation, and Redis-based blacklist.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from loguru import logger
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis import get_redis

settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# Redis key prefixes
_BLACKLIST_PREFIX = "token:blacklist:"
_REFRESH_PREFIX = "token:refresh:"


# ── Token creation ────────────────────────────────────────────


def _build_payload(
    sub: str,
    token_type: str,
    expires_delta: timedelta,
    extra: dict | None = None,
) -> dict:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.jwt_issuer,
    }
    if extra:
        payload.update(extra)
    return payload


def create_access_token(user_id: UUID, role: str, email: str) -> str:
    payload = _build_payload(
        sub=str(user_id),
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_access_token_expires_minutes),
        extra={"role": role, "email": email},
    )
    return jwt.encode(payload, settings.get_private_key(), algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID) -> str:
    payload = _build_payload(
        sub=str(user_id),
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_token_expires_days),
    )
    return jwt.encode(payload, settings.get_private_key(), algorithm=settings.jwt_algorithm)


# ── Token validation ──────────────────────────────────────────


def decode_token(token: str) -> dict:
    """Decode and verify signature/expiry. Raises JWTError on failure."""
    return jwt.decode(
        token,
        settings.get_public_key(),
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
    )


async def _is_blacklisted(token: str) -> bool:
    redis = await get_redis()
    return bool(await redis.exists(f"{_BLACKLIST_PREFIX}{token}"))


async def blacklist_token(token: str, expires_in_seconds: int) -> None:
    redis = await get_redis()
    await redis.setex(f"{_BLACKLIST_PREFIX}{token}", expires_in_seconds, "1")


# ── Refresh token store ───────────────────────────────────────


async def store_refresh_token(user_id: UUID, token: str) -> None:
    redis = await get_redis()
    ttl = settings.jwt_refresh_token_expires_days * 86400
    await redis.setex(f"{_REFRESH_PREFIX}{user_id}", ttl, token)


async def get_stored_refresh_token(user_id: UUID) -> str | None:
    redis = await get_redis()
    return await redis.get(f"{_REFRESH_PREFIX}{user_id}")


async def delete_refresh_token(user_id: UUID) -> None:
    redis = await get_redis()
    await redis.delete(f"{_REFRESH_PREFIX}{user_id}")


# ── FastAPI dependency ────────────────────────────────────────


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Validates the Bearer token and returns the User ORM object.
    Raises 401 if token is missing, invalid, expired, or blacklisted.
    """
    from app.models.models import User, UserStatus  # avoid circular import

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise credentials_exc

    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError as exc:
        logger.debug(f"JWT decode error: {exc}")
        raise credentials_exc

    if payload.get("type") != "access":
        raise credentials_exc

    if await _is_blacklisted(token):
        raise credentials_exc

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise credentials_exc

    try:
        uid = UUID(user_id)
    except ValueError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exc
    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


def authorize(*roles):
    """
    Dependency factory for role-based access control.

    Usage::

        @router.get("/admin-only")
        async def admin_endpoint(user=Depends(authorize(UserRole.admin))):
            ...

        @router.get("/staff")
        async def staff_endpoint(user=Depends(authorize(UserRole.admin, UserRole.technician))):
            ...

    Always applied on top of ``get_current_user`` — so the token must be valid
    before the role check runs.
    """

    allowed = frozenset(roles)

    async def _check(user=Depends(get_current_user)):
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return _check


# ── Convenience aliases ───────────────────────────────────────


def require_admin():
    from app.models.models import UserRole

    return authorize(UserRole.admin)


def require_technician_or_admin():
    from app.models.models import UserRole

    return authorize(UserRole.admin, UserRole.technician)
