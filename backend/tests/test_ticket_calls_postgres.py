"""
A tabela `ticket_calls` contra um PostgreSQL de verdade.

Invariante de banco só se prova contra o banco. O CHECK de status e o índice
único são SQL portável — o `create_all` do SQLite os monta —, mas o que decide
a Fase 2B não é a sintaxe: é o **tipo** da coluna do identificador. Um `Text`
aceita os dois formatos que o fornecedor publica; um `uuid` nativo rejeitaria
o de 27 caracteres, e a diferença só aparece com o Postgres na frente.

Aqui a migration roda **de verdade**, como subprocesso, num banco recriado do
zero a cada teste. Nenhum teste toca banco compartilhado — a lição da Fase 1B,
quando um `DROP TABLE` contra a base do CI derrubou 18 testes alheios.

O que estes testes prendem, em uma frase cada:

- `provider_call_id` é string opaca, e **aceita NULL em quantidade**;
- tentativa `confirmed` não existe sem identificador;
- status fora da lista não entra;
- o ciclo `upgrade → downgrade → upgrade` é reversível.
"""

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.test_dashboard_postgres import _sobe_postgres

_BACKEND = Path(__file__).resolve().parent.parent
_BANCO = "ticket_calls_testes"

_ANTES = "h4c5d6e7f8a9"  # a irmã que a main mesclou; virou o pai desta migration
_DEPOIS = "h4c5d6e7f8g9"

# Os DOIS formatos que a documentação oficial mostra para o mesmo campo `id`.
_ID_BASE62 = "1PkXhmBsYAvr9legLB2d7BimT0Q"
_ID_UUID = "bdf199fa-f85b-4378-80cd-0ac28c1355e9"


def _alembic(url: str, comando: str, alvo: str) -> subprocess.CompletedProcess:
    """Roda o alembic como SUBPROCESSO, igual ao `start.sh`."""
    ambiente = {**os.environ, "DATABASE_URL": url, "APP_ENV": "testing"}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", comando, alvo],
        cwd=_BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


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
    """Banco no head, com um chamado e um usuário prontos para as FKs."""
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    motor = create_async_engine(banco, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with motor.connect() as conn:
        ids = await _semeia(conn)
    await motor.dispose()

    yield banco, ids


async def _cria_usuario(conn, papel: str) -> uuid.UUID:
    """Usuário mínimo, COM telefone.

    O telefone não é enfeite: a constraint da Fase 1C
    (`ck_users_cliente_ativo_tem_telefone`) recusa `client` + `active` sem ele,
    e este arquivo precisa justamente de um cliente ativo para ser o criador do
    chamado. A invariante da fase anterior aparecendo aqui é o sinal de que ela
    funciona.
    """
    identificador = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO users (id, name, email, password, role, status, phone,"
            " lgpd_consent, created_at, updated_at)"
            " VALUES (:id, 'Pessoa', :e, 'hash', :r, 'active', '+5581999999999',"
            " false, now(), now())"
        ),
        {"id": identificador, "e": f"{uuid.uuid4()}@x.com", "r": papel},
    )
    return identificador


async def _semeia(conn) -> dict:
    """Dois usuários e um chamado, só para as FKs terem alvo.

    São DOIS usuários de propósito: quem cria o chamado e quem inicia a ligação
    são pessoas diferentes na vida real — o cliente abre, o técnico liga. E são
    diferentes aqui por necessidade: `tickets.creator_id` não é `SET NULL`,
    então apagar o criador é impossível, e o teste de exclusão do autor da
    tentativa precisa de alguém que possa mesmo sumir.
    """
    criador = await _cria_usuario(conn, "client")
    usuario = await _cria_usuario(conn, "technician")
    chamado = uuid.uuid4()
    # Os booleanos e contadores vão explícitos porque os defaults de `tickets`
    # são do lado do PYTHON (`default=False`), não `server_default` — um INSERT
    # cru não os aplica, e a coluna é NOT NULL. Descoberto rodando.
    await conn.execute(
        text(
            "INSERT INTO tickets (id, protocol, title, description, status, priority,"
            " category, creator_id, ai_enabled, helo_saiu, sla_response_breach,"
            " sla_resolve_breach, sla_total_paused_ms, auto_closed, reopen_count,"
            " created_at, updated_at)"
            " VALUES (:id, :p, 'Titulo', 'Descricao', 'open', 'medium',"
            " 'general', :c, true, false, false, false, 0, false, 0, now(), now())"
        ),
        {"id": chamado, "p": str(uuid.uuid4())[:20], "c": criador},
    )
    return {"usuario": usuario, "criador": criador, "chamado": chamado}


async def _conecta(url):
    return create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)


async def _insere(conn, ids, *, status, provider_call_id=None, http=None, quem="usuario"):
    await conn.execute(
        text(
            "INSERT INTO ticket_calls (id, ticket_id, initiated_by_id, provider_call_id,"
            " creation_status, provider_http_status, created_at, updated_at)"
            " VALUES (gen_random_uuid(), :t, :u, :pid, :st, :http, now(), now())"
        ),
        {
            "t": ids["chamado"],
            "u": ids[quem] if quem else None,
            "pid": provider_call_id,
            "st": status,
            "http": http,
        },
    )


