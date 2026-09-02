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
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Equipment, Product, equipment_users
from tests.test_dashboard_postgres import _sobe_postgres

_BACKEND = Path(__file__).resolve().parent.parent
_BANCO = "migracoes_testes"

# A revision imediatamente anterior à que cria `equipment_users`. O teste de
# backfill para aqui, planta dado e só então sobe para head — é a única forma
# de exercitar um backfill: num banco vazio ele não tem o que copiar.
_ANTES_DO_BACKFILL = "u1p2q3r4s5t6"

# Cada par é (revisão sob teste, revisão imediatamente anterior). Subir só até a
# revisão alvo e descer um passo isola o `downgrade` daquela migration — descer
# a partir de `head` executaria a cadeia inteira e um `raise` de outra revisão
# mascararia o que se quer medir.
_A1_AUDITORIA = ("r8m9n0o1p2q3", "q7l8m9n0o1p2")
_A2_UNICIDADE = ("x4s5t6u7v8w9", "w3r4s5t6u7v8")
_A3_EQUIPAMENTOS = ("t0o1p2q3r4s5", "s9n0o1p2q3r4")
_A4_IA = ("z6u7v8w9x0y1", "y5t6u7v8w9x0")


async def _semeia_usuario(sessao, nome: str = "Fulana") -> uuid.UUID:
    """Um usuário mínimo, por SQL explícito.

    Pelo ORM não serve: estes testes rodam em pontos INTERMEDIÁRIOS da cadeia,
    onde o schema é mais antigo que o modelo, e o INSERT do ORM carregaria toda
    coluna que o modelo tem hoje. Já quebrou assim com `mfa_enabled` em 26/08.
    """
    identificador = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO users (id, name, email, password, role, status, "
            "lgpd_consent, email_verified, onboarding_completed) "
            "VALUES (:id, :nome, :email, 'x', 'client', 'active', true, true, true)"
        ),
        {"id": identificador, "nome": nome, "email": f"{identificador.hex[:8]}@test.com"},
    )
    return identificador


async def _semeia_chamado(sessao, criador: uuid.UUID) -> uuid.UUID:
    identificador = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO tickets (id, protocol, title, description, status, priority, "
            "category, creator_id, sla_response_breach, sla_resolve_breach, "
            "sla_total_paused_ms) "
            "VALUES (:id, :protocolo, 'Chamado de teste', 'corpo', 'open', 'medium', "
            "'general', :criador, false, false, 0)"
        ),
        {"id": identificador, "protocolo": identificador.hex[:12], "criador": criador},
    )
    return identificador


async def _semeia_produto(sessao) -> uuid.UUID:
    identificador = uuid.uuid4()
    await sessao.execute(
        text("INSERT INTO products (id, name, is_active) VALUES (:id, :nome, true)"),
        {"id": identificador, "nome": f"Produto {identificador.hex[:6]}"},
    )
    return identificador


