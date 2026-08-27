import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.core.config import get_settings
from app.core.contexto import CABECALHO
from app.core.database import engine
from app.core.exceptions import http_exception_handler, validation_exception_handler
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.redis import close_redis, get_redis
from app.middleware.correlacao import CorrelacaoMiddleware
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
from app.services import antivirus, storage
from app.services.chat_backplane import assinatura_ativa, start_chat_backplane
from app.services.ticket_lifecycle import start_auto_close_worker, ultima_rodada_sem_erro

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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

    # O antivírus fora do ar é um estado SILENCIOSO: o upload trata
    # "unavailable" como aprovado, e nada no download relê a marca. A política
    # continua essa de propósito — bloquear upload com o AV fora derrubaria o
    # anexo inteiro —, mas o boot passa a dizer em que estado o sistema está.
    # Só fora de dev/teste: quem desenvolve raramente sobe um ClamAV.
    if not settings.is_development and not settings.is_testing:
        if await antivirus.ping(settings.clamav_host, settings.clamav_port):
            logger.info(f"Antivírus OK: {settings.clamav_host}:{settings.clamav_port}")
        else:
            logger.warning(
                f"ANTIVÍRUS INALCANÇÁVEL em {settings.clamav_host}:{settings.clamav_port}. "
                "Os anexos continuam sendo aceitos, porém SEM varredura, e ficam "
                "gravados com virus_scanned=False. Depois de subir o ClamAV, rode "
                "`python -m scripts.revarre_anexos` para varrer o que entrou sem exame."
            )

    # RN-005 — fecha sozinho os chamados resolvidos que ninguém retomou.
    # Roda dentro da própria API por decisão, não por falta de fila (ver
    # app/services/ticket_lifecycle.py).
    auto_close_task = start_auto_close_worker()

    # Backplane do chat: sem ele, dois workers nao se enxergam e o sintoma e
    # silencioso (ver app/services/chat_backplane.py). Sobe sempre, inclusive
    # com --workers 1: assim ele fica exercitado em producao antes de o numero
    # de workers subir, e o readiness mostra se a assinatura se mantem de pe.
    chat_task = start_chat_backplane(chat.manager.entregar_local, chat.manager.origem)

    yield

    # Shutdown
    if auto_close_task is not None:
        auto_close_task.cancel()
        with suppress(asyncio.CancelledError):
            await auto_close_task

    # Antes do close_redis, de proposito: o laco segura uma conexao de pub/sub
    # tirada do mesmo cliente singleton.
    chat_task.cancel()
    with suppress(asyncio.CancelledError):
        await chat_task

    await close_redis()
    await engine.dispose()
    logger.info("Shutting down HelpHS API")


app = FastAPI(
    title="HelpHS — Help Desk Health & Safety",
    description="API RESTful para gestão de chamados de Saúde & Segurança do Trabalho",
    version=__version__,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    # Sem isto o spec fica no default e segue público mesmo com /docs
    # desligado — o mapa completo da API para quem procura o que atacar.
    openapi_url=settings.openapi_url_efetiva(),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # `allow_headers` vale para o que o navegador MANDA; para ele conseguir LER
    # um cabecalho de resposta e preciso expo-lo. Sem isto o id existe, viaja e
    # e invisivel justamente para quem abriria o chamado de suporte citando ele.
    expose_headers=[CABECALHO],
)

# Registrado DEPOIS do CORS de proposito: o `add_middleware` empilha por fora,
# entao este fica sendo o mais externo. O id passa a existir antes de qualquer
# outra camada, e o cabecalho e carimbado por ultimo, com a resposta ja pronta.
app.add_middleware(CorrelacaoMiddleware)


app.state.limiter = limiter


