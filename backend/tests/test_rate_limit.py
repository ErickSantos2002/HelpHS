"""
Rate limiting de autenticação.

O limiter fica desligado por padrão sob APP_ENV=testing (senão as várias
chamadas de /auth/login das outras suítes estourariam o limite). Aqui a gente
liga de propósito e prova que o brute-force é barrado.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import limiter
from app.main import app


@pytest.fixture()
def limiter_ligado():
    """Liga o limiter e zera a contagem em memória, restaurando ao final."""
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


def _db_sem_usuario():
    """get_db override: nenhum usuário encontrado → todo login dá 401."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    async def _gen():
        yield session

    return _gen


@pytest.mark.asyncio
async def test_login_barra_apos_estourar_o_limite(limiter_ligado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_sem_usuario()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            body = {"email": "quem@quer.com", "password": "SenhaErrada1"}

            # O limite é 5/15minutes: as 5 primeiras passam pela regra e batem
            # no 401 (credencial inválida); a 6ª é cortada pelo limiter antes.
            for _ in range(5):
                r = await c.post("/api/v1/auth/login", json=body)
                assert r.status_code == 401, r.text

            bloqueado = await c.post("/api/v1/auth/login", json=body)
            assert bloqueado.status_code == 429
            assert "Muitas tentativas" in bloqueado.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_limiter_desligado_nao_interfere():
    """Com o limiter desligado (padrão em teste), não há corte por volume."""
    assert limiter.enabled is False

    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_sem_usuario()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            body = {"email": "quem@quer.com", "password": "SenhaErrada1"}
            for _ in range(8):
                r = await c.post("/api/v1/auth/login", json=body)
                assert r.status_code == 401, r.text
    finally:
        app.dependency_overrides.clear()
