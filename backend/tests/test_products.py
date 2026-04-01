"""
Tests for Product and Equipment CRUD endpoints.
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

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


# ── Mock builders ─────────────────────────────────────────────

_NOW = datetime.now(UTC)
_PRODUCT_ID = uuid.uuid4()
_EQUIP_ID = uuid.uuid4()


def _mock_user(role=UserRole.admin):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_product(name="Titan", is_active=True):
    p = MagicMock()
    p.id = _PRODUCT_ID
    p.name = name
    p.description = "Bafômetro Titan"
    p.version = None
    p.is_active = is_active
    p.created_at = _NOW
    p.updated_at = _NOW
    return p


def _mock_equipment(serial=None):
    e = MagicMock()
    e.id = _EQUIP_ID
    e.product_id = _PRODUCT_ID
    e.name = "Titan #001"
    e.serial_number = serial or "SN-001"
    e.model = "TN-X"
    e.description = None
    e.is_active = True
    e.created_at = _NOW
    e.updated_at = _NOW
    return e


_ADMIN = _mock_user(UserRole.admin)
_CLIENT = _mock_user(UserRole.client)


# ── DB session factory ────────────────────────────────────────


def _db(lookup=None, count=0):
    """Single-value mock: scalar_one_or_none returns `lookup`, scalar_one returns `count`."""

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
    return session


def _db_override(lookup=None, count=0):
    session = _db(lookup, count)

    async def _gen():
        yield session

    return _gen


# ── Fixture helpers ───────────────────────────────────────────


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
# PRODUCT TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_product_as_admin(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(None)  # name not found
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/products", json={"name": "Titan"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Titan"


@pytest.mark.asyncio
async def test_create_product_as_client_forbidden(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/products", json={"name": "Titan"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_product_duplicate_name(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(_mock_product())  # name exists
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/products", json={"name": "Titan"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_products(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(_mock_product(), count=1)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/products")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_get_product(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    app.dependency_overrides[get_db] = _db_override(product)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{_PRODUCT_ID}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Titan"


@pytest.mark.asyncio
async def test_get_product_not_found(patch_redis):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_product_as_admin(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    app.dependency_overrides[get_db] = _db_override(product)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/products/{_PRODUCT_ID}", json={"version": "2.0"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_product_soft(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    app.dependency_overrides[get_db] = _db_override(product)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/products/{_PRODUCT_ID}")
    assert resp.status_code == 204


# ═══════════════════════════════════════════════════════════════
# EQUIPMENT TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_equipment_as_admin(patch_redis):
    from app.core.database import get_db

    product = _mock_product()

    # execute calls: 1) product lookup, 2) serial number check
    call_seq = [product, None]
    idx = 0

    async def _execute(*args, **kwargs):
        nonlocal idx
        val = call_seq[idx] if idx < len(call_seq) else None
        idx += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalar_one.return_value = 0
        result.scalars.return_value.all.return_value = []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            json={"name": "Titan #001", "serial_number": "SN-001"},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Titan #001"


@pytest.mark.asyncio
async def test_create_equipment_duplicate_serial(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    existing_equip = _mock_equipment("SN-001")

    call_seq = [product, existing_equip]
    idx = 0

    async def _execute(*args, **kwargs):
        nonlocal idx
        val = call_seq[idx] if idx < len(call_seq) else None
        idx += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalar_one.return_value = 0
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/products/{_PRODUCT_ID}/equipments",
            json={"name": "Titan #002", "serial_number": "SN-001"},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_equipments(patch_redis):
    from app.core.database import get_db

    product = _mock_product()
    equip = _mock_equipment()

    call_seq = [product, equip]
    idx = 0

    async def _execute(*args, **kwargs):
        nonlocal idx
        val = call_seq[idx] if idx < len(call_seq) else None
        idx += 1
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalar_one.return_value = 1
        result.scalars.return_value.all.return_value = [equip] if val == product else []
        return result

    session = AsyncMock()
    session.execute = _execute

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/products/{_PRODUCT_ID}/equipments")
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_get_equipment(patch_redis):
    from app.core.database import get_db

    equip = _mock_equipment()
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_CLIENT)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/equipments/{_EQUIP_ID}")
    assert resp.status_code == 200
    assert resp.json()["serial_number"] == "SN-001"


@pytest.mark.asyncio
async def test_delete_equipment_soft(patch_redis):
    from app.core.database import get_db

    equip = _mock_equipment()
    app.dependency_overrides[get_db] = _db_override(equip)
    _override_user(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/equipments/{_EQUIP_ID}")
    assert resp.status_code == 204
