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

from app.models.models import Equipment, Product, equipment_users
from tests.test_dashboard_postgres import _sobe_postgres

_BACKEND = Path(__file__).resolve().parent.parent
_BANCO = "migracoes_testes"

# A revision imediatamente anterior à que cria `equipment_users`. O teste de
# backfill para aqui, planta dado e só então sobe para head — é a única forma
# de exercitar um backfill: num banco vazio ele não tem o que copiar.
_ANTES_DO_BACKFILL = "u1p2q3r4s5t6"

# O pai da migration da agenda (`d0y1z2a3b4c5`). A descida aponta a revision,
# nunca "-1": o "-1" assumia que a agenda era o head e quebrou no primeiro
# merge que pôs outra migration em cima dela (15/09, índice único de e-mail) —
# o CI de main ficou vermelho sem a agenda ter mudado uma linha.
_ANTES_DA_AGENDA = "c9x0y1z2a3b4"

# O pai da saída do `other` do enum de categoria (`f2a3b4c5d6e7`).
_ANTES_DA_SAIDA_DO_OTHER = "e1z2a3b4c5d6"


def _alembic(url: str, alvo: str, comando: str = "upgrade") -> subprocess.CompletedProcess[str]:
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
        [sys.executable, "-m", "alembic", comando, alvo],
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
    """
    Banco vazio a cada teste. CREATE DATABASE exige autocommit.

    A extensão `vector` é criada AQUI, e não pela migration, porque é assim
    que acontece em produção: a `a7v8w9x0y1z2` exige a extensão e recusa
    criá-la, para não pedir superusuário no boot do container. Quem cria é o
    administrador, uma vez, antes do deploy — e este passo é a encenação
    disso. Criar aqui é o que mantém o teste fiel ao que roda lá.

    A extensão é por BANCO: o `CREATE DATABASE` acima nasce sem ela mesmo com
    o pgvector instalado no servidor, então isto tem de rodar a cada recriação.
    """
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
async def test_o_modelo_nao_anda_na_frente_das_migrations(sessao, banco):
    """
    Toda coluna declarada no modelo existe no banco depois do `upgrade head`.

    É a lacuna que o `create_all` esconde e que este arquivo existe para
    fechar, num caso que ele ainda não cobria. Os testes que montam o schema
    pela declaração — `test_helo_postgres.py` e companhia — ficam VERDES com
    uma coluna nova no modelo e nenhuma migration para ela: eles constroem o
    schema a partir do próprio modelo. O container não: ele roda
    `alembic upgrade head`, e a primeira consulta que tocar na coluna que só
    existe na declaração devolve `UndefinedColumn` em produção.

    A comparação é só de PRESENÇA — nome de tabela e de coluna. Tipo, default e
    nulabilidade ficam de fora de propósito: comparar isso a sério é o trabalho
    do `alembic check`, que precisa de um banco no head e não roda no CI. O que
    este teste pega é o esquecimento inteiro, que é o caso comum e o que
    derruba o boot.
    """
    resultado = _alembic(banco, "head")
    assert resultado.returncode == 0, resultado.stderr

    from app.models.models import Base

    reais = {}
    linhas = await sessao.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
    )
    for tabela, coluna in linhas.all():
        reais.setdefault(tabela, set()).add(coluna)

    faltando = []
    for tabela in Base.metadata.sorted_tables:
        if tabela.name not in reais:
            faltando.append(f"{tabela.name} (tabela inteira)")
            continue
        for coluna in tabela.columns:
            if coluna.name not in reais[tabela.name]:
                faltando.append(f"{tabela.name}.{coluna.name}")

    assert (
        not faltando
    ), "declarado no modelo e ausente depois do upgrade head — falta migration para: " + ", ".join(
        sorted(faltando)
    )


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

    assert _alembic(banco, "head").returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        vinculos = (await s.execute(select(equipment_users))).all()
    await motor.dispose()

    assert len(vinculos) == 1, f"esperava só o aparelho com dono, veio {vinculos}"
    assert vinculos[0].equipment_id == equipamento_id
    assert vinculos[0].user_id == dono_id


