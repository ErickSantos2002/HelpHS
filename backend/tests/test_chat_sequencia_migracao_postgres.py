"""
A migration da numeração do chat (`n0i1j2k3l4m5`) contra um PostgreSQL de verdade.

O que se prende aqui, em uma frase cada:

- o legado fica como estava: nenhuma mensagem ganha número, todo contador
  nasce em zero, nenhum conteúdo é tocado — e nenhuma tabela é reescrita;
- uma imagem ANTIGA do backend (que não conhece `seq`) continua gravando
  depois da migration, sem número — é o cenário do rollback de aplicação;
- o índice único vale no banco, e só onde há número;
- a migration grava o marco do corte no ÚLTIMO comando, e o downgrade o leva;
- o script avulso numera só o que entrou sem número DEPOIS do corte, na
  ordem de `created_at`, continuando o contador — e não mexe no legado;
- `upgrade → downgrade → upgrade` não perde mensagem; o contador volta a
  zero, e é por isso que o downgrade não é estratégia de rollback.

Banco recriado do zero a cada teste, migration como subprocesso — igual ao
`start.sh`.
"""

import asyncio
import shutil
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.services.chat_sequencia import MARGEM_DO_CORTE
from scripts.numera_mensagens_sem_seq import SemMarcoDoCorteError, numera, pendentes
from tests.test_dashboard_postgres import _sobe_postgres
from tests.test_ticket_calls_postgres import _alembic

_BANCO = "sequencia_do_chat_testes"
_ANTES = "m9h0i1j2k3l4"
_REVISION = "n0i1j2k3l4m5"


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


async def _usuario(url: str) -> uuid.UUID:
    uid = uuid.uuid4()
    await _executa(
        url,
        "INSERT INTO users (id, name, email, password, role, status, phone,"
        " lgpd_consent, email_verified, mfa_enabled, onboarding_completed, ai_enabled,"
        " created_at, updated_at) VALUES (:id, 'Pessoa', :e, 'x', 'client', 'active',"
        " '+5581999999999', false, true, false, true, true, now(), now())",
        id=uid,
        e=f"{uid.hex[:10]}@test.invalid",
    )
    return uid


async def _chamado(url: str, autor: uuid.UUID) -> uuid.UUID:
    tid = uuid.uuid4()
    await _executa(
        url,
        "INSERT INTO tickets (id, protocol, title, description, category, status,"
        " creator_id, sla_response_breach, sla_resolve_breach, reopen_count,"
        " sla_total_paused_ms, ai_enabled, helo_saiu,"
        " sla_resolve_extension_total_min, created_at, updated_at)"
        " VALUES (:id, :p, 'Teste', 'Desc', 'hardware', 'open',"
        " :c, false, false, 0, 0, true, false, 0, now(), now())",
        id=tid,
        p=f"HS-SEQ-{tid.hex[:8]}",
        c=autor,
    )
    return tid


async def _mensagem_antiga(url: str, chamado, autor, quando: datetime, texto="x") -> uuid.UUID:
    """O INSERT de uma imagem que não conhece `seq`: as colunas de antes."""
    mid = uuid.uuid4()
    await _executa(
        url,
        "INSERT INTO chat_messages (id, ticket_id, sender_id, content, is_system, is_ai,"
        " created_at) VALUES (:id, :t, :s, :c, false, false, :q)",
        id=mid,
        t=chamado,
        s=autor,
        c=texto,
        q=quando,
    )
    return mid


async def _arquivo_da_tabela(url: str, tabela: str) -> int:
    """`relfilenode` muda quando a tabela é reescrita; ADD COLUMN com padrão
    constante não reescreve (PostgreSQL 11+)."""
    return (await _consulta(url, f"SELECT relfilenode FROM pg_class WHERE relname = '{tabela}'"))[
        0
    ][0]


@pytest.mark.asyncio
async def test_upgrade_nao_numera_o_legado_nao_reescreve_e_imagem_antiga_segue_gravando(banco):
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr

    autor = await _usuario(banco)
    chamado = await _chamado(banco, autor)
    agora = datetime.now(UTC)
    for i in range(3):
        await _mensagem_antiga(banco, chamado, autor, agora - timedelta(days=1, minutes=-i))
    conteudo_antes = await _consulta(
        banco, "SELECT id, content, created_at FROM chat_messages ORDER BY id"
    )
    arquivos_antes = (
        await _arquivo_da_tabela(banco, "tickets"),
        await _arquivo_da_tabela(banco, "chat_messages"),
    )

    antes_do_upgrade = datetime.now(UTC)
    r = _alembic(banco, "upgrade", _REVISION)
    assert r.returncode == 0, r.stderr

    [(marco,)] = await _consulta(banco, "SELECT migrada_em FROM chat_seq_corte")
    assert antes_do_upgrade - timedelta(seconds=5) < marco < datetime.now(UTC)
    assert marco > max(q for _, _, q in conteudo_antes), "o legado fica antes do marco"
    assert await _consulta(banco, "SELECT chat_seq FROM tickets") == [(0,)]
    assert await _consulta(banco, "SELECT count(*) FROM chat_messages WHERE seq IS NOT NULL") == [
        (0,)
    ]
    assert (
        await _consulta(banco, "SELECT id, content, created_at FROM chat_messages ORDER BY id")
        == conteudo_antes
    )
    assert (
        await _arquivo_da_tabela(banco, "tickets"),
        await _arquivo_da_tabela(banco, "chat_messages"),
    ) == arquivos_antes, "a migration reescreveu uma tabela"

    [(definicao,)] = await _consulta(
        banco, "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_chat_messages_seq'"
    )
    assert "UNIQUE" in definicao and "(ticket_id, seq)" in definicao
    assert "WHERE (seq IS NOT NULL)" in definicao

    # A imagem antiga continua gravando — sem número, sem erro.
    await _mensagem_antiga(banco, chamado, autor, agora)
    assert await _consulta(banco, "SELECT count(*) FROM chat_messages WHERE seq IS NULL") == [(4,)]
    # O padrão está no BANCO: um chamado inserido sem falar da coluna nasce em 0.
    outro = await _chamado(banco, autor)
    assert await _consulta(banco, "SELECT chat_seq FROM tickets WHERE id = :t", t=outro) == [(0,)]


