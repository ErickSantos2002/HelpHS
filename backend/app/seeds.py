"""
Seeds do banco de dados.
Uso: python -m app.seeds
"""

import asyncio
import uuid

from loguru import logger
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.models import Product, SLAConfig, SLALevel, User, UserRole, UserStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Dados de seed ─────────────────────────────────────────────

# Sem senha aqui. Ela vem de `SEED_ADMIN_PASSWORD` — ver `seed_admin`.
ADMIN_USER = {
    "email": "admin@healthsafety.com",
    "name": "Administrador",
    "role": UserRole.admin,
    "status": UserStatus.active,
    "lgpd_consent": True,
}

PRODUCTS = [
    {"name": "Deimos", "description": "Bafômetro Deimos", "version": None},
    {"name": "EBS-010", "description": "Bafômetro EBS-010", "version": None},
    {"name": "iBlow 10 Pro", "description": "Bafômetro iBlow 10 Pro", "version": None},
    {"name": "Mark X", "description": "Bafômetro Mark X", "version": None},
    {"name": "Mercury", "description": "Bafômetro Mercury", "version": None},
    {"name": "Phoebus", "description": "Bafômetro Phoebus", "version": None},
    {"name": "Titan", "description": "Bafômetro Titan", "version": None},
]

SLA_CONFIGS = [
    {
        "level": SLALevel.critical,
        "response_time_hours": 1,
        "resolve_time_hours": 4,
        "warning_threshold": 80,
    },
    {
        "level": SLALevel.high,
        "response_time_hours": 2,
        "resolve_time_hours": 8,
        "warning_threshold": 80,
    },
    {
        "level": SLALevel.medium,
        "response_time_hours": 4,
        "resolve_time_hours": 24,
        "warning_threshold": 80,
    },
    {
        "level": SLALevel.low,
        "response_time_hours": 8,
        "resolve_time_hours": 48,
        "warning_threshold": 80,
    },
]


# ── Funções de seed ───────────────────────────────────────────


async def seed_admin(session: AsyncSession) -> None:
    """
    Cria o administrador inicial — nunca em produção, nunca sem senha vinda do
    ambiente.

    Este módulo roda no boot do container (`start.sh`, entre a migration e o
    uvicorn), **também em produção**. Enquanto a senha esteve escrita aqui e
    não houve guarda de ambiente, todo deploy criava (ou recriava, se alguém
    apagasse a linha) um administrador ativo com credencial publicada no
    repositório.

    São duas defesas independentes, e a ordem importa:

    1. `APP_ENV` de produção não cria conta.
    2. Sem `SEED_ADMIN_PASSWORD` não cria conta.

    A segunda não é redundância: `app_env` tem default ``"development"``, então
    a guarda de ambiente falha **aberta** se a variável faltar ou vier
    digitada errada. Senha ausente é o que segura esse caso.

    **Não levanta exceção, de propósito.** O módulo irmão que semeia as contas
    do Playwright pode levantar em produção porque nada o chama lá. Esta função
    não: ela está no caminho do boot, sob `set -e`, e levantar deixaria o
    container sem subir — trocaria um vazamento de credencial por uma
    indisponibilidade. A recusa é registrada e a execução segue; produto e SLA
    continuam sendo semeados normalmente.

    A idempotência continua valendo e protege quem já trocou a senha em
    produção: com a linha presente, nada é tocado.
    """
    settings = get_settings()

    if settings.is_production:
        logger.warning(
            "Ambiente de produção: criação do usuário admin ignorada. "
            "Conta de administrador não nasce de seed no banco real."
        )
        return

    senha = (settings.seed_admin_password or "").strip()
    if not senha:
        logger.warning(
            "SEED_ADMIN_PASSWORD não definida: criação do usuário admin ignorada. "
            "Defina a variável para semear o administrador em desenvolvimento."
        )
        return

    result = await session.execute(select(User).where(User.email == ADMIN_USER["email"]))
    if result.scalar_one_or_none():
        logger.info("Admin user already exists — skipping")
        return

    admin = User(
        id=uuid.uuid4(),
        email=ADMIN_USER["email"],
        name=ADMIN_USER["name"],
        password=pwd_context.hash(senha),
        role=ADMIN_USER["role"],
        status=ADMIN_USER["status"],
        lgpd_consent=ADMIN_USER["lgpd_consent"],
    )
    session.add(admin)
    logger.info(f"Admin user created: {admin.email}")


async def seed_products(session: AsyncSession) -> None:
    for data in PRODUCTS:
        result = await session.execute(select(Product).where(Product.name == data["name"]))
        if result.scalar_one_or_none():
            logger.info(f"Product '{data['name']}' already exists — skipping")
            continue

        product = Product(id=uuid.uuid4(), **data)
        session.add(product)
        logger.info(f"Product created: {data['name']}")


async def seed_sla_configs(session: AsyncSession) -> None:
    for data in SLA_CONFIGS:
        result = await session.execute(select(SLAConfig).where(SLAConfig.level == data["level"]))
        if result.scalar_one_or_none():
            logger.info(f"SLA config '{data['level'].value}' already exists — skipping")
            continue

        config = SLAConfig(id=uuid.uuid4(), **data)
        session.add(config)
        logger.info(
            f"SLA config created: {data['level'].value} — response {data['response_time_hours']}h / resolve {data['resolve_time_hours']}h"
        )


async def run_seeds() -> None:
    logger.info("Starting database seeds...")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await seed_admin(session)
            await seed_products(session)
            await seed_sla_configs(session)
    logger.info("Seeds completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_seeds())