def _segundos_ate_liberar(request: Request) -> int | None:
    """Quanto falta para a janela do limiter virar, em segundos.

    Sai do estado real da janela, não de uma constante: um número fixo passaria
    a mentir no instante em que alguém mudasse `RATE_LIMIT_*`, e mentira em
    `Retry-After` é pior que silêncio — o cliente confia e volta cedo demais.

    `view_rate_limit` é posto pelo próprio slowapi antes de levantar. Se não
    estiver lá, ou se o storage não responder, o cabeçalho simplesmente não sai:
    é melhor não dizer do que chutar.
    """
    janela = getattr(request.state, "view_rate_limit", None)
    if not janela:
        return None
    try:
        vira_em, _restantes = limiter.limiter.get_window_stats(janela[0], *janela[1])
    except Exception:  # pragma: no cover - depende do storage
        return None
    return max(1, int(1 + vira_em - time.time()))


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # Mantém o formato de erro do projeto (campo `detail`, mensagem em português)
    espera = _segundos_ate_liberar(request)
    return JSONResponse(
        status_code=429,
        content={"detail": "Muitas tentativas. Aguarde alguns minutos e tente novamente."},
        headers={"Retry-After": str(espera)} if espera is not None else None,
    )


# Cada handler declara a exceção CONCRETA que trata, o que é mais preciso que a
# assinatura do Starlette (que aceita Exception). Os ignores marcam essa
# diferença de variância — não um erro nosso.
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]

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


# Quanto o readiness espera por cada dependência antes de chamá-la de fora.
# Curto de propósito: quem pergunta "está pronto?" precisa de resposta rápida,
# e uma dependência que demora 5 s para responder já é uma dependência com
# problema. Não virou configuração porque não há o que ajustar por ambiente.
_READINESS_TIMEOUT_S = 2.0


async def _ping_banco() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _checar_banco() -> bool:
    try:
        await asyncio.wait_for(_ping_banco(), timeout=_READINESS_TIMEOUT_S)
        return True
    except Exception as exc:  # noqa: BLE001 — readiness reporta, não levanta
        logger.warning(f"Readiness: banco indisponível: {exc}")
        return False


async def _ping_redis() -> None:
    redis = await get_redis()
    await redis.ping()


async def _checar_redis() -> bool:
    try:
        await asyncio.wait_for(_ping_redis(), timeout=_READINESS_TIMEOUT_S)
        return True
    except Exception as exc:  # noqa: BLE001 — readiness reporta, não levanta
        logger.warning(f"Readiness: Redis indisponível: {exc}")
        return False


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """
    Liveness. Responde se o processo está de pé, e nada além disso.

    NÃO confere dependência nenhuma, de propósito: esta é a rota do
    HEALTHCHECK do Dockerfile e dos compose. Se ela passasse a depender do
    banco, uma oscilação do Postgres reiniciaria o container da API — trocando
    uma indisponibilidade parcial por uma total. Quem quer saber se dá para
    atender pergunta ao readiness, em /api/v1/health.
    """
    return {"status": "ok"}


@app.get(f"{settings.api_prefix}/health", tags=["Health"])
async def readiness_check(response: Response) -> dict:
    """
    Readiness. Confere as dependências e responde 503 quando alguma faltou.

    Sem a versão de propósito: esta rota responde sem autenticação, e dizer a
    release exata a qualquer um só ajuda quem procura uma vulnerabilidade
    conhecida. A versão fica no metadado do FastAPI, no /docs, desligado em
    produção.

    O carimbo do fechamento automático é REPORTADO, não usado para derrubar: é
    `None` nos primeiros 60 s de cada worker, porque o laço espera antes da
    primeira rodada, e derrubar por causa disso daria 503 em todo boot. Quem
    observa decide o que fazer com um carimbo velho — ver
    `ultima_rodada_sem_erro` para o que "sem erro" inclui.
    """
    banco_ok, redis_ok = await asyncio.gather(_checar_banco(), _checar_redis())
    pronto = banco_ok and redis_ok

    if not pronto:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    ultima = ultima_rodada_sem_erro()
    return {
        "status": "ok" if pronto else "degraded",
        "env": settings.app_env,
        "checks": {
            "database": "ok" if banco_ok else "down",
            "redis": "ok" if redis_ok else "down",
        },
        "auto_close": {"last_success": ultima.isoformat() if ultima else None},
        # Reportado, nao usado para derrubar -- mesma regra do carimbo acima. Com
        # a assinatura caida o chat ainda funciona dentro de cada worker; o que
        # se perde e o tempo real ENTRE workers, que e justamente a falha que
        # ninguem percebe sem alguem olhar para aqui.
        "chat_backplane": {"assinado": assinatura_ativa()},
    }
