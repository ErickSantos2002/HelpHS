"""
A revision `o1j2k3l4m5n6` (empresa do equipamento, ECE-01) contra PostgreSQL.

Fica em arquivo próprio, e não em `test_migrations_postgres.py`, só pelo
tempo: aquele módulo leva minutos, e esta revision tem perguntas próprias —

1. ela sobe por cima de um banco com equipamentos SEM tocar em nenhum deles?
2. a FK nasce `RESTRICT` e o índice existe?
3. a descida devolve o schema anterior quando não há o que perder, e ABORTA
   quando apagaria a empresa de algum aparelho?
4. a cadeia continua com um head só?

A subida do servidor e a chamada do alembic são as daquele arquivo,
importadas em vez de copiadas.
"""

import asyncio
import shutil
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.test_dashboard_postgres import _sobe_postgres
from tests.test_migrations_postgres import _BACKEND, _alembic

_BANCO = "ece01_migracao_testes"
_ESTA = "o1j2k3l4m5n6"
_ANTERIOR = "n0i1j2k3l4m5"


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


@pytest.fixture
def banco(servidor):
    """Banco vazio a cada teste, com a extensão `vector` que as revisions exigem."""
    base, _, _ = servidor.rpartition("/")
    url_do_banco = f"{base}/{_BANCO}"

    async def _recria() -> None:
        motor = create_async_engine(servidor, isolation_level="AUTOCOMMIT")
        async with motor.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
            await conn.execute(text(f"CREATE DATABASE {_BANCO}"))
        await motor.dispose()

        novo = create_async_engine(url_do_banco, isolation_level="AUTOCOMMIT")
        async with novo.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await novo.dispose()

    asyncio.run(_recria())
    return url_do_banco


async def _sql(url: str, instrucao: str, **parametros):
    motor = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with motor.connect() as conn:
            resultado = await conn.execute(text(instrucao), parametros)
            return resultado.all() if resultado.returns_rows else None
    finally:
        await motor.dispose()


async def _planta(url: str) -> dict[str, uuid.UUID]:
    """Um grupo, uma empresa, um produto e dois aparelhos — como o banco de antes."""
    ids = {nome: uuid.uuid4() for nome in ("grupo", "empresa", "produto", "um", "dois")}
    await _sql(url, "INSERT INTO groups (id, name) VALUES (:id, 'Grupo')", id=ids["grupo"])
    await _sql(
        url,
        "INSERT INTO companies (id, group_id, name) VALUES (:id, :g, 'Acme')",
        id=ids["empresa"],
        g=ids["grupo"],
    )
    await _sql(
        url,
        "INSERT INTO products (id, name, is_active) VALUES (:id, 'Titan', true)",
        id=ids["produto"],
    )
    for chave, serie in (("um", "SN-1"), ("dois", "SN-2")):
        await _sql(
            url,
            "INSERT INTO equipments (id, product_id, name, serial_number, is_active) "
            "VALUES (:id, :p, :nome, :serie, true)",
            id=ids[chave],
            p=ids["produto"],
            nome=f"Aparelho {chave}",
            serie=serie,
        )
    return ids


async def _colunas_de_equipments(url: str) -> dict[str, str]:
    linhas = await _sql(
        url,
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'equipments'",
    )
    return {nome: nula for nome, nula in linhas}


async def _revision_do_banco(url: str) -> str:
    [(versao,)] = await _sql(url, "SELECT version_num FROM alembic_version")
    return versao


def test_a_cadeia_tem_um_head_so_e_e_esta_revision():
    """Dois heads não são teste vermelho: são o `start.sh` morrendo no boot."""
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "heads"],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr
    heads = [linha for linha in resultado.stdout.splitlines() if "(head)" in linha]
    assert heads == [f"{_ESTA} (head)"], resultado.stdout


