"""
Targeted tests to cover remaining gaps after Sprint 2:
  - users.py: PATCH endpoint, self-access GET, list filters
  - products.py: PATCH equipment
  - security.py: require_admin / require_technician_or_admin aliases
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.security import (
    create_access_token,
    require_admin,
    require_technician_or_admin,
)
from app.models.models import UserRole, UserStatus

_NOW = datetime.now(UTC)


# ── Shared helpers ────────────────────────────────────────────


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


def _mock_user(role=UserRole.admin, uid=None):
    u = MagicMock()
    u.id = uid or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.name = f"Test {role.value}"
    u.role = role
    u.status = UserStatus.active
    u.phone = None
    u.department = None
    u.avatar_url = None
    u.last_login = None
    u.lgpd_consent = True
    u.lgpd_consent_at = None
    u.created_at = _NOW
    u.updated_at = _NOW
    return u


def _simple_db(lookup=None, count=1):
    async def _execute(*args, **kwargs):
        r = MagicMock()
        r.scalar_one_or_none.return_value = lookup
        r.scalar_one.return_value = count
        r.scalars.return_value.all.return_value = [lookup] if lookup else []
        return r

    s = AsyncMock()
    s.execute = _execute
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()

    async def _gen():
        yield s

    return _gen


def _override_user(user):
    from app.core.security import get_current_user
    from app.main import app

    async def _u():
        return user

    app.dependency_overrides[get_current_user] = _u


@pytest.fixture(autouse=True)
def _clear():
    from app.main import app

    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


# ═══════════════════════════════════════════════════════════════
# users.py gaps
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_user_client_sees_self(patch_redis):
    """Non-admin can fetch their own profile via GET /users/{id}."""
    from app.core.database import get_db
    from app.main import app

    client_user = _mock_user(UserRole.client)
    client_user.id = uuid.uuid4()

    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/users/{client_user.id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_user_admin_updates_anyone(patch_redis):
    """Admin can PATCH any user."""
    from app.core.database import get_db
    from app.main import app

    admin = _mock_user(UserRole.admin)
    target = _mock_user(UserRole.client)

    app.dependency_overrides[get_db] = _simple_db(target)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{target.id}", json={"name": "Updated Name"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_user_client_updates_self(patch_redis):
    """Non-admin can PATCH their own profile (no role change)."""
    from app.core.database import get_db
    from app.main import app

    client_user = _mock_user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{client_user.id}", json={"phone": "11999999999"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_user_client_cannot_change_role(patch_redis):
    """Non-admin cannot change their own role."""
    from app.core.database import get_db
    from app.main import app

    client_user = _mock_user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{client_user.id}", json={"role": "admin"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_user_client_cannot_edit_other(patch_redis):
    """Non-admin cannot PATCH another user."""
    from app.core.database import get_db
    from app.main import app

    client_user = _mock_user(UserRole.client)
    other_id = uuid.uuid4()

    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{other_id}", json={"name": "Hack"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_user_not_found(patch_redis):
    from app.core.database import get_db
    from app.main import app

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _simple_db(None)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{uuid.uuid4()}", json={"name": "NotFound User"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_users_with_filters(patch_redis):
    """GET /users with role + search query params hits the filter branches."""
    from app.core.database import get_db
    from app.main import app

    admin = _mock_user(UserRole.admin)
    client_user = _mock_user(UserRole.client)

    app.dependency_overrides[get_db] = _simple_db(client_user, count=1)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users?role=client&status=active&search=test")
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════
# products.py gaps — PATCH equipment
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_patch_equipment_as_admin(patch_redis):
    from app.core.database import get_db
    from app.main import app

    equip_id = uuid.uuid4()

    equip = MagicMock()
    equip.id = equip_id
    equip.product_id = uuid.uuid4()
    equip.name = "Titan #001"
    equip.serial_number = "SN-001"
    equip.model = "TN-X"
    equip.description = None
    equip.is_active = True
    equip.created_at = _NOW
    equip.updated_at = _NOW

    app.dependency_overrides[get_db] = _simple_db(equip)
    _override_user(_mock_user(UserRole.admin))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/equipments/{equip_id}", json={"model": "TN-X2"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_equipment_not_found(patch_redis):
    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = _simple_db(None)
    _override_user(_mock_user(UserRole.admin))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/equipments/{uuid.uuid4()}", json={"model": "X"})
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# security.py aliases
# ═══════════════════════════════════════════════════════════════

_alias_app = FastAPI()


@_alias_app.get("/admin")
async def _admin_route(user=Depends(require_admin())):
    return {"role": user.role.value}


@_alias_app.get("/staff")
async def _staff_route(user=Depends(require_technician_or_admin())):
    return {"role": user.role.value}


def _alias_db(user):
    from app.core.database import get_db

    r = MagicMock()
    r.scalar_one_or_none.return_value = user
    s = AsyncMock()
    s.execute = AsyncMock(return_value=r)

    async def _gen():
        yield s

    _alias_app.dependency_overrides[get_db] = _gen


@pytest.fixture(autouse=False)
def _clear_alias():
    yield
    _alias_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_require_admin_alias_allows_admin(_clear_alias):
    admin = _mock_user(UserRole.admin)
    _alias_db(admin)
    token = create_access_token(admin.id, admin.role.value, admin.email)

    with patch("app.core.security.get_redis", new=_get_redis):
        async with AsyncClient(
            transport=ASGITransport(app=_alias_app), base_url="http://test"
        ) as c:
            resp = await c.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_require_admin_alias_blocks_client(_clear_alias):
    client_user = _mock_user(UserRole.client)
    _alias_db(client_user)
    token = create_access_token(client_user.id, client_user.role.value, client_user.email)

    with patch("app.core.security.get_redis", new=_get_redis):
        async with AsyncClient(
            transport=ASGITransport(app=_alias_app), base_url="http://test"
        ) as c:
            resp = await c.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_require_technician_or_admin_allows_technician(_clear_alias):
    tech = _mock_user(UserRole.technician)
    _alias_db(tech)
    token = create_access_token(tech.id, tech.role.value, tech.email)

    with patch("app.core.security.get_redis", new=_get_redis):
        async with AsyncClient(
            transport=ASGITransport(app=_alias_app), base_url="http://test"
        ) as c:
            resp = await c.get("/staff", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