@pytest.mark.asyncio
async def test_o_artigo_que_ja_existia_nasce_lido_pela_helo(banco):
    """
    A decisão de 10/09/2026, provada no banco em vez de afirmada.

    Havia UM artigo publicado em produção (número do Rickelme), e a coluna
    `helo_pode_ler` chega com padrão `true` para cobri-lo SEM backfill e sem
    corrigir linha em migration. Este teste semeia um artigo ANTES da
    `c9x0y1z2a3b4` e confere que ele sai do outro lado lido pela Helô. Com o
    padrão invertido, o único artigo que existe sumiria das respostas no dia do
    deploy — em silêncio.
    """
    assert _alembic(banco, "b8w9x0y1z2a3").returncode == 0
    autor_id, artigo_id = uuid.uuid4(), uuid.uuid4()

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        # INSERT explícito pelo mesmo motivo do teste do backfill: nesta revisão
        # o schema é mais antigo que o modelo, e o ORM carregaria uma coluna
        # que ainda não existe.
        await s.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, "
                "lgpd_consent, email_verified, onboarding_completed) "
                "VALUES (:id, 'Autora', :email, 'x', 'technician', 'active', true, true, true)"
            ),
            {"id": autor_id, "email": f"{autor_id.hex[:8]}@test.com"},
        )
        await s.execute(
            text(
                "INSERT INTO kb_articles (id, title, content, slug, category, tags, status, "
                "author_id, view_count, helpful, not_helpful) "
                "VALUES (:id, 'O artigo que já existia', 'corpo', :slug, 'hardware', '{}', "
                "'published', :autor, 0, 0, 0)"
            ),
            {"id": artigo_id, "slug": f"ja-existia-{artigo_id.hex[:8]}", "autor": autor_id},
        )
        await s.commit()
    await motor.dispose()

    assert _alembic(banco, "head").returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        pode = (
            await s.execute(
                text("SELECT helo_pode_ler FROM kb_articles WHERE id = :id"), {"id": artigo_id}
            )
        ).scalar_one()
    await motor.dispose()

    assert pode is True


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


# ── O caminho de volta da agenda ──────────────────────────────
#
# Nenhuma migration deste projeto tinha caso de `downgrade` até aqui. Este
# existe porque o desenho da agenda pediu o caminho de volta guardado, e
# "guardado" só vale se alguém já tiver descido por ele: `downgrade` que nunca
# rodou é código que se descobre quebrado no pior momento possível, com o
# banco no meio de uma reversão.


@pytest.mark.asyncio
async def test_a_agenda_desce_e_sobe_sem_perder_horario(banco):
    """A descida até antes da agenda larga a chave e devolve as horas intactas."""
    assert _alembic(banco, "head").returncode == 0

    inicio = "2026-01-31 22:00:00+00"
    fim = "2026-02-01 02:00:00+00"
    motor = create_async_engine(banco)
    async with motor.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO calendar_events "
                "(id, title, event_type, color, start_date, end_date, all_day, "
                " created_at, updated_at) "
                "VALUES (gen_random_uuid(), 'plantão da virada', 'meeting', '#6366f1', "
                f"'{inicio}', '{fim}', false, now(), now())"
            )
        )
    await motor.dispose()

    descida = _alembic(banco, _ANTES_DA_AGENDA, comando="downgrade")
    assert descida.returncode == 0, f"downgrade falhou: {descida.stdout} {descida.stderr}"

    motor = create_async_engine(banco)
    async with motor.connect() as conn:
        colunas = (
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'calendar_events'"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "all_day" not in colunas, "a coluna ficou para trás"

        # O que importa: as horas continuam lá. O que se perde ao voltar é a
        # distinção entre "dia inteiro" e "evento que dura o dia todo", e ela é
        # recuperável por convenção — nenhum horário é destruído.
        linha = (await conn.execute(text("SELECT start_date, end_date FROM calendar_events"))).one()
        assert linha[0].isoformat().startswith("2026-01-31T22:00")
        assert linha[1].isoformat().startswith("2026-02-01T02:00")
    await motor.dispose()

    subida = _alembic(banco, "head")
    assert subida.returncode == 0, f"upgrade de volta falhou: {subida.stderr}"

    motor = create_async_engine(banco)
    async with motor.connect() as conn:
        # O `server_default` da subida alcança a linha que sobreviveu: ela volta
        # como dia inteiro, que é o mesmo destino dos eventos antigos.
        assert (
            await conn.execute(text("SELECT all_day FROM calendar_events"))
        ).scalar_one() is True
    await motor.dispose()


@pytest.mark.asyncio
async def test_depois_da_migration_quem_insere_evento_declara_a_chave(banco):
    """O `server_default` sai na mesma migration, e este caso prova que saiu.

    Ele existia para as linhas de antes. Se ficasse, um INSERT que omitisse a
    coluna viraria um evento de dia inteiro em SILÊNCIO — o contrário do que um
    evento com horário quer, e sem nada acusando.
    """
    assert _alembic(banco, "head").returncode == 0

    motor = create_async_engine(banco)
    with pytest.raises(Exception, match="all_day"):
        async with motor.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO calendar_events "
                    "(id, title, event_type, color, start_date, end_date, "
                    " created_at, updated_at) "
                    "VALUES (gen_random_uuid(), 'sem a chave', 'meeting', '#6366f1', "
                    "now(), now() + interval '1 hour', now(), now())"
                )
            )
    await motor.dispose()


