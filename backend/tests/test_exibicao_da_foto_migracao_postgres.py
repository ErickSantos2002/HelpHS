"""
A migration da autorização da foto (`l8g9h0i1j2k3`) contra um PostgreSQL de verdade.

O que se prende aqui, em uma frase cada:

- quem já existia continua SEM autorização — inclusive quem tem foto e quem
  aceitou a Política; nenhum evento é fabricado;
- nenhuma foto, protocolo ou chamado é tocado;
- o ciclo `upgrade → downgrade → upgrade` é reversível;
- os CHECK do model são os da migration.

Banco recriado do zero a cada teste, migration como subprocesso — igual ao
`start.sh`. Nenhum teste toca banco compartilhado.
"""

import importlib.util
import shutil
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.models.models import AvatarVisibilityEvent
from tests.test_dashboard_postgres import _sobe_postgres
from tests.test_ticket_calls_postgres import _BACKEND, _alembic

_BANCO = "exibicao_da_foto_testes"
_ANTES = "0a17fd87823c"
_REVISION = "l8g9h0i1j2k3"


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
    """Banco recém-criado por teste, e derrubado no fim — passe ou falhe."""
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

    admin = create_async_engine(servidor, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
    await admin.dispose()


async def _consulta(url: str, sql: str, **params) -> list:
    motor = create_async_engine(url, poolclass=NullPool)
    async with motor.connect() as conn:
        linhas = (await conn.execute(text(sql), params)).all()
    await motor.dispose()
    return [tuple(x) for x in linhas]


async def _executa(url: str, sql: str, **params) -> None:
    motor = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        await conn.execute(text(sql), params)
    await motor.dispose()


async def _usuario(url: str, papel: str, *, foto: bool, aceitou: bool) -> uuid.UUID:
    uid = uuid.uuid4()
    await _executa(
        url,
        "INSERT INTO users (id, name, email, password, role, status, phone, avatar_url,"
        " lgpd_consent, email_verified, mfa_enabled, onboarding_completed, ai_enabled,"
        " created_at, updated_at) VALUES (:id, 'Pessoa', :e, 'x', :r, 'active',"
        " '+5581999999999', :foto, :aceitou, true, false, true, true, now(), now())",
        id=uid,
        e=f"{uid.hex[:10]}@test.invalid",
        r=papel,
        foto=f"avatars/{uid}.png" if foto else None,
        aceitou=aceitou,
    )
    if aceitou:
        await _executa(
            url,
            "INSERT INTO lgpd_consents (id, user_id, revisao_politica, origem)"
            " VALUES (:id, :u, 'TESTE-00', 'auto_cadastro')",
            id=uuid.uuid4(),
            u=uid,
        )
    return uid


@pytest.mark.asyncio
async def test_quem_ja_existia_continua_sem_autorizacao_e_nada_mais_muda(banco):
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr

    com_foto_e_aceite = await _usuario(banco, "client", foto=True, aceitou=True)
    tecnico_com_foto = await _usuario(banco, "technician", foto=True, aceitou=True)
    admin_sem_nada = await _usuario(banco, "admin", foto=False, aceitou=False)
    await _executa(
        banco, "INSERT INTO ticket_protocol_counters (year, last_number) VALUES (2026, 26)"
    )
    fotos_antes = await _consulta(banco, "SELECT id, avatar_url FROM users ORDER BY id")

    r = _alembic(banco, "upgrade", _REVISION)
    assert r.returncode == 0, r.stderr

    estados = dict(await _consulta(banco, "SELECT id, avatar_visivel_a_terceiros FROM users"))
    assert estados == {com_foto_e_aceite: False, tecnico_com_foto: False, admin_sem_nada: False}
    assert await _consulta(banco, "SELECT count(*) FROM avatar_visibility_events") == [(0,)]
    assert await _consulta(banco, "SELECT id, avatar_url FROM users ORDER BY id") == fotos_antes
    assert await _consulta(banco, "SELECT year, last_number FROM ticket_protocol_counters") == [
        (2026, 26)
    ]
    # O padrão está no BANCO: um INSERT que não fala da coluna nasce falso.
    novo = await _usuario(banco, "client", foto=True, aceitou=True)
    assert await _consulta(
        banco, "SELECT avatar_visivel_a_terceiros FROM users WHERE id = :id", id=novo
    ) == [(False,)]


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade(banco):
    async def _tem_tabela_e_coluna() -> tuple[bool, bool]:
        tabela = await _consulta(banco, "SELECT to_regclass('public.avatar_visibility_events')")
        coluna = await _consulta(
            banco,
            "SELECT count(*) FROM information_schema.columns"
            " WHERE table_name = 'users' AND column_name = 'avatar_visivel_a_terceiros'",
        )
        return tabela[0][0] is not None, coluna[0][0] == 1

    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert await _tem_tabela_e_coluna() == (True, True)

    r = _alembic(banco, "downgrade", _ANTES)
    assert r.returncode == 0, r.stderr
    assert await _tem_tabela_e_coluna() == (False, False)

    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert await _tem_tabela_e_coluna() == (True, True)


@pytest.mark.asyncio
async def test_o_banco_migrado_recusa_evento_torto(banco):
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    dono = await _usuario(banco, "client", foto=False, aceitou=False)

    for evento, versao, origem in [
        ("autorizacao", None, "alteracao_propria"),  # autorizar sem texto
        ("talvez", "TESTE-AVISO-01", "alteracao_propria"),
        ("autorizacao", "TESTE-AVISO-01", "criado_por_terceiro"),  # ninguém autoriza pela pessoa
    ]:
        with pytest.raises(Exception, match="ck_avatar_visibility_events_"):
            await _executa(
                banco,
                "INSERT INTO avatar_visibility_events (id, user_id, evento, versao_aviso, origem)"
                " VALUES (:id, :u, :ev, :v, :o)",
                id=uuid.uuid4(),
                u=dono,
                ev=evento,
                v=versao,
                o=origem,
            )


def test_os_check_do_model_sao_os_da_migration():
    """O autogenerate não compara CHECK: a paridade é conferida aqui."""
    caminho = _BACKEND / "alembic" / "versions" / f"{_REVISION}_exibicao_da_foto_a_terceiros.py"
    spec = importlib.util.spec_from_file_location("migration_exibicao", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    regras = {
        c.name: str(c.sqltext)
        for c in AvatarVisibilityEvent.__table__.constraints
        if c.name and c.name.startswith("ck_")
    }
    assert regras == {
        "ck_avatar_visibility_events_evento_conhecido": modulo._REGRA_EVENTO,
        "ck_avatar_visibility_events_origem_conhecida": modulo._REGRA_ORIGEM,
        "ck_avatar_visibility_events_autorizacao_tem_aviso": modulo._REGRA_AVISO,
    }
