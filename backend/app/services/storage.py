"""
Armazenamento de arquivos em disco.

Anexos de chamado e fotos de perfil ficam em `settings.upload_dir`, que no
deploy precisa apontar para um volume — sem volume, o Docker descarta os
arquivos a cada redeploy.

A interface e a mesma de quando o armazenamento era MinIO/S3, entao os routers
nao precisam saber onde o arquivo esta:

    ensure_bucket(settings)                  -> garante o diretorio
    upload_file(data, key, mime, settings)   -> grava e devolve a key
    delete_file(key, settings)               -> remove
    get_presigned_url(key, settings, expires)-> link temporario assinado

O "presigned url" aqui e um JWT curto embutido na URL, validado pelo endpoint
/files. Mesma ideia do link temporario do S3: quem nao tem o token nao baixa.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

from jose import JWTError, jwt
from loguru import logger

from app.core.config import Settings

_TOKEN_TYPE = "file"


class StorageError(Exception):
    """Falha ao gravar, ler ou apagar um arquivo."""


def _root(settings: Settings) -> Path:
    return Path(settings.upload_dir).resolve()


def resolve_path(key: str, settings: Settings) -> Path:
    """
    Converte a key num caminho absoluto dentro de upload_dir.

    Recusa qualquer key que tente escapar do diretorio (../, caminho absoluto,
    link simbolico) — sem isso, uma key manipulada leria arquivos do servidor.
    """
    if not key or key.startswith(("/", "\\")) or Path(key).is_absolute():
        raise StorageError(f"Caminho de arquivo invalido: {key}")

    root = _root(settings)
    candidate = (root / key).resolve()
    if root not in candidate.parents:
        raise StorageError(f"Caminho de arquivo invalido: {key}")
    return candidate


async def ensure_bucket(settings: Settings) -> None:
    """Cria o diretorio de uploads se ainda nao existir (idempotente)."""
    loop = asyncio.get_event_loop()
    root = _root(settings)

    def _create() -> None:
        root.mkdir(parents=True, exist_ok=True)

    await loop.run_in_executor(None, _create)


async def upload_file(
    data: bytes,
    key: str,
    content_type: str,
    settings: Settings,
) -> str:
    """Grava os bytes em disco e devolve a key."""
    loop = asyncio.get_event_loop()
    destino = resolve_path(key, settings)

    def _write() -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)

    try:
        await loop.run_in_executor(None, _write)
    except OSError as exc:
        # Causa mais comum em producao: o volume nao esta montado ou o
        # usuario do container nao tem permissao de escrita
        logger.error(f"Falha ao gravar {key} em {destino.parent}: {exc}")
        raise StorageError(
            "Nao foi possivel salvar o arquivo no servidor. "
            "Verifique se o volume de uploads esta montado e com permissao de escrita."
        ) from exc

    logger.info(f"Arquivo gravado: {key} ({len(data)} bytes)")
    return key


async def delete_file(key: str, settings: Settings) -> None:
    """Remove o arquivo. Ausencia do arquivo nao e tratada como erro."""
    loop = asyncio.get_event_loop()

    try:
        alvo = resolve_path(key, settings)
    except StorageError as exc:
        logger.warning(f"Nao foi possivel remover {key}: {exc}")
        return

    def _remove() -> None:
        alvo.unlink(missing_ok=True)

    try:
        await loop.run_in_executor(None, _remove)
        logger.info(f"Arquivo removido: {key}")
    except OSError as exc:
        logger.warning(f"Nao foi possivel remover {key}: {exc}")


def create_file_token(key: str, settings: Settings, expires: int | None = None) -> str:
    """Token curto que autoriza baixar exatamente um arquivo."""
    now = datetime.now(UTC)
    ttl = expires if expires is not None else settings.file_url_expires_seconds
    payload = {
        "sub": key,
        "type": _TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(payload, settings.get_private_key(), algorithm=settings.jwt_algorithm)


def read_file_token(token: str, settings: Settings) -> str:
    """Valida o token e devolve a key. Levanta StorageError se nao servir."""
    try:
        payload = jwt.decode(
            token,
            settings.get_public_key(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise StorageError("Link expirado ou invalido.") from exc

    if payload.get("type") != _TOKEN_TYPE:
        raise StorageError("Link invalido para download de arquivo.")

    key = payload.get("sub")
    if not key:
        raise StorageError("Link invalido para download de arquivo.")
    return str(key)


async def get_presigned_url(key: str, settings: Settings, expires: int = 3600) -> str:
    """
    Link temporario para baixar o arquivo pela API.

    Assinatura mantida por compatibilidade com o codigo que ja existia.
    """
    loop = asyncio.get_event_loop()
    token = await loop.run_in_executor(None, partial(create_file_token, key, settings, expires))
    return f"{settings.api_prefix}/files/{token}"