@pytest.mark.asyncio
async def test_sobe_por_cima_dos_equipamentos_sem_tocar_em_nenhum(banco):
    assert _alembic(banco, _ANTERIOR).returncode == 0
    ids = await _planta(banco)
    antes = await _sql(banco, "SELECT id, name, serial_number, updated_at FROM equipments")
    colunas = await _colunas_de_equipments(banco)
    assert "company_id" not in colunas
    assert "sem_empresa_por_decisao" not in colunas

    resultado = _alembic(banco, "head")

    assert resultado.returncode == 0, f"{resultado.stdout}\n{resultado.stderr}"
    assert await _revision_do_banco(banco) == _ESTA
    assert (await _colunas_de_equipments(banco))["company_id"] == "YES", "a coluna nasce nula"
    depois = await _sql(banco, "SELECT id, name, serial_number, updated_at FROM equipments")
    assert sorted(depois) == sorted(antes), "nenhuma linha muda, nem o `updated_at`"
    empresas = await _sql(banco, "SELECT company_id FROM equipments")
    assert empresas == [(None,), (None,)], "a revision não preenche empresa de ninguém"
    assert len(ids) == 5


@pytest.mark.asyncio
async def test_a_chave_nasce_restrict_e_o_indice_existe(banco):
    assert _alembic(banco, "head").returncode == 0
    ids = await _planta(banco)

    [(regra,)] = await _sql(
        banco,
        "SELECT confdeltype::text FROM pg_constraint WHERE conname = 'fk_equipments_company_id_companies'",
    )
    indices = await _sql(
        banco,
        "SELECT indexname FROM pg_indexes WHERE tablename = 'equipments' "
        "AND indexname = 'ix_equipments_company_id'",
    )
    assert regra == "r", "RESTRICT: empresa com equipamento não é apagada por baixo"
    assert indices == [("ix_equipments_company_id",)]

    await _sql(
        banco,
        "UPDATE equipments SET company_id = :c WHERE id = :id",
        c=ids["empresa"],
        id=ids["um"],
    )
    with pytest.raises(IntegrityError):
        await _sql(banco, "DELETE FROM companies WHERE id = :id", id=ids["empresa"])
    with pytest.raises(IntegrityError):
        await _sql(
            banco,
            "UPDATE equipments SET company_id = :c WHERE id = :id",
            c=uuid.uuid4(),
            id=ids["dois"],
        )

    # Sem aparelho apontando, a empresa volta a poder sair.
    await _sql(banco, "UPDATE equipments SET company_id = NULL")
    await _sql(banco, "DELETE FROM companies WHERE id = :id", id=ids["empresa"])
    assert await _sql(banco, "SELECT count(*) FROM companies") == [(0,)]


@pytest.mark.asyncio
async def test_desce_e_sobe_de_novo_quando_nenhum_aparelho_tem_empresa(banco):
    assert _alembic(banco, "head").returncode == 0
    await _planta(banco)

    descida = _alembic(banco, _ANTERIOR, comando="downgrade")

    assert descida.returncode == 0, f"{descida.stdout}\n{descida.stderr}"
    assert await _revision_do_banco(banco) == _ANTERIOR
    colunas = await _colunas_de_equipments(banco)
    assert "company_id" not in colunas
    assert "sem_empresa_por_decisao" not in colunas
    assert await _sql(banco, "SELECT count(*) FROM equipments") == [(2,)]
    sobras = await _sql(
        banco,
        "SELECT 1 FROM pg_constraint WHERE conname = 'fk_equipments_company_id_companies' "
        "UNION ALL SELECT 1 FROM pg_indexes WHERE indexname = 'ix_equipments_company_id' "
        "UNION ALL SELECT 1 FROM pg_constraint "
        "WHERE conname = 'ck_equipments_sem_empresa_por_decisao'",
    )
    assert sobras == []

    subida = _alembic(banco, "head")
    assert subida.returncode == 0, f"{subida.stdout}\n{subida.stderr}"
    colunas = await _colunas_de_equipments(banco)
    assert colunas["company_id"] == "YES"
    assert colunas["sem_empresa_por_decisao"] == "NO"


