"""
Geração do número de protocolo (`app/utils/protocol.py`).

Banco de verdade, não mock: o que se prova aqui é o **contador persistido** e a
**ordenação feita pelo banco** no piso, e um mock que devolve o que o teste
mandar não prova nenhum dos dois. SQLite em memória basta para as regras de
número — `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` existe nos dois
bancos. A concorrência, que o SQLite não tem como reproduzir, está em
`test_protocolo_contador_postgres.py`.

As tabelas `tickets` e `ticket_protocol_counters` compilam no SQLite (ao
contrário de `kb_articles`, que tem uma coluna ARRAY), então dá para criar só
elas.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.models import (
    Base,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketProtocolCounter,
    TicketStatus,
)
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
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                Base.metadata.tables["tickets"],
                Base.metadata.tables["ticket_protocol_counters"],
            ],
        )

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


async def _emite(sessao) -> str:
    """O caminho do `create_ticket`: gera, grava o chamado e commita junto."""
    protocolo = await generate_protocol(sessao)
    await _grava(sessao, protocolo)
    return protocolo


async def _contador(sessao, ano: int) -> int | None:
    return (
        await sessao.execute(
            select(TicketProtocolCounter.last_number).where(TicketProtocolCounter.year == ano)
        )
    ).scalar_one_or_none()


# ── Sequência e formato ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_primeiro_protocolo_do_ano(db):
    assert await generate_protocol(db) == f"HS-{_ANO}-0001"


@pytest.mark.asyncio
async def test_emissoes_seguidas_avancam_de_um_em_um(db):
    assert [await _emite(db) for _ in range(3)] == [
        f"HS-{_ANO}-0001",
        f"HS-{_ANO}-0002",
        f"HS-{_ANO}-0003",
    ]


@pytest.mark.asyncio
async def test_o_numero_emitido_fica_gravado_no_contador(db):
    await _emite(db)
    await _emite(db)
    assert await _contador(db, _ANO) == 2


@pytest.mark.asyncio
async def test_formato_hs_ano_quatro_digitos(db):
    protocolo = await generate_protocol(db)
    prefixo, ano, numero = protocolo.split("-")
    assert (prefixo, ano, numero) == ("HS", str(_ANO), "0001")


# ── O defeito que motivou o contador ──────────────────────────────


@pytest.mark.asyncio
async def test_base_com_0001_a_0026_emite_0027(db):
    """O estado de produção em 07/10/2026: 26 protocolos já emitidos."""
    for n in range(1, 27):
        await _grava(db, f"HS-{_ANO}-{n:04d}")

    assert await generate_protocol(db) == f"HS-{_ANO}-0027"


@pytest.mark.asyncio
async def test_apagar_todos_os_chamados_nao_reinicia_a_numeracao(db):
    """
    O defeito. Com `max()+1` sobre `tickets`, zerar a tabela fazia o próximo
    chamado nascer `0001` — reutilizando um protocolo que já tinha saído por
    e-mail e que segue no texto de notificações de outras pessoas.
    """
    for n in range(1, 27):
        await _grava(db, f"HS-{_ANO}-{n:04d}")
    assert await _emite(db) == f"HS-{_ANO}-0027"

    await db.execute(delete(Ticket))
    await db.commit()

    assert await _emite(db) == f"HS-{_ANO}-0028"
    assert await _emite(db) == f"HS-{_ANO}-0029"


@pytest.mark.asyncio
async def test_contador_semeado_pela_migration_vale_sem_chamado_nenhum(db):
    """O cenário do piloto: migration semeou 26 e depois a tabela foi zerada."""
    db.add(TicketProtocolCounter(year=_ANO, last_number=26))
    await db.commit()

    assert await generate_protocol(db) == f"HS-{_ANO}-0027"


@pytest.mark.asyncio
async def test_apagar_o_ultimo_chamado_nao_devolve_o_numero_dele(db):
    """Não é só zerar: apagar o mais recente também reusava o número dele."""
    await _emite(db)
    await _emite(db)
    await db.execute(delete(Ticket).where(Ticket.protocol == f"HS-{_ANO}-0002"))
    await db.commit()

    assert await _emite(db) == f"HS-{_ANO}-0003"


# ── O piso: chamado gravado por fora do gerador ────────────────────


@pytest.mark.asyncio
async def test_chamado_gravado_por_fora_do_gerador_eleva_o_contador(db):
    """
    Durante o deploy, o contêiner antigo (ainda com `max()+1`) pode abrir
    chamados DEPOIS da migration semear o contador. Seed e script avulso também
    gravam protocolo sem passar pelo contador. O piso impede que o contador
    proponha um número que já existe.
    """
    db.add(TicketProtocolCounter(year=_ANO, last_number=26))
    await db.commit()
    await _grava(db, f"HS-{_ANO}-0027")
    await _grava(db, f"HS-{_ANO}-0028")

    assert await generate_protocol(db) == f"HS-{_ANO}-0029"


@pytest.mark.asyncio
async def test_piso_baixo_nunca_faz_o_contador_regredir(db):
    db.add(TicketProtocolCounter(year=_ANO, last_number=40))
    await db.commit()
    await _grava(db, f"HS-{_ANO}-0003")

    assert await generate_protocol(db) == f"HS-{_ANO}-0041"


@pytest.mark.asyncio
async def test_a_virada_do_milesimo_nao_regride(db):
    """A fronteira onde o texto e o número passam a discordar."""
    await _grava(db, f"HS-{_ANO}-0999")
    assert await generate_protocol(db) == f"HS-{_ANO}-1000"


@pytest.mark.asyncio
async def test_passa_do_decimo_milesimo_chamado(db):
    """
    `'HS-2026-9999' > 'HS-2026-10000'` é verdade em texto. O piso continua
    ordenando por comprimento antes do texto, senão um chamado gravado por fora
    acima de 9999 não seria visto.
    """
    await _grava(db, f"HS-{_ANO}-9999")
    await _grava(db, f"HS-{_ANO}-10000")

    assert await generate_protocol(db) == f"HS-{_ANO}-10001"


@pytest.mark.asyncio
async def test_continua_avancando_muito_depois_da_virada(db):
    await _grava(db, f"HS-{_ANO}-99999")
    await _grava(db, f"HS-{_ANO}-100000")

    assert await generate_protocol(db) == f"HS-{_ANO}-100001"


# ── Ano ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_protocolo_de_outro_ano_nao_interfere(db):
    await _grava(db, f"HS-{_ANO - 1}-9999")
    assert await generate_protocol(db) == f"HS-{_ANO}-0001"


@pytest.mark.asyncio
async def test_ano_novo_comeca_em_0001_com_contador_proprio(db):
    """A semântica anual continua: cada ano tem a sua linha, e começa do 1."""
    db.add(TicketProtocolCounter(year=2026, last_number=26))
    await db.commit()

    virada = datetime(2027, 1, 1, 0, 0, 1, tzinfo=UTC)
    assert await generate_protocol(db, agora=virada) == "HS-2027-0001"
    assert await _contador(db, 2026) == 26
    assert await _contador(db, 2027) == 1


@pytest.mark.asyncio
async def test_o_ano_e_o_do_relogio_em_utc(db):
    """Regra de antes, preservada: 31/12 às 22:00 em Brasília já é janeiro em UTC."""
    assert (
        await generate_protocol(db, agora=datetime(2026, 12, 31, 23, 59, tzinfo=UTC))
        == "HS-2026-0001"
    )
    assert (
        await generate_protocol(db, agora=datetime(2027, 1, 1, 1, 0, tzinfo=UTC)) == "HS-2027-0001"
    )


# ── Transação ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alocacao_revertida_nao_conta_como_emitida(db):
    """
    O número vive na MESMA transação do chamado. Se ela reverte, o chamado não
    existe e o número nunca saiu — nem por e-mail, que também é gravado na
    outbox dentro dela. Reemiti-lo não duplica nada.
    """
    await _emite(db)
    perdido = await generate_protocol(db)
    await db.rollback()

    assert await _contador(db, _ANO) == 1
    assert await _emite(db) == perdido

    protocolos = (await db.execute(select(Ticket.protocol))).scalars().all()
    assert len(protocolos) == len(set(protocolos))


@pytest.mark.asyncio
async def test_gerar_nao_altera_chamado_existente(db):
    for n in (1, 2, 5):
        await _grava(db, f"HS-{_ANO}-{n:04d}")
    antes = (await db.execute(text("SELECT id, protocol FROM tickets ORDER BY protocol"))).all()

    await _emite(db)

    depois = (
        await db.execute(
            text("SELECT id, protocol FROM tickets WHERE protocol <> :novo ORDER BY protocol"),
            {"novo": f"HS-{_ANO}-0006"},
        )
    ).all()
    assert depois == antes
