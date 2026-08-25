"""Smoke tests — verifica que a aplicacao sobe e responde."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _get(url: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(url)


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize("banco_ok", [True, False])
async def test_health_versionado_nao_entrega_a_versao_a_quem_nao_esta_logado(banco_ok):
    """
    /api/v1/health responde sem autenticação. A versão exata entregue a
    qualquer um só ajuda quem quer casar release com vulnerabilidade
    conhecida — e quem chama um health check quer saber se a API está de pé,
    não qual versão ela é.

    Vale nos dois estados: a resposta de degradado é a que mais convida a
    despejar detalhe de diagnóstico, e é justamente a que um curioso consegue
    provocar.
    """
    with (
        patch("app.main._checar_banco", new=AsyncMock(return_value=banco_ok)),
        patch("app.main._checar_redis", new=AsyncMock(return_value=True)),
        patch("app.main.ultima_rodada_sem_erro", return_value=None),
    ):
        response = await _get("/api/v1/health")

    assert response.status_code == (200 if banco_ok else 503)
    assert "version" not in response.json()


def test_versao_da_api_vem_de_uma_fonte_so():
    """
    A versão já esteve escrita à mão em dois pontos do main.py, e as duas
    congelaram em 1.0.0 enquanto o produto seguiu para v1.8.0. Um literal
    novo aqui faz este teste cair.
    """
    from app import __version__

    assert app.version == __version__


# ═══════════════════════════════════════════════════════════════
# Readiness: /api/v1/health precisa CONFERIR, não afirmar
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_readiness_responde_200_com_tudo_no_ar():
    carimbo = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

    with (
        patch("app.main._checar_banco", new=AsyncMock(return_value=True)),
        patch("app.main._checar_redis", new=AsyncMock(return_value=True)),
        patch("app.main.ultima_rodada_sem_erro", return_value=carimbo),
    ):
        r = await _get("/api/v1/health")

    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status"] == "ok"
    assert corpo["checks"]["database"] == "ok"
    assert corpo["checks"]["redis"] == "ok"
    assert corpo["auto_close"]["last_success"] == carimbo.isoformat()


@pytest.mark.asyncio
async def test_readiness_responde_503_com_o_banco_fora():
    """
    O ponto do M2: uma rota que responde 'ok' sem conferir nada é pior que
    rota nenhuma — dá a quem observa a certeza de que está tudo bem.
    """
    with (
        patch("app.main._checar_banco", new=AsyncMock(return_value=False)),
        patch("app.main._checar_redis", new=AsyncMock(return_value=True)),
        patch("app.main.ultima_rodada_sem_erro", return_value=None),
    ):
        r = await _get("/api/v1/health")

    assert r.status_code == 503
    corpo = r.json()
    assert corpo["status"] == "degraded"
    assert corpo["checks"]["database"] == "down"
    assert corpo["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_readiness_responde_503_com_o_redis_fora():
    """Redis fora derruba blacklist de token e o lock do fechamento."""
    with (
        patch("app.main._checar_banco", new=AsyncMock(return_value=True)),
        patch("app.main._checar_redis", new=AsyncMock(return_value=False)),
        patch("app.main.ultima_rodada_sem_erro", return_value=None),
    ):
        r = await _get("/api/v1/health")

    assert r.status_code == 503
    assert r.json()["checks"]["redis"] == "down"


@pytest.mark.asyncio
async def test_readiness_reporta_rotina_nunca_concluida_sem_derrubar():
    """
    `None` é o normal nos primeiros 60 s de cada worker — o laço espera antes
    da primeira rodada. Derrubar por causa disso daria 503 em todo boot.
    """
    with (
        patch("app.main._checar_banco", new=AsyncMock(return_value=True)),
        patch("app.main._checar_redis", new=AsyncMock(return_value=True)),
        patch("app.main.ultima_rodada_sem_erro", return_value=None),
    ):
        r = await _get("/api/v1/health")

    assert r.status_code == 200
    assert r.json()["auto_close"]["last_success"] is None


@pytest.mark.asyncio
async def test_liveness_nao_depende_de_banco_nem_de_redis():
    """
    `/health` é o alvo do HEALTHCHECK do Dockerfile e do compose. Se passasse
    a depender do banco, uma oscilação do Postgres reiniciaria o container da
    API — trocando uma indisponibilidade parcial por uma total.
    """
    with (
        patch("app.main._checar_banco", new=AsyncMock(return_value=False)),
        patch("app.main._checar_redis", new=AsyncMock(return_value=False)),
    ):
        r = await _get("/health")

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ═══════════════════════════════════════════════════════════════
# O spec da API não é público fora de desenvolvimento
# ═══════════════════════════════════════════════════════════════


def test_spec_e_docs_desligados_fora_de_desenvolvimento():
    """
    /docs e /redoc já eram desligados, mas o openapi_url ficou no default —
    o spec inteiro (todas as rotas, parâmetros e formatos) seguia público em
    produção, que é o mapa que alguém precisa para procurar o que atacar.

    A regra é uma só: onde o /docs aparece, o spec aparece; onde não, nenhum
    dos dois. Por isso a mesma condição, e não uma flag separada.
    """
    from app.core.config import Settings

    prod = Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        app_env="production",
        secret_key="x" * 32,
        cors_origins="https://helphs.example.com",
        frontend_url="https://helphs.example.com",
    )
    assert prod.is_development is False
    assert prod.openapi_url_efetiva() is None

    dev = Settings(database_url="postgresql+asyncpg://u:p@localhost/db", app_env="development")
    assert dev.openapi_url_efetiva() == "/openapi.json"