@pytest.mark.asyncio
async def test_a_descida_aborta_enquanto_houver_aparelho_com_empresa(banco):
    assert _alembic(banco, "head").returncode == 0
    ids = await _planta(banco)
    await _sql(
        banco,
        "UPDATE equipments SET company_id = :c WHERE id = :id",
        c=ids["empresa"],
        id=ids["um"],
    )

    descida = _alembic(banco, _ANTERIOR, comando="downgrade")

    assert descida.returncode != 0
    assert "ROLLBACK BLOQUEADO" in descida.stderr
    assert "1 equipamento(s)" in descida.stderr
    assert await _revision_do_banco(banco) == _ESTA, "a descida que aborta não deixa meio caminho"
    guardada = await _sql(banco, "SELECT company_id FROM equipments WHERE id = :id", id=ids["um"])
    assert guardada == [(ids["empresa"],)]


@pytest.mark.asyncio
async def test_a_marca_nasce_falsa_em_todo_aparelho_que_ja_existia(banco):
    assert _alembic(banco, _ANTERIOR).returncode == 0
    await _planta(banco)

    subida = _alembic(banco, "head")

    assert subida.returncode == 0, f"{subida.stdout}\n{subida.stderr}"
    assert await _sql(
        banco, "SELECT sem_empresa_por_decisao, count(*) FROM equipments GROUP BY 1"
    ) == [(False, 2)]
    # E o INSERT de quem não conhece a coluna (imagem anterior) continua passando.
    ids = await _sql(banco, "SELECT product_id FROM equipments LIMIT 1")
    await _sql(
        banco,
        "INSERT INTO equipments (id, product_id, name, serial_number, is_active) "
        "VALUES (:id, :p, 'Novo', 'SN-3', true)",
        id=uuid.uuid4(),
        p=ids[0][0],
    )
    assert await _sql(
        banco, "SELECT count(*) FROM equipments WHERE NOT sem_empresa_por_decisao"
    ) == [(3,)]


@pytest.mark.asyncio
async def test_a_marca_so_existe_sem_empresa(banco):
    assert _alembic(banco, "head").returncode == 0
    ids = await _planta(banco)

    # Marca sem empresa: é o estado que ela descreve.
    await _sql(
        banco, "UPDATE equipments SET sem_empresa_por_decisao = true WHERE id = :id", id=ids["um"]
    )
    # Marca COM empresa, pelos dois caminhos: recusada.
    with pytest.raises(IntegrityError, match="ck_equipments_sem_empresa_por_decisao"):
        await _sql(
            banco,
            "UPDATE equipments SET company_id = :c WHERE id = :id",
            c=ids["empresa"],
            id=ids["um"],
        )
    await _sql(
        banco,
        "UPDATE equipments SET company_id = :c WHERE id = :id",
        c=ids["empresa"],
        id=ids["dois"],
    )
    with pytest.raises(IntegrityError, match="ck_equipments_sem_empresa_por_decisao"):
        await _sql(
            banco,
            "UPDATE equipments SET sem_empresa_por_decisao = true WHERE id = :id",
            id=ids["dois"],
        )


@pytest.mark.asyncio
async def test_a_descida_aborta_enquanto_houver_aparelho_sem_empresa_por_decisao(banco):
    assert _alembic(banco, "head").returncode == 0
    ids = await _planta(banco)
    await _sql(
        banco, "UPDATE equipments SET sem_empresa_por_decisao = true WHERE id = :id", id=ids["um"]
    )

    descida = _alembic(banco, _ANTERIOR, comando="downgrade")

    assert descida.returncode != 0
    assert "ROLLBACK BLOQUEADO" in descida.stderr
    assert "1 perderiam a marca" in descida.stderr.replace("\n", " ")
    assert await _revision_do_banco(banco) == _ESTA
    assert await _sql(
        banco, "SELECT sem_empresa_por_decisao FROM equipments WHERE id = :id", id=ids["um"]
    ) == [(True,)]
