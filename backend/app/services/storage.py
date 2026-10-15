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
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache, partial
from pathlib import Path

from jose import JWTError, jwk, jwt
from jose.backends.base import Key
from loguru import logger

from app.core.config import Settings

_TOKEN_TYPE = "file"
# Tipo PRÓPRIO para o lote de anexos: um token de arquivo único não abre ZIP, e
# o do ZIP não abre arquivo nenhum em `/files/{token}`.
_TOKEN_TYPE_LOTE = "attachments_archive"


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
    """Grava os bytes em disco e devolve a key.

    A gravação é atômica: os bytes vão para um temporário no mesmo diretório
    e só então substituem o destino. A foto de perfil sobrescreve a MESMA
    chave quando a extensão não muda, e um `write_bytes` direto que falhasse
    no meio (disco cheio) deixaria a foto anterior truncada no lugar.
    """
    loop = asyncio.get_event_loop()
    destino = resolve_path(key, settings)

    def _write() -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporario.write_bytes(data)
            os.replace(temporario, destino)
        finally:
            temporario.unlink(missing_ok=True)

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


async def isola_arquivo(key: str, settings: Settings) -> str | None:
    """Tira o arquivo da chave pública sem apagá-lo e devolve a chave isolada.

    `None` se não há arquivo.

    Renomeia para um nome reservado no MESMO diretório — `rename` no mesmo
    volume é atômico, e reversível por `devolve_arquivo`. Existe para quem
    precisa apagar DEPOIS do commit sem que a exclusão alcance um arquivo
    gravado na mesma chave depois dele: o que se apaga no fim é o nome
    isolado, nunca a chave pública. Ver "A foto removida pelo administrador"
    em docs/decisoes-e-regras.md.

    Erro de disco levanta `StorageError`: quem chama ainda não mudou nada.
    """
    loop = asyncio.get_event_loop()
    origem = resolve_path(key, settings)
    isolado = origem.with_name(f".{origem.name}.{uuid.uuid4().hex}.removendo")

    def _move() -> bool:
        try:
            os.rename(origem, isolado)
        except FileNotFoundError:
            return False
        return True

    try:
        movido = await loop.run_in_executor(None, _move)
    except OSError as exc:
        logger.error(f"Falha ao isolar {key}: {exc}")
        raise StorageError("Nao foi possivel remover o arquivo no servidor.") from exc
    if not movido:
        return None
    return isolado.relative_to(_root(settings)).as_posix()


async def devolve_arquivo(isolado: str, key: str, settings: Settings) -> None:
    """Desfaz `isola_arquivo` SEM sobrescrever o que estiver na chave.

    Se a chave já tem arquivo, ele é mais novo que o isolado (alguém gravou
    depois) e fica; o isolado é que sai. Nunca levanta: é chamado num caminho
    de erro, e a falha vira aviso no log.
    """
    loop = asyncio.get_event_loop()

    def _devolve() -> None:
        origem = resolve_path(isolado, settings)
        destino = resolve_path(key, settings)
        try:
            # `link` falha se o destino existe: devolve sem corrida de
            # "conferir e depois mover".
            os.link(origem, destino)
        except FileExistsError:
            pass
        except OSError:
            # Volume sem link físico (SMB, alguns FUSE): conferir e mover.
            # Sobra uma janela mínima, mas largar o arquivo isolado deixaria a
            # linha apontando para o vazio com certeza.
            if not destino.exists():
                os.rename(origem, destino)
                return
        origem.unlink(missing_ok=True)

    try:
        await loop.run_in_executor(None, _devolve)
    except (OSError, StorageError) as exc:
        logger.error(f"Nao foi possivel devolver {key}: {exc}")


def file_exists(key: str, settings: Settings) -> bool:
    """O arquivo está no disco? Key inválida conta como "não está"."""
    try:
        return resolve_path(key, settings).is_file()
    except StorageError:
        return False


# ── Assinatura dos links de arquivo ───────────────────────────
#
# Medido em 13/10/2026: cada link custava ~60 ms, e quase nada disso era a
# assinatura RS256 (~1 ms). Era o `jose` reinterpretando e validando a chave
# PEM a cada chamada, porque recebia o TEXTO da chave. Cem fotos numa lista
# seriam seis segundos de CPU.
#
# Duas medidas, nenhuma muda o algoritmo, a chave ou quem pode baixar o quê:
#
# 1. A chave interpretada fica em cache por processo, indexada pelo CONTEÚDO do
#    PEM. Não há recarga de segredo em tempo de execução no HelpHS (a chave vem
#    do ambiente ou de arquivo, lida no boot); se a configuração apontar para
#    outra chave, é outra entrada — a velha nunca é usada para o PEM novo.
# 2. O link é estável dentro de uma janela de `_JANELA_DO_TOKEN` segundos:
#    `iat` alinhado ao início da janela e `exp = iat + ttl`. Mesmo arquivo,
#    mesma versão e mesma janela produzem o MESMO token — RS256 PKCS#1 v1.5 é
#    determinístico —, e a assinatura fica memorizada. Isso deixa o navegador
#    reaproveitar a imagem (ver `Cache-Control` em routers/files.py).

_JANELA_DO_TOKEN = 300
"""Segundos. A validade restante de um link fica entre `ttl - janela` e `ttl`."""


def _agora() -> int:
    """Relógio da emissão, em segundos. Separado para os testes o controlarem."""
    return int(time.time())


