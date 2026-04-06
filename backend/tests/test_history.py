"""
Tests for Ticket History — automatic recording and GET endpoint.
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import TicketCategory, TicketPriority, TicketStatus, UserRole, UserStatus

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
_TICKET_ID = uuid.uuid4()
_CREATOR_ID = uuid.uuid4()
_TECH_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_ticket(status=TicketStatus.open, creator_id=None):
    t = MagicMock()
    t.id = _TICKET_ID
    t.protocol = "HS-2026-0001"
    t.title = "Equipamento com falha"
    t.description = "O bafômetro não liga"
    t.status = status
    t.priority = TicketPriority.medium
    t.category = TicketCategory.hardware
    t.creator_id = creator_id or _CREATOR_ID
    t.assignee_id = None
    t.product_id = None
    t.equipment_id = None
    t.sla_response_due_at = None
    t.sla_resolve_due_at = None
    t.sla_first_response = None
    t.sla_paused_at = None
    t.sla_total_paused_ms = 0
    t.sla_response_breach = False
    t.sla_resolve_breach = False
    t.closed_at = None
    t.created_at = _NOW
    t.updated_at = _NOW
    t.ai_classification = None
    t.ai_confidence = None
    t.ai_summary = None
    t.ai_conversation_summary = None
    return t


def _mock_history_entry(field="status", old_value=None, new_value="open"):
    h = MagicMock()
    h.id = uuid.uuid4()
    h.ticket_id = _TICKET_ID
    h.user_id = _CREATOR_ID
    h.field = field
    h.old_value = old_value
    h.new_value = new_value
    h.comment = None
    h.created_at = _NOW
    return h


# ── DB session factories ──────────────────────────────────────


def _db(lookup=None, count=0):
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


def _db_sequence(*responses):
    call_count = [0]

    async def _execute(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]

        result = MagicMock()
        if isinstance(resp, int):
            result.scalar_one.return_value = resp
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
        elif isinstance(resp, list):
            result.scalar_one_or_none.return_value = None
            result.scalar_one.return_value = len(resp)
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
    session = _db(lookup, count)

    async def _gen():
        yield session

    return _gen


def _db_seq_override(*responses):
    session = _db_sequence(*responses)

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
# _record_history unit tests (pure function)
# ═══════════════════════════════════════════════════════════════


def test_record_history_adds_to_session():
    from app.routers.tickets import _record_history

    db = MagicMock()
    db.add = MagicMock()
    ticket_id = uuid.uuid4()
    user_id = uuid.uuid4()

    _record_history(db, ticket_id, user_id, "status", "open", "in_progress", "Iniciando")

    db.add.assert_called_once()
    history_obj = db.add.call_args[0][0]
    assert history_obj.ticket_id == ticket_id
    assert history_obj.user_id == user_id
    assert history_obj.field == "status"
    assert history_obj.old_value == "open"
    assert history_obj.new_value == "in_progress"
    assert history_obj.comment == "Iniciando"


def test_record_history_none_values_stay_none():
    from app.routers.tickets import _record_history

    db = MagicMock()
    db.add = MagicMock()

    _record_history(db, uuid.uuid4(), uuid.uuid4(), "created", None, "open")

    history_obj = db.add.call_args[0][0]
    assert history_obj.old_value is None
    assert history_obj.new_value == "open"


def test_record_history_converts_values_to_str():
    from app.routers.tickets import _record_history

    db = MagicMock()
    db.add = MagicMock()
    some_uuid = uuid.uuid4()

    _record_history(db, uuid.uuid4(), uuid.uuid4(), "assignee_id", None, some_uuid)

    history_obj = db.add.call_args[0][0]
    assert history_obj.new_value == str(some_uuid)


# ═══════════════════════════════════════════════════════════════
# GET /tickets/{id}/history endpoint tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_history_admin(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    entry = _mock_history_entry()

    # Sequence: get ticket, count, list
    app.dependency_overrides[get_db] = _db_seq_override(ticket, 1, [entry])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/history")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["field"] == "status"
    assert data["items"][0]["new_value"] == "open"


@pytest.mark.asyncio
async def test_get_history_client_own_ticket(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    entry = _mock_history_entry()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 1, [entry])
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/history")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_history_client_other_ticket_forbidden(patch_redis):
    from app.core.database import get_db

    other_client = _mock_user(UserRole.client)  # different user
    ticket = _mock_ticket(creator_id=_CREATOR_ID)  # owned by someone else

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(other_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/history")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_history_ticket_not_found(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{uuid.uuid4()}/history")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_history_empty(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 0, [])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/history")

    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


# ═══════════════════════════════════════════════════════════════
# Integration: history is recorded on mutations
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_status_change_records_history(patch_redis):
    """Verifies _record_history is called when status changes."""
    from app.core.database import get_db
    from app.routers import tickets as tickets_module

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.open)
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    calls = []
    original = tickets_module._record_history

    def _spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    tickets_module._record_history = _spy

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.patch(
                f"/api/v1/tickets/{_TICKET_ID}/status",
                json={"status": "in_progress"},
            )
    finally:
        tickets_module._record_history = original

    # At least one history call with field="status"
    assert any(call[3] == "status" for call in calls)


@pytest.mark.asyncio
async def test_update_ticket_records_changed_fields(patch_redis):
    """Verifies _record_history is called only for changed fields."""
    from app.core.database import get_db
    from app.routers import tickets as tickets_module

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    calls = []
    original = tickets_module._record_history

    def _spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    tickets_module._record_history = _spy

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.patch(
                f"/api/v1/tickets/{_TICKET_ID}",
                json={"title": "Novo título"},
            )
    finally:
        tickets_module._record_history = original

    assert any(call[3] == "title" for call in calls)