def _alembic(url: str, *comando: str) -> subprocess.CompletedProcess[str]:
    """
    Roda o alembic como SUBPROCESSO, igual ao `start.sh`.

    Recebe o comando inteiro (`"upgrade", "head"` ou `"downgrade", "base"`) e
    não só o alvo: a volta precisa do mesmo caminho de execução da ida, senão o
    teste de ciclo estaria medindo dois mecanismos diferentes.

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
        [sys.executable, "-m", "alembic", *comando],
        cwd=_BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )


_INVENTARIO = {
    "tabelas": "SELECT tablename FROM pg_tables WHERE schemaname='public'",
    "enums": (
        "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname='public' AND t.typtype='e'"
    ),
    "indices": "SELECT indexname FROM pg_indexes WHERE schemaname='public'",
}


async def _fotografa(url: str) -> dict[str, set[str]]:
    """O que existe no banco agora, por categoria.

    A `alembic_version` fica de fora: ela é a contabilidade do próprio Alembic e
    sobrevive ao `downgrade base` por desenho, não por defeito.
    """
    motor = create_async_engine(url)
    foto: dict[str, set[str]] = {}
    async with motor.connect() as conn:
        for nome, sql in _INVENTARIO.items():
            foto[nome] = {
                str(x)
                for x in (await conn.execute(text(sql))).scalars().all()
                if not str(x).startswith("alembic_version")
            }
    await motor.dispose()
    return foto


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
    resultado = _alembic(banco, "upgrade", "head")

    assert (
        resultado.returncode == 0
    ), f"alembic upgrade head falhou:\n{resultado.stdout}\n{resultado.stderr}"


@pytest.mark.asyncio
async def test_downgrade_base_nao_deixa_tipo_para_tras(banco):
    """
    `downgrade base` tem que devolver o banco ao zero — e sair com 0 não prova isso.

    Medido em 02/09/2026: o comando saía com código **0** e deixava **nove**
    tipos ENUM no schema. `create_table` cria o tipo junto; `drop_table` não o
    remove. O sintoma não aparece na volta — aparece no `upgrade head` seguinte,
    com `DuplicateObjectError: type "slalevel" already exists`. Ou seja: no boot
    do container, depois de um rollback, com a API não subindo.

    A asserção é sobre o RESÍDUO, e não sobre o código de saída, de propósito:
    era justamente o código de saída que estava mentindo.
    """
    assert _alembic(banco, "upgrade", "head").returncode == 0

    volta = _alembic(banco, "downgrade", "base")
    assert volta.returncode == 0, f"{volta.stdout}\n{volta.stderr}"

    sobrou = await _fotografa(banco)

    assert not sobrou["enums"], (
        "tipos ENUM sobreviveram ao downgrade: "
        + ", ".join(sorted(sobrou["enums"]))
        + ". Toda migration que cria um tipo precisa derrubá-lo no downgrade; o"
        " modelo é o `DROP TYPE IF EXISTS` da n4i5j6k7l8m9."
    )
    assert not sobrou["tabelas"], f"tabelas de sobra: {sorted(sobrou['tabelas'])}"


@pytest.mark.asyncio
async def test_ciclo_upgrade_downgrade_upgrade_devolve_o_mesmo_schema(banco):
    """
    O caminho de volta do deploy, exercitado de ponta a ponta.

    O checklist de deploy do próprio projeto pede "upgrade → downgrade →
    upgrade" como item **manual**, e nada automatizava isso. E não basta o ciclo
    não estourar: o schema depois dele tem que ser o MESMO da subida limpa.
    Ficar diferente é pior do que falhar, porque não faz barulho — o banco passa
    a divergir do que o código espera, e o defeito reaparece numa consulta
    qualquer, dias depois, longe da causa.
    """
    assert _alembic(banco, "upgrade", "head").returncode == 0
    primeira = await _fotografa(banco)

    assert _alembic(banco, "downgrade", "base").returncode == 0

    subida = _alembic(banco, "upgrade", "head")
    assert subida.returncode == 0, (
        "o segundo `upgrade head` falhou — o downgrade não devolveu o banco ao"
        f" estado inicial:\n{subida.stdout}\n{subida.stderr}"
    )

    segunda = await _fotografa(banco)
    for categoria in _INVENTARIO:
        assert segunda[categoria] == primeira[categoria], (
            f"{categoria} diferente depois do ciclo. sumiram: "
            f"{sorted(primeira[categoria] - segunda[categoria])} · sobraram: "
            f"{sorted(segunda[categoria] - primeira[categoria])}"
        )


@pytest.mark.asyncio
async def test_backfill_leva_o_dono_para_equipment_users(banco):
    """
    O backfill da `v2q3r4s5t6u7` copia `equipments.owner_id` para a tabela nova.

    Sem ele, todo aparelho já cadastrado nasceria sem usuário nenhum e a tela
    do cliente ficaria vazia no dia do deploy.
    """
    assert _alembic(banco, "upgrade", _ANTES_DO_BACKFILL).returncode == 0

    dono_id = uuid.uuid4()
    equipamento_id = uuid.uuid4()
    produto_id = uuid.uuid4()

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        # INSERT explícito, e não pelo modelo ORM. Este teste roda num ponto
        # INTERMEDIÁRIO da cadeia, onde o schema é mais antigo que o modelo:
        # semear pelo ORM faz o INSERT carregar toda coluna que o modelo tenha
        # HOJE, então qualquer coluna nova quebra este teste com um erro que
        # não diz isso. Aconteceu com `mfa_enabled` em 26/08. Nomear as colunas
        # prende o seed ao schema daquele momento, que é o que se quer testar.
        await s.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, "
                "lgpd_consent, email_verified, onboarding_completed) "
                "VALUES (:id, :nome, :email, 'x', 'client', 'active', true, true, true)"
            ),
            {"id": dono_id, "nome": "Dona do aparelho", "email": f"{dono_id.hex[:8]}@test.com"},
        )
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

    assert _alembic(banco, "upgrade", "head").returncode == 0

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
    assert _alembic(banco, "upgrade", "head").returncode == 0
    segunda = _alembic(banco, "upgrade", "head")

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
    assert _alembic(banco, "upgrade", "head").returncode == 0

    from scripts.diagnostico_empresa_aparelho import (
        _CNPJ_DUPLICADO,
        _CNPJ_INVALIDO,
        _COLEGAS_POR_CNPJ,
        _DETALHE_DAS_DUPLICADAS,
        _PANORAMA_CLIENTES,
        _SERIE_DUPLICADA,
        _SERIE_ENTRE_PRODUTOS,
    )

    # O levantamento da fusão entra aqui pelo mesmo motivo: ele também roda uma
    # vez, à mão, contra produção — e ainda por cima antes de um DELETE.
    from scripts.funde_empresas_duplicadas import _LEVANTAMENTO

    for consulta in (
        _CNPJ_DUPLICADO,
        _DETALHE_DAS_DUPLICADAS,
        _SERIE_DUPLICADA,
        _SERIE_ENTRE_PRODUTOS,
        _PANORAMA_CLIENTES,
        _COLEGAS_POR_CNPJ,
        _CNPJ_INVALIDO,
        _LEVANTAMENTO,
    ):
        await sessao.execute(text(consulta))


# ══ Fase 4.1 — downgrades que precisam ABORTAR em vez de destruir ═══════════
#
# A política escrita em docs/decisoes-e-regras.md diz: o downgrade pode ser
# impossível em certos estados reais, e quando for, precisa falhar ANTES de
# destruir dado. Os testes abaixo exercem exatamente essa fronteira, cada um
# subindo só até a revisão em questão e descendo um passo.


@pytest.mark.asyncio
async def test_a1_downgrade_passa_quando_todo_historico_tem_autor(banco):
    """Histórico com autor humano não bloqueia o rollback — o caminho normal."""
    assert _alembic(banco, "upgrade", _A1_AUDITORIA[0]).returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        autor = await _semeia_usuario(s)
        chamado = await _semeia_chamado(s, autor)
        await s.execute(
            text(
                "INSERT INTO ticket_history (id, ticket_id, user_id, field, new_value) "
                "VALUES (:id, :chamado, :autor, 'status', 'in_progress')"
            ),
            {"id": uuid.uuid4(), "chamado": chamado, "autor": autor},
        )
        await s.commit()
    await motor.dispose()

    volta = _alembic(banco, "downgrade", _A1_AUDITORIA[1])

    assert volta.returncode == 0, f"{volta.stdout}\n{volta.stderr}"


@pytest.mark.asyncio
async def test_a1_downgrade_aborta_e_preserva_a_trilha_do_sistema(banco):
    """O rollback não pode apagar o que o sistema fez para caber no schema antigo.

    As linhas com `user_id` nulo são ação do sistema — fechamento automático
    (`ticket_lifecycle.py:115`) e a Helô. Elas não foram criadas por esta
    migration: foram gravadas pela aplicação depois do deploy. Apagá-las para
    poder repor o `NOT NULL` destrói a prova do que o sistema fez, sem aviso e
    sem volta.
    """
    assert _alembic(banco, "upgrade", _A1_AUDITORIA[0]).returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        autor = await _semeia_usuario(s)
        chamado = await _semeia_chamado(s, autor)
        for campo in ("status", "closed_at"):
            await s.execute(
                text(
                    "INSERT INTO ticket_history (id, ticket_id, user_id, field, new_value) "
                    "VALUES (:id, :chamado, NULL, :campo, 'x')"
                ),
                {"id": uuid.uuid4(), "chamado": chamado, "campo": campo},
            )
        await s.commit()
    await motor.dispose()

    volta = _alembic(banco, "downgrade", _A1_AUDITORIA[1])
    saida = volta.stdout + volta.stderr

    assert volta.returncode != 0, "o downgrade passou e apagou a trilha"
    assert "2" in saida, f"a mensagem precisa dizer quantas linhas bloqueiam:\n{saida}"
    assert "ticket_history" in saida
    assert "manual" in saida.lower(), "a mensagem precisa dizer que exige decisão humana"

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        sobreviventes = (
            await s.execute(text("SELECT count(*) FROM ticket_history WHERE user_id IS NULL"))
        ).scalar_one()
    await motor.dispose()

    assert sobreviventes == 2, "as linhas do sistema tinham que continuar lá"
