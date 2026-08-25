"""
Tests for User CRUD endpoints.
DB and Redis fully mocked.
"""

import threading
import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
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


# ── Mock user builders ────────────────────────────────────────


def _user(role=UserRole.admin, uid=None, status=UserStatus.active):
    u = MagicMock()
    u.id = uid or uuid.uuid4()
    u.email = f"{role.value}@test.com"
    u.name = f"Test {role.value.capitalize()}"
    u.role = role
    u.status = status
    u.phone = None
    u.department = None
    u.avatar_url = None
    u.last_login = None
    u.lgpd_consent = True
    u.lgpd_consent_at = None
    # Dados de empresa preenchidos no onboarding do cliente — fazem parte do
    # UserResponse, então precisam existir no mock
    u.company_name = None
    u.cnpj = None
    u.company_cep = None
    u.company_address = None
    u.company_city = None
    u.company_state = None
    u.onboarding_completed = True
    from datetime import datetime

    u.created_at = datetime.now(UTC)
    u.updated_at = datetime.now(UTC)
    return u


_ADMIN = _user(UserRole.admin)
_TECH = _user(UserRole.technician)
_CLIENT = _user(UserRole.client)


# ── DB mock helpers ───────────────────────────────────────────


def _db_returning(users_map: dict):
    """
    users_map: {email_or_id: User | None}
    Each execute() call pops the first entry in order.
    """
    calls = list(users_map.values())
    call_iter = iter(calls)

    async def _execute(*args, **kwargs):
        val = next(call_iter, None)
        result = MagicMock()
        result.scalar_one_or_none.return_value = val
        result.scalars.return_value.all.return_value = [val] if val else []
        result.scalar_one.return_value = 1 if val else 0
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return _gen


def _simple_db(user_for_lookup=None):
    """Returns the same user for any execute call."""

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = user_for_lookup
        result.scalars.return_value.all.return_value = [user_for_lookup] if user_for_lookup else []
        result.scalar_one.return_value = 1 if user_for_lookup else 0
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _gen():
        yield session

    return _gen


# ── Client fixture factory ────────────────────────────────────


def _make_client(actor: MagicMock, db_override):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = db_override
    token = create_access_token(actor.id, actor.role.value, actor.email)
    headers = {"Authorization": f"Bearer {token}"}
    return headers


# ── Tests ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


# POST /users


