import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import http_exception_handler, validation_exception_handler
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.redis import close_redis, get_redis
from app.routers import (
    attachments,
    audit,
    auth,
    calendar,
    chat,
    dashboard,
    files,
    groups,
    kb,
    notifications,
    products,
    quick_replies,
    sla,
    surveys,
    tags,
    tickets,
    users,
)
from app.services import storage
from app.services.ticket_lifecycle import start_auto_close_worker

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting HelpHS API — env={settings.app_env}")
    logger.info(f"CORS allowed origins: {settings.get_cors_origins()}")

    # Avisa, não derruba: derrubar trocaria um rate limit fraco por uma API que
    # não sobe, e quem tem o backend publicado direto na internet está certo em
    # ficar sem confiar no X-Forwarded-For.
    if settings.rate_limit_por_ip_do_proxy:
        logger.warning(
            "FORWARDED_ALLOW_IPS não configurado: atrás de um proxy o rate limit "
            "de login enxerga o IP do proxy, virando um limite único para todos "
            "os usuários. Confirme a topologia antes de ligar — ver mudanças.md."
        )

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

    # Diretório de uploads — precisa ser um volume, senão os anexos e avatares
    # somem a cada redeploy. Falhar aqui é melhor do que descobrir no upload.
    try:
        await storage.ensure_bucket(settings)
        logger.info(f"Upload directory OK: {settings.upload_dir}")
    except OSError as exc:
        logger.error(
            f"Upload directory unavailable ({settings.upload_dir}): {exc}. "
            "Anexos e fotos de perfil não vão funcionar até que o volume esteja "
            "montado e com permissão de escrita."
        )

    # RN-005 — fecha sozinho os chamados resolvidos que ninguém retomou.
    # Roda dentro da própria API por decisão, não por falta de fila (ver
    # app/services/ticket_lifecycle.py).
    auto_close_task = start_auto_close_worker()

    yield

    # Shutdown
    if auto_close_task is not None:
        auto_close_task.cancel()
        with suppress(asyncio.CancelledError):
            await auto_close_task

    await close_redis()
    await engine.dispose()
    logger.info("Shutting down HelpHS API")


app = FastAPI(
    title="HelpHS — Help Desk Health & Safety",
    description="API RESTful para gestão de chamados de Saúde & Segurança do Trabalho",
    version=__version__,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.state.limiter = limiter


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Mantém o formato de erro do projeto (campo `detail`, mensagem em português)
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas tentativas. Aguarde alguns minutos e tente novamente."},
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(products.router, prefix=settings.api_prefix)
app.include_router(tickets.router, prefix=settings.api_prefix)
app.include_router(attachments.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(surveys.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(kb.router, prefix=settings.api_prefix)
app.include_router(sla.router, prefix=settings.api_prefix)
app.include_router(tags.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(groups.router, prefix=settings.api_prefix)
app.include_router(calendar.router, prefix=settings.api_prefix)
app.include_router(quick_replies.router, prefix=settings.api_prefix)
app.include_router(files.router, prefix=settings.api_prefix)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health", tags=["Health"])
async def health_check_versioned() -> dict:
    # Sem a versão de propósito: esta rota responde sem autenticação, e
    # dizer a release exata a qualquer um só ajuda quem procura uma
    # vulnerabilidade conhecida. A versão fica no metadado do FastAPI, que
    # só aparece no /docs — desligado em produção.
    return {"status": "ok", "env": settings.app_env}
