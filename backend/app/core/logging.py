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


def setup_logging() -> None:
    settings = get_settings()

    logger.remove()

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
