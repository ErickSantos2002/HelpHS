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

from app.core.database import AsyncSessionLocal
from app.models.models import Product, SLAConfig, SLALevel, User, UserRole, UserStatus

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Dados de seed ─────────────────────────────────────────────

ADMIN_USER = {
    "email": "admin@healthsafety.com",
    "name": "Administrador",
    "password": "Admin@123456",
    "role": UserRole.admin,
    "status": UserStatus.active,
    "lgpd_consent": True,
}

PRODUCTS = [
    {
        "name": "HSGrowth CRM",
        "description": "Plataforma de CRM para gestão de relacionamento com clientes",
        "version": "2.0",
    },
    {
        "name": "HSGuard",
        "description": "Sistema de monitoramento e segurança do trabalho",
        "version": "1.5",
    },
    {
        "name": "HSFlow",
        "description": "Gestão de fluxos e processos internos de SST",
        "version": "1.2",
    },
    {
        "name": "HSDoc",
        "description": "Gestão documental e conformidade regulatória",
        "version": "1.0",
    },
    {
        "name": "HSTraining",
        "description": "Plataforma de treinamentos e capacitações em SST",
        "version": "1.1",
    },
    {
        "name": "HSAudit",
        "description": "Auditorias internas e externas de saúde e segurança",
        "version": "1.3",
    },
    {"name": "HSRisk", "description": "Análise e gestão de riscos ocupacionais", "version": "1.0"},
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
    result = await session.execute(select(User).where(User.email == ADMIN_USER["email"]))
    if result.scalar_one_or_none():
        logger.info("Admin user already exists — skipping")
        return

    admin = User(
        id=uuid.uuid4(),
        email=ADMIN_USER["email"],
        name=ADMIN_USER["name"],
        password=pwd_context.hash(ADMIN_USER["password"]),
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
