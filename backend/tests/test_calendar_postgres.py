"""
A janela do mês da agenda, contra PostgreSQL de verdade.

Existe separado do `test_calendar.py` porque lá o banco é mockado: nenhum caso
de lá consegue dizer QUAIS eventos a consulta devolve, só que a rota respondeu
200. E a pergunta que esta mudança levanta é exatamente "quais" — um evento às
22:00 do dia 31 de janeiro pertence a janeiro ou a fevereiro?

O banco aparece por `TEST_POSTGRES_URL` (o CI) ou por um `pgserver` efêmero.
Sem nenhum dos dois, os casos são pulados em vez de falharem.
"""

import asyncio
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Base, CalendarEvent, CalendarEventType
from app.routers.calendar import list_events

RECIFE = ZoneInfo("America/Recife")


def _sobe_postgres() -> tuple[str, object] | tuple[None, None]:
    """Devolve (url, recurso_para_encerrar). Recurso é None quando veio do CI."""
    do_ambiente = os.environ.get("TEST_POSTGRES_URL")
    if do_ambiente:
        return do_ambiente.replace("postgresql://", "postgresql+asyncpg://"), None

    try:
        import pgserver
    except ImportError:
        return None, None

    pasta = tempfile.mkdtemp(prefix="helphs-testes-agenda-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    servidor.psql("CREATE DATABASE agenda_testes;")
    url = servidor.get_uri(database="agenda_testes")
    return url.replace("postgresql://", "postgresql+asyncpg://"), (servidor, pasta)


@pytest.fixture(scope="module")
def url_do_banco():
    """Síncrona de propósito — ver a nota longa em `test_dashboard_postgres.py`."""
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            # A extensão vem antes do create_all: `helo_chunks.embedding` é
            # `vector(1024)`, e sem ela o create_all morre por causa de uma
            # tabela que este módulo nem usa.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    asyncio.run(_monta())

    yield url

    if recurso is not None:
        servidor, pasta = recurso
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def db(url_do_banco):
    """Sessão numa transação revertida no fim — isolamento por teste."""
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        async with async_sessionmaker(bind=conn, expire_on_commit=False)() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


async def _grava(sessao, titulo: str, inicio: datetime, fim: datetime, dia_inteiro=False):
    evento = CalendarEvent(
        id=uuid.uuid4(),
        title=titulo,
        description=None,
        event_type=CalendarEventType.meeting,
        color="#6366f1",
        start_date=inicio,
        end_date=fim,
        all_day=dia_inteiro,
        created_by=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    sessao.add(evento)
    await sessao.flush()
    return evento


async def _titulos(sessao, ano: int, mes: int, fuso: str | None = "America/Recife"):
    resposta = await list_events(db=sessao, _actor=None, year=ano, month=mes, timezone=fuso)
    return {item.title for item in resposta.items}


# ── O caso que motivou a mudança ──────────────────────────────


@pytest.mark.asyncio
async def test_evento_das_22h_de_31_01_aparece_em_janeiro(db):
    """22:00 do dia 31 em Recife é 01:00Z do dia 1º de fevereiro.

    Com a janela calculada em UTC — como era antes — janeiro terminava às
    00:00Z do dia 1º, e este evento ficava de fora da consulta: a pessoa criava
    em janeiro e ele aparecia em fevereiro.
    """
    await _grava(
        db,
        "reunião da virada",
        datetime(2026, 1, 31, 22, tzinfo=RECIFE),
        datetime(2026, 1, 31, 23, 30, tzinfo=RECIFE),
    )

    assert "reunião da virada" in await _titulos(db, 2026, 1)


@pytest.mark.asyncio
async def test_e_nao_aparece_tambem_em_fevereiro(db):
    """Ele pertence a um mês só. Aparecer nos dois seria outra forma de errado."""
    await _grava(
        db,
        "reunião da virada",
        datetime(2026, 1, 31, 22, tzinfo=RECIFE),
        datetime(2026, 1, 31, 23, 30, tzinfo=RECIFE),
    )

    assert "reunião da virada" not in await _titulos(db, 2026, 2)


@pytest.mark.asyncio
async def test_em_utc_o_mesmo_evento_some_de_janeiro(db):
    """A prova de que o fuso é o que decide, e não outra coisa do caminho.

    Sem este caso, os dois acima passariam com a correção desfeita se alguma
    outra mudança tivesse coincidentemente arrumado o resultado. Aqui a MESMA
    linha, consultada em UTC, cai fora — e é exatamente o comportamento antigo.
    """
    await _grava(
        db,
        "reunião da virada",
        datetime(2026, 1, 31, 22, tzinfo=RECIFE),
        datetime(2026, 1, 31, 23, 30, tzinfo=RECIFE),
    )

    assert "reunião da virada" not in await _titulos(db, 2026, 1, fuso="UTC")
    assert "reunião da virada" in await _titulos(db, 2026, 2, fuso="UTC")


# ── A virada do dia ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_evento_que_atravessa_a_meia_noite_aparece_nos_dois_meses(db):
    """De 22:00 do dia 31/01 às 02:00 do dia 01/02: pertence aos dois.

    A consulta é de SOBREPOSIÇÃO, não de contenção. Um evento que atravessa a
    virada do mês tem de sair nas duas telas — quem abre fevereiro precisa ver
    que a madrugada já estava ocupada.
    """
    await _grava(
        db,
        "plantão da virada",
        datetime(2026, 1, 31, 22, tzinfo=RECIFE),
        datetime(2026, 2, 1, 2, tzinfo=RECIFE),
    )

    assert "plantão da virada" in await _titulos(db, 2026, 1)
    assert "plantão da virada" in await _titulos(db, 2026, 2)


@pytest.mark.asyncio
async def test_evento_de_madrugada_no_dia_1_nao_vaza_para_o_mes_anterior(db):
    """01:00 do dia 1º em Recife é 04:00Z — dentro de fevereiro nos dois fusos.

    Ele existe para prender a outra ponta da janela. Um erro de sinal no
    deslocamento faria o começo do mês escorregar para trás, e só um evento
    logo depois da meia-noite acusaria.
    """
    await _grava(
        db,
        "manutenção de madrugada",
        datetime(2026, 2, 1, 1, tzinfo=RECIFE),
        datetime(2026, 2, 1, 3, tzinfo=RECIFE),
    )

    assert "manutenção de madrugada" in await _titulos(db, 2026, 2)
    assert "manutenção de madrugada" not in await _titulos(db, 2026, 1)


# ── Os eventos que já existiam ────────────────────────────────


@pytest.mark.asyncio
async def test_evento_antigo_de_dia_inteiro_continua_no_mes_dele(db):
    """A forma que TODA linha em produção tem hoje: `00:00:00Z`–`23:59:59Z`.

    Este é o caso que autoriza o "sem recálculo". A janela passou a ser a de
    Recife, deslocada três horas — e mesmo assim o evento antigo não se move de
    mês, porque ele ocupa vinte e quatro horas e um deslocamento de três não o
    tira de lugar nenhum. Se um dia alguém propuser ancorar dia inteiro no fuso
    de quem olha, é este caso que vai reprovar.
    """
    await _grava(
        db,
        "treinamento antigo",
        datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 23, 59, 59, tzinfo=UTC),
        dia_inteiro=True,
    )

    assert "treinamento antigo" in await _titulos(db, 2026, 1)
    assert "treinamento antigo" not in await _titulos(db, 2025, 12)


@pytest.mark.asyncio
async def test_dia_inteiro_no_ultimo_dia_do_mes_nao_vaza_para_o_seguinte(db):
    await _grava(
        db,
        "treinamento do dia 31",
        datetime(2026, 1, 31, 0, 0, 0, tzinfo=UTC),
        datetime(2026, 1, 31, 23, 59, 59, 999999, tzinfo=UTC),
        dia_inteiro=True,
    )

    assert "treinamento do dia 31" in await _titulos(db, 2026, 1)
    assert "treinamento do dia 31" not in await _titulos(db, 2026, 2)


# ── A virada do ano ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_dezembro_vira_o_ano_com_o_fuso_certo(db):
    """23:00 do dia 31/12 em Recife é 02:00Z do dia 1º de janeiro seguinte."""
    await _grava(
        db,
        "réveillon de plantão",
        datetime(2026, 12, 31, 23, tzinfo=RECIFE),
        datetime(2026, 12, 31, 23, 59, tzinfo=RECIFE),
    )

    assert "réveillon de plantão" in await _titulos(db, 2026, 12)
    assert "réveillon de plantão" not in await _titulos(db, 2027, 1)
