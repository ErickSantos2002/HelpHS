"""
Testes do armazenamento em disco.

Cada teste usa um diretório temporário próprio como upload_dir — nada toca o
sistema de arquivos real do projeto.
"""

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jose import jwt

from app.core.config import get_settings
from app.services import storage

_real = get_settings()


def _settings(tmp_path: Path, expires: int = 3600):
    """Settings de verdade para as chaves JWT, com upload_dir isolado."""
    s = MagicMock()
    s.upload_dir = str(tmp_path)
    s.file_url_expires_seconds = expires
    s.api_prefix = "/api/v1"
    s.jwt_algorithm = _real.jwt_algorithm
    s.jwt_issuer = _real.jwt_issuer
    s.get_private_key = _real.get_private_key
    s.get_public_key = _real.get_public_key
    return s


# ═══════════════════════════════════════════════════════════════
# resolve_path — proteção contra caminho malicioso
# ═══════════════════════════════════════════════════════════════


def test_resolve_path_dentro_do_diretorio(tmp_path):
    settings = _settings(tmp_path)
    caminho = storage.resolve_path("tickets/abc/arquivo.pdf", settings)
    assert str(caminho).startswith(str(tmp_path.resolve()))


def test_resolve_path_recusa_subir_diretorio(tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(storage.StorageError):
        storage.resolve_path("../../etc/passwd", settings)


def test_resolve_path_recusa_caminho_absoluto(tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(storage.StorageError):
        storage.resolve_path("/etc/passwd", settings)


# ═══════════════════════════════════════════════════════════════
# ensure_bucket
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ensure_bucket_cria_o_diretorio(tmp_path):
    alvo = tmp_path / "uploads"
    settings = _settings(alvo)

    await storage.ensure_bucket(settings)

    assert alvo.is_dir()


@pytest.mark.asyncio
async def test_ensure_bucket_e_idempotente(tmp_path):
    settings = _settings(tmp_path)

    await storage.ensure_bucket(settings)
    await storage.ensure_bucket(settings)  # não pode explodir

    assert tmp_path.is_dir()


# ═══════════════════════════════════════════════════════════════
# upload / delete
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_upload_grava_o_arquivo(tmp_path):
    settings = _settings(tmp_path)
    key = f"tickets/{uuid.uuid4()}/laudo.pdf"

    devolvido = await storage.upload_file(b"conteudo do laudo", key, "application/pdf", settings)

    assert devolvido == key
    assert (tmp_path / key).read_bytes() == b"conteudo do laudo"


@pytest.mark.asyncio
async def test_upload_cria_subpastas(tmp_path):
    settings = _settings(tmp_path)

    await storage.upload_file(b"x", "a/b/c/arquivo.txt", "text/plain", settings)

    assert (tmp_path / "a" / "b" / "c" / "arquivo.txt").is_file()


@pytest.mark.asyncio
async def test_upload_recusa_key_maliciosa(tmp_path):
    settings = _settings(tmp_path)

    with pytest.raises(storage.StorageError):
        await storage.upload_file(b"x", "../fora.txt", "text/plain", settings)


@pytest.mark.asyncio
async def test_delete_remove_o_arquivo(tmp_path):
    settings = _settings(tmp_path)
    await storage.upload_file(b"x", "arquivo.txt", "text/plain", settings)

    await storage.delete_file("arquivo.txt", settings)

    assert not (tmp_path / "arquivo.txt").exists()


@pytest.mark.asyncio
async def test_delete_de_arquivo_inexistente_nao_quebra(tmp_path):
    settings = _settings(tmp_path)
    await storage.delete_file("nao-existe.txt", settings)  # silencioso


@pytest.mark.asyncio
async def test_delete_com_key_maliciosa_nao_quebra(tmp_path):
    settings = _settings(tmp_path)
    await storage.delete_file("../../algo.txt", settings)  # apenas registra o aviso


# ═══════════════════════════════════════════════════════════════
# Token do link temporário
# ═══════════════════════════════════════════════════════════════


def test_token_de_ida_e_volta(tmp_path):
    settings = _settings(tmp_path)
    token = storage.create_file_token("tickets/x/laudo.pdf", settings)

    assert storage.read_file_token(token, settings) == "tickets/x/laudo.pdf"


def test_token_vencido_e_recusado(tmp_path):
    settings = _settings(tmp_path)
    token = storage.create_file_token("arquivo.pdf", settings, expires=-10)

    with pytest.raises(storage.StorageError):
        storage.read_file_token(token, settings)


def test_token_adulterado_e_recusado(tmp_path):
    settings = _settings(tmp_path)

    with pytest.raises(storage.StorageError):
        storage.read_file_token("nao.e.um.token", settings)


def test_token_de_login_nao_serve_para_baixar_arquivo(tmp_path):
    """Um access token comum não pode virar link de download."""
    settings = _settings(tmp_path)
    payload = {
        "sub": "qualquer-arquivo.pdf",
        "type": "access",
        "iss": settings.jwt_issuer,
        "exp": 9999999999,
    }
    token = jwt.encode(payload, settings.get_private_key(), algorithm=settings.jwt_algorithm)

    with pytest.raises(storage.StorageError):
        storage.read_file_token(token, settings)


@pytest.mark.asyncio
async def test_presigned_url_aponta_para_o_endpoint_de_arquivos(tmp_path):
    settings = _settings(tmp_path)

    url = await storage.get_presigned_url("tickets/x/laudo.pdf", settings)

    assert url.startswith("/api/v1/files/")
    token = url.rsplit("/", 1)[1]
    assert storage.read_file_token(token, settings) == "tickets/x/laudo.pdf"