@pytest.mark.asyncio
async def test_o_indice_unico_vale_no_banco_e_so_onde_ha_numero(banco):
    r = _alembic(banco, "upgrade", _REVISION)
    assert r.returncode == 0, r.stderr
    autor = await _usuario(banco)
    chamado, outro = await _chamado(banco, autor), await _chamado(banco, autor)
    agora = datetime.now(UTC)

    a = await _mensagem_antiga(banco, chamado, autor, agora)
    b = await _mensagem_antiga(banco, chamado, autor, agora)
    c = await _mensagem_antiga(banco, outro, autor, agora)
    await _executa(banco, "UPDATE chat_messages SET seq = 1 WHERE id = :m", m=a)
    await _executa(banco, "UPDATE chat_messages SET seq = 1 WHERE id = :m", m=c)  # outro chamado
    with pytest.raises(IntegrityError):
        await _executa(banco, "UPDATE chat_messages SET seq = 1 WHERE id = :m", m=b)


@pytest.mark.asyncio
async def test_script_numera_so_o_que_entrou_sem_numero_depois_do_corte(banco):
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr
    autor = await _usuario(banco)
    chamado, outro = await _chamado(banco, autor), await _chamado(banco, autor)
    base = datetime.now(UTC) - timedelta(hours=1)
    legado = await _mensagem_antiga(banco, chamado, autor, base - timedelta(days=2), "legado")

    r = _alembic(banco, "upgrade", _REVISION)
    assert r.returncode == 0, r.stderr
    # O marco em instante conhecido, para o cenário ser determinístico.
    await _executa(banco, "UPDATE chat_seq_corte SET migrada_em = :q", q=base)

    # A imagem nova numerou duas; depois um recuo trouxe a antiga, que gravou
    # três sem número — a última carimbada mais cedo — e uma na JANELA antes
    # do marco (montada antes, gravada depois: ambígua).
    for numero in (1, 2):
        mid = await _mensagem_antiga(banco, chamado, autor, base + timedelta(minutes=numero))
        await _executa(banco, "UPDATE chat_messages SET seq = :s WHERE id = :m", s=numero, m=mid)
    await _executa(banco, "UPDATE tickets SET chat_seq = 2 WHERE id = :t", t=chamado)
    sem_numero = [
        await _mensagem_antiga(banco, chamado, autor, base + timedelta(minutes=10), "s1"),
        await _mensagem_antiga(banco, chamado, autor, base + timedelta(minutes=20), "s2"),
        await _mensagem_antiga(banco, chamado, autor, base + timedelta(minutes=5), "s0"),
    ]
    na_janela = await _mensagem_antiga(banco, outro, autor, base - MARGEM_DO_CORTE / 2, "na janela")
    await _mensagem_antiga(banco, outro, autor, base + timedelta(minutes=1), "do outro")

    contagem = await pendentes(banco)
    assert contagem == {
        str(chamado): {"depois": 3, "janela": 0},
        str(outro): {"depois": 1, "janela": 1},
    }
    assert await _consulta(banco, "SELECT count(*) FROM chat_messages WHERE seq IS NULL") == [(6,)]

    assert await numera(banco) == {str(chamado): 3, str(outro): 1}

    numeradas = dict(
        await _consulta(
            banco,
            "SELECT content, seq FROM chat_messages WHERE id = ANY(:ids)",
            ids=sem_numero,
        )
    )
    assert numeradas == {"s0": 3, "s1": 4, "s2": 5}, "ordem de created_at, depois do contador"
    assert await _consulta(banco, "SELECT seq FROM chat_messages WHERE id = :m", m=legado) == [
        (None,)
    ], "o histórico NUNCA é numerado"
    assert await _consulta(banco, "SELECT seq FROM chat_messages WHERE id = :m", m=na_janela) == [
        (None,)
    ], "a janela ambígua só com --incluir-janela"
    assert await numera(banco) == {}, "rodar de novo não faz nada"

    assert await numera(banco, incluir_janela=True) == {str(outro): 1}
    assert await _consulta(banco, "SELECT seq FROM chat_messages WHERE id = :m", m=na_janela) == [
        (2,)
    ]
    assert await _consulta(banco, "SELECT seq FROM chat_messages WHERE id = :m", m=legado) == [
        (None,)
    ]


