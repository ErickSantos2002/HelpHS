"""
Tests for GET /audit-logs endpoint.
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import AuditAction, UserRole, UserStatus

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


# ── Constants ─────────────────────────────────────────────────

_NOW = datetime.now(UTC)
_USER_ID = uuid.uuid4()
_ENTRY_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.admin):
    u = MagicMock()
    u.id = _USER_ID
    u.email = "admin@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_entry(action=AuditAction.create, entity_type="ticket"):
    e = MagicMock()
    e.id = _ENTRY_ID
    e.user_id = _USER_ID
    e.action = action
    e.entity_type = entity_type
    e.entity_id = uuid.uuid4()
    e.old_data = None
    e.new_data = None
    e.ip_address = "127.0.0.1"
    e.user_agent = "pytest"
    e.created_at = _NOW
    return e


# ── DB session factories ──────────────────────────────────────


def _db_seq(*responses):
    call_count = [0]

    async def _execute(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]

        result = MagicMock()
        if isinstance(resp, int | float):
            result.scalar_one.return_value = resp
            result.scalar_one_or_none.return_value = resp
            result.scalars.return_value.all.return_value = []
        elif isinstance(resp, list):
            result.scalar_one.return_value = len(resp)
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = resp
        else:
            result.scalar_one_or_none.return_value = resp
            result.scalar_one.return_value = 0
            result.scalars.return_value.all.return_value = [resp] if resp else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _db_override(lookup=None, count=0):
    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = lookup
        result.scalar_one.return_value = count
        result.scalars.return_value.all.return_value = [lookup] if lookup else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return _gen


def _db_seq_override(*responses):
    session = _db_seq(*responses)

    async def _gen():
        yield session

    return _gen


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


def _override_user(user):
    from app.core.security import get_current_user

    async def _u():
        return user

    app.dependency_overrides[get_current_user] = _u


# ═══════════════════════════════════════════════════════════════
# GET /audit-logs
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_audit_logs_admin_success(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    entry = _mock_entry()

    app.dependency_overrides[get_db] = _db_seq_override(1, [entry])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["action"] == AuditAction.create.value


@pytest.mark.asyncio
async def test_list_audit_logs_client_forbidden(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_audit_logs_technician_forbidden(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_audit_logs_empty(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _db_seq_override(0, [])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_audit_logs_filter_by_action(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    entry = _mock_entry(action=AuditAction.login, entity_type="user")

    app.dependency_overrides[get_db] = _db_seq_override(1, [entry])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs?action=login")

    assert resp.status_code == 200
    assert resp.json()["items"][0]["action"] == "login"


@pytest.mark.asyncio
async def test_list_audit_logs_filter_by_entity_type(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    entry = _mock_entry(entity_type="survey")

    app.dependency_overrides[get_db] = _db_seq_override(1, [entry])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs?entity_type=survey")

    assert resp.status_code == 200
    assert resp.json()["items"][0]["entity_type"] == "survey"


@pytest.mark.asyncio
async def test_list_audit_logs_pagination(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _db_seq_override(5, [])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs?offset=5&limit=10")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["offset"] == 5
    assert data["limit"] == 10


@pytest.mark.asyncio
async def test_list_audit_logs_filter_by_user_id(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    entry = _mock_entry()

    app.dependency_overrides[get_db] = _db_seq_override(1, [entry])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/audit-logs?user_id={_USER_ID}")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_audit_logs_date_filters(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _db_seq_override(0, [])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/audit-logs?date_from=2026-01-01T00:00:00Z&date_to=2026-12-31T23:59:59Z"
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_audit_logs_invalid_limit(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/audit-logs?limit=300")

    assert resp.status_code == 422