async def _tenta(conn, coro):
    try:
        await coro
        return "ACEITO"
    except Exception as exc:  # noqa: BLE001
        return f"REJEITADO: {type(exc).__name__}"


# ── A migration sobe e desce ─────────────────────────────────


@pytest.mark.asyncio
async def test_upgrade_cria_a_tabela(banco):
    r = _alembic(banco, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    motor = await _conecta(banco)
    async with motor.connect() as conn:
        existe = await conn.scalar(text("SELECT to_regclass('public.ticket_calls')"))
    await motor.dispose()

    assert existe == "ticket_calls"


@pytest.mark.asyncio
async def test_downgrade_remove_a_tabela(banco):
    assert _alembic(banco, "upgrade", "head").returncode == 0
    r = _alembic(banco, "downgrade", _ANTES)
    assert r.returncode == 0, r.stderr

    motor = await _conecta(banco)
    async with motor.connect() as conn:
        existe = await conn.scalar(text("SELECT to_regclass('public.ticket_calls')"))
    await motor.dispose()

    assert existe is None


@pytest.mark.asyncio
async def test_upgrade_downgrade_upgrade(banco):
    """Reversível de verdade: o ciclo completo não deixa resto que impeça subir."""
    assert _alembic(banco, "upgrade", "head").returncode == 0
    assert _alembic(banco, "downgrade", _ANTES).returncode == 0
    r = _alembic(banco, "upgrade", _DEPOIS)
    assert r.returncode == 0, r.stderr

    motor = await _conecta(banco)
    async with motor.connect() as conn:
        existe = await conn.scalar(text("SELECT to_regclass('public.ticket_calls')"))
    await motor.dispose()

    assert existe == "ticket_calls"


# ── O identificador é string opaca ───────────────────────────


@pytest.mark.asyncio
async def test_a_coluna_do_identificador_e_textual_e_nao_uuid(migrado):
    """⚠️ O teste que justifica a escolha do tipo.

    `uuid` nativo do PostgreSQL rejeitaria `1PkXhmBsYAvr9legLB2d7BimT0Q`, que é
    o formato que a referência da API publica. Se alguém "melhorar" a coluna
    para `UUID`, é aqui que aparece.
    """
    banco, _ = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        tipo = await conn.scalar(
            text(
                "SELECT data_type FROM information_schema.columns"
                " WHERE table_name = 'ticket_calls' AND column_name = 'provider_call_id'"
            )
        )
    await motor.dispose()

    assert tipo == "text", f"a coluna virou {tipo}: um uuid nativo recusaria o id de 27 chars"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identificador",
    [_ID_BASE62, _ID_UUID, "x", "a" * 200],
    ids=["base62-27", "uuid-textual-36", "um-caractere", "muito-longo"],
)
async def test_aceita_qualquer_formato_de_identificador(migrado, identificador):
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        await _insere(conn, ids, status="confirmed", provider_call_id=identificador, http=200)
        gravado = await conn.scalar(text("SELECT provider_call_id FROM ticket_calls"))
    await motor.dispose()

    assert gravado == identificador


@pytest.mark.asyncio
async def test_varias_tentativas_sem_identificador_convivem(migrado):
    """Vários NULL sob o índice único — é o caso normal do indeterminado."""
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        for _ in range(3):
            await _insere(conn, ids, status="indeterminate")
        await _insere(conn, ids, status="pending")
        quantas = await conn.scalar(
            text("SELECT count(*) FROM ticket_calls WHERE provider_call_id IS NULL")
        )
    await motor.dispose()

    assert quantas == 4


@pytest.mark.asyncio
async def test_identificador_duplicado_e_recusado(migrado):
    """Duas linhas não podem afirmar ser a mesma chamada do fornecedor."""
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        await _insere(conn, ids, status="confirmed", provider_call_id=_ID_BASE62, http=200)
        resultado = await _tenta(
            conn,
            _insere(conn, ids, status="confirmed", provider_call_id=_ID_BASE62, http=200),
        )
    await motor.dispose()

    assert resultado.startswith("REJEITADO")


# ── A máquina de estados ─────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "indeterminate", "unavailable", "rejected"])
async def test_estados_sem_identificador_sao_aceitos(migrado, status):
    """Os quatro estados que não afirmam conhecer a chamada."""
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        resultado = await _tenta(conn, _insere(conn, ids, status=status))
    await motor.dispose()

    assert resultado == "ACEITO"


@pytest.mark.asyncio
async def test_confirmada_com_identificador_e_aceita(migrado):
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        resultado = await _tenta(
            conn,
            _insere(conn, ids, status="confirmed", provider_call_id=_ID_BASE62, http=200),
        )
    await motor.dispose()

    assert resultado == "ACEITO"


@pytest.mark.asyncio
async def test_confirmada_sem_identificador_e_recusada(migrado):
    """Afirmar que a chamada existe sem poder apontá-la — nem para desligar."""
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        resultado = await _tenta(conn, _insere(conn, ids, status="confirmed", http=200))
    await motor.dispose()

    assert resultado.startswith("REJEITADO")


