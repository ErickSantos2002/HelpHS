"""
A máquina de estados da tentativa de ligação, sem rede nenhuma.

`app/services/telefonia.py` não importa `httpx` nem `api4com.py` — e é por isso
que estes testes existem antes da orquestração: a máquina de estados fica
provada enquanto ainda não há efeito externo para depurar junto.

Dois grupos. O primeiro exercita as transições contra um banco de verdade,
porque `flush()` é o que revela violação de CHECK. O segundo é guard de
assinatura: prende que nenhuma função ACEITA telefone, corpo de resposta ou
metadata — a ausência de parâmetro é a garantia de que não há como persistir
isso por descuido, e vale mais que a disciplina de quem chamar.
"""

import inspect

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.models import CallCreationStatus, TicketCall
from app.services import telefonia
from tests.test_ticket_calls_postgres import _alembic, _semeia, servidor  # noqa: F401

_BANCO = "telefonia_persistencia_testes"
_ID_BASE62 = "1PkXhmBsYAvr9legLB2d7BimT0Q"


@pytest_asyncio.fixture
async def sessao(servidor):  # noqa: F811
    """Banco migrado, semeado, e uma AsyncSession aberta sobre ele."""
    admin = create_async_engine(servidor, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{_BANCO}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{_BANCO}"'))
    await admin.dispose()

    url = servidor.rsplit("/", 1)[0] + f"/{_BANCO}"
    preparo = create_async_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with preparo.connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await preparo.dispose()

    assert _alembic(url, "upgrade", "head").returncode == 0

    motor = create_async_engine(url, poolclass=NullPool)
    async with motor.connect() as conn:
        ids = await _semeia(conn)
        await conn.commit()

    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as db:
        yield db, ids
    await motor.dispose()


async def _nova(db, ids) -> TicketCall:
    return await telefonia.registra_tentativa(
        db, ticket_id=ids["chamado"], initiated_by_id=ids["usuario"]
    )


# ── O ciclo ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_tentativa_nasce_pending_e_sem_identificador(sessao):
    """A linha existe ANTES de a requisição sair. É o ponto da tabela."""
    db, ids = sessao
    tentativa = await _nova(db, ids)

    assert tentativa.creation_status == CallCreationStatus.pending.value
    assert tentativa.provider_call_id is None
    assert tentativa.provider_http_status is None
    assert tentativa.id is not None, "o UUID interno precisa existir já no pending"
    assert tentativa.ticket_id == ids["chamado"]
    assert tentativa.initiated_by_id == ids["usuario"]


@pytest.mark.asyncio
async def test_a_tentativa_pending_esta_mesmo_no_banco(sessao):
    """`flush()` e não só objeto na memória: o CHECK do banco já opinou."""
    db, ids = sessao
    tentativa = await _nova(db, ids)

    achada = (
        await db.execute(select(TicketCall).where(TicketCall.id == tentativa.id))
    ).scalar_one()
    assert achada.creation_status == "pending"


@pytest.mark.asyncio
async def test_confirma_grava_o_identificador_exatamente_como_veio(sessao):
    """Sem strip, sem caixa alterada, sem validação. String opaca."""
    db, ids = sessao
    tentativa = await _nova(db, ids)
    await telefonia.confirma(db, tentativa, provider_call_id=_ID_BASE62, provider_http_status=200)

    assert tentativa.provider_call_id == _ID_BASE62
    assert tentativa.provider_http_status == 200
    assert tentativa.creation_status == CallCreationStatus.confirmed.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identificador",
    ["  com-espaco  ", "MaIuSculas", "bdf199fa-f85b-4378-80cd-0ac28c1355e9", "x"],
    ids=["com-espaco", "caixa-mista", "uuid-textual", "um-caractere"],
)
async def test_confirma_nao_normaliza_nada(sessao, identificador):
    db, ids = sessao
    tentativa = await _nova(db, ids)
    await telefonia.confirma(
        db, tentativa, provider_call_id=identificador, provider_http_status=200
    )

    assert tentativa.provider_call_id == identificador


@pytest.mark.asyncio
async def test_recusada_grava_o_status_http(sessao):
    db, ids = sessao
    tentativa = await _nova(db, ids)
    await telefonia.marca_recusada(db, tentativa, provider_http_status=422)

    assert tentativa.creation_status == CallCreationStatus.rejected.value
    assert tentativa.provider_http_status == 422
    assert tentativa.provider_call_id is None


