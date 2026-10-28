"""
O aceite obrigatório da Política, cobrado pelo backend, contra um PostgreSQL de
verdade e com o `get_current_user` de verdade (token RS256 real, sem override).

Decisão 2, de 27/10/2026: com `LGPD_EXIGE_REACEITE` ligado, quem não tem um
aceite PRÓPRIO, aberto, da revisão vigente da Política recebe 428 em toda rota
autenticada, exceto as quatro de que a tela de re-aceite precisa. Vale para
cliente, técnico e admin. `criado_por_terceiro` não satisfaz. Os Termos NÃO
bloqueiam o backend nesta fase.

Pula sem PostgreSQL à mão: `TEST_POSTGRES_URL` ou `pgserver`.
"""

import asyncio
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token
from app.main import app
from app.models.models import AuditLog, Base, LgpdConsent, User, UserRole, UserStatus
from app.services.consentimento import (
    ORIGEM_ALTERACAO_PROPRIA,
    ORIGEM_AUTO_CADASTRO,
    ORIGEM_CRIADO_POR_TERCEIRO,
)
from tests.test_dashboard_postgres import _sobe_postgres

_VIGENTE = "01"
_PAPEIS = [UserRole.client, UserRole.technician, UserRole.admin]

# Uma amostra das rotas que NÃO estão na lista: routers diferentes, o próprio
# router de usuários (que mistura liberadas e bloqueadas), o de auth, e uma rota
# com `authorize` — que herda o bloqueio do `get_current_user`.
_BLOQUEADAS = [
    ("GET", "/api/v1/tickets", None),
    ("GET", "/api/v1/notifications", None),
    ("GET", "/api/v1/products", None),
    ("PATCH", "/api/v1/users/me", {"name": "Nome Novo"}),
    ("PATCH", "/api/v1/users/me/onboarding", {}),
    ("GET", "/api/v1/auth/cnpj/11222333000181", None),
    ("GET", "/api/v1/equipment/my", None),
]


@pytest.fixture(scope="module")
def url_do_banco():
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    asyncio.run(_monta())
    yield url

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def fabrica(url_do_banco):
    motor = create_async_engine(url_do_banco)
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


class _RedisNaMemoria:
    """O que o `security` usa do Redis: blacklist e o refresh token."""

    def __init__(self) -> None:
        self.dados: dict[str, str] = {}

    async def exists(self, chave):
        return 1 if chave in self.dados else 0

    async def setex(self, chave, _ttl, valor):
        self.dados[chave] = valor

    async def get(self, chave):
        return self.dados.get(chave)

    async def delete(self, chave):
        self.dados.pop(chave, None)


@pytest.fixture
def redis(monkeypatch):
    falso = _RedisNaMemoria()

    async def _get():
        return falso

    monkeypatch.setattr("app.core.security.get_redis", _get)
    return falso


@pytest.fixture
def exige(monkeypatch):
    """Liga o aceite obrigatório com a revisão 01 — e desfaz no fim."""
    s = get_settings()
    monkeypatch.setattr(s, "lgpd_exige_reaceite", True)
    monkeypatch.setattr(s, "lgpd_revisao_politica", _VIGENTE)
    monkeypatch.setattr(s, "lgpd_revisao_termos", None)
    return s


@pytest_asyncio.fixture
async def banco(fabrica, redis):
    """Liga o app ao banco real e apaga, no fim, o que o teste criou."""
    ids: list[uuid.UUID] = []

    async def _db():
        async with fabrica() as sessao:
            yield sessao

    app.dependency_overrides[get_db] = _db
    yield ids
    app.dependency_overrides.clear()
    if not ids:
        return
    async with fabrica() as s:
        await s.execute(text("SET LOCAL lock_timeout = '10s'"))
        await s.execute(delete(LgpdConsent).where(LgpdConsent.user_id.in_(ids)))
        await s.execute(
            delete(AuditLog).where(or_(AuditLog.user_id.in_(ids), AuditLog.entity_id.in_(ids)))
        )
        await s.execute(delete(User).where(User.id.in_(ids)))
        await s.commit()


