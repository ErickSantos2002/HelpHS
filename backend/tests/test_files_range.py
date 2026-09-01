"""
Guarda do cabeçalho `Range` no endpoint de arquivos.

O `FileResponse` do starlette mescla as faixas do `Range` em laço aninhado, sem
teto de quantidade. Medido na 0.51.0, com faixas crescentes e disjuntas — o pior
caso, porque cada nova precisa varrer a lista inteira antes do `append`:

    1000 faixas ->    43 ms
    4000 faixas ->   821 ms   (4,3x mais faixas, 19x mais tempo)
   16000 faixas -> 11874 ms

Ponta a ponta contra uvicorn real, um cabeçalho de 625 KB com 50 mil faixas foi
ACEITO e ocupou o processo por 180 segundos. Como o parsing é CPU síncrona
dentro do event loop e o deploy roda `--workers 1`, uma requisição congela a API
para todos os usuários.

É o PYSEC-2026-1942. O `pip-audit` deixou de reportá-lo depois do upgrade para
o starlette 0.51.0, mas o comportamento continua — a medição acima é do código
instalado, não da versão antiga.

Estes testes prendem a guarda que resolve isso na nossa camada.
"""

import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.services import storage

_CHAVE = "tickets/9/anexo.txt"
_CONTEUDO = b"0123456789" * 200  # 2000 bytes


@pytest.fixture()
def arquivo(tmp_path):
    """Grava um arquivo real e devolve (settings, token válido)."""
    settings = get_settings()
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    yield settings
    settings.upload_dir = original


async def _prepara(settings) -> str:
    await storage.upload_file(_CONTEUDO, _CHAVE, "text/plain", settings)
    return storage.create_file_token(_CHAVE, settings)


def _cliente() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── O que tem que continuar funcionando ───────────────────────


@pytest.mark.asyncio
async def test_sem_range_baixa_inteiro(arquivo):
    token = await _prepara(arquivo)
    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.status_code == 200
    assert r.content == _CONTEUDO


@pytest.mark.asyncio
async def test_range_simples_devolve_206_e_o_pedaco_certo(arquivo):
    """Uma faixa por requisição é o que navegador e gerenciador de download
    pedem, e é o que sustenta retomada de download e busca em vídeo."""
    token = await _prepara(arquivo)
    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}", headers={"Range": "bytes=0-99"})

    assert r.status_code == 206
    assert r.content == _CONTEUDO[:100]


@pytest.mark.asyncio
async def test_range_aberto_no_fim_continua_valendo(arquivo):
    token = await _prepara(arquivo)
    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}", headers={"Range": "bytes=1900-"})

    assert r.status_code == 206
    assert r.content == _CONTEUDO[1900:]


# ── O que passa a ser recusado ────────────────────────────────


@pytest.mark.asyncio
async def test_multi_range_e_recusado_com_416_e_nao_500(arquivo):
    """Duas faixas já quebravam antes desta guarda — `Response content longer
    than Content-Length` no starlette, tanto na 0.51.0 quanto na 0.46.2. Não há
    funcionalidade a preservar; o que muda é a recusa ser controlada."""
    token = await _prepara(arquivo)
    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}", headers={"Range": "bytes=0-99,200-299"})

    assert r.status_code == 416
    assert r.status_code != 500


@pytest.mark.asyncio
async def test_mil_faixas_sao_recusadas(arquivo):
    token = await _prepara(arquivo)
    cabecalho = "bytes=" + ",".join(f"{i*3}-{i*3+1}" for i in range(1, 1001))
    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}", headers={"Range": cabecalho})

    assert r.status_code in (416, 431)


@pytest.mark.asyncio
async def test_cabecalho_gigante_e_recusado_por_tamanho(arquivo):
    token = await _prepara(arquivo)
    cabecalho = "bytes=" + ",".join(f"{i}-{i+1}" for i in range(20_000))
    assert len(cabecalho) > 100_000
    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}", headers={"Range": cabecalho})

    assert r.status_code == 431


# ── A propriedade que dá nome ao achado ───────────────────────


@pytest.mark.asyncio
async def test_range_abusivo_nao_ocupa_o_processo(arquivo):
    """O ponto do achado não é o código de status: é o TEMPO.

    Sem a guarda, 50 mil faixas custavam 180 segundos de CPU síncrona, e com
    `--workers 1` isso é a API inteira parada. O limite de 2 s abaixo é folgado
    de propósito — a guarda é O(1) e responde em milissegundos; se algum dia
    alguém trocá-la por um parser, este teste cai antes de a lentidão chegar em
    produção.
    """
    token = await _prepara(arquivo)
    cabecalho = "bytes=" + ",".join(f"{i*3}-{i*3+1}" for i in range(1, 50_001))

    inicio = time.perf_counter()
    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}", headers={"Range": cabecalho})
    decorrido = time.perf_counter() - inicio

    assert r.status_code in (416, 431)
    assert decorrido < 2.0, f"a recusa levou {decorrido:.1f}s — a guarda deixou de ser O(1)"


# ── A ordem das recusas ───────────────────────────────────────


@pytest.mark.asyncio
async def test_token_invalido_e_recusado_antes_do_range(arquivo):
    """403 tem precedência sobre a guarda do Range.

    Se a ordem invertesse, a recusa do Range viraria oráculo: um 416 diria que
    o token é válido, e um 403 que não — informação que quem só tem o link não
    deveria conseguir separar.
    """
    cabecalho = "bytes=" + ",".join(f"{i}-{i+1}" for i in range(5_000))
    async with _cliente() as c:
        r = await c.get("/api/v1/files/token-inventado", headers={"Range": cabecalho})

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_token_vencido_tambem_vence_a_guarda_do_range(arquivo):
    settings = arquivo
    await storage.upload_file(_CONTEUDO, _CHAVE, "text/plain", settings)
    token = storage.create_file_token(_CHAVE, settings, expires=-10)

    async with _cliente() as c:
        r = await c.get(f"/api/v1/files/{token}", headers={"Range": "bytes=0-99,200-299"})

    assert r.status_code == 403