@pytest.mark.asyncio
async def test_identificador_sem_estar_confirmada_e_aceito(migrado):
    """O inverso NÃO é imposto, e é decisão.

    A reconciliação da Fase 2D pode descobrir o identificador de uma tentativa
    que ficou indeterminada. Proibir esse estado fecharia o caminho de conserto
    antes de ele existir.
    """
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        resultado = await _tenta(
            conn,
            _insere(conn, ids, status="indeterminate", provider_call_id=_ID_UUID),
        )
    await motor.dispose()

    assert resultado == "ACEITO"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ringing", "answered", "hangup", "", "PENDING", "confirmada"])
async def test_estado_fora_da_lista_e_recusado(migrado, status):
    """Inclui os estados TELEFÔNICOS de propósito.

    `ringing` e `answered` são da Fase 2D e pertencem a outra coluna. Se
    alguém tentar enfiá-los aqui, o banco recusa antes de a confusão crescer.
    """
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        resultado = await _tenta(conn, _insere(conn, ids, status=status))
    await motor.dispose()

    assert resultado.startswith("REJEITADO")


# ── As chaves estrangeiras ───────────────────────────────────


@pytest.mark.asyncio
async def test_apagar_o_chamado_leva_as_tentativas(migrado):
    """CASCADE, como todas as sete filhas de `tickets`."""
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        await _insere(conn, ids, status="pending")
        await conn.execute(text("DELETE FROM tickets WHERE id = :t"), {"t": ids["chamado"]})
        sobraram = await conn.scalar(text("SELECT count(*) FROM ticket_calls"))
    await motor.dispose()

    assert sobraram == 0


@pytest.mark.asyncio
async def test_apagar_quem_iniciou_preserva_a_tentativa(migrado):
    """SET NULL: a tentativa é fato do chamado e sobrevive; quem some é a autoria.

    Mesmo critério de `kb_comments.author_id` e `equipments.owner_id`.
    """
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        await _insere(conn, ids, status="indeterminate")
        await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": ids["usuario"]})
        linhas = await conn.scalar(text("SELECT count(*) FROM ticket_calls"))
        autor = await conn.scalar(text("SELECT initiated_by_id FROM ticket_calls"))
    await motor.dispose()

    assert linhas == 1
    assert autor is None


@pytest.mark.asyncio
async def test_tentativa_sem_chamado_e_recusada(migrado):
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        resultado = await _tenta(
            conn,
            _insere(conn, {"chamado": uuid.uuid4(), "usuario": ids["usuario"]}, status="pending"),
        )
    await motor.dispose()

    assert resultado.startswith("REJEITADO")


@pytest.mark.asyncio
async def test_tentativa_sem_autor_e_aceita(migrado):
    """`initiated_by_id` é nulável desde o início, não só depois do SET NULL."""
    banco, ids = migrado
    motor = await _conecta(banco)
    async with motor.connect() as conn:
        resultado = await _tenta(conn, _insere(conn, ids, status="pending", quem=None))
    await motor.dispose()

    assert resultado == "ACEITO"


# ── Model e migration dizem a mesma coisa ────────────────────


def test_o_model_declara_as_mesmas_constraints():
    """O `autogenerate` não compara CHECK — medido na 1.15.2. Quem compara é isto."""
    from app.models.models import TicketCall

    checks = {
        c.name: " ".join(str(c.sqltext).split())
        for c in TicketCall.__table__.constraints
        if type(c).__name__ == "CheckConstraint"
    }
    assert "ck_ticket_calls_status_conhecido" in checks
    assert "ck_ticket_calls_confirmada_tem_id" in checks

    indices = {i.name: i.unique for i in TicketCall.__table__.indexes}
    assert indices.get("uq_ticket_calls_provider_call_id") is True
    assert "ix_ticket_calls_ticket_created" in indices


def test_os_estados_do_enum_batem_com_o_check():
    """Se alguém acrescentar estado no Python sem migration, cai aqui.

    ⚠️ O retrato do fim é o que força a pergunta, e ele já foi atualizado uma
    vez: `dispatching` entrou na Fase 2C.2 com a migration `8d08cbca1768`, que
    derruba e recria este CHECK. A coluna é `String` + `CHECK` justamente para
    que crescer custe isto — uma linha aqui e uma migration barata — em vez de
    um `ALTER TYPE` que o alembic desta casa não consegue encadear.
    """
    from app.models.models import CallCreationStatus, TicketCall

    do_enum = {e.value for e in CallCreationStatus}
    check = next(
        str(c.sqltext)
        for c in TicketCall.__table__.constraints
        if getattr(c, "name", "") == "ck_ticket_calls_status_conhecido"
    )
    for valor in do_enum:
        assert f"'{valor}'" in check, f"{valor} não está no CHECK"
    assert do_enum == {
        "pending",
        "dispatching",
        "confirmed",
        "rejected",
        "unavailable",
        "indeterminate",
    }
