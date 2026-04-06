"""
Tests for the Notification service and endpoints.
DB and Redis are fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import NotificationType, UserRole, UserStatus

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
_NOTIF_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.client, user_id=None):
    u = MagicMock()
    u.id = user_id or _USER_ID
    u.email = "user@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_notif(read=False, user_id=None):
    n = MagicMock()
    n.id = _NOTIF_ID
    n.user_id = user_id or _USER_ID
    n.type = NotificationType.ticket_created
    n.title = "Ticket aberto"
    n.message = "Seu ticket foi registrado."
    n.data = {"ticket_id": str(uuid.uuid4())}
    n.read = read
    n.read_at = _NOW if read else None
    n.email_sent = False
    n.created_at = _NOW
    return n


# ── DB session factories ──────────────────────────────────────


def _db(lookup=None, count=0, unread=0):
    call_count = [0]

    async def _execute(*args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        # 1st call: total count, 2nd call: unread count, 3rd call: list
        if call_count[0] == 1:
            result.scalar_one.return_value = count
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        elif call_count[0] == 2:
            result.scalar_one.return_value = unread
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        else:
            result.scalar_one_or_none.return_value = lookup
            result.scalar_one.return_value = 0
            result.scalars.return_value.all.return_value = [lookup] if lookup else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _db_single(lookup=None):
    """Simple single-lookup mock."""

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = lookup
        result.scalar_one.return_value = 0
        result.scalars.return_value.all.return_value = [lookup] if lookup else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _db_override_custom(session):
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
# Notification service unit tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_notify_adds_notification_to_session():
    from app.services.notifications import notify

    db = MagicMock()
    db.add = MagicMock()

    async def _execute(*a, **kw):
        r = MagicMock()
        r.scalar_one_or_none.return_value = "user@test.com"
        return r

    db.execute = _execute

    with patch("app.services.notifications.asyncio.create_task"):
        await notify(
            db,
            _USER_ID,
            NotificationType.ticket_created,
            "Ticket aberto",
            "Protocolo HS-2026-0001",
        )

    db.add.assert_called_once()
    notif_obj = db.add.call_args[0][0]
    assert notif_obj.user_id == _USER_ID
    assert notif_obj.type == NotificationType.ticket_created
    assert notif_obj.read is False


@pytest.mark.asyncio
async def test_notify_schedules_email_task_when_settings_provided():
    from app.core.config import get_settings
    from app.services.notifications import notify

    db = MagicMock()
    db.add = MagicMock()

    async def _execute(*a, **kw):
        r = MagicMock()
        r.scalar_one_or_none.return_value = "user@test.com"
        return r

    db.execute = _execute
    settings = get_settings()

    with patch("app.services.notifications.asyncio.create_task") as _mock_task:
        await notify(
            db,
            _USER_ID,
            NotificationType.ticket_created,
            "Ticket aberto",
            "Protocolo HS-2026-0001",
            settings=settings,
        )
        _mock_task.assert_called_once()


@pytest.mark.asyncio
async def test_notify_no_email_task_without_settings():
    from app.services.notifications import notify

    db = MagicMock()
    db.add = MagicMock()

    async def _execute(*a, **kw):
        r = MagicMock()
        r.scalar_one_or_none.return_value = "user@test.com"
        return r

    db.execute = _execute

    with patch("app.services.notifications.asyncio.create_task") as mock_task:
        await notify(db, _USER_ID, NotificationType.ticket_created, "Title", "Body")
        mock_task.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# Email service unit tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_send_email_skips_when_not_configured():
    from app.core.config import Settings
    from app.services.email import send_email

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="",
        smtp_user="",
    )
    result = await send_email("user@test.com", "Subject", "Body", settings)
    assert result is False


@pytest.mark.asyncio
async def test_send_email_handles_smtp_failure():
    from app.core.config import Settings
    from app.services.email import send_email

    settings = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="from@test.com",
        smtp_user="from@test.com",
        smtp_host="localhost",
        smtp_port=1025,
    )

    with patch("app.services.email._get_mail_client") as mock_client:
        mock_fm = AsyncMock()
        mock_fm.send_message = AsyncMock(side_effect=Exception("SMTP error"))
        mock_client.return_value = mock_fm

        result = await send_email("to@test.com", "Subject", "Body", settings)

    assert result is False


# ═══════════════════════════════════════════════════════════════
# Notification endpoint tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_notifications(patch_redis):
    from app.core.database import get_db

    user = _mock_user()
    notif = _mock_notif()
    session = _db(lookup=notif, count=1, unread=1)

    # Override list query to return items
    call_count = [0]

    async def _patched_execute(*args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.scalar_one.return_value = 1  # total
        elif call_count[0] == 2:
            result.scalar_one.return_value = 1  # unread
        else:
            result.scalars.return_value.all.return_value = [notif]
        return result

    session.execute = _patched_execute
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/notifications")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["unread"] == 1


@pytest.mark.asyncio
async def test_mark_read(patch_redis):
    from app.core.database import get_db

    user = _mock_user(user_id=_USER_ID)
    notif = _mock_notif(read=False, user_id=_USER_ID)
    session = _db_single(notif)
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/notifications/{_NOTIF_ID}/read")

    assert resp.status_code == 200
    assert notif.read is True


@pytest.mark.asyncio
async def test_mark_all_read(patch_redis):
    from app.core.database import get_db

    user = _mock_user(user_id=_USER_ID)
    session = _db_single()
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/notifications/read-all")

    assert resp.status_code == 204
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_notification(patch_redis):
    from app.core.database import get_db

    user = _mock_user(user_id=_USER_ID)
    notif = _mock_notif(user_id=_USER_ID)
    session = _db_single(notif)
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/notifications/{_NOTIF_ID}")

    assert resp.status_code == 204
    session.delete.assert_called_once_with(notif)


@pytest.mark.asyncio
async def test_delete_notification_other_user(patch_redis):
    """Notification belonging to another user returns 404."""
    from app.core.database import get_db

    user = _mock_user(user_id=uuid.uuid4())  # different user
    session = _db_single(None)  # query filters by user_id → returns None
    app.dependency_overrides[get_db] = _db_override_custom(session)
    _override_user(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/notifications/{_NOTIF_ID}")

    assert resp.status_code == 404
