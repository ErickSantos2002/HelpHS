"""
Tests for Dashboard and Reports endpoints.
DB and Redis fully mocked — all scalar queries return 0, all row queries return [].
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import UserRole

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


# ── Mock actor ────────────────────────────────────────────────


def _mock_actor(role=UserRole.admin):
    u = MagicMock()
    u.id = "actor-uuid"
    u.role = role
    return u


_ADMIN = _mock_actor(UserRole.admin)
_TECH = _mock_actor(UserRole.technician)


# ── DB mock: all counts = 0, all row queries = [] ─────────────


def _empty_db():
    """
    Universal DB mock for dashboard endpoints.
    Every execute() returns a result where:
      - scalar_one()           → 0
      - scalar_one_or_none()   → None
      - .all()                 → []
      - scalars().all()        → []
    """

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one.return_value = 0
        result.scalar_one_or_none.return_value = None
        result.all.return_value = []
        result.scalars.return_value.all.return_value = []
        return result

    session = AsyncMock()
    session.execute = _execute

    async def _gen():
        yield session

    return _gen


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


def _make_client_with_actor(actor):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _empty_db()

    async def _actor():
        return actor

    app.dependency_overrides[get_current_user] = _actor


# ── Dashboard Stats ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_stats_admin(patch_redis):
    _make_client_with_actor(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert "tickets" in body
    assert "surveys" in body
    assert "sla" in body
    assert body["tickets"]["total"] == 0
    assert body["sla"]["response_breached"] == 0


@pytest.mark.asyncio
async def test_dashboard_stats_technician(patch_redis):
    _make_client_with_actor(_TECH)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/stats")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_stats_client_forbidden(patch_redis):
    client_actor = _mock_actor(UserRole.client)
    _make_client_with_actor(client_actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/stats")

    assert resp.status_code == 403


# ── Reports ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reports_default_period(patch_redis):
    _make_client_with_actor(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/reports")

    assert resp.status_code == 200
    body = resp.json()
    assert body["period_days"] == 30
    assert body["total_tickets"] == 0
    assert isinstance(body["tickets_by_day"], list)
    assert isinstance(body["sla_compliance"], list)
    assert len(body["sla_compliance"]) == 4  # one per priority level


@pytest.mark.asyncio
async def test_get_reports_custom_period(patch_redis):
    _make_client_with_actor(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/reports?period=7")

    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


@pytest.mark.asyncio
async def test_get_reports_period_out_of_range(patch_redis):
    _make_client_with_actor(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/reports?period=6")  # min is 7

    assert resp.status_code == 422


# ── CSV Export ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_csv(patch_redis):
    _make_client_with_actor(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/reports/export/csv")

    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")


# ── PDF Export ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_pdf(patch_redis):
    _make_client_with_actor(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/dashboard/reports/export/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    # PDF binary starts with %PDF
    assert resp.content[:4] == b"%PDF"
