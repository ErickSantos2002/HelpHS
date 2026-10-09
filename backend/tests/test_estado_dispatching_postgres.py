"""
O CHECK de `creation_status` aceitando `dispatching`, contra PostgreSQL real.

Por que este arquivo existe: `dispatching` no enum Python não vale nada se o
banco recusar o valor. A coluna é `String` com `CheckConstraint`, e o CHECK
antigo enumerava cinco valores — gravar o sexto daria violação de constraint na
primeira ligação real, e não antes.

O que se prova aqui:

* antes da migration o banco RECUSA `dispatching` (senão o teste seguinte não
  provaria nada);
* depois dela, aceita;
* os cinco estados antigos continuam aceitos — o conjunto novo é superconjunto;
* lixo continua recusado;
* `upgrade → downgrade → upgrade` fecha o ciclo.
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

_ANTES = "d68500999f24"
_DEPOIS = "8d08cbca1768"
_NOME = "ck_ticket_calls_status_conhecido"


async def _semeia_chamado(conn) -> str:
    """Um chamado com autor — `ticket_calls.ticket_id` é FK NOT NULL."""
    email = f"{uuid.uuid4()}@x.com"
    await conn.execute(
        text(
            "INSERT INTO users (id, name, email, password, role, status, phone,"
            " lgpd_consent, created_at, updated_at)"
            " VALUES (gen_random_uuid(), 'Autor', :e, 'hash', 'client', 'active',"
            " '+5581999999999', false, now(), now())"
        ),
        {"e": email},
    )
    autor = (
        await conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    ).scalar_one()
    protocolo = uuid.uuid4().hex[:12]
    await conn.execute(
        text(
            "INSERT INTO tickets (id, protocol, title, description, category, status,"
            " creator_id, sla_response_breach, sla_resolve_breach, reopen_count,"
            " sla_total_paused_ms, ai_enabled, helo_saiu,"
            " sla_resolve_extension_total_min, created_at, updated_at)"
            " VALUES (gen_random_uuid(), :p, 'Teste', 'Desc', 'hardware', 'open',"
            " :c, false, false, 0, 0, true, false, 0, now(), now())"
        ),
        {"p": protocolo, "c": autor},
    )
    return (
        await conn.execute(text("SELECT id FROM tickets WHERE protocol = :p"), {"p": protocolo})
    ).scalar_one()


async def _tenta_estado(conn, ticket_id, estado) -> str:
    try:
        await conn.execute(
            text(
                "INSERT INTO ticket_calls (id, ticket_id, creation_status, created_at, updated_at)"
                " VALUES (gen_random_uuid(), :t, :s, now(), now())"
            ),
            {"t": ticket_id, "s": estado},
        )
        return "ACEITO"
    except Exception:  # noqa: BLE001 - o erro É o resultado
        return "REJEITADO"


@pytest.mark.asyncio
async def test_antes_da_migration_o_banco_recusa_dispatching(banco):  # noqa: F811
    """A prova de que o teste seguinte mede alguma coisa."""
    assert _alembic(banco, "upgrade", _ANTES).returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        ticket_id = await _semeia_chamado(conn)
        assert await _tenta_estado(conn, ticket_id, "dispatching") == "REJEITADO"
    await engine.dispose()


@pytest.mark.asyncio
async def test_depois_da_migration_dispatching_e_aceito(banco):  # noqa: F811
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        ticket_id = await _semeia_chamado(conn)
        assert await _tenta_estado(conn, ticket_id, "dispatching") == "ACEITO"
    await engine.dispose()


@pytest.mark.asyncio
async def test_os_estados_antigos_continuam_aceitos(banco):  # noqa: F811
    """Superconjunto: nada do que passava antes passa a falhar."""
    assert _alembic(banco, "upgrade", "head").returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        ticket_id = await _semeia_chamado(conn)
        for estado in ("pending", "rejected", "unavailable", "indeterminate"):
            assert await _tenta_estado(conn, ticket_id, estado) == "ACEITO", estado
        # `confirmed` exige `provider_call_id` pelo outro CHECK, então fica de
        # fora desta volta — quem o cobre é o `test_ticket_calls_postgres.py`.
        assert await _tenta_estado(conn, ticket_id, "despachando") == "REJEITADO"
        assert await _tenta_estado(conn, ticket_id, "") == "REJEITADO"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ciclo_upgrade_downgrade_upgrade(banco):  # noqa: F811
    assert _alembic(banco, "upgrade", "head").returncode == 0

    r = _alembic(banco, "downgrade", _ANTES)
    assert r.returncode == 0, r.stderr[-2000:]

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        ticket_id = await _semeia_chamado(conn)
        assert await _tenta_estado(conn, ticket_id, "dispatching") == "REJEITADO"
        existe = (
            await conn.execute(
                text("SELECT count(*) FROM pg_constraint WHERE conname = :n"), {"n": _NOME}
            )
        ).scalar_one()
        assert existe == 1, "o downgrade deixou a tabela sem CHECK nenhum"
    await engine.dispose()

    assert _alembic(banco, "upgrade", _DEPOIS).returncode == 0

    engine = await _conecta(banco)
    async with engine.connect() as conn:
        ticket_id = await _semeia_chamado(conn)
        assert await _tenta_estado(conn, ticket_id, "dispatching") == "ACEITO"
    await engine.dispose()
