"""
Tests for JWT authentication endpoints.
All database and Redis calls are mocked — no external dependencies needed.
"""

import threading
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from app.main import app
from app.models.models import UserRole, UserStatus

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_ID = uuid.uuid4()
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "Test@123456"
_HASHED = _pwd.hash(ADMIN_PASSWORD)

# A mesma resposta para senha errada e para e-mail inexistente: distinguir os
# dois casos entregaria de graça quais e-mails têm conta
_DETALHE_CREDENCIAIS = "E-mail ou senha incorretos."


def _make_user(status=UserStatus.active):
    """Build a mock User object that satisfies attribute lookups without ORM."""
    user = MagicMock()
    user.id = ADMIN_ID
    user.email = ADMIN_EMAIL
    user.name = "Test Admin"
    user.password = _HASHED
    user.role = UserRole.admin
    user.status = status
    user.lgpd_consent = True
    # Conta antiga, de antes da confirmação de e-mail — o login não deve exigir
    user.email_verified = True
    return user


# ── In-memory Redis ───────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def setex(self, key, ttl, value):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        self._store.pop(key, None)

    async def exists(self, key):
        return 1 if key in self._store else 0


_fake_redis = _FakeRedis()


async def _get_fake_redis():
    return _fake_redis


# ── DB session mock factory ───────────────────────────────────


def _make_db_mock(user):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _gen():
        yield session

    return _gen


# ── Client fixtures ───────────────────────────────────────────


