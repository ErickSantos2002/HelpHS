"""
Abertura de chamado contra PostgreSQL de verdade.

Por que este arquivo existe
---------------------------
O `test_tickets.py` mocka a sessão inteira, e sessão mockada **não tem
autoflush**. Foi exatamente aí que passou um 500 em produção: abrir chamado
COM equipamento vinculado estourava `MissingGreenlet`, e os 51 testes de
chamado seguiam verdes.

A sequência que quebra só existe com ORM real:

1. `db.add(ticket)` — o chamado fica pendente
2. `await db.execute(select(Equipment)...)` — o autoflush INSERE o chamado, que
   passa a ser persistente
3. `ticket.equipments = [...]` — para calcular a diferença, o ORM tenta
   carregar a coleção ANTIGA do banco; esse IO acontece fora do greenlet e
   levanta `MissingGreenlet`

Nenhum passo é errado sozinho. É a ordem que quebra, e nenhum mock a reproduz.

Roda com PostgreSQL quando há um à mão e cai para **SQLite em memória** quando
não há. Não é preguiça: o `MissingGreenlet` é do ORM, não do dialeto, e
reproduz igual nos dois — verificado. Um teste que só roda no CI não protege
quem está escrevendo o código, e foi justamente na máquina de quem escreve que
este bug passou.

Sintoma no navegador, para quem for procurar de novo: **erro de CORS**. A
resposta 500 sai sem o header porque o handler de erro fica fora do middleware
de CORS, e o console culpa o CORS por um problema que é de banco.
"""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Equipment,
    Product,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.routers.tickets import _set_ticket_equipments
from tests.test_dashboard_postgres import _sobe_postgres

_AGORA = datetime.now(UTC)


# O subconjunto que este arquivo precisa. Nomear as tabelas é o que permite o
# SQLite: o `create_all` completo esbarra na coluna ARRAY de `kb_articles`.
_TABELAS = ("users", "products", "equipments", "tickets", "ticket_equipments")


@pytest.fixture(scope="module")
def url_do_banco():
    import asyncio
    import shutil

    from app.models.models import Base

    url, recurso = _sobe_postgres()
    if url is None:
        # SQLite em arquivo, não `:memory:` — cada conexão do pool abriria um
        # banco vazio próprio na memória, e a fixture da sessão abre a sua.
        import tempfile

        pasta_sqlite = tempfile.mkdtemp(prefix="helphs-tickets-")
        url = f"sqlite+aiosqlite:///{pasta_sqlite}/t.db"
        recurso = None

    tabelas = [Base.metadata.tables[n] for n in _TABELAS]

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=tabelas)
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


async def _cliente_com_aparelho(db) -> tuple[User, Equipment]:
    cliente = User(
        id=uuid.uuid4(),
        name="Suelen Fernandes",
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        password="x",
        role=UserRole.client,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        ai_enabled=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    produto = Product(id=uuid.uuid4(), name="Phoebus")
    db.add_all([cliente, produto])
    await db.flush()

    aparelho = Equipment(
        id=uuid.uuid4(),
        product_id=produto.id,
        owner_id=cliente.id,
        name="Phoebus da recepção",
        serial_number="WATFR01-73041",
        is_active=True,
    )
    db.add(aparelho)
    await db.flush()
    return cliente, aparelho


def _chamado_novo(cliente: User) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-2026-{uuid.uuid4().int % 10000:04d}",
        title="Equipamento com falha",
        description="O bafômetro não liga",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.open,
        creator_id=cliente.id,
        ai_enabled=True,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        auto_closed=False,
        reopen_count=0,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


@pytest.mark.asyncio
async def test_vincular_equipamento_a_chamado_novo_nao_estoura(db):
    """
    O 500 que chegou ao cliente: `MissingGreenlet` ao abrir chamado COM aparelho.

    Reproduz a ordem exata do `create_ticket` — add, SELECT (que autoflusha) e
    só então a atribuição da coleção.
    """
    cliente, aparelho = await _cliente_com_aparelho(db)
    ticket = _chamado_novo(cliente)
    db.add(ticket)

    await _set_ticket_equipments(db, ticket, [aparelho.id], cliente)

    assert [e.id for e in ticket.equipments] == [aparelho.id]


@pytest.mark.asyncio
async def test_chamado_sem_equipamento_continua_funcionando(db):
    """
    O ramo que sempre funcionou, e é por isso que o bug demorou a aparecer:
    sem equipamento a atribuição acontece antes de qualquer SELECT.
    """
    cliente, _ = await _cliente_com_aparelho(db)
    ticket = _chamado_novo(cliente)
    db.add(ticket)

    await _set_ticket_equipments(db, ticket, [], cliente)

    assert list(ticket.equipments) == []


@pytest.mark.asyncio
async def test_a_saudacao_da_helo_le_a_serie_sem_lazy_load(db, monkeypatch):
    """
    O passo seguinte no `create_ticket`, e o próximo candidato a estourar.

    `abre_triagem` recebe `list(ticket.equipments)`. Se a coleção não estivesse
    carregada em memória neste ponto, seria outro `MissingGreenlet` — três
    linhas depois do que acabou de ser corrigido.
    """
    from unittest.mock import MagicMock

    from app.services import helo

    cliente, aparelho = await _cliente_com_aparelho(db)
    ticket = _chamado_novo(cliente)
    db.add(ticket)
    await _set_ticket_equipments(db, ticket, [aparelho.id], cliente)

    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))
    falou = await helo.abre_triagem(db, ticket, cliente, list(ticket.equipments))

    assert falou is True
    assert ticket.status is TicketStatus.in_progress
