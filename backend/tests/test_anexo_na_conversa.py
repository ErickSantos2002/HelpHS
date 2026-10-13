"""
Anexo enviado vira acontecimento do chamado — contra banco de verdade.

O que se prova aqui:

- cada arquivo aceito grava UM evento `attachment_added` no histórico, na mesma
  transação do anexo, com quem enviou como autor;
- envio recusado no meio do lote não deixa evento (nem anexo) para trás;
- ler de novo não duplica nada — o evento nasce na escrita, nunca na leitura;
- o nome e o papel de quem enviou saem do cadastro VIVO, na hora da leitura.
  Anonimizar a conta faz o nome antigo sumir do anexo e do evento, porque o
  texto gravado no evento não carrega nome nenhum;
- cliente de outro chamado não alcança nem os anexos nem os eventos.

Por que banco de verdade e não a sessão mockada de `test_attachments.py`: as
duas primeiras afirmações são sobre TRANSAÇÃO. Um mock aceita `db.add` de
qualquer coisa e não desfaz nada quando o endpoint levanta — o teste de
"falha não grava evento" passaria com o evento gravado.

Roda em PostgreSQL quando há um (pgserver ou `TEST_POSTGRES_URL`) e em SQLite
quando não há, como `test_tickets_postgres.py`.
"""

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import (
    Attachment,
    Ticket,
    TicketCategory,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from tests.test_dashboard_postgres import _sobe_postgres

_AGORA = datetime.now(UTC)
_EVENTO = "attachment_added"

_TABELAS_NO_SQLITE = (
    "users",
    "tickets",
    "attachments",
    "ticket_history",
    "audit_logs",
)


@pytest.fixture(scope="module")
def url_do_banco():
    import asyncio
    import shutil
    import tempfile

    from app.models.models import Base

    url, recurso = _sobe_postgres()
    if url is None:
        pasta_sqlite = tempfile.mkdtemp(prefix="helphs-anexos-")
        url = f"sqlite+aiosqlite:///{pasta_sqlite}/t.db"
        recurso = None

    no_sqlite = url.startswith("sqlite")
    tabelas = [Base.metadata.tables[n] for n in _TABELAS_NO_SQLITE] if no_sqlite else None

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            if not no_sqlite:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
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
async def conn(url_do_banco):
    """Uma transação por teste, revertida no fim."""
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as c:
        transacao = await c.begin()
        yield c
        await transacao.rollback()
    await motor.dispose()


@pytest_asyncio.fixture
async def db(conn):
    """Sessão de montagem e de conferência — separada da sessão da requisição."""
    async with async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )() as sessao:
        yield sessao


@pytest.fixture
def api(conn):
    """
    Cliente HTTP cuja requisição abre a PRÓPRIA sessão, como o `get_db` real.

    Cada requisição ganha um savepoint: o `commit` do endpoint o libera, e uma
    exceção fecha a sessão sem commit — o savepoint volta, exatamente como o
    `async with AsyncSessionLocal()` de produção descarta o que ficou pendente.
    """

    async def _get_db():
        async with async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )() as sessao:
            yield sessao

    app.dependency_overrides[get_db] = _get_db
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


def _como(usuario: User) -> None:
    async def _u():
        return usuario

    app.dependency_overrides[get_current_user] = _u


@pytest.fixture(autouse=True)
def _servicos_de_fora():
    """MinIO e ClamAV não existem aqui; o que se testa é o banco."""
    with (
        patch("app.services.storage.upload_file", new=AsyncMock(return_value=None)),
        patch(
            "app.services.antivirus.scan_bytes",
            new=AsyncMock(return_value=(True, "clean")),
        ),
    ):
        yield


async def _pessoa(db, role: UserRole, nome: str) -> User:
    u = User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:10]}@test.com",
        password="x",
        role=role,
        status=UserStatus.active,
        phone="+5581999999999",
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        ai_enabled=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    db.add(u)
    await db.flush()
    return u


