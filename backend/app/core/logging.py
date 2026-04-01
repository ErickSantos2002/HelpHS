import sys

from loguru import logger

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()

    logger.remove()

    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # File logging apenas em desenvolvimento
    if settings.is_development:
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
