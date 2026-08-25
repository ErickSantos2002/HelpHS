"""Smoke tests — verifica que a aplicacao sobe e responde."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_check_versioned():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_versionado_nao_entrega_a_versao_a_quem_nao_esta_logado():
    """
    /api/v1/health responde sem autenticação. A versão exata entregue a
    qualquer um só ajuda quem quer casar release com vulnerabilidade
    conhecida — e quem chama um health check quer saber se a API está de pé,
    não qual versão ela é.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert "version" not in response.json()


def test_versao_da_api_vem_de_uma_fonte_so():
    """
    A versão já esteve escrita à mão em dois pontos do main.py, e as duas
    congelaram em 1.0.0 enquanto o produto seguiu para v1.8.0. Um literal
    novo aqui faz este teste cair.
    """
    from app import __version__

    assert app.version == __version__