async def _chamado(db, dono: User) -> Ticket:
    t = Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-2026-{uuid.uuid4().int % 100000:05d}",
        title="Bafômetro não liga",
        description="Não acende o visor",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.open,
        creator_id=dono.id,
        ai_enabled=True,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        auto_closed=False,
        reopen_count=0,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    db.add(t)
    await db.commit()
    return t


def _arquivo(nome: str = "laudo.pdf"):
    return ("files", (nome, io.BytesIO(b"%PDF-1.4 conteudo"), "application/pdf"))


async def _eventos(db, ticket_id) -> list[TicketHistory]:
    rows = await db.execute(
        select(TicketHistory)
        .where(TicketHistory.ticket_id == ticket_id, TicketHistory.field == _EVENTO)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _conta_anexos(db, ticket_id) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Attachment).where(Attachment.ticket_id == ticket_id)
        )
    ).scalar_one()


# ── Gravação ─────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("papel", "nome"),
    [
        (UserRole.client, "Suelen Fernandes"),
        (UserRole.technician, "Bruno Técnico"),
        (UserRole.admin, "Ana Administradora"),
    ],
)
async def test_cada_arquivo_aceito_grava_um_evento_com_o_autor_certo(db, api, papel, nome):
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    autor = dono if papel == UserRole.client else await _pessoa(db, papel, nome)
    if papel == UserRole.client:
        autor.name = nome
    ticket = await _chamado(db, dono)
    _como(autor)

    async with api as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/attachments",
            files=[_arquivo("a.pdf"), _arquivo("b.pdf")],
        )
    assert r.status_code == 201, r.text
    ids_enviados = {item["id"] for item in r.json()}

    eventos = await _eventos(db, ticket.id)
    assert len(eventos) == 2
    assert {e.user_id for e in eventos} == {autor.id}
    # O evento aponta para o anexo pelo id, e não guarda nome de pessoa nenhum.
    assert {e.new_value for e in eventos} == ids_enviados
    assert all(e.old_value is None and e.comment is None for e in eventos)


@pytest.mark.asyncio
async def test_lote_recusado_no_meio_nao_deixa_evento_nem_anexo(db, api):
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    _como(dono)

    async with api as c:
        r = await c.post(
            f"/api/v1/tickets/{ticket.id}/attachments",
            # O primeiro passa em tudo; o segundo cai na extensão. O primeiro
            # já tinha sido adicionado à sessão quando o segundo levantou.
            files=[_arquivo("bom.pdf"), _arquivo("ruim.exe")],
        )
    assert r.status_code == 422

    assert await _eventos(db, ticket.id) == []
    assert await _conta_anexos(db, ticket.id) == 0


@pytest.mark.asyncio
async def test_antivirus_recusa_e_nao_ha_evento(db, api):
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    _como(dono)

    with patch(
        "app.services.antivirus.scan_bytes",
        new=AsyncMock(return_value=(False, "Virus: EICAR-Test")),
    ):
        async with api as c:
            r = await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])
    assert r.status_code == 422
    assert await _eventos(db, ticket.id) == []


@pytest.mark.asyncio
async def test_ler_de_novo_nao_duplica_evento(db, api):
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    _como(dono)

    async with api as c:
        await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])
        primeira = (await c.get(f"/api/v1/tickets/{ticket.id}/history")).json()
        await c.get(f"/api/v1/tickets/{ticket.id}/attachments")
        segunda = (await c.get(f"/api/v1/tickets/{ticket.id}/history")).json()

    def _so_anexo(corpo):
        return [i["id"] for i in corpo["items"] if i["field"] == _EVENTO]

    assert len(_so_anexo(primeira)) == 1
    assert _so_anexo(primeira) == _so_anexo(segunda)
    assert len(await _eventos(db, ticket.id)) == 1


# ── Leitura: quem enviou ─────────────────────────────────────