@pytest.fixture()
async def client_ok():
    """Client with a valid active user in the DB."""
    _fake_redis._store.clear()
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _make_db_mock(_make_user())

    with patch("app.core.security.get_redis", new=_get_fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture()
async def client_no_user():
    """Client where DB returns no user (login should fail)."""
    _fake_redis._store.clear()
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _make_db_mock(None)

    with patch("app.core.security.get_redis", new=_get_fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(client_ok):
    response = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    # O TTL vem da configuração; comparar com ela evita quebrar o teste toda vez
    # que a política de expiração muda
    from app.core.config import get_settings

    assert data["expires_in"] == get_settings().jwt_access_token_expires_minutes * 60


@pytest.mark.asyncio
async def test_login_wrong_password(client_ok):
    response = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == _DETALHE_CREDENCIAIS


@pytest.mark.asyncio
async def test_login_unknown_user(client_no_user):
    response = await client_no_user.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 401
    # Mesmo detalhe do teste acima: a mensagem não distingue os dois casos
    assert response.json()["detail"] == _DETALHE_CREDENCIAIS


@pytest.mark.asyncio
async def test_refresh_token(client_ok):
    login_resp = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()

    response = await client_ok.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_invalid_token(client_ok):
    response = await client_ok.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_wrong_token_not_stored(client_ok):
    """Refresh token not in Redis (e.g. user already logged out)."""
    _fake_redis._store.clear()

    from app.core.security import create_refresh_token

    forged = create_refresh_token(ADMIN_ID)

    response = await client_ok.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": forged},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(client_ok):
    login_resp = await client_ok.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    access_token = login_resp.json()["access_token"]

    response = await client_ok.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_no_token_returns_401(client_ok):
    """Logout endpoint (protected by get_current_user) should 401 without token."""
    response = await client_ok.post("/api/v1/auth/logout")
    assert response.status_code == 401


# ── Enumeração por tempo de resposta ──────────────────────────
#
# O login não revela pela mensagem se a conta existe, mas revelava pelo
# relógio: com `user is None`, o short-circuit pulava o bcrypt e a resposta
# saía em ~1 ms, contra ~250 ms de um e-mail cadastrado (BCRYPT_ROUNDS=12).
#
# O teste não cronometra nada — medir tempo seria instável. Ele afirma que o
# caminho "usuário inexistente" executa a verificação de senha, que é o que
# iguala o custo dos dois caminhos.


@pytest.mark.asyncio
async def test_login_unknown_user_still_verifies_password(client_no_user):
    """E-mail inexistente também paga o custo do bcrypt (contra enumeração por tempo)."""
    with patch("app.routers.auth.verify_password", return_value=False) as verificacao:
        response = await client_no_user.post(
            "/api/v1/auth/login",
            json={"email": "nobody@test.com", "password": ADMIN_PASSWORD},
        )

    assert response.status_code == 401
    assert verificacao.called, (
        "com usuário inexistente o bcrypt precisa rodar assim mesmo; sem isso o "
        "tempo de resposta denuncia quais e-mails têm conta"
    )


def _custo_do_hash(hash_bcrypt: str) -> str:
    """Cost (número de rounds) declarado no prefixo `$2b$NN$` do hash."""
    return hash_bcrypt.split("$")[2]


def test_bcrypt_rounds_setting_reaches_the_context():
    """
    `BCRYPT_ROUNDS` precisa chegar ao `pwd_context`.

    A variável estava documentada no `.env.example` e lida pelo `Settings`, mas
    ninguém a passava para o passlib: o custo real era sempre o default da
    biblioteca. Quem subisse com `BCRYPT_ROUNDS=14` no painel acharia ter
    endurecido o hash das senhas e não teria mudado nada — configuração que
    finge proteger.
    """
    from app.core.config import get_settings
    from app.core.security import pwd_context

    assert pwd_context.to_dict().get("bcrypt__rounds") == get_settings().bcrypt_rounds


def test_dummy_hash_cost_matches_the_real_one():
    """
    O hash descartável precisa custar o mesmo que um hash de verdade.

    A defesa contra enumeração por tempo depende disso: se o dummy ficar mais
    barato que o hash das senhas reais, o e-mail inexistente volta a responder
    mais rápido e o oráculo reabre — sem que nenhum outro teste perceba.

    O lado direito é gerado pelo `pwd_context` já configurado, então a
    comparação é contra o custo EFETIVO: subir `BCRYPT_ROUNDS` sem regerar o
    dummy deixa este teste vermelho, que é exatamente o aviso desejado.
    """
    from app.core.security import DUMMY_PASSWORD_HASH, hash_password

    real = hash_password("SenhaDeReferencia1")

    assert _custo_do_hash(DUMMY_PASSWORD_HASH) == _custo_do_hash(real)


@pytest.mark.asyncio
async def test_login_verifies_password_off_the_event_loop(client_no_user):
    """
    O bcrypt não pode rodar no event loop.

    `verify_password` é síncrono e custa ~250 ms; executado direto no endpoint
    async, ele trava o loop e, com ele, todas as outras requisições em voo — o
    hash de custo igualado (contra enumeração por tempo) estendeu esse bloqueio
    também ao caminho do e-mail inexistente.

    O teste não mede tempo: compara a thread onde a verificação rodou com a
    thread do event loop.
    """
    thread_do_loop = threading.get_ident()
    threads_da_verificacao: list[int] = []

    def _verificacao_falsa(*_args, **_kwargs):
        threads_da_verificacao.append(threading.get_ident())
        return False

    with patch("app.routers.auth.verify_password", new=_verificacao_falsa):
        response = await client_no_user.post(
            "/api/v1/auth/login",
            json={"email": "nobody@test.com", "password": ADMIN_PASSWORD},
        )

    assert response.status_code == 401
    assert threads_da_verificacao, "a verificação de senha nem foi executada"
    assert thread_do_loop not in threads_da_verificacao, (
        "o bcrypt rodou na thread do event loop — cada login bloqueia a API " "inteira por ~250 ms"
    )


# A igualdade das mensagens é conferida em test_login_wrong_password e
# test_login_unknown_user, que já exercitam os dois cenários com as fixtures do
# arquivo — não vale um terceiro teste reimplementando o harness e pagando dois
# bcrypts reais para reafirmar o mesmo.
