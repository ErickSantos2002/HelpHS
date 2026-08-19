"""
Testes da confirmação de e-mail e da recuperação de senha.

Dois comportamentos merecem atenção especial aqui:
  - as respostas de "esqueci a senha" e de reenvio são sempre iguais, para não
    revelar quais e-mails existem na base;
  - enquanto o SMTP não estiver configurado, a confirmação não pode bloquear
    ninguém — o cliente ficaria esperando um e-mail que nunca chega.
"""

import threading
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from app.core.config import get_settings
from app.main import app
from app.models.models import UserRole, UserStatus
from app.services import account_tokens

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_settings = get_settings()

_USER_ID = uuid.uuid4()
_EMAIL = "cliente@test.com"
_SENHA_HASH = _pwd.hash("Senha@123456")


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


def _mock_user(email_verified=False, status=UserStatus.active):
    u = MagicMock()
    u.id = _USER_ID
    u.email = _EMAIL
    u.name = "Cliente Teste"
    u.password = _SENHA_HASH
    u.role = UserRole.client
    u.status = status
    u.email_verified = email_verified
    u.email_verified_at = None
    return u


def _db_with(user, get_result="same"):
    """Sessão mock: execute() devolve `user`; get() devolve o mesmo por padrão."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = user

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock(return_value=user if get_result == "same" else get_result)

    async def _gen():
        yield session

    return _gen


@pytest.fixture(autouse=True)
def _limpa():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def smtp_configurado():
    """Simula SMTP presente e intercepta o envio."""
    original = _settings.smtp_from_email
    _settings.smtp_from_email = "naoresponda@healthsafety.com"
    with (
        patch("app.routers.auth.send_verification_email", new=AsyncMock(return_value=True)) as v,
        patch("app.routers.auth.send_password_reset_email", new=AsyncMock(return_value=True)) as p,
    ):
        yield {"verification": v, "reset": p}
    _settings.smtp_from_email = original


@pytest.fixture()
def sem_smtp():
    original = _settings.smtp_from_email
    original_user = _settings.smtp_user
    _settings.smtp_from_email = ""
    _settings.smtp_user = ""
    yield
    _settings.smtp_from_email = original
    _settings.smtp_user = original_user


# ═══════════════════════════════════════════════════════════════
# LOGIN com e-mail não confirmado
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_login_bloqueado_ate_confirmar_o_email(smtp_configurado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(email_verified=False))

    with patch("app.core.security.get_redis", new=_get_fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/auth/login", json={"email": _EMAIL, "password": "Senha@123456"}
            )

    assert r.status_code == 403
    assert "Confirme seu e-mail" in r.json()["detail"]


@pytest.mark.asyncio
async def test_login_liberado_apos_confirmar(smtp_configurado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(email_verified=True))

    with patch("app.core.security.get_redis", new=_get_fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/auth/login", json={"email": _EMAIL, "password": "Senha@123456"}
            )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_sem_smtp_o_login_nao_e_bloqueado(sem_smtp):
    """Sem como enviar e-mail, exigir confirmação deixaria o cliente preso."""
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(email_verified=False))

    with patch("app.core.security.get_redis", new=_get_fake_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/auth/login", json={"email": _EMAIL, "password": "Senha@123456"}
            )

    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# CONFIRMAÇÃO DE E-MAIL
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_confirma_email_com_link_valido(smtp_configurado):
    from app.core.database import get_db

    user = _mock_user(email_verified=False)
    app.dependency_overrides[get_db] = _db_with(user)
    token = account_tokens.create_email_verification_token(_USER_ID, _settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/verify-email", json={"token": token})

    assert r.status_code == 200
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_link_de_confirmacao_invalido_e_recusado():
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/verify-email", json={"token": "token-qualquer-invalido"})

    assert r.status_code == 400


@pytest.mark.asyncio
async def test_confirmar_duas_vezes_nao_da_erro(smtp_configurado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(email_verified=True))
    token = account_tokens.create_email_verification_token(_USER_ID, _settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/verify-email", json={"token": token})

    assert r.status_code == 200
    assert "já estava confirmado" in r.json()["message"]


# ═══════════════════════════════════════════════════════════════
# ESQUECI A SENHA
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_esqueci_senha_envia_o_link(smtp_configurado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(email_verified=True))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/forgot-password", json={"email": _EMAIL})

    assert r.status_code == 200
    smtp_configurado["reset"].assert_awaited_once()


@pytest.mark.asyncio
async def test_esqueci_senha_de_email_inexistente_responde_igual(smtp_configurado):
    """A resposta não pode denunciar quem tem conta no sistema."""
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(None, get_result=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        existente = await c.post("/api/v1/auth/forgot-password", json={"email": _EMAIL})
        inexistente = await c.post(
            "/api/v1/auth/forgot-password", json={"email": "ninguem@test.com"}
        )

    assert existente.status_code == inexistente.status_code == 200
    assert existente.json() == inexistente.json()
    smtp_configurado["reset"].assert_not_awaited()


@pytest.mark.asyncio
async def test_esqueci_senha_sem_smtp_avisa_em_vez_de_prometer(sem_smtp):
    """
    Sem e-mail configurado, responder "você receberá as instruções" deixaria a
    pessoa esperando algo que nunca chega.
    """
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(email_verified=True))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/forgot-password", json={"email": _EMAIL})

    assert r.status_code == 503
    assert "administrador" in r.json()["detail"]


@pytest.mark.asyncio
async def test_reenvio_de_confirmacao_responde_igual_para_email_inexistente(smtp_configurado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(None, get_result=None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/resend-verification", json={"email": "ninguem@test.com"})

    assert r.status_code == 200
    smtp_configurado["verification"].assert_not_awaited()


# ═══════════════════════════════════════════════════════════════
# REDEFINIR A SENHA
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_redefine_a_senha_com_link_valido(smtp_configurado):
    from app.core.database import get_db

    user = _mock_user(email_verified=True)
    app.dependency_overrides[get_db] = _db_with(user)
    token = account_tokens.create_password_reset_token(_USER_ID, _SENHA_HASH, _settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "NovaSenha@123"}
        )

    assert r.status_code == 200
    assert user.password != _SENHA_HASH  # senha trocada


@pytest.mark.asyncio
async def test_link_de_senha_nao_serve_duas_vezes(smtp_configurado):
    """
    Uso único: depois que a senha muda, o mesmo link precisa parar de valer —
    senão um e-mail vazado abriria a conta a qualquer momento.
    """
    from app.core.database import get_db

    user = _mock_user(email_verified=True)
    token = account_tokens.create_password_reset_token(_USER_ID, _SENHA_HASH, _settings)

    # Simula a senha já trocada por esse mesmo link
    user.password = _pwd.hash("NovaSenha@123")
    app.dependency_overrides[get_db] = _db_with(user)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "OutraSenha@123"}
        )

    assert r.status_code == 400
    assert "não é mais válido" in r.json()["detail"]


@pytest.mark.asyncio
async def test_senha_fraca_e_recusada(smtp_configurado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_with(_mock_user(email_verified=True))
    token = account_tokens.create_password_reset_token(_USER_ID, _SENHA_HASH, _settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "semmaiuscula1"}
        )

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_redefinir_senha_confirma_o_email_junto(smtp_configurado):
    """Quem abriu o link provou ser dono da caixa."""
    from app.core.database import get_db

    user = _mock_user(email_verified=False)
    user.email_verified_at = None
    app.dependency_overrides[get_db] = _db_with(user)
    token = account_tokens.create_password_reset_token(_USER_ID, _SENHA_HASH, _settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "NovaSenha@123"}
        )

    assert r.status_code == 200
    assert user.email_verified is True
    assert isinstance(user.email_verified_at, datetime)
    assert user.email_verified_at.tzinfo is not None
    assert user.email_verified_at <= datetime.now(UTC)


# ═══════════════════════════════════════════════════════════════
# BCRYPT FORA DO EVENT LOOP
# ═══════════════════════════════════════════════════════════════
#
# hash_password custa o mesmo que verify_password (~250 ms): rodando direto no
# endpoint async, cada cadastro ou troca de senha trava o event loop e, com ele,
# todas as requisições em voo. Os testes comparam a thread do bcrypt com a do
# event loop — cronometrar seria instável.


@pytest.mark.asyncio
async def test_cadastro_hasheia_a_senha_fora_do_event_loop(smtp_configurado):
    from app.core.database import get_db
    from tests.conftest import EspiaDeThread

    # E-mail ainda não cadastrado. O refresh preenche o que o banco preencheria:
    # id, onboarding_completed e os timestamps vêm de default/server_default, e
    # sem eles o UserResponse não valida
    async def _refresh(obj, *_a, **_k):
        obj.id = obj.id or uuid.uuid4()
        if obj.onboarding_completed is None:
            obj.onboarding_completed = False
        obj.created_at = datetime.now(UTC)
        obj.updated_at = datetime.now(UTC)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = _refresh

    async def _gen():
        yield session

    app.dependency_overrides[get_db] = _gen

    espia = EspiaDeThread(retorno=_SENHA_HASH)
    thread_do_loop = threading.get_ident()

    with patch("app.routers.auth.hash_password", new=espia):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/auth/register",
                json={
                    "name": "Novo Cliente",
                    "email": "novo@test.com",
                    "password": "Senha@123456",
                    "lgpd_consent": True,
                },
            )

    assert r.status_code == 201, r.text
    assert espia.rodou_fora_da_thread(
        thread_do_loop
    ), "o hash da senha rodou na thread do event loop — cada cadastro trava a API"


@pytest.mark.asyncio
async def test_redefinir_senha_hasheia_fora_do_event_loop(smtp_configurado):
    from app.core.database import get_db
    from tests.conftest import EspiaDeThread

    user = _mock_user(email_verified=True)
    app.dependency_overrides[get_db] = _db_with(user)
    token = account_tokens.create_password_reset_token(_USER_ID, _SENHA_HASH, _settings)

    espia = EspiaDeThread(retorno="hash-novo")
    thread_do_loop = threading.get_ident()

    with patch("app.routers.auth.hash_password", new=espia):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "password": "NovaSenha@123"},
            )

    assert r.status_code == 200, r.text
    assert espia.rodou_fora_da_thread(thread_do_loop)
