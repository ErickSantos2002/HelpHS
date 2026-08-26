"""Rotas de adesão ao segundo fator: status, cadastro, ativação e desligamento.

O teste mais importante deste arquivo é
`test_ativar_apaga_o_refresh_token_das_sessoes_abertas`. Ele existe por causa de
um furo que só apareceu quando o desenho foi submetido a uma leitura adversarial:

    `/auth/refresh` valida o tipo do token, a correspondência com
    `token:refresh:{uid}` e o status da conta — nunca `mfa_enabled`.

Sem apagar o refresh na ativação, alguém que já tivesse a senha e uma sessão
aberta seguiria renovando access tokens por até sete dias sem jamais ver um
código. O recurso falharia exatamente no caso em que alguém liga o segundo fator
por desconfiar que foi comprometido.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.security import get_current_user
from app.main import app
from app.models.models import UserRole, UserStatus
from app.services import mfa

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

SENHA = "Test@123456"
_HASH = _pwd.hash(SENHA)

_CHAVE_DE_TESTE = "kZ7QpX3vN9sT2wR6yB1mL4hG8dF0jC5aE7nU3iO9kQs="


class _Usuario:
    """Usuário com atributos de verdade — o endpoint escreve neles."""

    def __init__(self, role=UserRole.technician, mfa_enabled=False, mfa_secret=None):
        self.id = uuid.uuid4()
        self.email = "suelen@healthsafetytech.com"
        self.name = "Suelen"
        self.password = _HASH
        self.role = role
        self.status = UserStatus.active
        self.email_verified = True
        self.mfa_enabled = mfa_enabled
        self.mfa_secret = mfa_secret
        self.mfa_confirmed_at = None


def _db():
    sessao = AsyncMock()
    sessao.add = MagicMock()
    sessao.commit = AsyncMock()

    async def _gen():
        yield sessao

    return _gen


@pytest.fixture
def chave_ligada():
    settings = get_settings()
    anterior = settings.mfa_secret_encryption_key
    settings.mfa_secret_encryption_key = _CHAVE_DE_TESTE
    yield
    settings.mfa_secret_encryption_key = anterior


@pytest.fixture
def chave_ausente():
    settings = get_settings()
    anterior = settings.mfa_secret_encryption_key
    settings.mfa_secret_encryption_key = ""
    yield
    settings.mfa_secret_encryption_key = anterior


async def _cliente(usuario):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db()
    app.dependency_overrides[get_current_user] = lambda: usuario
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class _FakeRedis:
    """Redis de mentira, para `delete_refresh_token` não procurar servidor."""

    def __init__(self) -> None:
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


@pytest.fixture(autouse=True)
def _ambiente():
    _fake_redis._store.clear()
    with patch("app.core.security.get_redis", new=_get_fake_redis):
        yield
    app.dependency_overrides.clear()


def _codigo_valido(usuario):
    import pyotp

    return pyotp.TOTP(mfa.decifrar_segredo(usuario.mfa_secret)).now()


# ── Quem pode chegar aqui ─────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("get", "/api/v1/auth/mfa"),
        ("post", "/api/v1/auth/mfa/setup"),
        ("post", "/api/v1/auth/mfa/activate"),
        ("delete", "/api/v1/auth/mfa"),
    ],
)
async def test_cliente_nao_alcanca_nenhuma_rota_de_mfa(chave_ligada, metodo, caminho):
    """Segundo fator é do staff. Cliente não vê nem a existência do recurso."""
    async with await _cliente(_Usuario(role=UserRole.client)) as c:
        # `request` e não `c.get`/`c.delete`: o httpx não aceita corpo nesses atalhos
        resposta = await c.request(metodo, caminho, json={"code": "123456", "password": SENHA})

    assert resposta.status_code == 403


# ── Estado ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_de_quem_nunca_aderiu(chave_ligada):
    async with await _cliente(_Usuario()) as c:
        corpo = (await c.get("/api/v1/auth/mfa")).json()

    assert corpo == {"enabled": False, "pending": False, "available": True}


@pytest.mark.asyncio
async def test_status_de_quem_cadastrou_e_nao_confirmou(chave_ligada):
    usuario = _Usuario(mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))

    async with await _cliente(usuario) as c:
        corpo = (await c.get("/api/v1/auth/mfa")).json()

    assert corpo["pending"] is True
    assert corpo["enabled"] is False


@pytest.mark.asyncio
async def test_status_diz_que_o_ambiente_nao_tem_chave(chave_ausente):
    async with await _cliente(_Usuario()) as c:
        corpo = (await c.get("/api/v1/auth/mfa")).json()

    assert corpo["available"] is False


# ── Cadastro ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sem_chave_configurada_o_cadastro_responde_503(chave_ausente):
    async with await _cliente(_Usuario()) as c:
        resposta = await c.post("/api/v1/auth/mfa/setup")

    assert resposta.status_code == 503


@pytest.mark.asyncio
async def test_o_cadastro_grava_cifrado_e_ainda_nao_liga(chave_ligada):
    usuario = _Usuario()

    async with await _cliente(usuario) as c:
        resposta = await c.post("/api/v1/auth/mfa/setup")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["otpauth_uri"].startswith("otpauth://totp/")

    # O que ficou no "banco" está cifrado, e abre no segredo que foi mostrado
    assert usuario.mfa_secret is not None
    guardado = mfa.decifrar_segredo(usuario.mfa_secret)
    assert guardado not in usuario.mfa_secret
    assert guardado == corpo["secret"].replace(" ", "")

    # Cadastrar não liga: sem confirmar o código, ninguém fica trancado fora
    assert usuario.mfa_enabled is False


@pytest.mark.asyncio
async def test_o_cadastro_nao_e_cacheavel(chave_ligada):
    """A resposta carrega o segredo em claro; cache intermediário é vazamento."""
    async with await _cliente(_Usuario()) as c:
        resposta = await c.post("/api/v1/auth/mfa/setup")

    assert "no-store" in resposta.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_cadastrar_de_novo_com_mfa_ligado_e_recusado(chave_ligada):
    usuario = _Usuario(mfa_enabled=True, mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))
    antes = usuario.mfa_secret

    async with await _cliente(usuario) as c:
        resposta = await c.post("/api/v1/auth/mfa/setup")

    assert resposta.status_code == 409
    # E o segredo em uso não foi substituído no caminho
    assert usuario.mfa_secret == antes


# ── Ativação ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ativar_com_o_codigo_certo_liga_e_carimba(chave_ligada):
    usuario = _Usuario(mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))

    async with await _cliente(usuario) as c:
        resposta = await c.post("/api/v1/auth/mfa/activate", json={"code": _codigo_valido(usuario)})

    assert resposta.status_code == 204
    assert usuario.mfa_enabled is True
    assert usuario.mfa_confirmed_at is not None


@pytest.mark.asyncio
async def test_ativar_com_codigo_errado_nao_liga(chave_ligada):
    usuario = _Usuario(mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))

    async with await _cliente(usuario) as c:
        resposta = await c.post("/api/v1/auth/mfa/activate", json={"code": "000000"})

    assert resposta.status_code == 400
    assert usuario.mfa_enabled is False


@pytest.mark.asyncio
async def test_ativar_sem_ter_cadastrado_e_recusado(chave_ligada):
    usuario = _Usuario()

    async with await _cliente(usuario) as c:
        resposta = await c.post("/api/v1/auth/mfa/activate", json={"code": "123456"})

    assert resposta.status_code == 409
    assert usuario.mfa_enabled is False


@pytest.mark.asyncio
async def test_ativar_apaga_o_refresh_token_das_sessoes_abertas(chave_ligada):
    """O teste que fecha o furo — ver o cabeçalho do arquivo.

    Como existe UMA chave `token:refresh:{uid}` por usuário, apagá-la despeja
    todas as sessões de uma vez. Quem tinha a senha e uma sessão aberta perde a
    renovação e volta ao login, agora com o segundo fator no caminho.
    """
    usuario = _Usuario(mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))

    with patch("app.routers.auth.delete_refresh_token", new=AsyncMock()) as apaga:
        async with await _cliente(usuario) as c:
            resposta = await c.post(
                "/api/v1/auth/mfa/activate", json={"code": _codigo_valido(usuario)}
            )

    assert resposta.status_code == 204
    apaga.assert_awaited_once_with(usuario.id)


@pytest.mark.asyncio
async def test_codigo_recusado_nao_despeja_sessao_nenhuma(chave_ligada):
    """Errar o código não pode ser um jeito de derrubar as sessões de alguém."""
    usuario = _Usuario(mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))

    with patch("app.routers.auth.delete_refresh_token", new=AsyncMock()) as apaga:
        async with await _cliente(usuario) as c:
            await c.post("/api/v1/auth/mfa/activate", json={"code": "000000"})

    apaga.assert_not_awaited()


# ── Desligamento ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_desligar_exige_a_senha_atual(chave_ligada):
    usuario = _Usuario(mfa_enabled=True, mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))

    async with await _cliente(usuario) as c:
        resposta = await c.request("DELETE", "/api/v1/auth/mfa", json={"password": "senha-errada"})

    assert resposta.status_code == 401
    assert usuario.mfa_enabled is True
    assert usuario.mfa_secret is not None


@pytest.mark.asyncio
async def test_desligar_com_a_senha_certa_limpa_tudo(chave_ligada):
    usuario = _Usuario(mfa_enabled=True, mfa_secret=mfa.cifrar_segredo(mfa.gerar_segredo()))

    with patch("app.routers.auth.delete_refresh_token", new=AsyncMock()) as apaga:
        async with await _cliente(usuario) as c:
            resposta = await c.request("DELETE", "/api/v1/auth/mfa", json={"password": SENHA})

    assert resposta.status_code == 204
    assert usuario.mfa_enabled is False
    # O segredo some junto: deixar para trás manteria o par proibido pelo CHECK
    assert usuario.mfa_secret is None
    assert usuario.mfa_confirmed_at is None
    apaga.assert_awaited_once_with(usuario.id)


# ── Segredo não vaza ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_nenhum_log_carrega_o_segredo_nem_a_uri(chave_ligada):
    """A regra do enunciado: TOTP, segredo e conteúdo do QR não vão para log."""
    from loguru import logger

    capturado: list[str] = []
    sink = logger.add(lambda m: capturado.append(str(m)), level="DEBUG")
    try:
        usuario = _Usuario()
        async with await _cliente(usuario) as c:
            corpo = (await c.post("/api/v1/auth/mfa/setup")).json()
            await c.post("/api/v1/auth/mfa/activate", json={"code": _codigo_valido(usuario)})
    finally:
        logger.remove(sink)

    texto = "\n".join(capturado)
    segredo = corpo["secret"].replace(" ", "")
    assert segredo not in texto
    assert "otpauth://" not in texto
