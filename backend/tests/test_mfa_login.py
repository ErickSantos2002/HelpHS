"""O login em dois tempos: senha, desafio, código, sessão.

Duas invariantes governam este arquivo, e quase todo teste existe para uma delas:

1. **2xx no `/auth/login` significa sempre que a sessão existe.** O desafio sai
   como 403 justamente para que nenhum consumidor consiga confundir "falta o
   segundo fator" com "entrou".

2. **Nada falha para o lado de deixar entrar.** Redis fora do ar, segredo
   ilegível, conta desativada no meio do caminho: tudo vira recusa. Um segundo
   fator que se desliga sozinho quando uma dependência cai não é um segundo
   fator.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from app.core.config import get_settings
from app.main import app
from app.models.models import AuditAction, UserRole, UserStatus
from app.services import mfa

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

SENHA = "Test@123456"
_HASH = _pwd.hash(SENHA)
EMAIL = "suelen@healthsafetytech.com"

_CHAVE = "kZ7QpX3vN9sT2wR6yB1mL4hG8dF0jC5aE7nU3iO9kQs="


# ── Redis de mentira, com o bastante para o desafio ───────────


class _FakeRedis:
    """Redis de mentira que **cede o event loop** em toda operação.

    O `await asyncio.sleep(0)` não é enfeite: sem ele duas requisições sob
    `asyncio.gather` correm até o fim uma depois da outra, porque `await` sobre
    um mock que não suspende não devolve o controle ao loop. A corrida que o
    `consumir` existe para resolver simplesmente não aconteceria, e o teste
    passaria pelo motivo errado.
    """

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.quebrado = False

    async def _ponto_de_troca(self):
        await asyncio.sleep(0)
        if self.quebrado:
            raise ConnectionError("redis fora do ar")

    async def hset(self, key, mapping=None, **_):
        await self._ponto_de_troca()
        self.hashes.setdefault(key, {}).update(mapping or {})

    async def hgetall(self, key):
        await self._ponto_de_troca()
        return dict(self.hashes.get(key, {}))

    async def hincrby(self, key, campo, quanto):
        await self._ponto_de_troca()
        atual = int(self.hashes.get(key, {}).get(campo, 0)) + quanto
        self.hashes.setdefault(key, {})[campo] = str(atual)
        return atual

    async def expire(self, key, ttl):
        await self._ponto_de_troca()

    async def delete(self, key):
        await self._ponto_de_troca()
        apagou = key in self.hashes or key in self.strings
        self.hashes.pop(key, None)
        self.strings.pop(key, None)
        return 1 if apagou else 0

    async def exists(self, key):
        await self._ponto_de_troca()
        return 1 if (key in self.strings or key in self.hashes) else 0

    async def setex(self, key, ttl, value):
        await self._ponto_de_troca()
        self.strings[key] = value

    async def get(self, key):
        await self._ponto_de_troca()
        return self.strings.get(key)


_redis = _FakeRedis()


async def _get_redis():
    return _redis


class _Usuario:
    def __init__(self, mfa_enabled=False, segredo=None, status=UserStatus.active):
        self.id = uuid.uuid4()
        self.email = EMAIL
        self.name = "Suelen"
        self.password = _HASH
        self.role = UserRole.technician
        self.status = status
        self.email_verified = True
        self.mfa_enabled = mfa_enabled
        self.mfa_secret = segredo
        self.mfa_confirmed_at = None


def _db_para(user):
    """Sessão que responde tanto ao `select` do login quanto ao `db.get` do verify."""
    resultado = MagicMock()
    resultado.scalar_one_or_none.return_value = user

    sessao = AsyncMock()
    sessao.execute = AsyncMock(return_value=resultado)
    sessao.get = AsyncMock(return_value=user)
    sessao.add = MagicMock()
    sessao.commit = AsyncMock()
    sessao.auditados = []

    def _add(obj):
        sessao.auditados.append(obj)

    sessao.add.side_effect = _add

    async def _gen():
        yield sessao

    return _gen, sessao


@pytest.fixture
def chave_ligada():
    s = get_settings()
    anterior = s.mfa_secret_encryption_key
    s.mfa_secret_encryption_key = _CHAVE
    yield
    s.mfa_secret_encryption_key = anterior


@pytest.fixture(autouse=True)
def _ambiente():
    _redis.strings.clear()
    _redis.hashes.clear()
    _redis.quebrado = False
    with (
        patch("app.core.security.get_redis", new=_get_redis),
        patch("app.services.mfa_challenge.get_redis", new=_get_redis),
    ):
        yield
    app.dependency_overrides.clear()


async def _cliente(user):
    from app.core.database import get_db

    gen, sessao = _db_para(user)
    app.dependency_overrides[get_db] = gen
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), sessao


def _com_mfa():
    segredo = mfa.gerar_segredo()
    return _Usuario(mfa_enabled=True, segredo=mfa.cifrar_segredo(segredo)), segredo


async def _entrar(c):
    return await c.post("/api/v1/auth/login", json={"email": EMAIL, "password": SENHA})


def _acoes(sessao):
    return [getattr(o, "action", None) for o in sessao.auditados]


# ── Quem não tem MFA não percebe nada ─────────────────────────


@pytest.mark.asyncio
async def test_sem_mfa_o_login_continua_identico(chave_ligada):
    """A regressão que mais importa: 99% dos usuários não podem sentir nada."""
    cliente, sessao = await _cliente(_Usuario())
    async with cliente as c:
        resposta = await _entrar(c)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert AuditAction.login in _acoes(sessao)


# ── Com MFA: o login para no desafio ──────────────────────────


@pytest.mark.asyncio
async def test_com_mfa_o_login_devolve_403_com_desafio(chave_ligada):
    user, _ = _com_mfa()
    cliente, _sessao = await _cliente(user)
    async with cliente as c:
        resposta = await _entrar(c)

    assert resposta.status_code == 403
    corpo = resposta.json()
    assert corpo["mfa_required"] is True
    assert corpo["mfa_token"]
    assert isinstance(corpo["detail"], str)
    # A invariante: 2xx sempre significa sessão, então nada de token aqui
    assert "access_token" not in corpo
    assert "refresh_token" not in corpo


@pytest.mark.asyncio
async def test_o_desafio_nao_grava_refresh_nem_audita_login(chave_ligada):
    """Senha certa sem código não é login, e não deixa rastro de sessão."""
    user, _ = _com_mfa()
    cliente, sessao = await _cliente(user)
    async with cliente as c:
        await _entrar(c)

    assert _redis.strings == {}  # nenhum token:refresh:<id>
    assert AuditAction.login not in _acoes(sessao)


@pytest.mark.asyncio
async def test_o_token_do_desafio_e_opaco(chave_ligada):
    """Não carrega id, e-mail nem papel — quem o recebe não aprende nada."""
    user, _ = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]

    assert str(user.id) not in token
    assert EMAIL not in token
    assert "technician" not in token
    assert token.count(".") != 2  # não é um JWT


@pytest.mark.asyncio
async def test_a_chave_no_redis_nao_e_o_token(chave_ligada):
    """Guardamos o sha256: um KEYS não entrega material que pula a senha."""
    user, _ = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]

    assert _redis.hashes
    assert all(token not in chave for chave in _redis.hashes)


@pytest.mark.asyncio
async def test_senha_errada_continua_401_mesmo_com_mfa(chave_ligada):
    """O desafio nasce depois da senha: não há como sondar contas com ele."""
    user, _ = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        resposta = await c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "errada"})

    assert resposta.status_code == 401
    assert _redis.hashes == {}


# ── Verificação ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_codigo_certo_entrega_a_sessao_e_audita_o_login(chave_ligada):
    user, segredo = _com_mfa()
    cliente, sessao = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        resposta = await c.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": token, "code": pyotp.TOTP(segredo).now()},
        )

    assert resposta.status_code == 200
    assert set(resposta.json()) == {"access_token", "refresh_token", "token_type", "expires_in"}
    # Agora sim: o refresh foi gravado e o login virou linha de auditoria
    assert any(k.startswith("token:refresh:") for k in _redis.strings)
    assert AuditAction.login in _acoes(sessao)


@pytest.mark.asyncio
async def test_codigo_errado_e_recusado(chave_ligada):
    user, _ = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        resposta = await c.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": "000000"}
        )

    assert resposta.status_code == 401
    assert not any(k.startswith("token:refresh:") for k in _redis.strings)


@pytest.mark.asyncio
async def test_desafio_inexistente_nao_diz_o_motivo(chave_ligada):
    user, segredo = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        resposta = await c.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": "nao-existe-nada-com-esse-nome", "code": pyotp.TOTP(segredo).now()},
        )

    assert resposta.status_code == 401
    assert resposta.json()["detail"] == "Sua verificação expirou. Entre novamente."


@pytest.mark.asyncio
async def test_o_mesmo_desafio_nao_serve_duas_vezes(chave_ligada):
    """Uso único: o DEL é a reivindicação, e só um ganha."""
    user, segredo = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        codigo = pyotp.TOTP(segredo).now()
        primeira = await c.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": codigo}
        )
        segunda = await c.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": codigo})

    assert primeira.status_code == 200
    assert segunda.status_code == 401


@pytest.mark.asyncio
async def test_duas_requisicoes_simultaneas_no_mesmo_desafio_so_uma_ganha(chave_ligada):
    """A corrida — e o único cenário em que o retorno do `DEL` importa.

    Sequencialmente, a segunda tentativa já morre na leitura do desafio, porque
    a primeira apagou a chave. É por isso que o teste acima, sozinho, prova o
    antirreplay e não o uso único: descobri isso mutando `consumir` para
    devolver sempre `True` e vendo a suíte inteira continuar verde.

    Aqui as duas passam pela leitura e pela conferência do código antes de
    qualquer uma reivindicar. Só a atomicidade do `DEL` separa uma da outra.
    """
    user, segredo = _com_mfa()
    codigo = pyotp.TOTP(segredo).now()

    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        a, b = await asyncio.gather(
            c.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": codigo}),
            c.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": codigo}),
        )

    assert sorted([a.status_code, b.status_code]) == [200, 401]


@pytest.mark.asyncio
async def test_o_mesmo_codigo_nao_serve_num_desafio_novo(chave_ligada):
    """Antirreplay: o código continua válido por ~90 s, o passo não.

    Sem isto, quem interceptasse o código teria uma janela inteira para abrir
    outra sessão com ele.
    """
    user, segredo = _com_mfa()
    codigo = pyotp.TOTP(segredo).now()

    cliente, _s = await _cliente(user)
    async with cliente as c:
        primeiro = (await _entrar(c)).json()["mfa_token"]
        assert (
            await c.post("/api/v1/auth/mfa/verify", json={"mfa_token": primeiro, "code": codigo})
        ).status_code == 200

        segundo = (await _entrar(c)).json()["mfa_token"]
        repetido = await c.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": segundo, "code": codigo}
        )

    assert repetido.status_code == 401


@pytest.mark.asyncio
async def test_cinco_erros_queimam_o_desafio(chave_ligada):
    user, segredo = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        respostas = [
            await c.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": "000000"})
            for _ in range(5)
        ]
        # Depois de queimado, nem o código certo entra
        certo = await c.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": token, "code": pyotp.TOTP(segredo).now()},
        )

    assert [r.status_code for r in respostas[:4]] == [401, 401, 401, 401]
    assert respostas[4].status_code == 429
    assert certo.status_code == 401


@pytest.mark.asyncio
async def test_conta_desativada_entre_o_login_e_o_codigo(chave_ligada):
    """O desafio não carrega o estado da conta: ela é relida do banco."""
    user, segredo = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        user.status = UserStatus.inactive
        resposta = await c.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": token, "code": pyotp.TOTP(segredo).now()},
        )

    assert resposta.status_code == 401


# ── Nada falha para o lado de deixar entrar ───────────────────


@pytest.mark.asyncio
async def test_redis_fora_no_login_recusa_em_vez_de_liberar(chave_ligada):
    """O teste que define a postura do desenho.

    Sem onde guardar o desafio não há como exigir o código. Emitir a sessão aqui
    desligaria o segundo fator toda vez que o Redis piscasse — que é exatamente
    quando alguém gostaria que ele estivesse desligado.
    """
    user, _ = _com_mfa()
    cliente, _s = await _cliente(user)
    _redis.quebrado = True
    async with cliente as c:
        resposta = await _entrar(c)

    assert resposta.status_code == 503
    assert "access_token" not in resposta.json()


@pytest.mark.asyncio
async def test_redis_fora_no_verify_recusa(chave_ligada):
    user, segredo = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        _redis.quebrado = True
        resposta = await c.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": token, "code": pyotp.TOTP(segredo).now()},
        )

    assert resposta.status_code == 503


@pytest.mark.asyncio
async def test_segredo_ilegivel_recusa_em_vez_de_deixar_passar(chave_ligada):
    """Chave de cifra trocada depois do cadastro: ninguém entra até recadastrar."""
    user, _ = _com_mfa()
    cliente, _s = await _cliente(user)
    async with cliente as c:
        token = (await _entrar(c)).json()["mfa_token"]
        get_settings().mfa_secret_encryption_key = "9xV2bN8mK4jH6gF3dS1aQ7wE5rT0yU2iO4pL8zX6cA0="
        resposta = await c.post(
            "/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": "123456"}
        )

    assert resposta.status_code == 503


@pytest.mark.asyncio
async def test_nenhum_log_carrega_o_codigo_nem_o_token_do_desafio(chave_ligada):
    from loguru import logger

    capturado: list[str] = []
    sink = logger.add(lambda m: capturado.append(str(m)), level="DEBUG")
    try:
        user, segredo = _com_mfa()
        codigo = pyotp.TOTP(segredo).now()
        cliente, _s = await _cliente(user)
        async with cliente as c:
            token = (await _entrar(c)).json()["mfa_token"]
            await c.post("/api/v1/auth/mfa/verify", json={"mfa_token": token, "code": codigo})
    finally:
        logger.remove(sink)

    texto = "\n".join(capturado)
    assert codigo not in texto
    assert token not in texto
