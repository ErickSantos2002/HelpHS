"""Correlação de requisição: um id que amarra as linhas de log de uma chamada.

Antes disto o backend não tinha **nada** — nem `request_id`, nem `ContextVar`,
nem middleware que não fosse o CORS. Cada linha de log era um evento solto, e
reconstruir o percurso de uma requisição dependia de adivinhar pela ordem e pelo
relógio.

O teste que mais importa aqui é
`test_requisicoes_simultaneas_nao_trocam_de_id`. Um id guardado em variável de
módulo, ou num atributo do app, passaria em todos os outros testes deste arquivo
e vazaria entre requisições concorrentes — que é o caso normal de um servidor,
não a exceção.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from loguru import logger

from app.main import app

_CAMINHO = "/health"


def _cliente() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── O cabeçalho ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_toda_resposta_carrega_um_id():
    async with _cliente() as c:
        resposta = await c.get(_CAMINHO)

    assert resposta.headers.get("x-request-id")


@pytest.mark.asyncio
async def test_dois_pedidos_recebem_ids_diferentes():
    async with _cliente() as c:
        primeiro = (await c.get(_CAMINHO)).headers["x-request-id"]
        segundo = (await c.get(_CAMINHO)).headers["x-request-id"]

    assert primeiro != segundo


@pytest.mark.asyncio
async def test_um_id_de_fora_e_reaproveitado():
    """Quem já tem um id — proxy, front, outro serviço — manda e a gente adota.

    É o que permite amarrar o log do backend ao do lado de fora sem combinar
    formato nenhum.
    """
    async with _cliente() as c:
        resposta = await c.get(_CAMINHO, headers={"X-Request-ID": "abc-123-DEF"})

    assert resposta.headers["x-request-id"] == "abc-123-DEF"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sujo",
    [
        # Só ASCII: o httpx recusa cabeçalho com acento no próprio cliente, e o
        # caso viraria um teste do httpx em vez do middleware.
        "id com espaco",
        "quebra\nde linha",
        "x" * 300,
        "aspas\"e'coisas",
        "",
        "; DROP TABLE users",
    ],
)
async def test_id_de_fora_sujo_e_descartado_em_vez_de_ecoado(sujo):
    """O id entra no log de todas as linhas da requisição.

    Ecoar entrada arbitrária ali é injeção de log: quebra de linha forja
    registros inteiros, e um valor gigante enche o agregador. Aceitar de fora é
    conveniência; conferir é o preço dela.
    """
    async with _cliente() as c:
        resposta = await c.get(_CAMINHO, headers={"X-Request-ID": sujo})

    devolvido = resposta.headers["x-request-id"]
    assert devolvido != sujo
    assert devolvido, "descartar o sujo não pode deixar a resposta sem id"


# ── O id chega ao log ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_as_linhas_de_log_da_requisicao_carregam_o_id():
    """De nada adianta o cabeçalho se o log não souber dele.

    A asserção é sobre `record["extra"]`, não sobre o texto: em produção o sink
    serializa em JSON, e campo estruturado é o que se filtra sem regex.
    """
    from app.middleware.correlacao import CorrelacaoMiddleware

    capturado: list[dict] = []
    sink = logger.add(lambda m: capturado.append(dict(m.record["extra"])), level="DEBUG")

    async def _app_que_loga(scope, receive, send):
        # DENTRO da requisição. Logar depois do `await` do cliente não provaria
        # nada: o contexto já foi restaurado, e o campo sairia vazio de direito.
        logger.info("linha emitida de dentro da requisição")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    try:
        envolvido = CorrelacaoMiddleware(_app_que_loga)
        async with AsyncClient(transport=ASGITransport(app=envolvido), base_url="http://t") as c:
            resposta = await c.get("/qualquer", headers={"X-Request-ID": "amarra-1"})
    finally:
        logger.remove(sink)

    assert resposta.headers["x-request-id"] == "amarra-1"
    # O id EXATO, não "algum id": bastaria carimbar um valor novo a cada linha
    # para a asserção fraca passar sem correlacionar coisa nenhuma.
    assert any(e.get("request_id") == "amarra-1" for e in capturado)


@pytest.mark.asyncio
async def test_fora_de_requisicao_o_log_nao_quebra():
    """Boot, worker de fundo e scripts logam sem requisição nenhuma."""
    capturado: list[dict] = []
    sink = logger.add(lambda m: capturado.append(dict(m.record["extra"])), level="DEBUG")
    try:
        logger.info("linha de fora de qualquer requisição")
    finally:
        logger.remove(sink)

    assert capturado, "o log parou de funcionar fora de requisição"
    assert capturado[-1].get("request_id", "") == ""


# ── Isolamento entre requisições concorrentes ─────────────────


@pytest.mark.asyncio
async def test_requisicoes_simultaneas_nao_trocam_de_id():
    """O teste que separa `ContextVar` de variável global.

    Um id guardado em variável de módulo passaria em todos os testes acima e
    vazaria aqui: as duas requisições veriam o valor da última a escrever. Como
    o servidor atende concorrente o tempo todo, esse é o caso normal.
    """
    async with _cliente() as c:
        a, b = await asyncio.gather(
            c.get(_CAMINHO, headers={"X-Request-ID": "corrida-A"}),
            c.get(_CAMINHO, headers={"X-Request-ID": "corrida-B"}),
        )

    assert a.headers["x-request-id"] == "corrida-A"
    assert b.headers["x-request-id"] == "corrida-B"


# ── A camada nova não pode estragar o que já existia ──────────


@pytest.mark.asyncio
async def test_erro_de_validacao_continua_igual_e_ganha_o_id():
    """Middleware novo entra ENTRE o cliente e os três exception handlers.

    O corpo e o status dos erros não podem mudar de forma — só ganhar o
    cabeçalho.
    """
    async with _cliente() as c:
        resposta = await c.post("/api/v1/auth/login", json={"email": "nao-e-email"})

    assert resposta.status_code == 422
    assert "detail" in resposta.json()
    assert resposta.headers.get("x-request-id")


@pytest.mark.asyncio
async def test_404_continua_igual_e_ganha_o_id():
    async with _cliente() as c:
        resposta = await c.get("/api/v1/nao-existe-isso")

    assert resposta.status_code == 404
    assert resposta.headers.get("x-request-id")


@pytest.mark.asyncio
async def test_o_cors_continua_respondendo():
    """O CORS é o único middleware que existia; a ordem não pode quebrá-lo.

    Sem os cabeçalhos de CORS o navegador recusa a resposta antes de o front
    conseguir lê-la — a falha apareceria como "erro de rede", não como erro de
    middleware.
    """
    from app.core.config import get_settings

    origem = get_settings().get_cors_origins()[0]

    async with _cliente() as c:
        resposta = await c.get(_CAMINHO, headers={"Origin": origem})

    assert resposta.headers.get("access-control-allow-origin") == origem


@pytest.mark.asyncio
async def test_o_front_consegue_ler_o_id_de_outra_origem():
    """`expose_headers` é o que deixa o JavaScript enxergar o cabeçalho.

    Sem isso o id existe, viaja e é invisível para quem abriria o chamado de
    suporte citando ele.
    """
    from app.core.config import get_settings

    origem = get_settings().get_cors_origins()[0]

    async with _cliente() as c:
        resposta = await c.get(_CAMINHO, headers={"Origin": origem})

    expostos = resposta.headers.get("access-control-expose-headers", "").lower()
    assert "x-request-id" in expostos


# ── Higiene: dado pessoal fora do log ─────────────────────────


def test_o_login_falhado_nao_registra_o_email_digitado():
    """Era o pior dos treze pontos que logavam e-mail em claro.

    A linha registrava o que foi DIGITADO numa tentativa falha — e-mail de quem
    não tem conta (material de enumeração, servido pronto no agregador) e, de
    vez em quando, a senha, quando a pessoa erra o campo.

    A asserção é sobre o código-fonte porque o valor de provar isso está em
    impedir que a linha volte, não em exercitar o caminho: quem reintroduzir o
    e-mail aqui vai reintroduzi-lo numa f-string.
    """
    import inspect

    from app.routers import auth

    fonte = inspect.getsource(auth)
    assert "Failed login attempt for email=" not in fonte
    assert 'logger.warning("Failed login attempt")' in fonte


def test_os_logs_de_auth_identificam_por_id_e_nao_por_email():
    """Identidade em log vira `user_id`, que correlaciona igual e não é PII."""
    import inspect
    import re

    from app.routers import auth

    fonte = inspect.getsource(auth)
    vazando = re.findall(r"logger\.\w+\(f?\"[^\"]*\{[^}]*\.email\}", fonte)

    assert vazando == [], f"linha de log com e-mail em claro: {vazando}"
