"""
JWT RS256 token creation, validation, and Redis-based blacklist.
"""

import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
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
# `bcrypt__rounds` é o que liga BCRYPT_ROUNDS ao passlib. Sem esse argumento a
# variável existia no `.env.example` e no `Settings` sem efeito nenhum: o custo
# era sempre o default da biblioteca, e quem subisse com 14 no painel acharia
# ter endurecido as senhas sem ter mudado nada.
#
# Mudar o valor só afeta hashes NOVOS — o custo vai gravado dentro do próprio
# hash, então as senhas já cadastradas continuam sendo verificadas normalmente.
pwd_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.bcrypt_rounds
)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _custo_do_hash(hash_bcrypt: str) -> int:
    """Cost (número de rounds) declarado no prefixo `$2b$NN$` do hash."""
    return int(hash_bcrypt.split("$")[2])


def _dummy_no_custo_do_contexto(contexto: CryptContext, hash_fixo: str) -> str:
    """
    Devolve um hash descartável que custa o mesmo que os hashes reais.

    No caminho normal o literal já está no custo certo e sai como está — sem
    pagar bcrypt nenhum no import. Quando `BCRYPT_ROUNDS` muda, o literal fica
    defasado e é refeito uma vez por processo.
    """
    if _custo_do_hash(hash_fixo) == contexto.to_dict().get("bcrypt__rounds"):
        return hash_fixo
    return contexto.hash(secrets.token_urlsafe(32))


# Hash descartável, de uma senha aleatória que ninguém conhece, usado quando o
# e-mail informado no login não existe: sem ele o bcrypt seria pulado e a
# resposta voltaria em ~1 ms, contra ~250 ms de um e-mail cadastrado — o tempo
# viraria oráculo de quais contas existem.
#
# O literal fica em 12 rounds em vez de ser gerado sempre, que somaria centenas
# de milissegundos a cada boot e a cada processo de teste. Não é segredo: é
# hash de uma senha jogada fora.
#
# O custo TEM de acompanhar o dos hashes reais. Enquanto isso dependia de
# alguém regerar o literal na mão, `BCRYPT_ROUNDS=14` no painel reabria o
# oráculo em silêncio — o dummy custava 486 ms contra 1777 ms de um hash real,
# e nenhum teste pegava, porque a suíte roda sem BCRYPT_ROUNDS no ambiente e
# comparava 12 com 12. Agora o próprio import se encarrega.
DUMMY_PASSWORD_HASH = _dummy_no_custo_do_contexto(
    pwd_context, "$2b$12$hC.ULm90gnH9mf/U6suX2ezkP9nmIJr6IvegxxvGTZ1toStl/.WqW"
)


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
) -> Any:
    """
    Validates the Bearer token and returns the User ORM object.

    O retorno é `Any` e não `User` de propósito: o modelo é importado dentro da
    função para evitar import circular, então o nome não existe aqui em cima.
    Raises 401 if token is missing, invalid, expired, or blacklisted.
    """
    from app.models.models import User, UserStatus  # avoid circular import

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sua sessão não é mais válida. Entre novamente para continuar.",
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
            detail="Esta conta está inativa. Fale com um administrador.",
        )

    return user


def authorize(*roles: Any) -> Callable[..., Awaitable[Any]]:
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

    async def _check(user: Any = Depends(get_current_user)) -> Any:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para realizar esta ação.",
            )
        return user

    return _check


# ── Convenience aliases ───────────────────────────────────────


def require_admin() -> Callable[..., Awaitable[Any]]:
    from app.models.models import UserRole

    return authorize(UserRole.admin)


def require_technician_or_admin() -> Callable[..., Awaitable[Any]]:
    from app.models.models import UserRole

    return authorize(UserRole.admin, UserRole.technician)
