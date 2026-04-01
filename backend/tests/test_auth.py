"""
Tests for JWT authentication endpoints.
All database and Redis calls are mocked — no external dependencies needed.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from app.main import app
from app.models.models import UserRole, UserStatus

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_ID = uuid.uuid4()
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "Test@123456"
_HASHED = _pwd.hash(ADMIN_PASSWORD)


def _make_user(status=UserStatus.active):
    """Build a mock User object that satisfies attribute lookups without ORM."""
    user = MagicMock()
    user.id = ADMIN_ID
    user.email = ADMIN_EMAIL
    user.name = "Test Admin"
    user.password = _HASHED
    user.role = UserRole.admin
    user.status = status
    user.lgpd_consent = True
    return user


# ── In-memory Redis ───────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def setex(self, key, ttl, value):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        self._store.pop(key, None)

    async def exists(self, key):
        return 1 if key in self._store else 0


_fake_redis = _FakeRedis()


async def _get_fake_redis():
    return _fake_redis


# ── DB session mock factory ───────────────────────────────────


def _make_db_mock(user):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _gen():
        yield session

    return _gen


# ── Client fixtures ───────────────────────────────────────────


@pytest.fixture()
async def client_ok():
    """Client with a valid active user in the DB."""
    _fake_redis._store.clear()
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _make_db_mock(_make_user())

    with patch("app.core.security.get_redis", new=_get_fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture()
async def client_no_user():
    """Client where DB returns no user (login should fail)."""
    _fake_redis._store.clear()
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _make_db_mock(None)

    with patch("app.core.security.get_redis", new=_get_fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(client_ok):
    response = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 15 * 60


@pytest.mark.asyncio
async def test_login_wrong_password(client_ok):
    response = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": "WrongPassword!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client_no_user):
    response = await client_no_user.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client_ok):
    login_resp = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()

    response = await client_ok.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_invalid_token(client_ok):
    response = await client_ok.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_wrong_token_not_stored(client_ok):
    """Refresh token not in Redis (e.g. user already logged out)."""
    _fake_redis._store.clear()

    from app.core.security import create_refresh_token

    forged = create_refresh_token(ADMIN_ID)

    response = await client_ok.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": forged},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(client_ok):
    login_resp = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    response = await client_ok.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_no_token_returns_401(client_ok):
    """Logout endpoint (protected by get_current_user) should 401 without token."""
    response = await client_ok.post("/api/v1/auth/logout")
    assert response.status_code == 401