@pytest.mark.asyncio
async def test_indisponivel_nao_inventa_status_http(sessao):
    """Não houve resposta — então não há número para gravar.

    A assinatura da função é a garantia: ela não RECEBE status. Inventar um
    zero ou um 503 faria o banco afirmar que o fornecedor respondeu algo.
    """
    db, ids = sessao
    tentativa = await _nova(db, ids)
    await telefonia.marca_indisponivel(db, tentativa)

    assert tentativa.creation_status == CallCreationStatus.unavailable.value
    assert tentativa.provider_http_status is None
    assert tentativa.provider_call_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("http", [None, 500, 503, 302, 200])
async def test_indeterminada_preserva_a_ausencia_do_identificador(sessao, http):
    """⚠️ O estado que justifica a tabela: pode ter tocado, e não sabemos qual.

    `provider_call_id` continua NULL em todos os caminhos — é essa ausência que
    a reconciliação da Fase 2D vai procurar. O status HTTP é opcional porque o
    indeterminado chega com resposta (5xx, 3xx, 200 sem `id`) e sem resposta
    nenhuma (`ReadTimeout`).
    """
    db, ids = sessao
    tentativa = await _nova(db, ids)
    await telefonia.marca_indeterminada(db, tentativa, provider_http_status=http)

    assert tentativa.creation_status == CallCreationStatus.indeterminate.value
    assert tentativa.provider_call_id is None
    assert tentativa.provider_http_status == http


@pytest.mark.asyncio
async def test_tentativa_sem_autor_e_aceita(sessao):
    """Ligação disparada por caminho sem usuário identificado."""
    db, ids = sessao
    tentativa = await telefonia.registra_tentativa(
        db, ticket_id=ids["chamado"], initiated_by_id=None
    )

    assert tentativa.initiated_by_id is None
    assert tentativa.creation_status == "pending"


@pytest.mark.asyncio
async def test_duas_tentativas_indeterminadas_convivem(sessao):
    """Nada impede o mesmo chamado de ter várias — e a 2B não deve impedir.

    Proteção contra duplo clique é decisão da 2C, junto com o endpoint. A
    tabela só precisa conseguir representar o estado.
    """
    db, ids = sessao
    primeira = await _nova(db, ids)
    segunda = await _nova(db, ids)
    await telefonia.marca_indeterminada(db, primeira)
    await telefonia.marca_indeterminada(db, segunda)

    quantas = await db.scalar(text("SELECT count(*) FROM ticket_calls"))
    assert quantas == 2


# ── Guard de assinatura: o que não há como persistir ─────────


_PROIBIDOS = {
    "phone",
    "telefone",
    "called",
    "caller",
    "extension",
    "numero",
    "payload",
    "body",
    "corpo",
    "response",
    "resposta",
    "metadata",
    "token",
    "authorization",
    "headers",
    "cabecalho",
    "record",
    "gravacao",
}


@pytest.mark.parametrize(
    "funcao",
    [
        telefonia.registra_tentativa,
        telefonia.confirma,
        telefonia.marca_recusada,
        telefonia.marca_indisponivel,
        telefonia.marca_indeterminada,
    ],
    ids=lambda f: f.__name__,
)
def test_nenhuma_funcao_aceita_pii_ou_corpo_bruto(funcao):
    """A ausência de parâmetro é a garantia, não a disciplina de quem chama.

    Se alguém acrescentar `called=` ou `payload=` a uma destas funções para
    "guardar para depurar", o teste cai antes de o dado chegar ao banco.
    """
    parametros = set(inspect.signature(funcao).parameters)
    intrusos = {p for p in parametros if any(x in p.lower() for x in _PROIBIDOS)}
    assert not intrusos, f"{funcao.__name__} passou a aceitar {intrusos}"


def test_a_tabela_nao_tem_coluna_para_pii_ou_corpo_bruto():
    """Mesmo guard, do lado do schema."""
    colunas = {c.name for c in TicketCall.__table__.columns}
    intrusos = {c for c in colunas if any(x in c.lower() for x in _PROIBIDOS)}
    assert not intrusos, f"a tabela ganhou {intrusos}"
    assert colunas == {
        "id",
        "ticket_id",
        "initiated_by_id",
        "provider_call_id",
        "creation_status",
        "provider_http_status",
        "created_at",
        "updated_at",
    }


def test_o_modulo_nao_conhece_o_transporte():
    """Domínio de um lado, transporte do outro — molde `helo.py`/`helo_embedding.py`."""
    fonte = inspect.getsource(telefonia)
    arvore = __import__("ast").parse(fonte)
    importados = set()
    for no in __import__("ast").walk(arvore):
        if isinstance(no, __import__("ast").Import):
            importados.update(a.name for a in no.names)
        elif isinstance(no, __import__("ast").ImportFrom):
            importados.add(no.module or "")

    assert not any("httpx" in m for m in importados), importados
    assert not any("api4com" in m for m in importados), importados