@pytest.mark.asyncio
async def test_script_sem_o_marco_nao_faz_nada(banco):
    r = _alembic(banco, "upgrade", _REVISION)
    assert r.returncode == 0, r.stderr
    await _executa(banco, "DELETE FROM chat_seq_corte")
    autor = await _usuario(banco)
    chamado = await _chamado(banco, autor)
    await _mensagem_antiga(banco, chamado, autor, datetime.now(UTC))

    with pytest.raises(SemMarcoDoCorteError):
        await numera(banco, incluir_janela=True)
    with pytest.raises(SemMarcoDoCorteError):
        await pendentes(banco)
    assert await _consulta(banco, "SELECT count(*) FROM chat_messages WHERE seq IS NULL") == [(1,)]


@pytest.mark.asyncio
async def test_downgrade_nao_perde_mensagem_e_o_contador_volta_a_zero(banco):
    r = _alembic(banco, "upgrade", _REVISION)
    assert r.returncode == 0, r.stderr
    autor = await _usuario(banco)
    chamado = await _chamado(banco, autor)
    mid = await _mensagem_antiga(banco, chamado, autor, datetime.now(UTC))
    await _executa(banco, "UPDATE chat_messages SET seq = 1 WHERE id = :m", m=mid)
    await _executa(banco, "UPDATE tickets SET chat_seq = 1 WHERE id = :t", t=chamado)

    r = _alembic(banco, "downgrade", _ANTES)
    assert r.returncode == 0, r.stderr
    assert await _consulta(banco, "SELECT id FROM chat_messages") == [(mid,)]
    colunas = await _consulta(
        banco,
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE (table_name, column_name) IN (('tickets', 'chat_seq'), ('chat_messages', 'seq'))",
    )
    assert colunas == []
    assert (
        await _consulta(banco, "SELECT 1 FROM pg_indexes WHERE indexname = 'uq_chat_messages_seq'")
        == []
    )
    assert await _consulta(banco, "SELECT to_regclass('chat_seq_corte')") == [(None,)]

    r = _alembic(banco, "upgrade", _REVISION)
    assert r.returncode == 0, r.stderr
    # O número que a tela guardou (1) agora é MAIOR que o contador (0): a
    # API responde 409 e ela recarrega. Nada se perde, mas todo mundo
    # ressincroniza — por isso o rollback é de aplicação, mantendo a migration.
    assert await _consulta(banco, "SELECT chat_seq FROM tickets") == [(0,)]
    assert await _consulta(banco, "SELECT seq FROM chat_messages") == [(None,)]


@pytest.mark.asyncio
async def test_custo_da_migration_com_volume(banco, capsys):
    """Não é teste de desempenho com teto: é a MEDIDA que entra nas notas.
    A coluna é só metadado; o custo é a varredura do CREATE INDEX, que segura
    `SHARE` em `chat_messages` (bloqueia gravação, não leitura) — com o
    índice vazio, já que nenhuma linha tem número."""
    r = _alembic(banco, "upgrade", _ANTES)
    assert r.returncode == 0, r.stderr
    autor = await _usuario(banco)
    chamados = [await _chamado(banco, autor) for _ in range(20)]
    await _executa(
        banco,
        "INSERT INTO chat_messages (id, ticket_id, sender_id, content, is_system, is_ai,"
        " created_at)"
        " SELECT gen_random_uuid(), (CAST(:ts AS uuid[]))[1 + (g % 20)], :s, repeat('x', 200), false, false,"
        " now() - make_interval(secs => g)"
        " FROM generate_series(1, 200000) AS g",
        ts=chamados,
        s=autor,
    )
    await _executa(banco, "ANALYZE chat_messages")

    inicio = time.perf_counter()
    motor = create_async_engine(banco, poolclass=NullPool)
    async with motor.connect() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = '60s'"))
        await conn.execute(
            text("ALTER TABLE tickets ADD COLUMN chat_seq BIGINT NOT NULL DEFAULT 0")
        )
        await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN seq BIGINT"))
        meio = time.perf_counter()
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_chat_messages_seq ON chat_messages (ticket_id, seq)"
                " WHERE seq IS NOT NULL"
            )
        )
        fim = time.perf_counter()
        await conn.rollback()  # medida só: o banco volta a m9h0
    await motor.dispose()
    with capsys.disabled():
        print(
            f"\n[medida] 200000 mensagens: colunas {1000 * (meio - inicio):.0f} ms,"
            f" índice {1000 * (fim - meio):.0f} ms"
        )
    assert fim - inicio < 60


def test_o_script_sem_url_nao_roda(monkeypatch, capsys):
    from scripts import numera_mensagens_sem_seq as script

    monkeypatch.setattr("sys.argv", ["x", "--aplicar"])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert asyncio.run(script.principal()) == 2
    assert "DATABASE_URL" in capsys.readouterr().out
