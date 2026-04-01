"""
Tests for RBAC — authorize() dependency factory.

Mounts three test-only routes (admin-only, staff-only, any-auth) and verifies
that each role combination gets the correct HTTP response.
No external dependencies — DB and Redis are fully mocked.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from app.core.security import authorize, create_access_token
from app.models.models import UserRole, UserStatus

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Fake Redis (shared across test session) ───────────────────


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


_redis = _FakeRedis()


async def _get_redis():
    return _redis


# ── Mock user factory ─────────────────────────────────────────


def _mock_user(role: UserRole, status=UserStatus.active):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = status
    return u


# ── Minimal app with test routes ──────────────────────────────


_test_app = FastAPI()


@_test_app.get("/admin-only")
async def admin_only(user=Depends(authorize(UserRole.admin))):
    return {"role": user.role.value}


@_test_app.get("/staff")
async def staff(user=Depends(authorize(UserRole.admin, UserRole.technician))):
    return {"role": user.role.value}


@_test_app.get("/any-auth")
async def any_auth(user=Depends(authorize(UserRole.admin, UserRole.technician, UserRole.client))):
    return {"role": user.role.value}


# ── Helper: build auth header for a given role ────────────────


def _token_for(user) -> str:
    return create_access_token(user.id, user.role.value, user.email)


def _make_db_override(user):
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    async def _gen():
        yield session

    return _gen


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture()
async def client_as(request):
    """
    Parametrized fixture: receives a UserRole, returns an authenticated client.
    Usage: indirect via pytest.mark.parametrize.
    """
    from app.core.database import get_db

    role = request.param
    user = _mock_user(role)
    _test_app.dependency_overrides[get_db] = _make_db_override(user)

    with patch("app.core.security.get_redis", new=_get_redis):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as c:
            c._role_user = user
            yield c

    _test_app.dependency_overrides.clear()


# ── Tests: admin-only route ───────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("client_as", [UserRole.admin], indirect=True)
async def test_admin_route_allows_admin(client_as):
    headers = {"Authorization": f"Bearer {_token_for(client_as._role_user)}"}
    resp = await client_as.get("/admin-only", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
@pytest.mark.parametrize("client_as", [UserRole.technician], indirect=True)
async def test_admin_route_blocks_technician(client_as):
    headers = {"Authorization": f"Bearer {_token_for(client_as._role_user)}"}
    resp = await client_as.get("/admin-only", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("client_as", [UserRole.client], indirect=True)
async def test_admin_route_blocks_client(client_as):
    headers = {"Authorization": f"Bearer {_token_for(client_as._role_user)}"}
    resp = await client_as.get("/admin-only", headers=headers)
    assert resp.status_code == 403


# ── Tests: staff route (admin + technician) ───────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("client_as", [UserRole.admin], indirect=True)
async def test_staff_route_allows_admin(client_as):
    headers = {"Authorization": f"Bearer {_token_for(client_as._role_user)}"}
    resp = await client_as.get("/staff", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("client_as", [UserRole.technician], indirect=True)
async def test_staff_route_allows_technician(client_as):
    headers = {"Authorization": f"Bearer {_token_for(client_as._role_user)}"}
    resp = await client_as.get("/staff", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("client_as", [UserRole.client], indirect=True)
async def test_staff_route_blocks_client(client_as):
    headers = {"Authorization": f"Bearer {_token_for(client_as._role_user)}"}
    resp = await client_as.get("/staff", headers=headers)
    assert resp.status_code == 403


# ── Tests: any-auth route (all roles allowed) ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_as",
    [UserRole.admin, UserRole.technician, UserRole.client],
    indirect=True,
)
async def test_any_auth_route_allows_all_roles(client_as):
    headers = {"Authorization": f"Bearer {_token_for(client_as._role_user)}"}
    resp = await client_as.get("/any-auth", headers=headers)
    assert resp.status_code == 200


# ── Tests: no token ───────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("client_as", [UserRole.admin], indirect=True)
async def test_no_token_returns_401(client_as):
    resp = await client_as.get("/admin-only")
    assert resp.status_code == 401
