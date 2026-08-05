"""
Tests for Quick Replies (respostas rápidas do chat).
DB e Redis totalmente mockados.
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


_NOW = datetime.now(UTC)
_REPLY_ID = uuid.uuid4()


# ── Mocks ─────────────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = f"{role.value}_user"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_reply(shortcut="bomdia"):
    r = MagicMock()
    r.id = _REPLY_ID
    r.shortcut = shortcut
    r.title = "Saudação inicial"
    r.content = "Bom dia! Sou Gabriel Moura, da equipe de suporte da H&S."
    r.is_active = True
    r.created_by = uuid.uuid4()
    r.created_at = _NOW
    r.updated_at = _NOW
    return r


def _db_sequence(*responses):
    call_count = [0]

    async def _execute(*args, **kwargs):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        resp = responses[idx]

        result = MagicMock()
        if isinstance(resp, list):
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = resp
        else:
            result.scalar_one_or_none.return_value = resp
            result.scalars.return_value.all.return_value = [resp] if resp else []
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _db_override(*responses):
    session = _db_sequence(*responses)

    async def _gen():
        yield session

    return _gen


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

    async def _current():
        return user

    app.dependency_overrides[get_current_user] = _current


# ── GET /quick-replies ────────────────────────────────────────


@pytest.mark.asyncio
async def test_tecnico_lista_respostas_rapidas(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override([_mock_reply()])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/quick-replies")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["shortcut"] == "bomdia"


@pytest.mark.asyncio
async def test_cliente_nao_acessa_respostas_rapidas(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override([])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/quick-replies")

    assert r.status_code == 403


# ── POST /quick-replies ───────────────────────────────────────


@pytest.mark.asyncio
async def test_criar_resposta_rapida(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(None)  # atalho livre

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/quick-replies",
            json={
                "shortcut": "bomdia",
                "title": "Saudação inicial",
                "content": "Bom dia! Como posso ajudar?",
            },
        )

    assert r.status_code == 201
    assert r.json()["shortcut"] == "bomdia"


@pytest.mark.asyncio
async def test_atalho_e_normalizado(patch_redis):
    """A barra e as maiúsculas são removidas do atalho."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/quick-replies",
            json={"shortcut": "/BomDia", "title": "Saudação", "content": "Bom dia!"},
        )

    assert r.status_code == 201
    assert r.json()["shortcut"] == "bomdia"


@pytest.mark.asyncio
async def test_atalho_com_espaco_e_rejeitado(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/quick-replies",
            json={"shortcut": "bom dia", "title": "Saudação", "content": "Bom dia!"},
        )

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_atalho_duplicado_retorna_409(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(_mock_reply())  # já existe

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/quick-replies",
            json={"shortcut": "bomdia", "title": "Outra", "content": "Bom dia!"},
        )

    assert r.status_code == 409
    assert "bomdia" in r.json()["detail"]


@pytest.mark.asyncio
async def test_cliente_nao_cria_resposta_rapida(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/quick-replies",
            json={"shortcut": "oi", "title": "Oi", "content": "Oi!"},
        )

    assert r.status_code == 403


# ── PATCH /quick-replies/{id} ─────────────────────────────────


@pytest.mark.asyncio
async def test_editar_resposta_rapida(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(_mock_reply())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/quick-replies/{_REPLY_ID}",
            json={"content": "Bom dia! Tudo bem?"},
        )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_editar_resposta_inexistente_retorna_404(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/quick-replies/{uuid.uuid4()}", json={"title": "X"})

    assert r.status_code == 404


# ── DELETE /quick-replies/{id} ────────────────────────────────


@pytest.mark.asyncio
async def test_excluir_resposta_rapida(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(_mock_reply())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/quick-replies/{_REPLY_ID}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_cliente_nao_exclui_resposta_rapida(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override(_mock_reply())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/quick-replies/{_REPLY_ID}")

    assert r.status_code == 403
