import logging
import sys
from typing import Any

from loguru import logger

from app.core.config import get_settings
from app.core.contexto import id_atual


def _carimba(record: Any) -> None:
    """Poe o id da requisicao no `extra` de toda linha.

    Fica em `extra`, e nao no texto, porque em producao o sink serializa em JSON
    e campo estruturado e o que se filtra sem regex. Ate aqui o `extra` saia
    sempre vazio: nao ha um `bind` ou `contextualize` no backend inteiro, entao
    o `serialize=True` produzia JSON sem nenhum campo alem da mensagem.
    """
    record["extra"]["request_id"] = id_atual()


# Instalado na IMPORTACAO, nao dentro do `setup_logging`. O `setup_logging` so
# roda no lifespan, e tudo logado durante o import dos modulos escaparia do
# carimbo -- inclusive os avisos de configuracao, que sao os que mais interessa
# correlacionar quando um boot da errado.
logger.configure(patcher=_carimba)


# Loggers que o uvicorn cria por conta propria. Ele nao sabe do loguru, e sem a
# ponte abaixo o stdout de producao era um fluxo MISTO: JSON serializado das
# linhas da aplicacao e texto plano do access log, lado a lado.
_LOGGERS_DO_UVICORN = ("uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.asgi")


class _PonteStdlib(logging.Handler):
    """Encaminha registros do `logging` da stdlib para o loguru.

    Assim a linha de access ganha o mesmo tratamento das nossas: sai em JSON e,
    o que importa mais, **carimbada com o `request_id`**.

    Isso funciona por causa de onde o uvicorn emite: o access log sai de dentro
    do `send()` do protocolo, no tratamento de `http.response.start`
    (`uvicorn/protocols/http/h11_impl.py`). O `send` e chamado PELO app ASGI,
    entao a linha nasce dentro do escopo do middleware de correlacao — com o
    `ContextVar` ainda setado. Se o uvicorn emitisse depois da resposta, fora da
    pilha do app, o carimbo sairia vazio e esta ponte so consertaria o formato.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            nivel: str | int = logger.level(record.levelname).name
        except ValueError:
            nivel = record.levelno

        # Sobe a pilha ate sair do modulo `logging`, senao toda linha do uvicorn
        # apareceria como vinda de dentro da stdlib.
        quadro: Any = logging.currentframe()
        profundidade = 2
        while quadro and quadro.f_code.co_filename == logging.__file__:
            quadro = quadro.f_back
            profundidade += 1

        logger.opt(depth=profundidade, exception=record.exc_info).log(nivel, record.getMessage())


def instalar_ponte_stdlib() -> None:
    """Faz o logging da stdlib desaguar no loguru. Idempotente."""
    raiz = logging.getLogger()
    if not any(isinstance(h, _PonteStdlib) for h in raiz.handlers):
        raiz.handlers = [_PonteStdlib()]

    # O nivel da aplicacao, e NAO `NOTSET`. Com `NOTSET` a raiz aceita tudo, e
    # toda biblioteca que usa o `logging` da stdlib -- asyncpg, httpx, botocore
    # -- passa a despejar DEBUG na ponte. Alem do volume, isso enche o log de
    # producao com linha que nao e nossa e nao ajuda ninguem.
    raiz.setLevel(get_settings().log_level)

    for nome in _LOGGERS_DO_UVICORN:
        lg = logging.getLogger(nome)
        lg.handlers = []
        # Precisa propagar para a raiz. O uvicorn decide se loga acesso com
        # `access_logger.hasHandlers()`, que sobe a cadeia: sem a propagacao,
        # tirar os handlers desligaria o access log por completo — trocando
        # "formato misto" por "sem access log nenhum".
        lg.propagate = True


def setup_logging() -> None:
    settings = get_settings()

    logger.remove()

    # Depois do `logger.remove()` e antes de adicionar os sinks: a partir daqui
    # o access log do uvicorn tambem passa por eles.
    instalar_ponte_stdlib()

    if settings.is_development:
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True,
        )
        try:
            logger.add(
                f"{settings.log_dir}/app.log",
                level=settings.log_level,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
                rotation="10 MB",
                retention="30 days",
                compression="zip",
                serialize=True,
            )
        except PermissionError:
            logger.warning("Could not create log file — stdout only")
    else:
        # Producao: JSON estruturado para facilitar parsing no EasyPanel/Loki
        logger.add(
            sys.stdout,
            level=settings.log_level,
            serialize=True,
        )