@pytest.mark.asyncio
async def test_create_user_as_admin(patch_redis):
    db = _simple_db(None)  # email not found → can create
    from app.core.database import get_db

    app.dependency_overrides[get_db] = db

    # Override get_current_user to return admin
    from app.core.security import get_current_user

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/users",
            json={
                "name": "New Client",
                "email": "newclient@test.com",
                "password": "Secret1234",
                "role": "client",
                "lgpd_consent": True,
            },
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_user_as_client_forbidden(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(None)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/users",
            json={
                "name": "Hacker",
                "email": "hacker@test.com",
                "password": "Secret1234",
                "role": "admin",
                "lgpd_consent": True,
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user_duplicate_email(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    # email check returns existing user → conflict
    app.dependency_overrides[get_db] = _simple_db(_CLIENT)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/users",
            json={
                "name": "Dup",
                "email": "dup@test.com",
                "password": "Secret1234",
                "lgpd_consent": True,
            },
        )
    assert resp.status_code == 409


# GET /users/me


@pytest.mark.asyncio
async def test_get_me(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


# GET /users/{id}


@pytest.mark.asyncio
async def test_get_user_admin_sees_anyone(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/users/{target.id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_user_client_blocked_from_other(patch_redis):
    target = _user(UserRole.technician)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _client_user():
        return _CLIENT  # different id from target

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/users/{target.id}")
    assert resp.status_code == 403


# PATCH /users/{id}/status


@pytest.mark.asyncio
async def test_update_status_as_admin(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/users/{target.id}/status",
            json={"status": "inactive"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/users/{_ADMIN.id}/status",
            json={"status": "inactive"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_client_cannot_change_status(patch_redis):
    target = _user(UserRole.technician)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/users/{target.id}/status",
            json={"status": "inactive"},
        )
    assert resp.status_code == 403


# GET /users (list)


@pytest.mark.asyncio
async def test_list_users_as_admin(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_CLIENT)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users")
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_list_users_as_client_forbidden(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(None)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users")
    assert resp.status_code == 403


# ── Helper: two-step DB (user lookup + scalar count) ─────────


def _db_two_step(first_user, count_value: int = 0):
    """First execute returns a user; second returns a scalar count."""
    calls = iter([first_user, count_value])

    async def _execute(*args, **kwargs):
        val = next(calls, None)
        result = MagicMock()
        if isinstance(val, int):
            result.scalar_one_or_none.return_value = None
            result.scalar_one.return_value = val
        else:
            result.scalar_one_or_none.return_value = val
            result.scalar_one.return_value = 1 if val else 0
        result.scalars.return_value.all.return_value = (
            [val] if val and not isinstance(val, int) else []
        )
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()

    async def _gen():
        yield session

    return _gen


# GET /users/{id} — 404


@pytest.mark.asyncio
async def test_get_user_not_found(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(None)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/users/{uuid.uuid4()}")
    assert resp.status_code == 404


# PATCH /users/{id}/status — 404


@pytest.mark.asyncio
async def test_update_status_user_not_found(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    target_id = uuid.uuid4()
    app.dependency_overrides[get_db] = _simple_db(None)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{target_id}/status", json={"status": "inactive"})
    assert resp.status_code == 404


# PATCH /users/me/lgpd-consent


@pytest.mark.asyncio
async def test_update_lgpd_consent(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_CLIENT)

    async def _client_user():
        return _CLIENT

    app.dependency_overrides[get_current_user] = _client_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/lgpd-consent", json={"lgpd_consent": True})
    assert resp.status_code == 200


# PATCH /users/{id} — admin updates another user


@pytest.mark.asyncio
async def test_update_user_as_admin(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/users/{target.id}", json={"name": "Nome Atualizado"})
    assert resp.status_code == 200


# POST /users/{id}/anonymize — success


@pytest.mark.asyncio
async def test_anonymize_user(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/users/{target.id}/anonymize")
    assert resp.status_code == 200


# POST /users/{id}/anonymize — cannot anonymize self


@pytest.mark.asyncio
async def test_anonymize_self_blocked(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/users/{_ADMIN.id}/anonymize")
    assert resp.status_code == 400


# POST /users/{id}/anonymize — already anonymized → 409


@pytest.mark.asyncio
async def test_anonymize_already_anonymized(patch_redis):
    target = _user(UserRole.client, status=UserStatus.anonymized)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(target)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/users/{target.id}/anonymize")
    assert resp.status_code == 409


# DELETE /users/{id} — success (no tickets)


@pytest.mark.asyncio
async def test_delete_user_success(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    # First execute: returns user; second: count = 0 tickets
    app.dependency_overrides[get_db] = _db_two_step(target, count_value=0)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{target.id}")
    assert resp.status_code == 204


# DELETE /users/{id} — cannot delete self


@pytest.mark.asyncio
async def test_delete_self_blocked(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _simple_db(_ADMIN)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{_ADMIN.id}")
    assert resp.status_code == 400


# DELETE /users/{id} — user has tickets → 409


@pytest.mark.asyncio
async def test_delete_user_has_tickets(patch_redis):
    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    # First execute: returns user; second: count = 3 tickets
    app.dependency_overrides[get_db] = _db_two_step(target, count_value=3)

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{target.id}")
    assert resp.status_code == 409


# PATCH /users/me/onboarding — CNPJ e CEP obrigatórios


def _onboarding_body(**overrides):
    body = {
        "company_name": "Health & Safety LTDA",
        "cnpj": "08.857.492/0001-48",
        "company_cep": "50070-000",
        "company_address": "Rua Viscondessa do Livramento, 54",
        "company_city": "Recife",
        "company_state": "PE",
    }
    body.update(overrides)
    return body


def _override_client(user):
    from app.core.security import get_current_user

    async def _current():
        return user

    app.dependency_overrides[get_current_user] = _current


@pytest.mark.asyncio
async def test_onboarding_completo_salva_dados(patch_redis):
    from app.core.database import get_db

    client_user = _user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_client(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/onboarding", json=_onboarding_body())

    assert resp.status_code == 200
    # A máscara é removida antes de gravar
    assert client_user.cnpj == "08857492000148"
    assert client_user.company_cep == "50070000"


@pytest.mark.asyncio
async def test_onboarding_sem_cnpj_e_rejeitado(patch_redis):
    from app.core.database import get_db

    client_user = _user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_client(client_user)

    body = _onboarding_body()
    body.pop("cnpj")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/onboarding", json=body)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_onboarding_sem_cep_e_rejeitado(patch_redis):
    from app.core.database import get_db

    client_user = _user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_client(client_user)

    body = _onboarding_body()
    body.pop("company_cep")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/onboarding", json=body)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_onboarding_com_cnpj_incompleto_e_rejeitado(patch_redis):
    from app.core.database import get_db

    client_user = _user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_client(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/onboarding", json=_onboarding_body(cnpj="123"))

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_onboarding_com_cep_incompleto_e_rejeitado(patch_redis):
    from app.core.database import get_db

    client_user = _user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(client_user)
    _override_client(client_user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            "/api/v1/users/me/onboarding", json=_onboarding_body(company_cep="5007")
        )

    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# BCRYPT FORA DO EVENT LOOP
# ═══════════════════════════════════════════════════════════════
#
# hash_password e verify_password são síncronos e custam ~250 ms cada. Rodando
# direto no endpoint async, travam o event loop e com ele todas as requisições
# em voo. Os testes comparam a thread do bcrypt com a do event loop — medir
# tempo seria instável.


@pytest.mark.asyncio
async def test_create_user_hashes_password_off_the_event_loop(patch_redis):
    from app.core.database import get_db
    from app.core.security import get_current_user
    from tests.conftest import EspiaDeThread

    app.dependency_overrides[get_db] = _simple_db(None)  # e-mail livre

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    espia = EspiaDeThread(retorno="hash-falso")
    thread_do_loop = threading.get_ident()

    with patch("app.routers.users.hash_password", new=espia):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/users",
                json={
                    "name": "New Client",
                    "email": "newclient@test.com",
                    "password": "Secret1234",
                    "role": "client",
                    "lgpd_consent": True,
                },
            )

    assert resp.status_code == 201, resp.text
    assert espia.rodou_fora_da_thread(
        thread_do_loop
    ), "o hash da senha rodou na thread do event loop — cada cadastro trava a API"


@pytest.mark.asyncio
async def test_change_password_runs_bcrypt_off_the_event_loop(patch_redis):
    """Troca de senha faz duas operações de bcrypt: conferir a atual e hashear a nova."""
    from app.core.database import get_db
    from app.core.security import get_current_user
    from tests.conftest import EspiaDeThread

    alvo = _user(UserRole.client)
    app.dependency_overrides[get_db] = _simple_db(alvo)

    async def _actor():
        return alvo

    app.dependency_overrides[get_current_user] = _actor

    espia_verify = EspiaDeThread(retorno=True)
    espia_hash = EspiaDeThread(retorno="hash-novo")
    thread_do_loop = threading.get_ident()

    with (
        patch("app.routers.users.verify_password", new=espia_verify),
        patch("app.routers.users.hash_password", new=espia_hash),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/users/me/change-password",
                json={"current_password": "Secret1234", "new_password": "NovaSenha1"},
            )

    assert resp.status_code == 204, resp.text
    assert espia_verify.rodou_fora_da_thread(thread_do_loop), "verify_password no event loop"
    assert espia_hash.rodou_fora_da_thread(thread_do_loop), "hash_password no event loop"


# ═══════════════════════════════════════════════════════════════
# DELETE /users/{id} — a guarda precisa cobrir o que o banco recusa
# ═══════════════════════════════════════════════════════════════


def _db_contagens(user, *contagens, erro_no_delete=None):
    """Sessão que devolve o usuário e depois uma sequência de COUNTs."""
    valores = iter(contagens)

    async def _execute(*args, **kwargs):
        result = MagicMock()
        if not hasattr(_execute, "_deu_usuario"):
            _execute._deu_usuario = True
            result.scalar_one_or_none.return_value = user
            result.scalar_one.return_value = 1
            return result
        result.scalar_one_or_none.return_value = None
        result.scalar_one.return_value = next(valores, 0)
        return result

    session = AsyncMock()
    session.execute = _execute
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    if erro_no_delete is not None:
        session.commit = AsyncMock(side_effect=erro_no_delete)
    return session


def _override(session):
    async def _gen():
        yield session

    return _gen


@pytest.mark.asyncio
async def test_delete_bloqueia_tecnico_com_chamados_atribuidos(patch_redis):
    """
    A guarda contava só Ticket.creator_id. Um técnico que nunca abriu chamado,
    mas tem dez atribuídos, passava pela verificação e ia bater na FK — que não
    tem ondelete. Sem except, isso vira 500, e um 500 num DELETE não diz ao
    admin o que fazer.
    """
    target = _user(UserRole.technician)
    from app.core.database import get_db
    from app.core.security import get_current_user

    # criador: 0 chamados; atribuído: 3
    app.dependency_overrides[get_db] = _override(_db_contagens(target, 0, 3))

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{target.id}")

    assert resp.status_code == 409
    detalhe = resp.json()["detail"]
    assert "anonimiz" in detalhe.lower(), f"a mensagem não diz o que fazer: {detalhe}"


@pytest.mark.asyncio
async def test_delete_devolve_409_legivel_quando_o_banco_recusa(patch_redis):
    """
    Rede de segurança: mesmo que a contagem não cubra alguma referência nova,
    o IntegrityError precisa virar 409 explicado, não 500.
    """
    from sqlalchemy.exc import IntegrityError

    target = _user(UserRole.client)
    from app.core.database import get_db
    from app.core.security import get_current_user

    erro = IntegrityError("DELETE", {}, Exception("violates foreign key constraint"))
    app.dependency_overrides[get_db] = _override(
        _db_contagens(target, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, erro_no_delete=erro)
    )

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{target.id}")

    assert resp.status_code == 409
    assert "anonimiz" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_diz_quantos_e_de_que_tipo(patch_redis):
    """A mensagem tem de servir para agir, não só para recusar."""
    target = _user(UserRole.technician)
    from app.core.database import get_db
    from app.core.security import get_current_user

    app.dependency_overrides[get_db] = _override(_db_contagens(target, 2, 0, 0, 0, 0, 0, 0, 5))

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/v1/users/{target.id}")

    assert resp.status_code == 409
    detalhe = resp.json()["detail"]
    assert "2" in detalhe and "5" in detalhe, f"não diz quantos: {detalhe}"


@pytest.mark.asyncio
async def test_lista_de_tecnicos_nao_mente_o_limit(patch_redis):
    """
    A resposta trazia limit=100, offset=0 fixos sobre uma query SEM limit.
    Com mais de 100 técnicos, o cliente leria "100 de N" e concluiria que há
    outra página — que não existe, porque a rota devolve tudo.
    """
    from app.core.database import get_db
    from app.core.security import get_current_user

    tecnicos = [_user(UserRole.technician) for _ in range(3)]

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.scalars.return_value.all.return_value = tecnicos
        return result

    session = AsyncMock()
    session.execute = _execute

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen

    async def _admin():
        return _ADMIN

    app.dependency_overrides[get_current_user] = _admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/users/technicians")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 3
    assert corpo["offset"] == 0
    assert corpo["limit"] == 3, "limit precisa refletir o que a resposta traz"
    assert (
        corpo["offset"] + len(corpo["items"]) >= corpo["total"]
    ), "não pode sugerir próxima página"
