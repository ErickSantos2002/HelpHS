"""
Tests for Chat REST endpoints (T52 — Sprint 6 integration tests).
WebSocket is tested at the unit level; REST endpoints are fully mocked.
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
_MSG_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = f"{role.value}_user"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_ticket(creator_id=None):
    t = MagicMock()
    t.id = _TICKET_ID
    t.protocol = "HS-2026-0001"
    t.title = "Falha no bafômetro"
    t.description = "Dispositivo não inicializa"
    t.status = TicketStatus.open
    t.priority = TicketPriority.medium
    t.category = TicketCategory.hardware
    t.creator_id = creator_id or _CREATOR_ID
    t.assignee_id = _TECH_ID
    t.ai_conversation_summary = None
    t.updated_at = _NOW
    return t


def _mock_message(sender=None):
    msg = MagicMock()
    msg.id = _MSG_ID
    msg.ticket_id = _TICKET_ID
    msg.sender_id = _TECH_ID
    msg.content = "Olá, vou analisar o problema."
    msg.is_system = False
    msg.is_ai = False
    msg.read_at = None
    msg.created_at = _NOW
    msg.sender = sender or _mock_user()
    return msg


# ── DB helpers ────────────────────────────────────────────────


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
            result.scalar_one.return_value = resp
            result.scalars.return_value.all.return_value = [resp] if resp else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


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
# LIST MESSAGES
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_messages_returns_history(patch_redis):
    """GET /tickets/{id}/messages returns paginated message list."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 1, [msg])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{_TICKET_ID}/messages")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["content"] == msg.content


@pytest.mark.asyncio
async def test_list_messages_client_own_ticket(patch_redis):
    """Client can list messages for their own ticket."""
    client_user = _mock_user(UserRole.client, _CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    msg = _mock_message(sender=client_user)

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, 1, [msg])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{_TICKET_ID}/messages")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_list_messages_client_other_ticket_forbidden(patch_redis):
    """Client cannot list messages for another user's ticket."""
    other_id = uuid.uuid4()
    client_user = _mock_user(UserRole.client, other_id)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)  # owned by CREATOR_ID

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{_TICKET_ID}/messages")

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_messages_ticket_not_found(patch_redis):
    """Returns 404 when ticket does not exist."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/tickets/{uuid.uuid4()}/messages")

    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# CREATE MESSAGE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_message_technician(patch_redis):
    """Technician can post a message to a ticket."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, msg)

    with patch("app.routers.chat.notify", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                f"/api/v1/tickets/{_TICKET_ID}/messages",
                json={"content": "Olá, vou analisar o problema."},
            )

    assert r.status_code == 201
    assert r.json()["content"] == msg.content


@pytest.mark.asyncio
async def test_create_message_empty_content_rejected(patch_redis):
    """Empty content should be rejected (422)."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/tickets/{_TICKET_ID}/messages",
            json={"content": ""},
        )

    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# SUGGEST REPLY
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_suggest_reply_returns_suggestion(patch_redis):
    """POST /tickets/{id}/suggest-reply returns an AI suggestion."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [msg])

    with patch(
        "app.routers.chat.suggest_reply",
        new=AsyncMock(return_value="Prezado solicitante, identificamos o problema."),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/suggest-reply")

    assert r.status_code == 200
    assert "suggestion" in r.json()
    assert len(r.json()["suggestion"]) > 0


@pytest.mark.asyncio
async def test_suggest_reply_llm_unavailable_returns_503(patch_redis):
    """Returns 503 when LLM returns None."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [msg])

    with patch("app.routers.chat.suggest_reply", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/suggest-reply")

    assert r.status_code == 503


@pytest.mark.asyncio
async def test_suggest_reply_client_forbidden(patch_redis):
    """Clients cannot access suggest-reply (403)."""
    client_user = _mock_user(UserRole.client, _CREATOR_ID)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/suggest-reply")

    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# SUMMARIZE CONVERSATION
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_summarize_returns_summary(patch_redis):
    """POST /tickets/{id}/summarize returns and persists a summary."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()
    msg = _mock_message(sender=tech)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [msg])

    with patch(
        "app.routers.chat.summarize_conversation",
        new=AsyncMock(return_value="O técnico identificou falha no hardware do bafômetro."),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/summarize")

    assert r.status_code == 200
    assert "summary" in r.json()


@pytest.mark.asyncio
async def test_summarize_no_messages_returns_422(patch_redis):
    """Returns 422 when there are no messages to summarize."""
    tech = _mock_user(UserRole.technician, _TECH_ID)
    ticket = _mock_ticket()

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(ticket, [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/summarize")

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_summarize_client_forbidden(patch_redis):
    """Clients cannot access summarize (403)."""
    client_user = _mock_user(UserRole.client, _CREATOR_ID)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/tickets/{_TICKET_ID}/summarize")

    assert r.status_code == 403
