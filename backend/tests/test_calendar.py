"""
Tests da agenda da equipe (calendar events).
DB e Redis totalmente mockados.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.models import CalendarEventType, UserRole, UserStatus

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
_EVENT_ID = uuid.uuid4()
_CREATOR_ID = uuid.uuid4()


# ── Mocks ─────────────────────────────────────────────────────


def _mock_user(role=UserRole.technician, user_id=None):
    u = MagicMock()
    u.id = user_id or uuid.uuid4()
    u.name = f"{role.value}_user"
    u.email = f"{role.value}@test.com"
    u.role = role
    u.status = UserStatus.active
    return u


def _mock_event(created_by=_CREATOR_ID):
    e = MagicMock()
    e.id = _EVENT_ID
    e.title = "Treinamento de bafômetros"
    e.description = "Sala 201"
    e.event_type = CalendarEventType.training
    e.color = "#10b981"
    e.start_date = _NOW
    e.end_date = _NOW + timedelta(days=1)
    e.created_by = created_by
    e.creator = None
    # O response lê este atributo direto do objeto; sem valor explícito o
    # MagicMock devolveria um objeto e a validação falharia
    e.creator_name = None
    e.created_at = _NOW
    e.updated_at = _NOW
    return e


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


def _event_body(**overrides):
    body = {
        "title": "Treinamento de bafômetros",
        "description": "Sala 201",
        "event_type": "training",
        "color": "#10b981",
        "start_date": _NOW.isoformat(),
        "end_date": (_NOW + timedelta(days=1)).isoformat(),
    }
    body.update(overrides)
    return body


# ── GET /calendar/events ──────────────────────────────────────


@pytest.mark.asyncio
async def test_tecnico_lista_eventos(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event()
    creator = _mock_user(UserRole.admin, user_id=_CREATOR_ID)
    # 1ª query: eventos · 2ª query: autores
    app.dependency_overrides[get_db] = _db_override([event], [creator])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["creator_name"] == creator.name


@pytest.mark.asyncio
async def test_lista_eventos_filtrando_por_mes(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override([], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events?year=2026&month=8")

    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_lista_eventos_em_dezembro_vira_o_ano(patch_redis):
    """Dezembro precisa terminar em janeiro do ano seguinte."""
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override([], [])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events?year=2026&month=12")

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_cliente_nao_acessa_a_agenda(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override([])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/calendar/events")

    assert r.status_code == 403


# ── POST /calendar/events ─────────────────────────────────────


@pytest.mark.asyncio
async def test_criar_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=_event_body())

    assert r.status_code == 201
    assert r.json()["title"] == "Treinamento de bafômetros"


@pytest.mark.asyncio
async def test_criar_evento_com_fim_antes_do_inicio_e_rejeitado(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    body = _event_body(end_date=(_NOW - timedelta(days=2)).isoformat())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=body)

    assert r.status_code == 422
    assert "data de fim" in r.json()["detail"]


@pytest.mark.asyncio
async def test_cliente_nao_cria_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/calendar/events", json=_event_body())

    assert r.status_code == 403


# ── PATCH /calendar/events/{id} ───────────────────────────────


@pytest.mark.asyncio
async def test_editar_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event()
    creator = _mock_user(UserRole.admin, user_id=_CREATOR_ID)
    # 1ª query: evento · 2ª query: autor
    app.dependency_overrides[get_db] = _db_override(event, creator)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={"title": "Treinamento remarcado", "color": "#ef4444"},
        )

    assert r.status_code == 200
    assert event.title == "Treinamento remarcado"
    assert event.color == "#ef4444"


@pytest.mark.asyncio
async def test_editar_todos_os_campos_do_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    novo_inicio = _NOW + timedelta(days=7)
    novo_fim = _NOW + timedelta(days=8)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={
                "title": "Reunião de equipe",
                "description": "Pauta: metas do trimestre",
                "event_type": "meeting",
                "color": "#3b82f6",
                "start_date": novo_inicio.isoformat(),
                "end_date": novo_fim.isoformat(),
            },
        )

    assert r.status_code == 200
    assert event.description == "Pauta: metas do trimestre"
    assert event.event_type == CalendarEventType.meeting
    assert event.start_date == novo_inicio
    assert event.end_date == novo_fim


@pytest.mark.asyncio
async def test_editar_evento_inexistente_retorna_404(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{uuid.uuid4()}", json={"title": "X"})

    assert r.status_code == 404
    assert "não encontrado" in r.json()["detail"]


@pytest.mark.asyncio
async def test_editar_evento_invertendo_as_datas_e_rejeitado(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    event = _mock_event()
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={"end_date": (_NOW - timedelta(days=3)).isoformat()},
        )

    assert r.status_code == 422


# ── DELETE /calendar/events/{id} ──────────────────────────────


@pytest.mark.asyncio
async def test_excluir_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    app.dependency_overrides[get_db] = _db_override(_mock_event())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/calendar/events/{_EVENT_ID}")

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_excluir_evento_inexistente_retorna_404(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.admin))
    app.dependency_overrides[get_db] = _db_override(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/calendar/events/{uuid.uuid4()}")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cliente_nao_exclui_evento(patch_redis):
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.client))
    app.dependency_overrides[get_db] = _db_override(_mock_event())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete(f"/api/v1/calendar/events/{_EVENT_ID}")

    assert r.status_code == 403


# ── Nulo explicito no PATCH ─────────────────────────────────


@pytest.mark.asyncio
async def test_descricao_nula_apaga_a_descricao(patch_redis):
    """Limpar o campo de descrição precisa apagar o texto.

    O front manda `description.trim() || null` — nulo explícito — quando a
    pessoa esvazia o campo. O router testava `body.description is not None`,
    que não distingue "campo ausente" de "campo enviado como nulo": o nulo era
    ignorado, o texto antigo ficava no banco e reaparecia no próximo
    carregamento, como se a edição não tivesse acontecido.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(f"/api/v1/calendar/events/{_EVENT_ID}", json={"description": None})

    assert r.status_code == 200
    assert event.description is None


@pytest.mark.asyncio
async def test_descricao_ausente_nao_e_apagada(patch_redis):
    """A correção não pode transformar PATCH em PUT.

    Quem edita só o título não está pedindo para apagar a descrição — e um
    `event.description = body.description` incondicional faria exatamente
    isso, trocando um bug por outro pior.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}", json={"title": "Só o título mudou"}
        )

    assert r.status_code == 200
    assert event.title == "Só o título mudou"
    assert event.description == "Sala 201", "a descrição sumiu sem ninguém ter pedido"


@pytest.mark.asyncio
async def test_nulo_em_campo_not_null_continua_ignorado(patch_redis):
    """Só `description` é nullable no modelo (models.py:873-893).

    `title`, `event_type`, `color`, `start_date` e `end_date` são NOT NULL —
    para eles, ignorar o nulo está certo. Este teste existe para reprovar quem
    "uniformizar" os seis campos: aceitar nulo neles trocaria um bug de
    usabilidade por um erro de integridade no banco.
    """
    from app.core.database import get_db

    _override_user(_mock_user(UserRole.technician))
    event = _mock_event(created_by=None)
    app.dependency_overrides[get_db] = _db_override(event)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.patch(
            f"/api/v1/calendar/events/{_EVENT_ID}",
            json={"title": None, "color": None, "event_type": None},
        )

    assert r.status_code == 200
    assert event.title == "Treinamento de bafômetros"
    assert event.color == "#10b981"
    assert event.event_type == CalendarEventType.training
