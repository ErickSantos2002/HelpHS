from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting HelpHS API — env={settings.app_env}")
    yield
    logger.info("Shutting down HelpHS API")


app = FastAPI(
    title="HelpHS — Help Desk Health & Safety",
    description="API RESTful para gestão de chamados de Saúde & Segurança do Trabalho",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health", tags=["Health"])
async def health_check_versioned() -> dict:
    return {"status": "ok", "version": "1.0.0", "env": settings.app_env}
