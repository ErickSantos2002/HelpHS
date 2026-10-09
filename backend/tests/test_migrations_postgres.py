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
                # `phone` entrou aqui quando a Fase 1C pôs
                # `ck_users_cliente_ativo_tem_telefone` no banco: este seed
                # planta um cliente ATIVO, e sem telefone o `upgrade head`
                # passa a falhar na criação da constraint. O teste segue
                # medindo o backfill de equipamento — só o dado ficou
                # conforme a regra de domínio.
                "INSERT INTO users (id, name, email, password, role, status, phone, "
                "lgpd_consent, email_verified, onboarding_completed) "
                "VALUES (:id, :nome, :email, 'x', 'client', 'active', "
                "'+5581999999999', true, true, true)"
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


# ── O caminho de volta da prioridade ──────────────────────────

_ANTES_DA_PRIORIDADE_VAZIA = "g3b4c5d6e7f8"


@pytest.mark.asyncio
async def test_a_prioridade_desce_e_sobe_sem_perder_o_que_ja_estava(banco):
    """A coluna aceita NULL na subida, e a descida carimba `medium` no que é nulo.

    O downgrade desta revision é o único do projeto que ESCREVE. Ele existe
    porque `NOT NULL` não volta com linha nula na tabela, e o valor que ele
    carimba é o que o código antigo teria gravado. Um caminho de volta que
    nunca rodou é código que se descobre quebrado no meio de uma reversão —
    daí este teste.
    """
    assert _alembic(banco, "head").returncode == 0

    criador_id = uuid.uuid4()
    sem_prioridade = uuid.uuid4()
    com_prioridade = uuid.uuid4()

    motor = create_async_engine(banco)
    async with motor.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, phone, "
                "lgpd_consent, email_verified, onboarding_completed) "
                "VALUES (:id, 'Cliente', :email, 'x', 'client', 'active', "
                "'+5581999999999', true, true, true)"
            ),
            {"id": criador_id, "email": f"{criador_id.hex[:8]}@test.com"},
        )
        # O chamado recém-aberto: sem prioridade. É a linha que o `NOT NULL`
        # anterior recusaria, e é por ela que esta migration existe.
        await conn.execute(
            text(
                "INSERT INTO tickets (id, protocol, title, description, status, "
                "category, creator_id, sla_response_breach, sla_resolve_breach, "
                "sla_total_paused_ms, auto_closed, reopen_count, created_at, updated_at) "
                "VALUES (:id, :protocolo, 'Sem triagem', 'corpo', 'open', 'hardware', "
                ":criador, false, false, 0, false, 0, now(), now())"
            ),
            {
                "id": sem_prioridade,
                "protocolo": f"HS-MIG-{sem_prioridade.hex[:6]}",
                "criador": criador_id,
            },
        )
        # E um chamado antigo, que já tinha prioridade: ele não pode ser tocado
        # por nada disto.
        await conn.execute(
            text(
                "INSERT INTO tickets (id, protocol, title, description, status, priority, "
                "category, creator_id, sla_response_breach, sla_resolve_breach, "
                "sla_total_paused_ms, auto_closed, reopen_count, created_at, updated_at) "
                "VALUES (:id, :protocolo, 'Antigo', 'corpo', 'open', 'critical', 'hardware', "
                ":criador, false, false, 0, false, 0, now(), now())"
            ),
            {
                "id": com_prioridade,
                "protocolo": f"HS-MIG-{com_prioridade.hex[:6]}",
                "criador": criador_id,
            },
        )
    await motor.dispose()

    descida = _alembic(banco, _ANTES_DA_PRIORIDADE_VAZIA, comando="downgrade")
    assert descida.returncode == 0, f"downgrade falhou: {descida.stdout} {descida.stderr}"

    motor = create_async_engine(banco)
    async with motor.connect() as conn:
        nulavel = (
            await conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'tickets' AND column_name = 'priority'"
                )
            )
        ).scalar_one()
        assert nulavel == "NO", "o NOT NULL não voltou"

        # O que era nulo virou `medium` — o valor que o código antigo daria.
        assert (
            await conn.execute(
                text("SELECT priority::text FROM tickets WHERE id = :id"),
                {"id": sem_prioridade},
            )
        ).scalar_one() == "medium"
        # E o chamado que já tinha prioridade continua com a dele.
        assert (
            await conn.execute(
                text("SELECT priority::text FROM tickets WHERE id = :id"),
                {"id": com_prioridade},
            )
        ).scalar_one() == "critical"
    await motor.dispose()

    subida = _alembic(banco, "head")
    assert subida.returncode == 0, f"upgrade de volta falhou: {subida.stderr}"

    motor = create_async_engine(banco)
    async with motor.connect() as conn:
        nulavel = (
            await conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'tickets' AND column_name = 'priority'"
                )
            )
        ).scalar_one()
        assert nulavel == "YES", "a coluna não voltou a aceitar NULL"
        # A subida NÃO desfaz o carimbo da descida: nenhuma migration deste
        # projeto reescreve dado para trás.
        assert (
            await conn.execute(
                text("SELECT priority::text FROM tickets WHERE id = :id"),
                {"id": sem_prioridade},
            )
        ).scalar_one() == "medium"
    await motor.dispose()


