"""
O registro de QUAL revisão cada pessoa aceitou — os caminhos que gravam.

A seção 15 da Política de Privacidade promete guardar, a cada aceite, quem
aceitou, quando e a revisão dos documentos vigentes. Até aqui o sistema
gravava só um booleano e uma data em `users`, e revogar apagava a data. Estes
casos prendem cada caminho que escreve em `lgpd_consents`, com a `origem`
certa — em especial a criação pela equipe, que não pode se disfarçar de
aceite do próprio titular.

Com banco simulado: o que depende do PostgreSQL de verdade (a migration, a
revogação que não apaga, a exclusão que desvincula) está em
`test_lgpd_consents_postgres.py`. Desenho em
`docs/superpowers/specs/2026-08-31-registro-da-revisao-aceita-design.md`.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.models.models import LgpdConsent, User, UserRole
from app.services.consentimento import (
    ORIGEM_ALTERACAO_PROPRIA,
    ORIGEM_AUTO_CADASTRO,
    ORIGEM_CRIADO_POR_TERCEIRO,
    precisa_reaceitar,
)
from tests.test_users import _ADMIN, _CLIENT, _get_redis, _user

_settings = get_settings()


@pytest.fixture(autouse=True)
def _limpa_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def patch_redis():
    with patch("app.core.security.get_redis", new=_get_redis):
        yield


@pytest.fixture()
def revisoes():
    """Revisões vigentes com valores que NENHUM default produziria.

    É a mutação que a spec exige: se o teste passasse com qualquer valor, ele
    não estaria provando que o aceite grava o que a configuração declara.
    """
    antes = (_settings.lgpd_revisao_politica, _settings.lgpd_revisao_termos)
    _settings.lgpd_revisao_politica = "07"
    _settings.lgpd_revisao_termos = "03"
    yield
    _settings.lgpd_revisao_politica, _settings.lgpd_revisao_termos = antes


def _sessao(*, usuario_da_consulta=None, ultimo_aceite=None):
    """Sessão simulada que coleciona o que foi adicionado e executado."""
    adicionados: list = []
    executados: list = []

    async def _execute(stmt, *args, **kwargs):
        executados.append(stmt)
        r = MagicMock()
        r.scalar_one_or_none.return_value = usuario_da_consulta
        r.scalars.return_value.first.return_value = ultimo_aceite
        return r

    async def _flush():
        agora = datetime.now(UTC)
        for obj in adicionados:
            if isinstance(obj, User):
                obj.id = obj.id or uuid.uuid4()
                obj.onboarding_completed = bool(obj.onboarding_completed)
                obj.ai_enabled = True if obj.ai_enabled is None else obj.ai_enabled
                obj.created_at = obj.created_at or agora
                obj.updated_at = obj.updated_at or agora

    sessao = AsyncMock()
    sessao.execute = _execute
    sessao.add = MagicMock(side_effect=adicionados.append)
    sessao.flush = AsyncMock(side_effect=_flush)
    sessao.commit = AsyncMock()
    sessao.refresh = AsyncMock()

    async def _gen():
        yield sessao

    return _gen, adicionados, executados


def _aceites(adicionados) -> list[LgpdConsent]:
    return [o for o in adicionados if isinstance(o, LgpdConsent)]


def _como(ator):
    from app.core.security import get_current_user

    async def _ator():
        return ator

    app.dependency_overrides[get_current_user] = _ator


_CORPO_CADASTRO = {
    "name": "Cliente Novo",
    "email": "novo@test.com",
    "password": "Senha@123456",
    "phone": "(81) 99999-9999",
    "lgpd_consent": True,
}


# ══════════════════════════════════════════════════════════════
# Caminho 1 — o cadastro público: o titular marcou a caixa
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cadastro_grava_o_aceite_com_a_revisao_vigente(revisoes):
    from app.core.database import get_db

    gen, adicionados, _ = _sessao()
    app.dependency_overrides[get_db] = gen

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/auth/register",
            json=_CORPO_CADASTRO,
            headers={"User-Agent": "Navegador/1.0"},
        )

    assert resp.status_code == 201, resp.text
    usuario = next(o for o in adicionados if isinstance(o, User))
    [aceite] = _aceites(adicionados)
    assert aceite.user_id == usuario.id
    assert aceite.origem == ORIGEM_AUTO_CADASTRO
    assert aceite.revisao_politica == "07"
    assert aceite.revisao_termos == "03"
    assert aceite.revogado_em is None
    # O ASGITransport do httpx apresenta o cliente como 127.0.0.1.
    assert aceite.ip == "127.0.0.1"


@pytest.mark.asyncio
async def test_sem_termos_de_uso_o_aceite_grava_nulo(revisoes):
    """Os Termos ainda não existem: a revisão deles é NULL, não um valor inventado."""
    from app.core.database import get_db

    _settings.lgpd_revisao_termos = None
    gen, adicionados, _ = _sessao()
    app.dependency_overrides[get_db] = gen

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/auth/register", json=_CORPO_CADASTRO)

    assert resp.status_code == 201, resp.text
    [aceite] = _aceites(adicionados)
    assert aceite.revisao_termos is None
    assert aceite.revisao_politica == "07"


# ══════════════════════════════════════════════════════════════
# Caminho 2 — a equipe cria a conta: aceite afirmado por terceiro
# ══════════════════════════════════════════════════════════════


def _corpo_criacao(consentiu: bool) -> dict:
    return {
        "name": "Cliente da Equipe",
        "email": "criado@test.com",
        "password": "Secret1234",
        "role": "client",
        "phone": "(81) 99999-9999",
        "lgpd_consent": consentiu,
    }


@pytest.mark.asyncio
async def test_conta_criada_pela_equipe_nao_se_disfarca_de_auto_cadastro(patch_redis, revisoes):
    from app.core.database import get_db

    gen, adicionados, _ = _sessao()
    app.dependency_overrides[get_db] = gen
    _como(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/users", json=_corpo_criacao(True))

    assert resp.status_code == 201, resp.text
    usuario = next(o for o in adicionados if isinstance(o, User))
    [aceite] = _aceites(adicionados)
    assert aceite.user_id == usuario.id
    assert aceite.origem == ORIGEM_CRIADO_POR_TERCEIRO
    assert aceite.revisao_politica == "07"
    # O IP da requisição é o de quem CRIOU a conta, não o do titular: gravá-lo
    # faria o registro afirmar de onde a pessoa aceitou, e ela não aceitou.
    assert aceite.ip is None


@pytest.mark.asyncio
async def test_conta_criada_sem_consentimento_nao_grava_aceite(patch_redis, revisoes):
    from app.core.database import get_db

    gen, adicionados, _ = _sessao()
    app.dependency_overrides[get_db] = gen
    _como(_ADMIN)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/users", json=_corpo_criacao(False))

    assert resp.status_code == 201, resp.text
    assert _aceites(adicionados) == []


# ══════════════════════════════════════════════════════════════
# Caminho 3 — o próprio titular concede ou revoga
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_conceder_grava_alteracao_propria(patch_redis, revisoes):
    from app.core.database import get_db

    titular = _user(UserRole.client)
    gen, adicionados, _ = _sessao(usuario_da_consulta=titular)
    app.dependency_overrides[get_db] = gen
    _como(titular)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/lgpd-consent", json={"lgpd_consent": True})

    assert resp.status_code == 200, resp.text
    [aceite] = _aceites(adicionados)
    assert aceite.user_id == titular.id
    assert aceite.origem == ORIGEM_ALTERACAO_PROPRIA
    assert aceite.revisao_politica == "07"
    assert aceite.ip == "127.0.0.1"


@pytest.mark.asyncio
async def test_revogar_marca_revogado_em_e_nao_apaga(patch_redis, revisoes):
    """Revogar ESCREVE `revogado_em` nos aceites abertos — nunca apaga linha.

    Antes, revogar zerava `lgpd_consent_at` e a prova do período consentido
    sumia. O comportamento contra o banco real está no teste de Postgres; aqui
    se prende que o caminho emite um UPDATE, e não um DELETE nem um aceite novo.
    """
    from app.core.database import get_db

    titular = _user(UserRole.client)
    gen, adicionados, executados = _sessao(usuario_da_consulta=titular)
    app.dependency_overrides[get_db] = gen
    _como(titular)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/users/me/lgpd-consent", json={"lgpd_consent": False})

    assert resp.status_code == 200, resp.text
    assert _aceites(adicionados) == []
    sql = [str(stmt).lower() for stmt in executados]
    assert any("update lgpd_consents" in s and "revogado_em" in s for s in sql), sql
    assert not any("delete" in s and "lgpd_consents" in s for s in sql), sql


# ══════════════════════════════════════════════════════════════
# O re-aceite — quem precisa aceitar a revisão vigente
# ══════════════════════════════════════════════════════════════


def _aceite(politica="07", termos="03") -> LgpdConsent:
    return LgpdConsent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        revisao_politica=politica,
        revisao_termos=termos,
        origem=ORIGEM_AUTO_CADASTRO,
        concedido_em=datetime.now(UTC),
    )


def _config(*, exige=True, politica="07", termos="03"):
    c = MagicMock()
    c.lgpd_exige_reaceite = exige
    c.lgpd_revisao_politica = politica
    c.lgpd_revisao_termos = termos
    return c


def test_interruptor_desligado_nao_cobra_ninguem():
    assert precisa_reaceitar(None, role=UserRole.client, settings=_config(exige=False)) is False


@pytest.mark.parametrize("papel", [UserRole.admin, UserRole.technician])
def test_equipe_nunca_passa_pela_tela(papel):
    """Decisão de 24/09: só clientes. Travar a equipe no dia da publicação é
    risco operacional que foi recusado."""
    assert precisa_reaceitar(None, role=papel, settings=_config()) is False


def test_cliente_sem_aceite_registrado_precisa_aceitar():
    """Quem se cadastrou antes do histórico tem revisão DESCONHECIDA — e é
    esse NULL que dispara o re-aceite, em vez de fingir que foi a 00."""
    assert precisa_reaceitar(None, role=UserRole.client, settings=_config()) is True


def test_cliente_com_a_revisao_vigente_segue():
    assert precisa_reaceitar(_aceite(), role=UserRole.client, settings=_config()) is False


def test_politica_nova_cobra_de_novo():
    ultimo = _aceite(politica="06")
    assert precisa_reaceitar(ultimo, role=UserRole.client, settings=_config()) is True


def test_termos_publicados_depois_cobram_de_novo():
    """Aceitou quando os Termos não existiam (NULL); agora existem."""
    ultimo = _aceite(termos=None)
    assert precisa_reaceitar(ultimo, role=UserRole.client, settings=_config()) is True


# ══════════════════════════════════════════════════════════════
# GET /users/me/lgpd-consent — o que a tela de re-aceite consulta
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_situacao_do_aceite_para_a_tela(patch_redis, revisoes):
    from app.core.database import get_db

    antes = _settings.lgpd_exige_reaceite
    _settings.lgpd_exige_reaceite = True
    try:
        gen, _, _ = _sessao(ultimo_aceite=_aceite(politica="06", termos="03"))
        app.dependency_overrides[get_db] = gen
        _como(_CLIENT)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/users/me/lgpd-consent")
    finally:
        _settings.lgpd_exige_reaceite = antes

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "revisao_politica_vigente": "07",
        "revisao_termos_vigente": "03",
        "revisao_politica_aceita": "06",
        "revisao_termos_aceita": "03",
        "precisa_reaceitar": True,
    }
