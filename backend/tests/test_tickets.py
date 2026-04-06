"""
Tests for Ticket CRUD endpoints and protocol generation.
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


def _mock_user(role=UserRole.client, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_ticket(
    ticket_id=None,
    creator_id=None,
    status=TicketStatus.open,
    protocol="HS-2026-0001",
):
    t = MagicMock()
    t.id = ticket_id or _TICKET_ID
    t.protocol = protocol
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


# ── DB session factory ────────────────────────────────────────


def _db(lookup=None, count=0):
    """Single-value mock: scalar_one_or_none → lookup, scalar_one → count."""

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
    """Mock that returns different responses for sequential execute calls."""
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
# PROTOCOL GENERATION UNIT TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_protocol_first_ticket():
    """When no tickets exist, protocol should be HS-YYYY-0001."""
    from app.utils.protocol import generate_protocol

    db = _db(lookup=None)
    protocol = await generate_protocol(db)
    year = datetime.now(UTC).year
    assert protocol == f"HS-{year}-0001"


@pytest.mark.asyncio
async def test_generate_protocol_increments():
    """When last ticket is HS-YYYY-0005, next should be HS-YYYY-0006."""
    from app.utils.protocol import generate_protocol

    year = datetime.now(UTC).year
    db = _db(lookup=f"HS-{year}-0005")
    protocol = await generate_protocol(db)
    assert protocol == f"HS-{year}-0006"


@pytest.mark.asyncio
async def test_generate_protocol_pads_to_4_digits():
    """Sequence number should always be zero-padded to 4 digits."""
    from app.utils.protocol import generate_protocol

    year = datetime.now(UTC).year
    db = _db(lookup=f"HS-{year}-0009")
    protocol = await generate_protocol(db)
    assert protocol == f"HS-{year}-0010"
    assert len(protocol.split("-")[-1]) == 4


@pytest.mark.asyncio
async def test_generate_protocol_large_seq():
    """Protocol handles sequence numbers beyond 9999 (zero-padding still works)."""
    from app.utils.protocol import generate_protocol

    year = datetime.now(UTC).year
    db = _db(lookup=f"HS-{year}-9999")
    protocol = await generate_protocol(db)
    assert protocol == f"HS-{year}-10000"


# ═══════════════════════════════════════════════════════════════
# TICKET CRUD TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_ticket(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client)
    ticket = _mock_ticket(creator_id=creator.id)

    # Sequence: 1st execute = generate_protocol (returns None → seq 1)
    # commit + refresh sets up the ticket
    db_session = _db_sequence(None)

    async def _refresh(obj):
        obj.id = ticket.id
        obj.protocol = ticket.protocol
        obj.title = ticket.title
        obj.description = ticket.description
        obj.status = TicketStatus.open
        obj.priority = TicketPriority.medium
        obj.category = TicketCategory.hardware
        obj.creator_id = creator.id
        obj.assignee_id = None
        obj.product_id = None
        obj.equipment_id = None
        obj.sla_response_due_at = None
        obj.sla_resolve_due_at = None
        obj.sla_response_breach = False
        obj.sla_resolve_breach = False
        obj.closed_at = None
        obj.created_at = _NOW
        obj.updated_at = _NOW

    db_session.refresh = _refresh

    async def _gen():
        yield db_session

    app.dependency_overrides[get_db] = _gen
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/tickets",
            json={
                "title": "Equipamento com falha",
                "description": "O bafômetro não liga",
                "category": "hardware",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["protocol"] == "HS-2026-0001"
    assert data["status"] == "open"


@pytest.mark.asyncio
async def test_list_tickets_client_sees_own(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)

    # count=1, then list=[ticket]
    app.dependency_overrides[get_db] = _db_seq_override(1, [ticket])
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/tickets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["protocol"] == "HS-2026-0001"


@pytest.mark.asyncio
async def test_list_tickets_admin_sees_all(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(1, [ticket])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/tickets")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_get_ticket_client_own(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(ticket.id)


@pytest.mark.asyncio
async def test_get_ticket_client_forbidden(patch_redis):
    from app.core.database import get_db

    other_client = _mock_user(UserRole.client)  # different user_id
    ticket = _mock_ticket(creator_id=_CREATOR_ID)  # owned by someone else

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(other_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_ticket_not_found(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_ticket_technician(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}",
            json={"title": "Novo título", "priority": "high"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_ticket_client_own_open(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID, status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}",
            json={"title": "Título atualizado"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_ticket_client_not_open(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID, status=TicketStatus.in_progress)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}",
            json={"title": "Tentativa de edição"},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_status_valid_transition(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "in_progress"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_status_invalid_transition(patch_redis):
    from app.core.database import get_db

    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket(status=TicketStatus.closed)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "open"},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_status_client_forbidden(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client)
    ticket = _mock_ticket()
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/status",
            json={"status": "in_progress"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_assign_ticket(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    assignee = _mock_user(UserRole.technician, user_id=_TECH_ID)

    # Sequence: 1st execute = get ticket, 2nd = get assignee
    app.dependency_overrides[get_db] = _db_seq_override(ticket, assignee)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": str(_TECH_ID)},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_assign_ticket_unassign(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/tickets/{_TICKET_ID}/assign",
            json={"assignee_id": None},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cancel_ticket_admin(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.open)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cancel_already_cancelled(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket(status=TicketStatus.cancelled)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_ticket_client_forbidden(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client)
    ticket = _mock_ticket()
    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/tickets/{_TICKET_ID}")
    assert resp.status_code == 403
