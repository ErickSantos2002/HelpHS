"""
A tabela `lgpd_consents` contra um PostgreSQL de verdade.

O que a tabela promete só se prova contra o banco: que revogar NÃO apaga, e
que excluir a conta desvincula em vez de levar o histórico junto — este último
é o `ON DELETE SET NULL`, que nenhum mock exercita.

A migration roda como subprocesso, num banco recriado do zero a cada teste —
nenhum teste toca banco compartilhado.

O que estes testes prendem, em uma frase cada:

- o ciclo `upgrade → downgrade → upgrade` é reversível;
- origem fora das três conhecidas não entra, e o CHECK do model é o da migration;
- revogar marca `revogado_em` e preserva `concedido_em`;
- excluir o usuário deixa a linha, com `user_id` nulo;
- o "último aceite vigente" ignora os revogados.
"""

import importlib.util
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.models import LgpdConsent
from app.services.consentimento import (
    ORIGEM_ALTERACAO_PROPRIA,
    ORIGEM_AUTO_CADASTRO,
    registra_aceite,
    revoga_aceites,
    ultimo_aceite_vigente,
)
from tests.test_dashboard_postgres import _sobe_postgres
from tests.test_ticket_calls_postgres import _BACKEND, _alembic, _cria_usuario

_BANCO = "lgpd_consents_testes"
_ANTES = "i5d6e7f8a9b0"


@pytest.fixture(scope="module")
def servidor():
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    yield url

    if recurso is not None:
        servidor_pg, pasta = recurso
        try:
            servidor_pg.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def banco(servidor):
    """Banco recém-criado por teste."""
    admin = create_async_engine(servidor, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{_BANCO}"'))
    await admin.dispose()

    url = servidor.rsplit("/", 1)[0] + f"/{_BANCO}"
    novo = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with novo.connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await novo.dispose()

    yield url


@pytest_asyncio.fixture
async def migrado(banco):
    """Banco no head, com um cliente pronto para ser o titular."""
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        titular = await _cria_usuario(conn, "client")
    await motor.dispose()

    yield banco, titular


def _config(politica="00", termos=None):
    class _C:
        lgpd_revisao_politica = politica
        lgpd_revisao_termos = termos

    return _C()


async def _linhas(url) -> list[dict]:
    motor = create_async_engine(url, poolclass=NullPool)
    async with motor.connect() as conn:
        r = await conn.execute(
            text(
                "SELECT user_id, revisao_politica, revisao_termos, origem,"
                " concedido_em, revogado_em FROM lgpd_consents ORDER BY concedido_em"
            )
        )
        linhas = [dict(x._mapping) for x in r]
    await motor.dispose()
    return linhas


# ── A migration sobe e desce ─────────────────────────────────


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade(banco):
    async def _existe() -> bool:
        motor = create_async_engine(banco, poolclass=NullPool)
        async with motor.connect() as conn:
            r = await conn.execute(text("SELECT to_regclass('public.lgpd_consents')"))
            valor = r.scalar()
        await motor.dispose()
        return valor is not None

    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert await _existe()

    r = _alembic(banco, "downgrade", _ANTES)
    assert r.returncode == 0, r.stderr
    assert not await _existe()

    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert await _existe()


def test_o_check_do_model_e_o_da_migration():
    """O autogenerate não compara CHECK: a paridade é conferida aqui."""
    caminho = _BACKEND / "alembic" / "versions" / "j6e7f8a9b0c1_historico_de_aceites_lgpd.py"
    spec = importlib.util.spec_from_file_location("migration_lgpd", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    [check] = [
        c
        for c in LgpdConsent.__table__.constraints
        if c.name == "ck_lgpd_consents_origem_conhecida"
    ]
    assert str(check.sqltext) == modulo._REGRA_ORIGEM


@pytest.mark.asyncio
async def test_origem_desconhecida_nao_entra(migrado):
    url, titular = migrado
    motor = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        with pytest.raises(Exception, match="ck_lgpd_consents_origem_conhecida"):
            await conn.execute(
                text(
                    "INSERT INTO lgpd_consents (id, user_id, origem)"
                    " VALUES (gen_random_uuid(), :u, 'inventada')"
                ),
                {"u": titular},
            )
    await motor.dispose()


# ── O que o histórico promete ────────────────────────────────


@pytest.mark.asyncio
async def test_revogar_preserva_o_aceite(migrado):
    """O defeito que motivou a tabela: revogar apagava a prova do período consentido."""
    url, titular = migrado
    concedido = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    revogado = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)

    motor = create_async_engine(url, poolclass=NullPool)
    async with AsyncSession(motor) as db:
        registra_aceite(
            db,
            user_id=titular,
            origem=ORIGEM_AUTO_CADASTRO,
            ip="203.0.113.7",
            agora=concedido,
            settings=_config(politica="00"),
        )
        await db.commit()
        await revoga_aceites(db, user_id=titular, agora=revogado)
        await db.commit()
    await motor.dispose()

    [linha] = await _linhas(url)
    assert linha["user_id"] == titular
    assert linha["revisao_politica"] == "00"
    assert linha["concedido_em"] == concedido
    assert linha["revogado_em"] == revogado


@pytest.mark.asyncio
async def test_excluir_a_conta_desvincula_e_nao_apaga(migrado):
    """Decisão de 24/09/2026: a linha fica, sem a pessoa."""
    url, titular = migrado

    motor = create_async_engine(url, poolclass=NullPool)
    async with AsyncSession(motor) as db:
        registra_aceite(
            db,
            user_id=titular,
            origem=ORIGEM_AUTO_CADASTRO,
            ip=None,
            agora=datetime.now(UTC),
            settings=_config(),
        )
        await db.commit()
        await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": titular})
        await db.commit()
    await motor.dispose()

    [linha] = await _linhas(url)
    assert linha["user_id"] is None
    assert linha["origem"] == ORIGEM_AUTO_CADASTRO
    assert linha["revisao_politica"] == "00"


@pytest.mark.asyncio
async def test_ultimo_aceite_vigente_ignora_os_revogados(migrado):
    url, titular = migrado
    t0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    motor = create_async_engine(url, poolclass=NullPool)
    async with AsyncSession(motor) as db:
        registra_aceite(
            db,
            user_id=titular,
            origem=ORIGEM_AUTO_CADASTRO,
            ip=None,
            agora=t0,
            settings=_config(politica="00"),
        )
        await db.commit()
        await revoga_aceites(db, user_id=titular, agora=t0 + timedelta(days=1))
        await db.commit()
        assert await ultimo_aceite_vigente(db, titular) is None

        registra_aceite(
            db,
            user_id=titular,
            origem=ORIGEM_ALTERACAO_PROPRIA,
            ip=None,
            agora=t0 + timedelta(days=2),
            settings=_config(politica="01"),
        )
        await db.commit()
        ultimo = await ultimo_aceite_vigente(db, titular)
        assert ultimo is not None
        assert ultimo.revisao_politica == "01"
        assert ultimo.origem == ORIGEM_ALTERACAO_PROPRIA
    await motor.dispose()

    # O revogado continua lá: dois registros, nenhum apagado.
    assert len(await _linhas(url)) == 2


@pytest.mark.asyncio
async def test_usuario_inexistente_nao_tem_aceite(migrado):
    url, _ = migrado
    motor = create_async_engine(url, poolclass=NullPool)
    async with AsyncSession(motor) as db:
        assert await ultimo_aceite_vigente(db, uuid.uuid4()) is None
    await motor.dispose()
