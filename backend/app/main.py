from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import http_exception_handler, validation_exception_handler
from app.core.logging import setup_logging
from app.core.redis import close_redis, get_redis
from app.routers import auth, products, users

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting HelpHS API — env={settings.app_env}")

    # Validate database connection
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as exc:
        logger.error(f"Database connection failed: {exc}")
        raise

    # Validate Redis connection
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("Redis connection OK")
    except Exception as exc:
        logger.warning(f"Redis connection failed: {exc}")

    yield

    # Shutdown
    await close_redis()
    await engine.dispose()
    logger.info("Shutting down HelpHS API")


app = FastAPI(
    title="HelpHS — Help Desk Health & Safety",
    description="API RESTful para gestão de chamados de Saúde & Segurança do Trabalho",
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)


app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(products.router, prefix=settings.api_prefix)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health", tags=["Health"])
async def health_check_versioned() -> dict:
    return {"status": "ok", "version": "1.0.0", "env": settings.app_env}