# ── A saída do `other` do enum de categoria ───────────────────


async def _rotulos_da_categoria(url: str) -> list[str]:
    motor = create_async_engine(url)
    async with motor.connect() as conn:
        rotulos = (
            (
                await conn.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'ticketcategory' ORDER BY e.enumsortorder"
                    )
                )
            )
            .scalars()
            .all()
        )
    await motor.dispose()
    return list(rotulos)


@pytest.mark.asyncio
async def test_o_tipo_de_categoria_perde_o_other_e_o_recupera_na_descida(banco):
    """O caminho de ida e o de volta, medidos no catálogo do Postgres.

    Não há `DROP VALUE` em enum: a migration recria o tipo, converte as duas
    colunas que o usam e derruba o antigo. Um erro nessa dança não aparece em
    teste que monta o schema por `create_all` — aparece no boot do container.
    """
    assert _alembic(banco, "head").returncode == 0
    assert await _rotulos_da_categoria(banco) == [
        "hardware",
        "software",
        "network",
        "access",
        "email",
        "security",
        "general",
    ]

    descida = _alembic(banco, _ANTES_DA_SAIDA_DO_OTHER, comando="downgrade")
    assert descida.returncode == 0, f"downgrade falhou: {descida.stdout} {descida.stderr}"
    assert "other" in await _rotulos_da_categoria(banco), "o caminho de volta não devolveu o valor"

    subida = _alembic(banco, "head")
    assert subida.returncode == 0, f"upgrade de volta falhou: {subida.stderr}"
    assert "other" not in await _rotulos_da_categoria(banco)


@pytest.mark.asyncio
async def test_a_migration_para_alto_se_alguma_linha_ainda_usa_other(banco):
    """As contagens deram zero em 18/09, e é justamente por isso que há guarda.

    A medição vale para o instante em que foi feita. Entre ela e o deploy uma
    linha pode nascer, e converter dado dentro de migration é o que a casa não
    faz: o boot para, dizendo qual tabela e quantas linhas, e quem decide o
    destino delas é uma pessoa.
    """
    assert _alembic(banco, _ANTES_DA_SAIDA_DO_OTHER).returncode == 0

    autor_id = uuid.uuid4()
    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        # Colunas nomeadas, e não o ORM: este INSERT roda num schema mais
        # antigo que o modelo — ver a nota longa no teste do backfill.
        await s.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, "
                "lgpd_consent, email_verified, onboarding_completed) "
                "VALUES (:id, 'Autor', :email, 'x', 'technician', 'active', true, true, true)"
            ),
            {"id": autor_id, "email": f"{autor_id.hex[:8]}@test.com"},
        )
        await s.execute(
            text(
                "INSERT INTO kb_articles (id, title, content, slug, category, tags, "
                "status, helo_pode_ler, author_id, view_count, helpful, not_helpful) "
                "VALUES (gen_random_uuid(), 'Sobra do other', 'x', 'sobra-do-other', "
                "'other', '{}', 'draft', true, :autor, 0, 0, 0)"
            ),
            {"autor": autor_id},
        )
        await s.commit()
    await motor.dispose()

    subida = _alembic(banco, "head")
    assert subida.returncode != 0, "a migration passou por cima de uma linha em `other`"

    recado = subida.stdout + subida.stderr
    assert "kb_articles.category: 1" in recado, recado
    assert "script avulso" in recado, recado

    # E o tipo continua inteiro: a transação foi desfeita, não meio aplicada.
    assert "other" in await _rotulos_da_categoria(banco)