@lru_cache(maxsize=8)
def _chave_jwt(pem: str, algoritmo: str) -> Key:
    """A chave PEM interpretada uma vez por conteúdo — privada ou pública."""
    return jwk.construct(pem, algoritmo)


def _versao_do_arquivo(key: str, settings: Settings) -> int:
    """`st_mtime_ns` do arquivo, ou 0 se ele não existe.

    Entra no token para conteúdo novo sair com URL nova. A troca da própria
    foto com a MESMA extensão sobrescreve a mesma chave: sem isto, o link
    novo seria idêntico ao velho dentro da janela, o React não recarregaria a
    `<img>` e o cache mostraria a foto antiga.
    """
    try:
        return resolve_path(key, settings).stat().st_mtime_ns
    except (StorageError, OSError):
        return 0


def _janela(agora: int, ttl: int) -> tuple[int, int]:
    """(iat, exp) do link. Nunca devolve `exp` além de `agora + ttl`.

    Abaixo de duas janelas, alinhar comeria uma fatia grande demais da
    validade — e um `ttl` negativo (link já vencido, usado em teste) tem de
    continuar vencido. Nesses casos vale o relógio puro, como era antes.
    """
    if ttl < 2 * _JANELA_DO_TOKEN:
        return agora, agora + ttl
    inicio = agora - (agora % _JANELA_DO_TOKEN)
    return inicio, inicio + ttl


@lru_cache(maxsize=4096)
def _assina_token_de_arquivo(
    key: str, versao: int, iat: int, exp: int, emissor: str, algoritmo: str, pem: str
) -> str:
    """A assinatura em si, memorizada por (arquivo, versão, janela, chave).

    A janela está no próprio `iat`/`exp` da chave do cache: na virada, o token
    é outro. Como `exp > agora` para todo `ttl >= 2 * janela`, o memo nunca
    devolve um link já vencido.
    """
    payload = {
        "sub": key,
        "type": _TOKEN_TYPE,
        "v": versao,
        "iat": iat,
        "exp": exp,
        "iss": emissor,
    }
    return jwt.encode(payload, _chave_jwt(pem, algoritmo), algorithm=algoritmo)


def create_file_token(key: str, settings: Settings, expires: int | None = None) -> str:
    """Token curto que autoriza baixar exatamente um arquivo."""
    ttl = expires if expires is not None else settings.file_url_expires_seconds
    iat, exp = _janela(_agora(), ttl)
    return _assina_token_de_arquivo(
        key,
        _versao_do_arquivo(key, settings),
        iat,
        exp,
        settings.jwt_issuer,
        settings.jwt_algorithm,
        settings.get_private_key(),
    )


def ler_token_de_arquivo(token: str, settings: Settings) -> tuple[str, int]:
    """Valida o token e devolve (key, exp). Levanta StorageError se não servir.

    O `exp` vai para o `Cache-Control` do `/files`: o navegador não pode
    guardar a resposta além da validade do link que a pediu.
    """
    try:
        payload = jwt.decode(
            token,
            _chave_jwt(settings.get_public_key(), settings.jwt_algorithm),
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
    return str(key), int(payload["exp"])


def read_file_token(token: str, settings: Settings) -> str:
    """Valida o token e devolve a key. Levanta StorageError se nao servir."""
    return ler_token_de_arquivo(token, settings)[0]


def create_archive_token(
    ticket_id: str, attachment_ids: list[str], settings: Settings, expires: int | None = None
) -> str:
    """Token curto que autoriza baixar UM lote congelado de anexos de um chamado.

    Os ids vão dentro do token assinado: o que foi autorizado no pedido é
    exatamente o que pode sair no ZIP, nem um anexo a mais.
    """
    now = datetime.now(UTC)
    ttl = expires if expires is not None else settings.file_url_expires_seconds
    payload = {
        "sub": ticket_id,
        "ids": attachment_ids,
        "type": _TOKEN_TYPE_LOTE,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "iss": settings.jwt_issuer,
    }
    # Sem janela: o lote é emitido uma vez por pedido, e não se repete. A chave
    # interpretada é a mesma do cache, então não paga os ~60 ms.
    return jwt.encode(
        payload,
        _chave_jwt(settings.get_private_key(), settings.jwt_algorithm),
        algorithm=settings.jwt_algorithm,
    )


def read_archive_token(token: str, settings: Settings) -> tuple[str, list[str]]:
    """Valida o token do lote e devolve (ticket_id, ids). StorageError se não servir."""
    try:
        payload = jwt.decode(
            token,
            _chave_jwt(settings.get_public_key(), settings.jwt_algorithm),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise StorageError("Link expirado ou invalido.") from exc

    if payload.get("type") != _TOKEN_TYPE_LOTE:
        raise StorageError("Link invalido para download de anexos.")

    ticket_id = payload.get("sub")
    ids = payload.get("ids")
    if not ticket_id or not isinstance(ids, list) or not ids:
        raise StorageError("Link invalido para download de anexos.")
    return str(ticket_id), [str(i) for i in ids]


async def get_presigned_url(key: str, settings: Settings, expires: int = 3600) -> str:
    """
    Link temporario para baixar o arquivo pela API.

    Assinatura mantida por compatibilidade com o codigo que ja existia.
    """
    loop = asyncio.get_event_loop()
    token = await loop.run_in_executor(None, partial(create_file_token, key, settings, expires))
    return f"{settings.api_prefix}/files/{token}"
