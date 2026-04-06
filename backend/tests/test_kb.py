"""
Tests for Knowledge Base endpoints (T52 — Sprint 6 integration tests).
DB and Redis fully mocked.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import KBArticleStatus, TicketCategory, UserRole, UserStatus

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
_ARTICLE_ID = uuid.uuid4()
_AUTHOR_ID = uuid.uuid4()
_TICKET_ID = uuid.uuid4()


# ── Mock builders ─────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = f"{role.value}_user"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_article(
    status=KBArticleStatus.published,
    category=TicketCategory.hardware,
    article_id=None,
):
    a = MagicMock()
    a.id = article_id or _ARTICLE_ID
    a.title = "Como resolver falha no bafômetro"
    a.content = "Verifique a conexão de energia e reinicie o dispositivo."
    a.slug = "como-resolver-falha-no-bafometro"
    a.category = category
    a.tags = ["bafômetro", "hardware"]
    a.status = status
    a.author_id = _AUTHOR_ID
    a.author = _mock_user(UserRole.technician, _AUTHOR_ID)
    a.view_count = 10
    a.helpful = 5
    a.not_helpful = 1
    a.created_at = _NOW
    a.updated_at = _NOW
    return a


def _mock_ticket():
    t = MagicMock()
    t.id = _TICKET_ID
    t.title = "Bafômetro com defeito"
    t.category = TicketCategory.hardware
    return t


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
# LIST ARTICLES
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_articles_returns_published(patch_redis):
    """GET /kb/articles returns published articles for clients."""
    client_user = _mock_user(UserRole.client)
    article = _mock_article()

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(1, [article])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/kb/articles")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == article.title


@pytest.mark.asyncio
async def test_list_articles_staff_sees_all_statuses(patch_redis):
    """Staff can filter by status including draft."""
    tech = _mock_user(UserRole.technician)
    draft = _mock_article(status=KBArticleStatus.draft)

    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(1, [draft])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/kb/articles?status=draft")

    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# CREATE ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_article_technician_success(patch_redis):
    """Technician can create a KB article."""
    tech = _mock_user(UserRole.technician, _AUTHOR_ID)
    article = _mock_article(status=KBArticleStatus.draft)

    _override_user(tech)
    from app.core.database import get_db

    # slug uniqueness check returns None (slug available), then article after creation
    app.dependency_overrides[get_db] = _db_seq_override(None, article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Como resolver falha no bafômetro",
                "content": "Verifique a conexão de energia.",
                "category": "hardware",
                "tags": ["bafômetro"],
                "status": "draft",
            },
        )

    assert r.status_code == 201
    assert r.json()["title"] == article.title


@pytest.mark.asyncio
async def test_create_article_client_forbidden(patch_redis):
    """Client cannot create KB articles (403)."""
    client_user = _mock_user(UserRole.client)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={
                "title": "Teste",
                "content": "Conteúdo",
                "category": "general",
                "tags": [],
                "status": "draft",
            },
        )

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_article_missing_title_rejected(patch_redis):
    """Missing title should fail validation (422)."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/v1/kb/articles",
            json={"content": "Conteúdo sem título", "category": "general"},
        )

    assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════
# GET ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_article_increments_view_count(patch_redis):
    """GET /kb/articles/{id} returns the article and increments view_count."""
    tech = _mock_user(UserRole.technician)
    article = _mock_article()

    _override_user(tech)
    from app.core.database import get_db

    session = _db_sequence(article)
    # Also mock the UPDATE for view_count
    session.execute = AsyncMock(
        side_effect=[
            _make_result(article),
            _make_result(None),  # UPDATE result
        ]
    )

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 200
    assert r.json()["id"] == str(_ARTICLE_ID)


def _make_result(obj):
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    result.scalar_one.return_value = 0
    result.scalars.return_value.all.return_value = [obj] if obj else []
    return result


@pytest.mark.asyncio
async def test_get_article_not_found(patch_redis):
    """Returns 404 for non-existent article."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/{uuid.uuid4()}")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_draft_article_client_forbidden(patch_redis):
    """Client cannot see draft articles (404)."""
    client_user = _mock_user(UserRole.client)
    draft_article = _mock_article(status=KBArticleStatus.draft)

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(draft_article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# UPDATE ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_article_success(patch_redis):
    """Technician can update a KB article."""
    tech = _mock_user(UserRole.technician)
    article = _mock_article()

    _override_user(tech)
    from app.core.database import get_db

    # get article (scalar_one_or_none), then reload after update (scalar_one)
    # no title in payload → no slug check execute
    app.dependency_overrides[get_db] = _db_seq_override(article, article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.patch(
            f"/api/v1/kb/articles/{_ARTICLE_ID}",
            json={"status": "published"},
        )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_update_article_client_forbidden(patch_redis):
    """Client cannot update KB articles (403)."""
    client_user = _mock_user(UserRole.client)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.patch(
            f"/api/v1/kb/articles/{_ARTICLE_ID}",
            json={"status": "published"},
        )

    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# DELETE (ARCHIVE) ARTICLE
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_article_admin_archives(patch_redis):
    """Admin can archive (DELETE) a KB article — returns 204."""
    admin = _mock_user(UserRole.admin)
    article = _mock_article()

    _override_user(admin)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_article_technician_forbidden(patch_redis):
    """Technician cannot archive articles (403)."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.delete(f"/api/v1/kb/articles/{_ARTICLE_ID}")

    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# FEEDBACK
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_feedback_helpful(patch_redis):
    """POST /kb/articles/{id}/feedback with helpful=true returns 204."""
    client_user = _mock_user(UserRole.client)
    article = _mock_article()

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/kb/articles/{_ARTICLE_ID}/feedback",
            json={"helpful": True},
        )

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_feedback_not_helpful(patch_redis):
    """POST /kb/articles/{id}/feedback with helpful=false returns 204."""
    client_user = _mock_user(UserRole.client)
    article = _mock_article()

    _override_user(client_user)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(article)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/api/v1/kb/articles/{_ARTICLE_ID}/feedback",
            json={"helpful": False},
        )

    assert r.status_code == 204


# ═══════════════════════════════════════════════════════════════
# SUGGESTIONS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_suggestions_requires_staff(patch_redis):
    """Client cannot access suggestions endpoint (403)."""
    client_user = _mock_user(UserRole.client)
    _override_user(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={_TICKET_ID}")

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_suggestions_ticket_not_found(patch_redis):
    """Returns 404 when ticket does not exist."""
    tech = _mock_user(UserRole.technician)
    _override_user(tech)
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_seq_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={uuid.uuid4()}")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_suggestions_returns_articles(patch_redis):
    """Returns matching KB articles for a ticket's category."""
    tech = _mock_user(UserRole.technician)
    ticket = _mock_ticket()
    article = _mock_article(category=TicketCategory.hardware)

    _override_user(tech)
    from app.core.database import get_db

    # ticket lookup, then 3 suggestion queries
    app.dependency_overrides[get_db] = _db_seq_override(ticket, [article], [], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/kb/articles/suggestions?ticket_id={_TICKET_ID}")

    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 1