async def _cria(fabrica, ids, papel=UserRole.client, *, aceites=(), **extra) -> User:
    """Usuário comitado, com os aceites dados como (revisão, origem, revogado)."""
    ontem = datetime.now(UTC) - timedelta(days=1)
    campos = {
        "id": uuid.uuid4(),
        "name": f"Pessoa {papel.value}",
        "email": f"{uuid.uuid4().hex[:10]}@test.invalid",
        "password": "x",
        "role": papel,
        "status": UserStatus.active,
        "phone": "+5581999999999",
        "lgpd_consent": True,
        "email_verified": True,
        "onboarding_completed": True,
        "created_at": ontem,
        "updated_at": ontem,
    }
    campos.update(extra)
    usuario = User(**campos)
    ids.append(usuario.id)
    async with fabrica() as s:
        s.add(usuario)
        await s.flush()
        for n, (revisao, origem, revogado) in enumerate(aceites):
            quando = ontem + timedelta(minutes=n)
            s.add(
                LgpdConsent(
                    id=uuid.uuid4(),
                    user_id=usuario.id,
                    revisao_politica=revisao,
                    revisao_termos=None,
                    origem=origem,
                    concedido_em=quando,
                    revogado_em=quando + timedelta(seconds=1) if revogado else None,
                    ip=None if origem == ORIGEM_CRIADO_POR_TERCEIRO else "10.0.0.1",
                )
            )
        await s.commit()
    return usuario


def _token(quem: User) -> str:
    return create_access_token(quem.id, quem.role.value, quem.email)


async def _pede(metodo, url, quem=None, *, token=None, json=None):
    token = token or (_token(quem) if quem else None)
    cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        return await c.request(metodo, url, headers=cabecalhos, json=json)


async def _abertos(fabrica, uid) -> list[LgpdConsent]:
    async with fabrica() as s:
        r = await s.execute(
            select(LgpdConsent).where(LgpdConsent.user_id == uid, LgpdConsent.revogado_em.is_(None))
        )
        return list(r.scalars().all())


def _e_o_428(resp) -> None:
    assert resp.status_code == 428, resp.text
    assert resp.json() == {
        "detail": "Para continuar, aceite a revisão vigente da Política de Privacidade.",
        "code": "aceite_politica_pendente",
        "revisao_politica_vigente": _VIGENTE,
    }


# ── Quem é bloqueado ──────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", _PAPEIS)
async def test_sem_aceite_todos_os_papeis_recebem_428(fabrica, banco, exige, papel):
    quem = await _cria(fabrica, banco, papel)
    _e_o_428(await _pede("GET", "/api/v1/tickets", quem))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "aceites",
    [
        pytest.param([(_VIGENTE, ORIGEM_CRIADO_POR_TERCEIRO, False)], id="so-criado-por-terceiro"),
        pytest.param([(_VIGENTE, ORIGEM_AUTO_CADASTRO, True)], id="revogado"),
        pytest.param([("00", ORIGEM_AUTO_CADASTRO, False)], id="politica-anterior"),
        pytest.param([("02", ORIGEM_ALTERACAO_PROPRIA, False)], id="politica-diferente"),
        pytest.param([], id="legado-so-com-users-lgpd-consent"),
    ],
)
async def test_sem_aceite_proprio_da_revisao_vigente_recebe_428(fabrica, banco, exige, aceites):
    quem = await _cria(fabrica, banco, aceites=aceites, lgpd_consent=True)
    _e_o_428(await _pede("GET", "/api/v1/tickets", quem))


