"""
Geração do número de protocolo (`app/utils/protocol.py`).

Banco de verdade, não mock: o que se prova aqui é a **ordenação feita pelo
banco**, e um mock que devolve o que o teste mandar não prova ordenação
nenhuma. SQLite em memória basta — comparação de texto é comparação de texto
nos dois bancos, e é justamente ela o defeito.

A tabela `tickets` compila no SQLite (ao contrário de `kb_articles`, que tem
uma coluna ARRAY), então dá para criar só ela.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.models import Base, Ticket, TicketCategory, TicketPriority, TicketStatus
from app.utils.protocol import generate_protocol

_ANO = datetime.now(UTC).year
_CRIADOR = uuid.uuid4()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Base.metadata.tables["tickets"]])

    async with async_sessionmaker(engine, expire_on_commit=False)() as sessao:
        yield sessao

    await engine.dispose()


async def _grava(sessao, protocolo: str) -> None:
    agora = datetime.now(UTC)
    sessao.add(
        Ticket(
            id=uuid.uuid4(),
            protocol=protocolo,
            title="Chamado de teste",
            description="corpo",
            priority=TicketPriority.medium,
            category=TicketCategory.general,
            status=TicketStatus.open,
            creator_id=_CRIADOR,
            sla_response_breach=False,
            sla_resolve_breach=False,
            sla_total_paused_ms=0,
            auto_closed=False,
            reopen_count=0,
            created_at=agora,
            updated_at=agora,
        )
    )
    await sessao.commit()


@pytest.mark.asyncio
async def test_primeiro_protocolo_do_ano(db):
    assert await generate_protocol(db) == f"HS-{_ANO}-0001"


@pytest.mark.asyncio
async def test_sequencia_normal_avanca(db):
    await _grava(db, f"HS-{_ANO}-0007")
    assert await generate_protocol(db) == f"HS-{_ANO}-0008"


@pytest.mark.asyncio
async def test_a_virada_do_milesimo_nao_regride(db):
    """A fronteira onde o texto e o número passam a discordar."""
    await _grava(db, f"HS-{_ANO}-0999")
    assert await generate_protocol(db) == f"HS-{_ANO}-1000"


@pytest.mark.asyncio
async def test_passa_do_decimo_milesimo_chamado(db):
    """
    O defeito: a consulta ordena `protocol` como TEXTO, e a sequência tem 4
    dígitos. `'HS-2026-9999' > 'HS-2026-10000'` é verdade em texto, então a
    partir do 10.000º o máximo volta a ser 9999 para sempre — o gerador propõe
    10000 de novo, as cinco tentativas colidem no índice único e **nenhum
    chamado novo pode ser aberto**.
    """
    await _grava(db, f"HS-{_ANO}-9999")
    await _grava(db, f"HS-{_ANO}-10000")

    assert await generate_protocol(db) == f"HS-{_ANO}-10001"


@pytest.mark.asyncio
async def test_continua_avancando_muito_depois_da_virada(db):
    """Não é uma fronteira só: a de 99.999 para 100.000 é a mesma classe."""
    await _grava(db, f"HS-{_ANO}-99999")
    await _grava(db, f"HS-{_ANO}-100000")

    assert await generate_protocol(db) == f"HS-{_ANO}-100001"


@pytest.mark.asyncio
async def test_protocolo_de_outro_ano_nao_interfere(db):
    """O filtro por ano precisa continuar valendo depois da mudança de ordem."""
    await _grava(db, f"HS-{_ANO - 1}-9999")
    assert await generate_protocol(db) == f"HS-{_ANO}-0001"
