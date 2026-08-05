"""
Testes do endpoint que entrega os arquivos.

O acesso é por link temporário assinado — não pela sessão do usuário — porque a
foto de perfil e a pré-visualização de anexo são carregadas pelo <img> do
navegador, que não manda cabeçalho de autenticação.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.services import storage


@pytest.fixture()
def settings_com_upload_dir(tmp_path):
    """Aponta o upload_dir para uma pasta temporária durante o teste."""
    settings = get_settings()
    original = settings.upload_dir
    settings.upload_dir = str(tmp_path)
    yield settings
    settings.upload_dir = original


@pytest.mark.asyncio
async def test_baixa_o_arquivo_com_token_valido(settings_com_upload_dir, tmp_path):
    settings = settings_com_upload_dir
    await storage.upload_file(b"conteudo do laudo", "tickets/1/laudo.txt", "text/plain", settings)
    token = storage.create_file_token("tickets/1/laudo.txt", settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.status_code == 200
    assert r.content == b"conteudo do laudo"


@pytest.mark.asyncio
async def test_sem_token_valido_nao_baixa(settings_com_upload_dir):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/files/token-inventado")

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_token_vencido_nao_baixa(settings_com_upload_dir):
    settings = settings_com_upload_dir
    await storage.upload_file(b"x", "arquivo.txt", "text/plain", settings)
    token = storage.create_file_token("arquivo.txt", settings, expires=-10)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.status_code == 403
    assert "expirado" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_arquivo_removido_do_disco_retorna_404(settings_com_upload_dir):
    settings = settings_com_upload_dir
    token = storage.create_file_token("nunca-gravado.pdf", settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_imagem_e_exibida_inline(settings_com_upload_dir):
    """Avatar e preview precisam abrir no <img>, então imagem vai inline."""
    settings = settings_com_upload_dir
    await storage.upload_file(b"\x89PNG fake", "avatars/1.png", "image/png", settings)
    token = storage.create_file_token("avatars/1.png", settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert "attachment" not in r.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_html_nunca_e_servido_inline(settings_com_upload_dir):
    """
    Arquivo que o navegador executaria precisa descer como download.

    Servir HTML inline na origem da API seria XSS armazenado: bastaria um
    anexo malicioso para rodar script no domínio do sistema.
    """
    settings = settings_com_upload_dir
    await storage.upload_file(
        b"<script>alert(1)</script>", "tickets/1/x.html", "text/html", settings
    )
    token = storage.create_file_token("tickets/1/x.html", settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.status_code == 200
    assert "text/html" not in r.headers["content-type"]
    assert r.headers["content-disposition"].startswith("attachment")


@pytest.mark.asyncio
async def test_svg_nao_e_servido_inline(settings_com_upload_dir):
    """SVG é imagem, mas aceita <script> dentro — trata como download."""
    settings = settings_com_upload_dir
    await storage.upload_file(b"<svg onload=alert(1)>", "tickets/1/x.svg", "image/svg+xml", settings)
    token = storage.create_file_token("tickets/1/x.svg", settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert "svg" not in r.headers["content-type"]
    assert r.headers["content-disposition"].startswith("attachment")


@pytest.mark.asyncio
async def test_resposta_traz_cabecalhos_de_protecao(settings_com_upload_dir):
    settings = settings_com_upload_dir
    await storage.upload_file(b"conteudo", "tickets/1/laudo.pdf", "application/pdf", settings)
    token = storage.create_file_token("tickets/1/laudo.pdf", settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_token_com_caminho_malicioso_e_recusado(settings_com_upload_dir):
    """Mesmo assinado pelo servidor, uma key que escapa do diretório não serve."""
    settings = settings_com_upload_dir
    token = storage.create_file_token("../../../etc/passwd", settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{token}")

    assert r.status_code == 403
