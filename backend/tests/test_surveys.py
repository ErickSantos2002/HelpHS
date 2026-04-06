"""
Tests for CSAT Survey endpoints.
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

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
_SURVEY_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.client, user_id=None):
    u = MagicMock()
    u.id = user_id or _CREATOR_ID
    u.email = "creator@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_ticket(status=TicketStatus.resolved, creator_id=None):
    t = MagicMock()
    t.id = _TICKET_ID
    t.protocol = "HS-2026-0001"
    t.status = status
    t.creator_id = creator_id or _CREATOR_ID
    t.priority = TicketPriority.medium
    t.category = TicketCategory.hardware
    return t


def _mock_survey(rating=5):
    s = MagicMock()
    s.id = _SURVEY_ID
    s.ticket_id = _TICKET_ID
    s.user_id = _CREATOR_ID
    s.rating = rating
    s.comment = "Ótimo atendimento!"
    s.created_at = _NOW
    return s


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
        if isinstance(resp, int) or isinstance(resp, float):
            result.scalar_one.return_value = resp
            result.scalar_one_or_none.return_value = resp
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
# POST /tickets/{id}/survey
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_submit_survey_success(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.resolved, creator_id=_CREATOR_ID)
    survey = _mock_survey(rating=5)

    session = _db_sequence(ticket)

    async def _refresh(obj):
        obj.id = survey.id
        obj.ticket_id = _TICKET_ID
        obj.user_id = _CREATOR_ID
        obj.rating = 5
        obj.comment = "Ótimo atendimento!"
        obj.created_at = _NOW

    session.refresh = _refresh

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/survey",
            json={"rating": 5, "comment": "Ótimo atendimento!"},
        )

    assert resp.status_code == 201
    assert resp.json()["rating"] == 5


@pytest.mark.asyncio
async def test_submit_survey_ticket_not_resolved(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.open, creator_id=_CREATOR_ID)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/survey",
            json={"rating": 4},
        )

    assert resp.status_code == 409
    assert "resolved or closed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_submit_survey_wrong_creator(patch_redis):
    from app.core.database import get_db

    other_client = _mock_user(UserRole.client, user_id=uuid.uuid4())
    ticket = _mock_ticket(status=TicketStatus.resolved, creator_id=_CREATOR_ID)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(other_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/survey",
            json={"rating": 3},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_survey_duplicate(patch_redis):
    """IntegrityError (unique constraint) → 409."""
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(status=TicketStatus.resolved, creator_id=_CREATOR_ID)

    session = _db_sequence(ticket)
    session.commit = AsyncMock(side_effect=IntegrityError("unique", {}, Exception()))

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/survey",
            json={"rating": 4},
        )

    assert resp.status_code == 409
    assert "already submitted" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_submit_survey_invalid_rating(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/tickets/{_TICKET_ID}/survey",
            json={"rating": 6},  # out of range
        )

    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# GET /tickets/{id}/survey
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_survey_by_creator(patch_redis):
    from app.core.database import get_db

    creator = _mock_user(UserRole.client, user_id=_CREATOR_ID)
    ticket = _mock_ticket(creator_id=_CREATOR_ID)
    survey = _mock_survey()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, survey)
    _override_user(creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/survey")

    assert resp.status_code == 200
    assert resp.json()["rating"] == 5


@pytest.mark.asyncio
async def test_get_survey_admin(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()
    survey = _mock_survey()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, survey)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/survey")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_survey_not_found(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    ticket = _mock_ticket()

    app.dependency_overrides[get_db] = _db_seq_override(ticket, None)
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/survey")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_survey_client_other_ticket_forbidden(patch_redis):
    from app.core.database import get_db

    other_client = _mock_user(UserRole.client, user_id=uuid.uuid4())
    ticket = _mock_ticket(creator_id=_CREATOR_ID)

    app.dependency_overrides[get_db] = _db_override(ticket)
    _override_user(other_client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/tickets/{_TICKET_ID}/survey")

    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# GET /surveys (admin/technician list)
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_surveys_admin(patch_redis):
    from app.core.database import get_db

    admin = _mock_user(UserRole.admin)
    survey = _mock_survey()

    # Sequence: count=1, avg=4.5, list=[survey]
    app.dependency_overrides[get_db] = _db_seq_override(1, 4.5, [survey])
    _override_user(admin)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/surveys")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["average_rating"] == 4.5


@pytest.mark.asyncio
async def test_list_surveys_client_forbidden(patch_redis):
    from app.core.database import get_db

    client = _mock_user(UserRole.client)
    app.dependency_overrides[get_db] = _db_override(None)
    _override_user(client)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/surveys")

    assert resp.status_code == 403
