import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.models.models import Base
from app.utils.migrations import comandos_de_limite, exige_alvo_liberado

config = context.config
settings = get_settings()

# ANTES de qualquer coisa que conecte. A trava é sobre o ALVO, e o alvo já está
# decidido aqui — esperar pelo `run_migrations_online` seria travar depois de a
# URL já ter sido passada adiante.
exige_alvo_liberado(settings.database_url)
# Também antes de conectar: limite com valor inválido não chega a abrir conexão.
limites = comandos_de_limite()

config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        for comando in limites:
            context.execute(comando)
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    # DENTRO da transação que roda TODAS as revisions pendentes: o limite vale
    # para cada comando de cada uma, e estourar desfaz o conjunto inteiro.
    with context.begin_transaction():
        for comando in limites:
            connection.exec_driver_sql(comando)
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