# ── O caminho de volta da extensao de SLA ─────────────────────

_ANTES_DA_EXTENSAO = "h4c5d6e7f8g9"


@pytest.mark.asyncio
async def test_a_extensao_de_sla_sobe_e_desce(banco):
    """A coluna nasce com 0, o prazo efetivo nasce calculado, e volta limpo.

    O `UPDATE` da subida NAO e correcao de dado historico: ele materializa um
    valor que o motor ja calculava e ninguem guardava. Este caso prova que a
    conta bate — base mais pausa — para uma linha que ja existia.
    """
    assert _alembic(banco, _ANTES_DA_EXTENSAO).returncode == 0

    criador_id = uuid.uuid4()
    antigo = uuid.uuid4()
    prazo = "2026-09-24 15:11:00+00"
    pausa_ms = 3 * 60 * 60 * 1000

    motor = create_async_engine(banco)
    async with motor.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, email, password, role, status, phone, "
                "lgpd_consent, email_verified, onboarding_completed) "
                "VALUES (:id, 'Cliente', :email, 'x', 'client', 'active', "
                "'+5581999999999', true, true, true)"
            ),
            {"id": criador_id, "email": f"{criador_id.hex[:8]}@test.com"},
        )
        await conn.execute(
            text(
                "INSERT INTO tickets (id, protocol, title, description, status, priority, "
                "category, creator_id, sla_resolve_due_at, sla_total_paused_ms, "
                "sla_response_breach, sla_resolve_breach, auto_closed, reopen_count, "
                "created_at, updated_at) "
                "VALUES (:id, :protocolo, 'Antigo', 'corpo', 'open', 'medium', 'hardware', "
                f":criador, '{prazo}', {pausa_ms}, false, false, false, 0, now(), now())"
            ),
            {"id": antigo, "protocolo": f"HS-MIG-{antigo.hex[:6]}", "criador": criador_id},
        )
    await motor.dispose()

    subida = _alembic(banco, "head")
    assert subida.returncode == 0, f"upgrade falhou: {subida.stdout} {subida.stderr}"

    motor = create_async_engine(banco)
    async with motor.connect() as conn:
        linha = (
            await conn.execute(
                text(
                    "SELECT sla_resolve_extension_total_min, sla_resolve_effective_due_at "
                    "FROM tickets WHERE id = :id"
                ),
                {"id": antigo},
            )
        ).one()
        assert linha[0] == 0, "a coluna nova devia nascer zerada"
        # base + 3h de pausa acumulada
        assert linha[1].isoformat().startswith("2026-09-24T18:11")

        # E a tabela de eventos existe, vazia.
        assert (
            await conn.execute(text("SELECT count(*) FROM ticket_sla_extensions"))
        ).scalar_one() == 0
    await motor.dispose()

    descida = _alembic(banco, _ANTES_DA_EXTENSAO, comando="downgrade")
    assert descida.returncode == 0, f"downgrade falhou: {descida.stdout} {descida.stderr}"

    motor = create_async_engine(banco)
    async with motor.connect() as conn:
        colunas = (
            (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'tickets'"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "sla_resolve_extension_total_min" not in colunas
        assert "sla_resolve_effective_due_at" not in colunas
        # O prazo ORIGINAL sobrevive ao caminho de volta: nada de dado se perde.
        assert (
            (
                await conn.execute(
                    text("SELECT sla_resolve_due_at FROM tickets WHERE id = :id"), {"id": antigo}
                )
            )
            .scalar_one()
            .isoformat()
            .startswith("2026-09-24T15:11")
        )
    await motor.dispose()

    assert _alembic(banco, "head").returncode == 0


# ---------------------------------------------------------------------------
# Guardas do CAMINHO DE VOLTA (02/09/2026)
#
# Os testes acima medem a ida. Os de baixo medem a volta, que era onde o
# `downgrade` mentia: saía com código 0 e deixava o banco impróprio para o
# `upgrade` seguinte. Cada par abaixo é (revisão sob teste, revisão
# imediatamente anterior): subir só até a revisão alvo e descer UM passo isola
# o `downgrade` daquela migration — descer a partir de `head` executaria a
# cadeia inteira, e um `raise` de outra revisão mascararia o que se quer medir.
# ---------------------------------------------------------------------------

# Cada par é (revisão sob teste, revisão imediatamente anterior). Subir só até a
# revisão alvo e descer um passo isola o `downgrade` daquela migration — descer
# a partir de `head` executaria a cadeia inteira e um `raise` de outra revisão
# mascararia o que se quer medir.
_A1_AUDITORIA = ("r8m9n0o1p2q3", "q7l8m9n0o1p2")


# Cada par é (revisão sob teste, revisão imediatamente anterior). Subir só até a
# revisão alvo e descer um passo isola o `downgrade` daquela migration — descer
# a partir de `head` executaria a cadeia inteira e um `raise` de outra revisão
# mascararia o que se quer medir.
_A1_AUDITORIA = ("r8m9n0o1p2q3", "q7l8m9n0o1p2")
_A2_UNICIDADE = ("x4s5t6u7v8w9", "w3r4s5t6u7v8")


_A2_UNICIDADE = ("x4s5t6u7v8w9", "w3r4s5t6u7v8")
_A3_EQUIPAMENTOS = ("t0o1p2q3r4s5", "s9n0o1p2q3r4")


_A3_EQUIPAMENTOS = ("t0o1p2q3r4s5", "s9n0o1p2q3r4")
_A4_IA = ("z6u7v8w9x0y1", "y5t6u7v8w9x0")


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
    assert _alembic(banco, "head").returncode == 0

    volta = _alembic(banco, "base", comando="downgrade")
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
    assert _alembic(banco, "head").returncode == 0
    primeira = await _fotografa(banco)

    assert _alembic(banco, "base", comando="downgrade").returncode == 0

    subida = _alembic(banco, "head")
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
async def test_a1_downgrade_passa_quando_todo_historico_tem_autor(banco):
    """Histórico com autor humano não bloqueia o rollback — o caminho normal."""
    assert _alembic(banco, _A1_AUDITORIA[0]).returncode == 0

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

    volta = _alembic(banco, _A1_AUDITORIA[1], comando="downgrade")

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
    assert _alembic(banco, _A1_AUDITORIA[0]).returncode == 0

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

    volta = _alembic(banco, _A1_AUDITORIA[1], comando="downgrade")
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


@pytest.mark.asyncio
async def test_a2_downgrade_passa_sem_serie_repetida(banco):
    assert _alembic(banco, _A2_UNICIDADE[0]).returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        dono = await _semeia_usuario(s)
        produto = await _semeia_produto(s)
        await s.execute(
            text(
                "INSERT INTO equipments (id, product_id, owner_id, name, serial_number, "
                "is_active) VALUES (:id, :produto, :dono, 'Phoebus', 'SERIE-A', true)"
            ),
            {"id": uuid.uuid4(), "produto": produto, "dono": dono},
        )
        await s.commit()
    await motor.dispose()

    volta = _alembic(banco, _A2_UNICIDADE[1], comando="downgrade")

    assert volta.returncode == 0, f"{volta.stdout}\n{volta.stderr}"


@pytest.mark.asyncio
async def test_a2_downgrade_aborta_com_serie_que_a_chave_nova_permite(banco):
    """A chave nova é (produto, série); a antiga era (dono, série).

    Mesmo dono, mesma série, produtos diferentes: legítimo sob a chave de hoje e
    proibido sob a de ontem. O downgrade precisa dizer isso antes de tentar criar
    o índice — `CREATE UNIQUE INDEX` estourando sozinho dá um erro opaco que não
    diz quantos casos existem nem o que fazer.
    """
    assert _alembic(banco, _A2_UNICIDADE[0]).returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        dono = await _semeia_usuario(s)
        for _ in range(2):
            produto = await _semeia_produto(s)
            await s.execute(
                text(
                    "INSERT INTO equipments (id, product_id, owner_id, name, "
                    "serial_number, is_active) "
                    "VALUES (:id, :produto, :dono, 'Phoebus', 'SERIE-REPETIDA', true)"
                ),
                {"id": uuid.uuid4(), "produto": produto, "dono": dono},
            )
        await s.commit()
    await motor.dispose()

    volta = _alembic(banco, _A2_UNICIDADE[1], comando="downgrade")
    saida = volta.stdout + volta.stderr

    assert volta.returncode != 0, "o downgrade passou com dado que a chave antiga proíbe"
    assert "1" in saida, "a mensagem precisa dizer quantos grupos conflitam"
    assert "serial_number" in saida
    assert "SERIE-REPETIDA" not in saida, "a mensagem não deve despejar o dado em si"

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        quantos = (await s.execute(text("SELECT count(*) FROM equipments"))).scalar_one()
    await motor.dispose()

    assert quantos == 2, "nenhum aparelho podia ter sido apagado"


@pytest.mark.asyncio
async def test_a3_downgrade_escolhe_o_equipamento_mais_antigo_e_nao_o_uuid_menor(banco):
    """ "Mais antigo" tem que ser tempo, não ordem lexical de UUID.

    O UUID é v4: não carrega cronologia nenhuma. Este teste monta o caso que
    separa as duas leituras — o aparelho MAIS ANTIGO recebe o UUID MAIOR. Se a
    escolha voltar a ser por id, o resultado inverte e o teste acusa.
    """
    assert _alembic(banco, _A3_EQUIPAMENTOS[0]).returncode == 0

    antigo = uuid.UUID(int=2**127)  # maior lexicalmente
    novo = uuid.UUID(int=1)  # menor lexicalmente

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        criador = await _semeia_usuario(s)
        produto = await _semeia_produto(s)
        chamado = await _semeia_chamado(s, criador)
        for identificador, serie, quando in (
            (antigo, "SERIE-ANTIGA", datetime(2020, 1, 1, tzinfo=UTC)),
            (novo, "SERIE-NOVA", datetime(2026, 1, 1, tzinfo=UTC)),
        ):
            await s.execute(
                text(
                    "INSERT INTO equipments (id, product_id, name, serial_number, "
                    "is_active, created_at) "
                    "VALUES (:id, :produto, 'Phoebus', :serie, true, :quando)"
                ),
                {"id": identificador, "produto": produto, "serie": serie, "quando": quando},
            )
            await s.execute(
                text(
                    "INSERT INTO ticket_equipments (ticket_id, equipment_id) "
                    "VALUES (:chamado, :equipamento)"
                ),
                {"chamado": chamado, "equipamento": identificador},
            )
        await s.commit()
    await motor.dispose()

    volta = _alembic(banco, _A3_EQUIPAMENTOS[1], comando="downgrade")
    assert volta.returncode == 0, f"{volta.stdout}\n{volta.stderr}"

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        escolhido = (
            await s.execute(
                text("SELECT equipment_id FROM tickets WHERE id = :id"), {"id": chamado}
            )
        ).scalar_one()
    await motor.dispose()

    assert escolhido == antigo, (
        "o downgrade escolheu por UUID, não por data: ficou com o aparelho de 2026 "
        "em vez do de 2020"
    )


@pytest.mark.asyncio
async def test_a4_downgrade_passa_quando_ninguem_desligou_a_ia(banco):
    assert _alembic(banco, _A4_IA[0]).returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        await _semeia_usuario(s)  # nasce com ai_enabled = true
        await s.commit()
    await motor.dispose()

    volta = _alembic(banco, _A4_IA[1], comando="downgrade")

    assert volta.returncode == 0, f"{volta.stdout}\n{volta.stderr}"


@pytest.mark.asyncio
async def test_a4_downgrade_aborta_quando_alguem_desligou_a_ia(banco):
    """Descer e subir de novo RELIGA a IA de quem a tinha desligado.

    O `server_default` do re-upgrade é TRUE, e não existe de onde reconstruir o
    valor: `_audit()` em `users.py:75` grava o AuditLog sem `old_data`/`new_data`.
    Como não há fonte confiável, o downgrade não tenta restaurar nada — ele para
    e exige decisão humana, que é melhor do que religar em silêncio uma coisa
    que o cliente desligou de propósito.
    """
    assert _alembic(banco, _A4_IA[0]).returncode == 0

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        quem_desligou = await _semeia_usuario(s, "Empresa sem robô")
        await s.execute(
            text("UPDATE users SET ai_enabled = false WHERE id = :id"),
            {"id": quem_desligou},
        )
        await s.commit()
    await motor.dispose()

    volta = _alembic(banco, _A4_IA[1], comando="downgrade")
    saida = volta.stdout + volta.stderr

    assert volta.returncode != 0, "o downgrade passou e o re-upgrade religaria a IA"
    assert "1" in saida, "a mensagem precisa dizer quantos opt-outs bloqueiam"
    assert "ai_enabled" in saida

    motor = create_async_engine(banco)
    async with async_sessionmaker(bind=motor, expire_on_commit=False)() as s:
        ainda_desligado = (
            await s.execute(
                text("SELECT ai_enabled FROM users WHERE id = :id"), {"id": quem_desligou}
            )
        ).scalar_one()
    await motor.dispose()

    assert ainda_desligado is False, "o opt-out tinha que continuar valendo"
