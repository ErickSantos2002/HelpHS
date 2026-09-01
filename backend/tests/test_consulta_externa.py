"""
Consulta de CNPJ e CEP: cache, teto por usuário e falha do provedor.

O risco aqui não é derrubar o HelpHS. É o caminho
`usuário → HelpHS → API externa`: sem teto e sem cache, um usuário autenticado
usa a nossa API como proxy ilimitado para a `brasilapi` e a `viacep`, e quem
leva o bloqueio é o **IP público do servidor** — aí a funcionalidade morre para
todo mundo, e a causa não aparece em nenhum log nosso.

Por isso a ordem que estes testes prendem é **cache primeiro, teto depois**: o
teto limita cada pessoa, mas é o cache que reduz o número de chamadas que de
fato saem daqui.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import chave_por_usuario, limiter
from app.core.security import create_access_token
from app.main import app
from app.services import consulta_externa

_CEP = "01001000"
_CNPJ = "11222333000181"

_RESP_VIACEP = {
    "logradouro": "Praça da Sé",
    "bairro": "Sé",
    "localidade": "São Paulo",
    "uf": "SP",
}


class _CacheFalso:
    """Redis em memória, com contagem — o suficiente para get/setex."""

    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.gravacoes = 0

    async def get(self, chave):
        return self.dados.get(chave)

    async def setex(self, chave, ttl, valor):
        self.dados[chave] = valor
        self.gravacoes += 1


def _resposta(payload, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = payload
    return r


# ══ Cache ═════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_segunda_consulta_do_mesmo_cep_nao_chama_o_provedor():
    """O ponto do módulo. Os colegas de uma empresa moram no mesmo CEP."""
    cache = _CacheFalso()
    cliente = AsyncMock()
    cliente.get = AsyncMock(return_value=_resposta(_RESP_VIACEP))

    with (
        patch.object(consulta_externa, "get_redis", AsyncMock(return_value=cache)),
        patch.object(httpx, "AsyncClient") as fabrica,
    ):
        fabrica.return_value.__aenter__.return_value = cliente

        primeira = await consulta_externa.consulta_cep(_CEP)
        segunda = await consulta_externa.consulta_cep(_CEP)

    assert primeira == segunda
    assert primeira["city"] == "São Paulo"
    assert cliente.get.await_count == 1, "a segunda consulta saiu para a rede"


@pytest.mark.asyncio
async def test_cep_inexistente_tambem_entra_no_cache():
    """A viacep responde 200 com `{"erro": true}`, e não 404.

    Sem cache negativo, varrer CEPs inválidos passaria inteiro por fora do
    cache — que é exatamente o padrão de quem está abusando, não de quem está
    preenchendo um formulário.
    """
    cache = _CacheFalso()
    cliente = AsyncMock()
    cliente.get = AsyncMock(return_value=_resposta({"erro": True}))

    with (
        patch.object(consulta_externa, "get_redis", AsyncMock(return_value=cache)),
        patch.object(httpx, "AsyncClient") as fabrica,
    ):
        fabrica.return_value.__aenter__.return_value = cliente

        for _ in range(2):
            with pytest.raises(consulta_externa.ConsultaNaoEncontradaError):
                await consulta_externa.consulta_cep("99999999")

    assert cliente.get.await_count == 1


@pytest.mark.asyncio
async def test_redis_fora_do_ar_nao_derruba_a_consulta():
    """Cache é otimização. Otimização que vira ponto de falha piora o sistema."""
    cliente = AsyncMock()
    cliente.get = AsyncMock(return_value=_resposta(_RESP_VIACEP))

    with (
        patch.object(consulta_externa, "get_redis", AsyncMock(side_effect=OSError("redis fora"))),
        patch.object(httpx, "AsyncClient") as fabrica,
    ):
        fabrica.return_value.__aenter__.return_value = cliente
        resultado = await consulta_externa.consulta_cep(_CEP)

    assert resultado["city"] == "São Paulo"


# ══ Falha do provedor ═════════════════════════════════════════


@pytest.mark.asyncio
async def test_timeout_do_provedor_vira_503_e_nao_500():
    """Antes disto não havia try/except nenhum: um ReadTimeout da viacep subia
    como exceção não tratada e o usuário recebia 500 — dizendo que o defeito é
    nosso quando o provedor é que está fora."""
    cliente = AsyncMock()
    cliente.get = AsyncMock(side_effect=httpx.ReadTimeout("estourou"))

    with (
        patch.object(consulta_externa, "get_redis", AsyncMock(return_value=_CacheFalso())),
        patch.object(httpx, "AsyncClient") as fabrica,
    ):
        fabrica.return_value.__aenter__.return_value = cliente
        with pytest.raises(consulta_externa.ConsultaIndisponivelError):
            await consulta_externa.consulta_cep(_CEP)


@pytest.mark.asyncio
async def test_provedor_inalcancavel_tambem_vira_indisponivel():
    cliente = AsyncMock()
    cliente.get = AsyncMock(side_effect=httpx.ConnectError("sem rota"))

    with (
        patch.object(consulta_externa, "get_redis", AsyncMock(return_value=_CacheFalso())),
        patch.object(httpx, "AsyncClient") as fabrica,
    ):
        fabrica.return_value.__aenter__.return_value = cliente
        with pytest.raises(consulta_externa.ConsultaIndisponivelError):
            await consulta_externa.consulta_cnpj(_CNPJ)


@pytest.mark.asyncio
async def test_o_timeout_e_declarado_e_finito():
    """Chamada externa sem timeout prende o worker até o outro lado desistir.

    O valor não é o ponto — a existência é. Este teste cai se alguém trocar o
    cliente por um sem timeout.
    """
    assert consulta_externa._TIMEOUT.read is not None
    assert consulta_externa._TIMEOUT.connect is not None
    assert consulta_externa._TIMEOUT.read <= 30


# ══ Chave do rate limit ═══════════════════════════════════════


def _requisicao_com(cabecalhos: dict) -> MagicMock:
    req = MagicMock()
    req.headers = cabecalhos
    req.client = MagicMock(host="203.0.113.9")
    return req


def test_a_chave_do_limite_e_o_usuario_e_nao_o_ip():
    """IP é a chave errada para endpoint autenticado: uma empresa atrás de NAT
    dividiria o balde, e quem abusa troca de IP mais fácil que de conta."""
    token = create_access_token(
        __import__("uuid").UUID("11111111-1111-1111-1111-111111111111"), "client", "a@b.com"
    )
    chave = chave_por_usuario(_requisicao_com({"authorization": f"Bearer {token}"}))

    assert chave == "usuario:11111111-1111-1111-1111-111111111111"
    assert "203.0.113.9" not in chave


def test_usuarios_diferentes_recebem_baldes_diferentes():
    import uuid as _uuid

    def _chave(uid: str) -> str:
        t = create_access_token(_uuid.UUID(uid), "client", "x@y.com")
        return chave_por_usuario(_requisicao_com({"authorization": f"Bearer {t}"}))

    a = _chave("11111111-1111-1111-1111-111111111111")
    b = _chave("22222222-2222-2222-2222-222222222222")
    assert a != b, "o usuário A consumiria o limite do usuário B"


def test_sem_token_utilizavel_cai_para_o_ip():
    """Não acontece nestas rotas, que exigem sessão — mas chave vazia juntaria
    todo mundo num balde só, e o padrão precisa ser o restritivo."""
    assert chave_por_usuario(_requisicao_com({})) == "203.0.113.9"
    assert chave_por_usuario(_requisicao_com({"authorization": "Bearer lixo"})) == "203.0.113.9"


# ══ O teto, ponta a ponta ═════════════════════════════════════


@pytest.fixture()
def limiter_ligado():
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


@pytest.mark.asyncio
async def test_estouro_devolve_429_e_para_de_chamar_o_provedor(limiter_ligado):
    """As duas metades importam. O 429 protege o usuário; **parar de chamar o
    provedor** é o que protege o IP do servidor, que é o risco real."""
    from app.core.security import get_current_user

    usuario = MagicMock()
    usuario.id = __import__("uuid").UUID("33333333-3333-3333-3333-333333333333")
    app.dependency_overrides[get_current_user] = lambda: usuario

    token = create_access_token(usuario.id, "client", "c@d.com")
    cache = _CacheFalso()
    cliente = AsyncMock()
    # Valores diferentes a cada chamada, para o cache não mascarar o teto
    cliente.get = AsyncMock(return_value=_resposta(_RESP_VIACEP))

    try:
        with (
            patch.object(consulta_externa, "get_redis", AsyncMock(return_value=cache)),
            patch.object(httpx, "AsyncClient") as fabrica,
        ):
            fabrica.return_value.__aenter__.return_value = cliente
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://t") as c:
                cabecalho = {"Authorization": f"Bearer {token}"}
                # 30/hour: as 30 primeiras passam, a 31ª é cortada
                for i in range(30):
                    r = await c.get(f"/api/v1/auth/cep/0100100{i % 10}", headers=cabecalho)
                    assert r.status_code == 200, f"a {i+1}ª foi cortada cedo demais: {r.text}"

                chamadas_antes = cliente.get.await_count
                bloqueada = await c.get("/api/v1/auth/cep/70002900", headers=cabecalho)

        assert bloqueada.status_code == 429
        assert cliente.get.await_count == chamadas_antes, (
            "o provedor externo foi chamado DEPOIS do 429 — o teto não está "
            "protegendo o IP do servidor, que é o motivo de ele existir"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_o_teto_de_um_usuario_nao_gasta_o_do_outro(limiter_ligado):
    from app.core.security import get_current_user

    usuario = MagicMock()
    usuario.id = __import__("uuid").UUID("44444444-4444-4444-4444-444444444444")
    app.dependency_overrides[get_current_user] = lambda: usuario

    import uuid as _uuid

    token_a = create_access_token(
        _uuid.UUID("44444444-4444-4444-4444-444444444444"), "client", "a@a"
    )
    token_b = create_access_token(
        _uuid.UUID("55555555-5555-5555-5555-555555555555"), "client", "b@b"
    )

    cliente = AsyncMock()
    cliente.get = AsyncMock(return_value=_resposta(_RESP_VIACEP))

    try:
        with (
            patch.object(consulta_externa, "get_redis", AsyncMock(return_value=_CacheFalso())),
            patch.object(httpx, "AsyncClient") as fabrica,
        ):
            fabrica.return_value.__aenter__.return_value = cliente
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://t") as c:
                for i in range(30):
                    r = await c.get(
                        f"/api/v1/auth/cep/0100100{i % 10}",
                        headers={"Authorization": f"Bearer {token_a}"},
                    )
                    assert r.status_code == 200

                estourado_a = await c.get(
                    "/api/v1/auth/cep/70002900",
                    headers={"Authorization": f"Bearer {token_a}"},
                )
                # O B chega com o balde intacto
                primeiro_b = await c.get(
                    "/api/v1/auth/cep/70002900",
                    headers={"Authorization": f"Bearer {token_b}"},
                )

        assert estourado_a.status_code == 429
        assert primeiro_b.status_code == 200, "o usuário B pagou pelo consumo do A"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_a_consulta_normal_continua_passando(limiter_ligado):
    from app.core.security import get_current_user

    usuario = MagicMock()
    usuario.id = __import__("uuid").UUID("66666666-6666-6666-6666-666666666666")
    app.dependency_overrides[get_current_user] = lambda: usuario
    token = create_access_token(usuario.id, "client", "e@f.com")

    cliente = AsyncMock()
    cliente.get = AsyncMock(return_value=_resposta(_RESP_VIACEP))

    try:
        with (
            patch.object(consulta_externa, "get_redis", AsyncMock(return_value=_CacheFalso())),
            patch.object(httpx, "AsyncClient") as fabrica,
        ):
            fabrica.return_value.__aenter__.return_value = cliente
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.get(
                    f"/api/v1/auth/cep/{_CEP}", headers={"Authorization": f"Bearer {token}"}
                )

        assert r.status_code == 200
        assert r.json()["city"] == "São Paulo"
        assert r.json()["cep"] == "01001-000"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
