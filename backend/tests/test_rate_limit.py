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


# ── Baldes separados por endpoint ─────────────────────────────


def _db_vazio():
    """get_db override genérico, para endpoints que nem chegam a consultar."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.get = AsyncMock(return_value=None)

    async def _gen():
        yield session

    return _gen


async def _esgota(c, caminho, corpo, status_esperado, quantas):
    for _ in range(quantas):
        r = await c.post(caminho, json=corpo)
        assert r.status_code == status_esperado, r.text
    return await c.post(caminho, json=corpo)


@pytest.mark.asyncio
async def test_reset_password_tem_limite(limiter_ligado):
    """Trocar senha por token era o único caminho de escrita sem limite algum."""
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_vazio()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            corpo = {"token": "nao.e.um.token.valido", "password": "SenhaNova1"}
            bloqueado = await _esgota(c, "/api/v1/auth/reset-password", corpo, 400, 10)

        assert bloqueado.status_code == 429
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_email_tem_limite(limiter_ligado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_vazio()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            corpo = {"token": "nao.e.um.token.valido"}
            bloqueado = await _esgota(c, "/api/v1/auth/verify-email", corpo, 400, 10)

        assert bloqueado.status_code == 429
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cada_endpoint_tem_o_proprio_balde(limiter_ligado):
    """Esgotar o login não pode fechar a confirmação de e-mail junto.

    O slowapi separa por rota, então isto já vale hoje — o teste existe para que
    continue valendo se alguém trocar o `key_func` ou o `key_style`, que é
    exatamente o tipo de mudança que junta baldes sem ninguém perceber.
    """
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_sem_usuario()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            login = {"email": "quem@quer.com", "password": "SenhaErrada1"}
            for _ in range(5):
                await c.post("/api/v1/auth/login", json=login)
            assert (await c.post("/api/v1/auth/login", json=login)).status_code == 429

            # Outro endpoint, outro balde: ainda responde a regra, não o limiter
            outro = await c.post(
                "/api/v1/auth/verify-email", json={"token": "nao.e.um.token.valido"}
            )
            assert outro.status_code != 429
    finally:
        app.dependency_overrides.clear()


# ── O 429 diz quanto esperar ──────────────────────────────────


@pytest.mark.asyncio
async def test_o_429_diz_quanto_esperar(limiter_ligado):
    """Sem `Retry-After`, o cliente só pode chutar — e chutar é tentar de novo.

    O valor sai do estado real da janela do limiter, não de uma constante: um
    número fixo mentiria assim que alguém mudasse a configuração.
    """
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_sem_usuario()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            corpo = {"email": "quem@quer.com", "password": "SenhaErrada1"}
            bloqueado = await _esgota(c, "/api/v1/auth/login", corpo, 401, 5)

        assert bloqueado.status_code == 429
        cabecalho = bloqueado.headers.get("retry-after")
        assert cabecalho is not None, "o 429 saiu sem Retry-After"
        segundos = int(cabecalho)
        # Janela de 15 min: qualquer coisa fora disso é constante disfarçada
        assert 0 < segundos <= 15 * 60
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resposta_normal_nao_carrega_retry_after(limiter_ligado):
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_sem_usuario()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post(
                "/api/v1/auth/login", json={"email": "a@b.com", "password": "SenhaErrada1"}
            )

        assert r.status_code == 401
        assert "retry-after" not in {k.lower() for k in r.headers}
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_o_retry_after_encolhe_conforme_a_janela_passa(limiter_ligado, monkeypatch):
    """Separa "número derivado" de "constante disfarçada".

    O teste acima aceita qualquer valor dentro da janela — e uma constante de
    900 passaria nele. O que distingue os dois é o número **diminuir** quando o
    relógio anda: só um valor calculado da janela real faz isso.
    """
    import time as _time

    import app.main as main
    from app.core.database import get_db

    app.dependency_overrides[get_db] = _db_sem_usuario()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            corpo = {"email": "quem@quer.com", "password": "SenhaErrada1"}
            primeiro = int(
                (await _esgota(c, "/api/v1/auth/login", corpo, 401, 5)).headers["retry-after"]
            )

            agora = _time.time
            monkeypatch.setattr(main.time, "time", lambda: agora() + 120)
            segundo = int((await c.post("/api/v1/auth/login", json=corpo)).headers["retry-after"])

        assert segundo <= primeiro - 115, f"{primeiro} -> {segundo}: não acompanhou o relógio"
    finally:
        app.dependency_overrides.clear()


# ── Inventário ────────────────────────────────────────────────


def test_o_inventario_de_endpoints_limitados_e_este():
    """Rota nova em `/auth` nasce sem limite, e nada avisa.

    Não há `default_limits` nem `SlowAPIMiddleware`: a proteção vem só do
    decorator por rota. Esquecer é fácil e o sintoma é a ausência de sintoma.
    Este teste transforma o esquecimento em falha de suíte — quem adicionar um
    endpoint de autenticação precisa decidir se ele leva limite e dizer aqui.

    Os números também estão fixados: mudar um limite passa a ser uma alteração
    deliberada, visível no diff, e não um ajuste que ninguém revisa.
    """
    from app.core.rate_limit import limiter

    esperado = {
        # Tentativa de credencial
        "app.routers.auth.login": "5 per 15 minute",
        "app.routers.auth.mfa_verify": "5 per 15 minute",
        # Ciclo de conta — cada chamada dispara e-mail
        "app.routers.auth.register": "5 per 15 minute",
        "app.routers.auth.forgot_password": "5 per 15 minute",
        "app.routers.auth.resend_verification": "5 per 15 minute",
        # Resgate de token de e-mail — mais folgado, ver config.py
        "app.routers.auth.verify_email": "10 per 15 minute",
        "app.routers.auth.reset_password": "10 per 15 minute",
    }
    real = {
        nome: str(limites[0].limit)
        for nome, limites in limiter._route_limits.items()
        if nome.startswith("app.routers.auth.")
    }

    assert real == esperado


def test_o_refresh_segue_sem_limite_de_proposito():
    """Decisão registrada, não esquecimento — e o motivo é o balde compartilhado.

    Em produção o `FORWARDED_ALLOW_IPS` está vazio (a porta 8000 está publicada,
    e preenchê-lo antes de fechá-la seria pior). Isso faz o `get_remote_address`
    devolver o IP do proxy: **um balde único para o sistema inteiro**.

    `/auth/refresh` é chamado automaticamente pelo interceptor de toda sessão
    ativa. Um limite por IP nesse endpoint, sob balde compartilhado, deslogaria a
    empresa toda assim que o volume normal passasse do teto — trocando um risco
    hipotético de força bruta por uma indisponibilidade certa.

    E o ganho seria pequeno: o endpoint exige um JWT RS256 válido **e** que ele
    bata com o que está no Redis. Não há o que adivinhar.

    Revisitar quando a porta 8000 for fechada e o `FORWARDED_ALLOW_IPS` puder
    ser preenchido.
    """
    from app.core.rate_limit import limiter

    assert "app.routers.auth.refresh" not in limiter._route_limits
