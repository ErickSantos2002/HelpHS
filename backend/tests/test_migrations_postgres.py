"""
As migrations do Alembic, executadas contra PostgreSQL de verdade.

Por que este arquivo existe
---------------------------
Nenhum teste da suíte tocava numa migration — e neste projeto elas rodam
**sozinhas no boot do container** (`start.sh`: alembic upgrade head → seeds →
uvicorn). Migration que falha não é um teste vermelho: é a API que não sobe,
em produção, no meio de um deploy. Já aconteceu em 19/08 por outro motivo.

O `create_all` dos modelos, usado pelo `test_dashboard_postgres.py`, não cobre
isso: ele monta o schema pela declaração, não pela sequência de revisions. Um
`ALTER TYPE` mal colocado, um índice único sobre coluna com duplicata ou um
`down_revision` apontando para o vazio passam ilesos por ele e só aparecem no
container.

Cada teste roda num banco **recém-criado**, porque `upgrade head` precisa
partir do zero e não pode encontrar tabela montada por outro teste.

Como o banco aparece: `TEST_POSTGRES_URL` (o CI passa, do serviço `postgres`),
senão `pgserver`. Sem nenhum dos dois, pula — mesma regra do arquivo do
dashboard, de onde a função de subida é importada em vez de copiada.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Equipment, Product, UserRole, equipment_users
from tests.test_dashboard_postgres import _sobe_postgres, _usuario

_BACKEND = Path(__file__).resolve().parent.parent
_BANCO = "migracoes_testes"

# A revision imediatamente anterior à que cria `equipment_users`. O teste de
# backfill para aqui, planta dado e só então sobe para head — é a única forma
# de exercitar um backfill: num banco vazio ele não tem o que copiar.
_ANTES_DO_BACKFILL = "u1p2q3r4s5t6"


def _alembic(url: str, alvo: str) -> subprocess.CompletedProcess[str]:
    """
    Roda o alembic como SUBPROCESSO, igual ao `start.sh`.

    Não é preciosismo: o `alembic/env.py` chama `asyncio.run()` por dentro, e
    invocá-lo de dentro de um teste async estouraria com "cannot be called from
    a running event loop". O subprocesso também garante que o `get_settings()`
    seja lido do zero, sem o cache do processo de teste.
    """
    ambiente = {
        **os.environ,
        "DATABASE_URL": url,
        "APP_ENV": "testing",
    }
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", alvo],
        cwd=_BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def servidor():
    """Sobe o Postgres uma vez para o módulo — o custo grande do pgserver."""
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
    """Banco vazio a cada teste. CREATE DATABASE exige autocommit."""
    base, _, _ = servidor.rpartition("/")

    async def _recria() -> None:
        motor = create_async_engine(servidor, isolation_level="AUTOCOMMIT")
        async with motor.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)"))
            await conn.execute(text(f"CREATE DATABASE {_BANCO}"))
        await motor.dispose()

    asyncio.run(_recria())
    return f"{base}/{_BANCO}"


@pytest_asyncio.fixture
async def sessao(banco):
    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        yield s
    await motor.dispose()


def test_upgrade_head_sobe_do_zero(banco):
    """
    A cadeia inteira, do banco vazio até head.

    É o que o container faz a cada boot. Se este teste passar a falhar, o
    próximo deploy não sobe — e o aviso chega no CI em vez de no EasyPanel.
    """
    resultado = _alembic(banco, "head")

    assert (
        resultado.returncode == 0
    ), f"alembic upgrade head falhou:\n{resultado.stdout}\n{resultado.stderr}"


@pytest.mark.asyncio
async def test_backfill_leva_o_dono_para_equipment_users(banco):
    """
    O backfill da `v2q3r4s5t6u7` copia `equipments.owner_id` para a tabela nova.

    Sem ele, todo aparelho já cadastrado nasceria sem usuário nenhum e a tela
    do cliente ficaria vazia no dia do deploy.
    """
    assert _alembic(banco, _ANTES_DO_BACKFILL).returncode == 0

    dono_id = uuid.uuid4()
    equipamento_id = uuid.uuid4()
    produto_id = uuid.uuid4()

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        dono = _usuario(UserRole.client, "Dona do aparelho")
        dono.id = dono_id
        s.add(dono)
        s.add(Product(id=produto_id, name="Phoebus"))
        await s.flush()
        s.add(
            Equipment(
                id=equipamento_id,
                product_id=produto_id,
                owner_id=dono_id,
                name="Phoebus da recepção",
                serial_number="WATFR01-73041",
                is_active=True,
            )
        )
        # Órfão: sem dono, não deve gerar linha nenhuma no backfill.
        s.add(
            Equipment(
                id=uuid.uuid4(),
                product_id=produto_id,
                owner_id=None,
                name="Phoebus sem dono",
                serial_number="WATFR01-00000",
                is_active=True,
            )
        )
        await s.commit()
    await motor.dispose()

    assert _alembic(banco, "head").returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        vinculos = (await s.execute(select(equipment_users))).all()
    await motor.dispose()

    assert len(vinculos) == 1, f"esperava só o aparelho com dono, veio {vinculos}"
    assert vinculos[0].equipment_id == equipamento_id
    assert vinculos[0].user_id == dono_id


def test_upgrade_head_e_idempotente_apos_o_backfill(banco):
    """
    Rodar `upgrade head` de novo não pode estourar.

    O container reexecuta a migration a cada boot; a segunda passada não
    encontra revision pendente, mas se o `ON CONFLICT DO NOTHING` do backfill
    tivesse sido esquecido, um reprocessamento manual quebraria na PK composta.
    """
    assert _alembic(banco, "head").returncode == 0
    segunda = _alembic(banco, "head")

    assert segunda.returncode == 0, f"{segunda.stdout}\n{segunda.stderr}"


@pytest.mark.asyncio
async def test_consultas_do_diagnostico_executam(sessao, banco):
    """
    O SQL do `scripts/diagnostico_empresa_aparelho.py`, contra o schema real.

    Ele foi escrito para rodar uma vez, à mão, contra PRODUÇÃO — é o pior lugar
    do mundo para descobrir um nome de coluna errado. As consultas são
    importadas do próprio script: uma cópia aqui validaria a cópia, não o que
    vai rodar.
    """
    assert _alembic(banco, "head").returncode == 0

    from scripts.diagnostico_empresa_aparelho import (
        _CNPJ_DUPLICADO,
        _CNPJ_INVALIDO,
        _COLEGAS_POR_CNPJ,
        _DETALHE_DAS_DUPLICADAS,
        _PANORAMA_CLIENTES,
        _SERIE_DUPLICADA,
        _SERIE_ENTRE_PRODUTOS,
    )

    for consulta in (
        _CNPJ_DUPLICADO,
        _DETALHE_DAS_DUPLICADAS,
        _SERIE_DUPLICADA,
        _SERIE_ENTRE_PRODUTOS,
        _PANORAMA_CLIENTES,
        _COLEGAS_POR_CNPJ,
        _CNPJ_INVALIDO,
    ):
        await sessao.execute(text(consulta))