# ── Quem passa ────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("origem", [ORIGEM_AUTO_CADASTRO, ORIGEM_ALTERACAO_PROPRIA])
@pytest.mark.parametrize("papel", _PAPEIS)
async def test_aceite_proprio_da_revisao_vigente_passa(fabrica, banco, exige, origem, papel):
    quem = await _cria(fabrica, banco, papel, aceites=[(_VIGENTE, origem, False)])
    resp = await _pede("GET", "/api/v1/tickets", quem)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_aceite_proprio_vale_mesmo_com_o_da_equipe_por_cima(fabrica, banco, exige):
    """'Existe algum', não 'o último'."""
    quem = await _cria(
        fabrica,
        banco,
        aceites=[
            (_VIGENTE, ORIGEM_AUTO_CADASTRO, False),
            (_VIGENTE, ORIGEM_CRIADO_POR_TERCEIRO, False),
        ],
    )
    assert (await _pede("GET", "/api/v1/tickets", quem)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", _PAPEIS)
async def test_interruptor_desligado_nao_bloqueia_ninguem(fabrica, banco, papel):
    assert get_settings().lgpd_exige_reaceite is False
    quem = await _cria(fabrica, banco, papel)
    assert (await _pede("GET", "/api/v1/tickets", quem)).status_code == 200


@pytest.mark.asyncio
async def test_termos_novos_nao_bloqueiam_o_backend(fabrica, banco, exige, monkeypatch):
    """Decisão 2: só a Política bloqueia. Termos novos ficam na tela, e só do
    cliente."""
    monkeypatch.setattr(exige, "lgpd_revisao_termos", "05")
    quem = await _cria(fabrica, banco, aceites=[(_VIGENTE, ORIGEM_AUTO_CADASTRO, False)])

    assert (await _pede("GET", "/api/v1/tickets", quem)).status_code == 200
    situacao = (await _pede("GET", "/api/v1/users/me/lgpd-consent", quem)).json()
    assert situacao["politica_pendente"] is False
    assert situacao["termos_pendentes"] is True
    assert situacao["precisa_reaceitar"] is True


# ── A lista das rotas liberadas ───────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", _PAPEIS)
async def test_as_quatro_rotas_liberadas_funcionam_sem_aceite(fabrica, banco, exige, papel):
    quem = await _cria(fabrica, banco, papel)
    token = _token(quem)

    assert (await _pede("GET", "/api/v1/users/me", token=token)).status_code == 200
    situacao = await _pede("GET", "/api/v1/users/me/lgpd-consent", token=token)
    assert situacao.status_code == 200
    assert situacao.json()["politica_pendente"] is True
    aceite = await _pede(
        "PATCH", "/api/v1/users/me/lgpd-consent", token=token, json={"lgpd_consent": True}
    )
    assert aceite.status_code == 200, aceite.text

    # "Recusar e sair": quem SAI é quem ainda não aceitou — outra conta, porque
    # esta já aceitou acima.
    recusa = await _cria(fabrica, banco, papel)
    assert (await _pede("POST", "/api/v1/auth/logout", recusa)).status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize(("metodo", "rota", "corpo"), _BLOQUEADAS)
async def test_as_demais_rotas_recebem_428(fabrica, banco, exige, metodo, rota, corpo):
    quem = await _cria(fabrica, banco)
    _e_o_428(await _pede(metodo, rota, quem, json=corpo))


@pytest.mark.asyncio
async def test_rota_com_authorize_herda_o_bloqueio(fabrica, banco, exige):
    admin = await _cria(fabrica, banco, UserRole.admin)
    _e_o_428(await _pede("GET", "/api/v1/users", admin))


@pytest.mark.asyncio
async def test_rota_sem_autenticacao_continua_401_e_nao_428(fabrica, banco, exige):
    """Sem token, o problema é a sessão: 401, como sempre."""
    assert (await _pede("GET", "/api/v1/tickets")).status_code == 401


# ── Sessão ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_emitido_antes_de_ligar_passa_a_receber_428(fabrica, banco, monkeypatch):
    quem = await _cria(fabrica, banco, aceites=[("00", ORIGEM_AUTO_CADASTRO, False)])
    token = _token(quem)
    assert (await _pede("GET", "/api/v1/tickets", token=token)).status_code == 200

    s = get_settings()
    monkeypatch.setattr(s, "lgpd_exige_reaceite", True)
    monkeypatch.setattr(s, "lgpd_revisao_politica", _VIGENTE)
    _e_o_428(await _pede("GET", "/api/v1/tickets", token=token))


@pytest.mark.asyncio
async def test_refresh_continua_funcionando_com_aceite_pendente(fabrica, banco, exige, redis):
    quem = await _cria(fabrica, banco)
    refresh = create_refresh_token(quem.id)
    await redis.setex(f"token:refresh:{quem.id}", 60, refresh)

    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://t") as c:
        resp = await c.post("/api/v1/auth/refresh", json={"refresh_token": refresh})

    assert resp.status_code == 200, resp.text
    _e_o_428(await _pede("GET", "/api/v1/tickets", token=resp.json()["access_token"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("situacao", [UserStatus.inactive, UserStatus.anonymized])
async def test_conta_fora_de_uso_continua_403_e_nao_428(fabrica, banco, exige, situacao):
    """A ordem importa: a conta inativa é recusada antes do aceite."""
    quem = await _cria(fabrica, banco, status=situacao, phone=None)
    for rota in ("/api/v1/tickets", "/api/v1/users/me"):
        resp = await _pede("GET", rota, quem)
        assert resp.status_code == 403, (rota, resp.text)


# ── O contrato ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_o_428_nao_carrega_a_revisao_dos_termos(fabrica, banco, exige, monkeypatch):
    monkeypatch.setattr(exige, "lgpd_revisao_termos", "05")
    quem = await _cria(fabrica, banco)
    corpo = (await _pede("GET", "/api/v1/tickets", quem)).json()
    assert set(corpo) == {"detail", "code", "revisao_politica_vigente"}


@pytest.mark.asyncio
async def test_erro_na_verificacao_nao_libera_o_acesso(fabrica, banco, exige):
    quem = await _cria(fabrica, banco, aceites=[(_VIGENTE, ORIGEM_AUTO_CADASTRO, False)])
    falha = AsyncMock(side_effect=RuntimeError("banco caiu no meio"))
    with patch("app.services.consentimento.aceites_abertos", falha):
        resp = await _pede("GET", "/api/v1/tickets", quem)
    assert resp.status_code == 500
    assert falha.await_count == 1


# ── O aceite ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aceitar_destrava_e_repetir_nao_grava_de_novo(fabrica, banco, exige):
    quem = await _cria(fabrica, banco, aceites=[("00", ORIGEM_AUTO_CADASTRO, False)])
    token = _token(quem)
    _e_o_428(await _pede("GET", "/api/v1/tickets", token=token))

    primeiro = await _pede(
        "PATCH", "/api/v1/users/me/lgpd-consent", token=token, json={"lgpd_consent": True}
    )
    assert primeiro.status_code == 200, primeiro.text
    async with fabrica() as s:
        momento = (await s.get(User, quem.id)).lgpd_consent_at

    segundo = await _pede(
        "PATCH", "/api/v1/users/me/lgpd-consent", token=token, json={"lgpd_consent": True}
    )
    assert segundo.status_code == 200, segundo.text

    assert (await _pede("GET", "/api/v1/tickets", token=token)).status_code == 200
    novos = [a for a in await _abertos(fabrica, quem.id) if a.revisao_politica == _VIGENTE]
    assert [a.origem for a in novos] == [ORIGEM_ALTERACAO_PROPRIA]
    async with fabrica() as s:
        assert (await s.get(User, quem.id)).lgpd_consent_at == momento
        auditorias = (
            await s.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == quem.id)
            )
        ).scalar_one()
    assert auditorias == 1


@pytest.mark.asyncio
async def test_aceite_da_equipe_nao_torna_o_patch_um_no_op(fabrica, banco, exige):
    """Com só o `criado_por_terceiro` da revisão vigente, aceitar GRAVA o aceite
    do titular — não pode ser confundido com um aceite já existente."""
    quem = await _cria(fabrica, banco, aceites=[(_VIGENTE, ORIGEM_CRIADO_POR_TERCEIRO, False)])
    resp = await _pede("PATCH", "/api/v1/users/me/lgpd-consent", quem, json={"lgpd_consent": True})
    assert resp.status_code == 200
    origens = sorted(a.origem for a in await _abertos(fabrica, quem.id))
    assert origens == [ORIGEM_ALTERACAO_PROPRIA, ORIGEM_CRIADO_POR_TERCEIRO]
    assert (await _pede("GET", "/api/v1/tickets", quem)).status_code == 200


@pytest.mark.asyncio
async def test_aceites_simultaneos_gravam_uma_linha_so(fabrica, banco, exige):
    quem = await _cria(fabrica, banco)
    token = _token(quem)

    respostas = await asyncio.gather(
        *(
            _pede(
                "PATCH", "/api/v1/users/me/lgpd-consent", token=token, json={"lgpd_consent": True}
            )
            for _ in range(5)
        )
    )

    assert [r.status_code for r in respostas] == [200] * 5
    assert len(await _abertos(fabrica, quem.id)) == 1


@pytest.mark.asyncio
async def test_aceitar_e_revogar_simultaneos_terminam_coerentes(fabrica, banco, exige):
    """Serializados pela trava, o resultado é o de UMA das ordens possíveis:
    aceito (linha aberta e `lgpd_consent`) ou revogado (nenhuma aberta)."""
    quem = await _cria(fabrica, banco)
    token = _token(quem)

    pedidos = [{"lgpd_consent": True}, {"lgpd_consent": False}] * 3
    respostas = await asyncio.gather(
        *(_pede("PATCH", "/api/v1/users/me/lgpd-consent", token=token, json=c) for c in pedidos)
    )

    assert {r.status_code for r in respostas} == {200}
    abertos = await _abertos(fabrica, quem.id)
    async with fabrica() as s:
        usuario = await s.get(User, quem.id)
    assert len(abertos) <= 1
    assert usuario.lgpd_consent is bool(abertos)


# ── Revogar ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revogar_bloqueia_na_hora_e_fecha_os_chats(fabrica, banco, exige):
    quem = await _cria(fabrica, banco, aceites=[(_VIGENTE, ORIGEM_AUTO_CADASTRO, False)])
    token = _token(quem)
    assert (await _pede("GET", "/api/v1/tickets", token=token)).status_code == 200

    fecha = AsyncMock(return_value=1)
    with patch("app.routers.users.fecha_chats_do_usuario", fecha):
        resp = await _pede(
            "PATCH", "/api/v1/users/me/lgpd-consent", token=token, json={"lgpd_consent": False}
        )

    assert resp.status_code == 200
    fecha.assert_awaited_once_with(quem.id)
    _e_o_428(await _pede("GET", "/api/v1/tickets", token=token))
    # E volta aceitando de novo.
    await _pede("PATCH", "/api/v1/users/me/lgpd-consent", token=token, json={"lgpd_consent": True})
    assert (await _pede("GET", "/api/v1/tickets", token=token)).status_code == 200


@pytest.mark.asyncio
async def test_revogar_com_o_interruptor_desligado_nao_fecha_chat(fabrica, banco):
    quem = await _cria(fabrica, banco, aceites=[("00", ORIGEM_AUTO_CADASTRO, False)])
    fecha = AsyncMock(return_value=0)
    with patch("app.routers.users.fecha_chats_do_usuario", fecha):
        resp = await _pede(
            "PATCH", "/api/v1/users/me/lgpd-consent", quem, json={"lgpd_consent": False}
        )
    assert resp.status_code == 200
    fecha.assert_not_awaited()
