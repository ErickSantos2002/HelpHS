import redis.asyncio as aioredis
from loguru import logger

from app.core.config import get_settings

settings = get_settings()

_redis_client: aioredis.Redis | None = None


def _make_client() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30,
    )


async def get_redis() -> aioredis.Redis:
    """Retorna o cliente Redis. Thread-safe: cada worker cria sua propria instancia."""
    global _redis_client
    if _redis_client is None:
        _redis_client = _make_client()
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


async def ping_redis() -> bool:
    try:
        client = await get_redis()
        await client.ping()
        return True
    except Exception as exc:
        logger.warning(f"Redis ping failed: {exc}")
        return False
