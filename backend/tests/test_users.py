"""
Tests for User CRUD endpoints.
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.models import UserRole, UserStatus

# ── Fake Redis ────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self._store: dict = {}

    async def setex(self, k, t, v):
        self._store[k] = v

    async def get(self, k):
        return self._store.get(k)

    async def delete(self, k):
        self._store.pop(k, None)

    async def exists(self, k):
        return 1 if k in self._store else 0


_redis = _FakeRedis()


async def _get_redis():
    return _redis


# ── Mock user builders ────────────────────────────────────────


def _user(role=UserRole.admin, uid=None, status=UserStatus.active):
    u = MagicMock()
    u.id = uid or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.name = f"Test {role.value.capitalize()}"
    u.role = role
    u.status = status
    u.phone = None
    u.department = None
    u.avatar_url = None
    u.last_login = None
    u.lgpd_consent = True
    u.lgpd_consent_at = None
    from datetime import datetime

    u.created_at = datetime.now(UTC)
    u.updated_at = datetime.now(UTC)
    return u


_ADMIN = _user(UserRole.admin)
_TECH = _user(UserRole.technician)
_CLIENT = _user(UserRole.client)


# ── DB mock helpers ───────────────────────────────────────────


def _db_returning(users_map: dict):
    """
    users_map: {email_or_id: User | None}
    Each execute() call pops the first entry in order.
    """
    calls = list(users_map.values())
    call_iter = iter(calls)

    async def _execute(*args, **kwargs):
        val = next(call_iter, None)
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalars.return_value.all.return_value = [val] if val else []
        result.scalar_one.return_value = 1 if val else 0
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return _gen


def _simple_db(user_for_lookup=None):
    """Returns the same user for any execute call."""

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = user_for_lookup
        result.scalars.return_value.all.return_value = [user_for_lookup] if user_for_lookup else []
        result.scalar_one.return_value = 1 if user_for_lookup else 0
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return _gen


# ── Client fixture factory ────────────────────────────────────


def _make_client(actor: MagicMock, db_override):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = db_override
    token = create_access_token(actor.id, actor.role.value, actor.email)
    headers = {"Authorization": f"Bearer {token}"}
    return headers


# ── Tests ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


# POST /users


@pytest.mark.asyncio
async def test_create_user_as_admin(patch_redis):
    db = _simple_db(None)  # email not found → can create
    from app.core.database import get_db

    app.dependency_overrides[get_db] = db

    # Override get_current_user to return admin
    from app.core.security import get_current_user

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/users",
            json={
                "name": "New Client",
                "email": "newclient@test.com",
                "password": "Secret1234",
                "role": "client",
                "lgpd_consent": True,
            },
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_user_as_client_forbidden(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(None)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/users",
            json={
                "name": "Hacker",
                "email": "hacker@test.com",
                "password": "Secret1234",
                "role": "admin",
                "lgpd_consent": True,
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user_duplicate_email(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    # email check returns existing user → conflict
    app.dependency_overrides[get_db] = _simple_db(_CLIENT)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/users",
            json={
                "name": "Dup",
                "email": "dup@test.com",
                "password": "Secret1234",
                "lgpd_consent": True,
            },
        )
    assert resp.status_code == 409


# GET /users/me


@pytest.mark.asyncio
async def test_get_me(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


# GET /users/{id}


@pytest.mark.asyncio
async def test_get_user_admin_sees_anyone(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/users/{target.id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_user_client_blocked_from_other(patch_redis):
    target = _user(UserRole.technician)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _client_user():
        return _CLIENT  # different id from target

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/users/{target.id}")
    assert resp.status_code == 403


# PATCH /users/{id}/status


@pytest.mark.asyncio
async def test_update_status_as_admin(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/users/{target.id}/status",
            json={"status": "inactive"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/users/{_ADMIN.id}/status",
            json={"status": "inactive"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_client_cannot_change_status(patch_redis):
    target = _user(UserRole.technician)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/users/{target.id}/status",
            json={"status": "inactive"},
        )
    assert resp.status_code == 403


# GET /users (list)


@pytest.mark.asyncio
async def test_list_users_as_admin(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_CLIENT)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users")
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_list_users_as_client_forbidden(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(None)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users")
    assert resp.status_code == 403


# ── Helper: two-step DB (user lookup + scalar count) ─────────


def _db_two_step(first_user, count_value: int = 0):
    """First execute returns a user; second returns a scalar count."""
    calls = iter([first_user, count_value])

    async def _execute(*args, **kwargs):
        val = next(calls, None)
        result = MagicMock()
        if isinstance(val, int):
            result.scalar_one_or_none.return_value = None
            result.scalar_one.return_value = val
        else:
            result.scalar_one_or_none.return_value = val
            result.scalar_one.return_value = 1 if val else 0
        result.scalars.return_value.all.return_value = (
            [val] if val and not isinstance(val, int) else []
        )
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()

    async def _gen():
        yield session

    return _gen


# GET /users/{id} — 404


@pytest.mark.asyncio
async def test_get_user_not_found(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(None)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/users/{uuid.uuid4()}")
    assert resp.status_code == 404


# PATCH /users/{id}/status — 404


@pytest.mark.asyncio
async def test_update_status_user_not_found(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    target_id = uuid.uuid4()
    app.dependency_overrides[get_db] = _simple_db(None)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{target_id}/status", json={"status": "inactive"})
    assert resp.status_code == 404


# PATCH /users/me/lgpd-consent


@pytest.mark.asyncio
async def test_update_lgpd_consent(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_CLIENT)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/lgpd-consent", json={"lgpd_consent": True})
    assert resp.status_code == 200


# PATCH /users/{id} — admin updates another user


@pytest.mark.asyncio
async def test_update_user_as_admin(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{target.id}", json={"name": "Nome Atualizado"})
    assert resp.status_code == 200


# POST /users/{id}/anonymize — success


@pytest.mark.asyncio
async def test_anonymize_user(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/users/{target.id}/anonymize")
    assert resp.status_code == 200


# POST /users/{id}/anonymize — cannot anonymize self


@pytest.mark.asyncio
async def test_anonymize_self_blocked(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/users/{_ADMIN.id}/anonymize")
    assert resp.status_code == 400


# POST /users/{id}/anonymize — already anonymized → 409


@pytest.mark.asyncio
async def test_anonymize_already_anonymized(patch_redis):
    target = _user(UserRole.client, status=UserStatus.anonymized)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/users/{target.id}/anonymize")
    assert resp.status_code == 409


# DELETE /users/{id} — success (no tickets)


@pytest.mark.asyncio
async def test_delete_user_success(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    # First execute: returns user; second: count = 0 tickets
    app.dependency_overrides[get_db] = _db_two_step(target, count_value=0)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{target.id}")
    assert resp.status_code == 204


# DELETE /users/{id} — cannot delete self


@pytest.mark.asyncio
async def test_delete_self_blocked(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{_ADMIN.id}")
    assert resp.status_code == 400


# DELETE /users/{id} — user has tickets → 409


@pytest.mark.asyncio
async def test_delete_user_has_tickets(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    # First execute: returns user; second: count = 3 tickets
    app.dependency_overrides[get_db] = _db_two_step(target, count_value=3)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{target.id}")
    assert resp.status_code == 409
