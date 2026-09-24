"""
O índice `uq_users_api4com_extension` contra PostgreSQL real.

Por que este arquivo existe: a unicidade do ramal é a única parte desta fase
que a aplicação NÃO pode garantir sozinha. A consulta do router transforma o
conflito em 409 com texto de domínio, mas entre ela e o INSERT há uma corrida —
e é o índice que fecha a porta. Defesa de banco só se prova contra um banco.

A parte que a suíte mockada não alcança e esta alcança:

* vários `NULL` convivem sob o UNIQUE (dezesseis pessoas sem ramal);
* dois usuários com o mesmo ramal: o segundo é recusado;
* `upgrade → downgrade → upgrade` fecha o ciclo sem deixar resíduo.

⚠️ Tabelas temporárias não serviriam: o que se testa é o índice que a migration
aplica à `public.users` real. Por isso cada teste recria o banco do zero, com o
mesmo mecanismo do `test_constraint_telefone_postgres.py`, de onde as fixtures
são IMPORTADAS em vez de copiadas.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.test_constraint_telefone_postgres import (  # noqa: F401
    _alembic,
    _conecta,
    banco,
    servidor,
)

_ANTES = "j6e7f8a9b0c1"
_DEPOIS = "d68500999f24"
_INDICE = "uq_users_api4com_extension"


async def _insere(conn, ramal, email=None):
    """Um técnico mínimo. Técnico, e não cliente, para não esbarrar na
    constraint de telefone da Fase 1C — que não é o assunto aqui."""
    await conn.execute(
        text(
            "INSERT INTO users (id, name, email, password, role, status, phone,"
            " api4com_extension, lgpd_consent, created_at, updated_at)"
            " VALUES (gen_random_uuid(), 'Teste', :e, 'hash', 'technician', 'active',"
            " '+5581999999999', :r, false, now(), now())"
        ),
        {"e": email or f"{uuid.uuid4()}@x.com", "r": ramal},
    )


async def _tenta(conn, ramal):
    try:
        await _insere(conn, ramal)
        return "ACEITO"
    except Exception:  # noqa: BLE001 - o erro É o resultado
        return "REJEITADO"


@pytest.mark.asyncio
async def test_upgrade_cria_a_coluna_e_o_indice(banco):  # noqa: F811
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        coluna = (
            await conn.execute(
                text(
                    "SELECT data_type, character_maximum_length, is_nullable"
                    "  FROM information_schema.columns"
                    " WHERE table_name = 'users' AND column_name = 'api4com_extension'"
                )
            )
        ).first()
        assert coluna is not None, "a coluna não foi criada"
        assert coluna[0] == "character varying"
        assert coluna[1] == 20
        assert coluna[2] == "YES", "a coluna precisa ser nullable"

        indice = (
            await conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"), {"n": _INDICE}
            )
        ).scalar_one_or_none()
        assert indice is not None, "o índice único não foi criado"
        assert "UNIQUE" in indice
    await engine.dispose()


@pytest.mark.asyncio
async def test_ninguem_nasce_com_ramal(banco):  # noqa: F811
    """Sem backfill: a migration não inventa vínculo para ninguém."""
    assert _alembic(banco, "upgrade", _ANTES).returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        # Uma conta ANTERIOR à migration, para provar que ela sobe sem ramal.
        await conn.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, phone,"
                " lgpd_consent, created_at, updated_at)"
                " VALUES (gen_random_uuid(), 'Legado', :e, 'hash', 'technician', 'active',"
                " '+5581999999999', false, now(), now())"
            ),
            {"e": f"{uuid.uuid4()}@x.com"},
        )
    await engine.dispose()

    assert _alembic(banco, "upgrade", _DEPOIS).returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        com_ramal = (
            await conn.execute(
                text("SELECT count(*) FROM users WHERE api4com_extension IS NOT NULL")
            )
        ).scalar_one()
        assert com_ramal == 0, "a migration preencheu ramal de alguém"
    await engine.dispose()


@pytest.mark.asyncio
async def test_varios_nulos_convivem_e_o_ramal_repetido_nao(banco):  # noqa: F811
    assert _alembic(banco, "upgrade", "head").returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        # Dezesseis pessoas sem ramal é o estado normal desta fase.
        for _ in range(3):
            assert await _tenta(conn, None) == "ACEITO"

        assert await _tenta(conn, "2001") == "ACEITO"
        assert await _tenta(conn, "2001") == "REJEITADO", "o UNIQUE deixou passar"
        assert await _tenta(conn, "2002") == "ACEITO"

        quantos = (
            await conn.execute(text("SELECT count(*) FROM users WHERE api4com_extension = '2001'"))
        ).scalar_one()
        assert quantos == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_ciclo_upgrade_downgrade_upgrade(banco):  # noqa: F811
    assert _alembic(banco, "upgrade", "head").returncode == 0

    r = _alembic(banco, "downgrade", _ANTES)
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        sobrou_coluna = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns"
                    " WHERE table_name = 'users' AND column_name = 'api4com_extension'"
                )
            )
        ).scalar_one()
        sobrou_indice = (
            await conn.execute(
                text("SELECT count(*) FROM pg_indexes WHERE indexname = :n"), {"n": _INDICE}
            )
        ).scalar_one()
        assert sobrou_coluna == 0, "o downgrade deixou a coluna"
        assert sobrou_indice == 0, "o downgrade deixou o índice"
    await engine.dispose()

    assert _alembic(banco, "upgrade", "head").returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        voltou = (
            await conn.execute(
                text("SELECT count(*) FROM pg_indexes WHERE indexname = :n"), {"n": _INDICE}
            )
        ).scalar_one()
        assert voltou == 1
    await engine.dispose()