@pytest.mark.asyncio
async def test_anexo_e_evento_dizem_nome_e_papel_de_quem_enviou(db, api):
    dono = await _pessoa(db, UserRole.client, "Suelen Fernandes")
    tecnico = await _pessoa(db, UserRole.technician, "Bruno Técnico")
    ticket = await _chamado(db, dono)

    async with api as c:
        _como(tecnico)
        await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])
        # Quem LÊ é o cliente: o nome do técnico tem de chegar a ele.
        _como(dono)
        anexos = (await c.get(f"/api/v1/tickets/{ticket.id}/attachments")).json()["items"]
        historico = (await c.get(f"/api/v1/tickets/{ticket.id}/history")).json()["items"]

    assert anexos[0]["uploaded_by_name"] == "Bruno Técnico"
    assert anexos[0]["uploaded_by_role"] == "technician"

    evento = next(i for i in historico if i["field"] == _EVENTO)
    assert evento["user_name"] == "Bruno Técnico"
    assert evento["user_role"] == "technician"
    assert evento["new_value"] == anexos[0]["id"]


@pytest.mark.asyncio
async def test_resposta_do_upload_ja_traz_o_autor(db, api):
    admin = await _pessoa(db, UserRole.admin, "Ana Administradora")
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    ticket = await _chamado(db, dono)
    _como(admin)

    async with api as c:
        r = await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])

    assert r.json()[0]["uploaded_by_name"] == "Ana Administradora"
    assert r.json()[0]["uploaded_by_role"] == "admin"


@pytest.mark.asyncio
async def test_conta_anonimizada_nao_traz_o_nome_antigo_de_volta(db, api):
    dono = await _pessoa(db, UserRole.client, "Suelen Fernandes")
    admin = await _pessoa(db, UserRole.admin, "Ana Administradora")
    ticket = await _chamado(db, dono)

    async with api as c:
        _como(dono)
        await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])
        _como(admin)
        r = await c.post(f"/api/v1/users/{dono.id}/anonymize")
        assert r.status_code == 200, r.text
        anexos = (await c.get(f"/api/v1/tickets/{ticket.id}/attachments")).text
        historico = (await c.get(f"/api/v1/tickets/{ticket.id}/history")).text

    assert "Suelen" not in anexos
    assert "Suelen" not in historico
    assert "Usuário Anonimizado" in anexos
    assert "Usuário Anonimizado" in historico


# ── Quem não pode ver ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cliente_de_outro_chamado_nao_alcanca_anexos_nem_eventos(db, api):
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    intruso = await _pessoa(db, UserRole.client, "Outro Cliente")
    ticket = await _chamado(db, dono)

    async with api as c:
        _como(dono)
        await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])
        _como(intruso)
        anexos = await c.get(f"/api/v1/tickets/{ticket.id}/attachments")
        historico = await c.get(f"/api/v1/tickets/{ticket.id}/history")
        envio = await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])

    assert anexos.status_code == 404
    assert historico.status_code == 404
    assert "Dona do Chamado" not in anexos.text + historico.text
    assert envio.status_code == 404
    assert len(await _eventos(db, ticket.id)) == 1


@pytest.mark.asyncio
async def test_upload_nao_mexe_em_sla_nem_em_status(db, api):
    """O evento é registro, não interação: a primeira resposta segue nula."""
    dono = await _pessoa(db, UserRole.client, "Dona do Chamado")
    tecnico = await _pessoa(db, UserRole.technician, "Bruno Técnico")
    ticket = await _chamado(db, dono)
    _como(tecnico)

    async with api as c:
        await c.post(f"/api/v1/tickets/{ticket.id}/attachments", files=[_arquivo()])

    fresco = (
        await db.execute(
            select(Ticket).where(Ticket.id == ticket.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert fresco.status == TicketStatus.open
    assert fresco.sla_first_response is None
    assert fresco.updated_at == ticket.updated_at
