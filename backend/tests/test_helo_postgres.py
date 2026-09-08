"""
A guarda de silêncio da Helô, executada contra PostgreSQL de verdade.

Por que este arquivo existe
---------------------------
`_humano_ja_esta_na_conversa` decide se a Helô fala olhando uma consulta com
três condições no `WHERE` — o chamado, a junção com o autor e o papel dele. Os
testes de `test_helo.py` usam sessão mockada, e mock não valida `WHERE`: o
mock responde ao `EXISTS` com um valor combinado de antemão, sem olhar quais
linhas a consulta casaria.

Isso foi medido, não suposto. Removendo o filtro por papel da consulta, os 39
testes de `test_helo.py` continuavam verdes — e a Helô, no ar, ficaria muda
para sempre: sem o filtro o `EXISTS` casa a mensagem do PRÓPRIO cliente, que
está sempre lá quando ela vai responder. O defeito que este arquivo pega é o
oposto do que motivou a correção, e igualmente invisível.

Como o banco aparece
--------------------
`TEST_POSTGRES_URL` quando existe (é o que o CI passa), senão um Postgres
efêmero via `pgserver`. Sem nenhum dos dois, os testes são pulados em vez de
falhar — mesma regra do `test_dashboard_postgres.py`.
"""

import asyncio
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    ChatMessage,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services import helo
from app.services.helo import _humano_ja_esta_na_conversa, responde_triagem

_AGORA = datetime.now(UTC)


def _sobe_postgres() -> tuple[str, object] | tuple[None, None]:
    """Devolve (url, recurso_para_encerrar). Recurso é None quando veio do CI."""
    do_ambiente = os.environ.get("TEST_POSTGRES_URL")
    if do_ambiente:
        return do_ambiente.replace("postgresql://", "postgresql+asyncpg://"), None

    try:
        import pgserver
    except ImportError:
        return None, None

    pasta = tempfile.mkdtemp(prefix="helphs-testes-pg-helo-")
    servidor = pgserver.get_server(pasta, cleanup_mode=None)
    servidor.psql("CREATE DATABASE helo_testes;")
    url = servidor.get_uri(database="helo_testes")
    return url.replace("postgresql://", "postgresql+asyncpg://"), (servidor, pasta)


@pytest.fixture(scope="module")
def url_do_banco():
    """
    SÍNCRONA de propósito, pelo mesmo motivo do `test_dashboard_postgres.py`:
    o pytest-asyncio dá um laço de evento por teste, e a conexão criada num
    laço de módulo morre no primeiro uso.
    """
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
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


@pytest.fixture
def helo_ligada(monkeypatch):
    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))


# ── Dados sintéticos ──────────────────────────────────────────


def _usuario(papel: UserRole, nome: str) -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        password="x",
        role=papel,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _chamado(criador: User, responsavel: User | None = None) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-TEST-{uuid.uuid4().hex[:10]}",
        title="Chamado sintético",
        description="corpo",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.in_progress,
        creator_id=criador.id,
        assignee_id=responsavel.id if responsavel else None,
        ai_enabled=True,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        auto_closed=False,
        reopen_count=0,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _mensagem(chamado: Ticket, autor: User | None, texto: str, is_ai: bool = False) -> ChatMessage:
    return ChatMessage(
        id=uuid.uuid4(),
        ticket_id=chamado.id,
        sender_id=autor.id if autor else None,
        content=texto,
        is_system=False,
        is_ai=is_ai,
        created_at=_AGORA,
    )


async def _cenario(db, *, responsavel=None, autores_das_falas=()):
    """Monta cliente, chamado e as mensagens pedidas, já gravados."""
    cliente = _usuario(UserRole.client, "Suelen")
    db.add(cliente)
    if responsavel is not None:
        db.add(responsavel)

    chamado = _chamado(cliente, responsavel)
    db.add(chamado)
    await db.flush()

    # A saudação dela é sempre a primeira mensagem do chamado — é o que faz a
    # contagem de falas valer 1 quando o cliente responde.
    db.add(_mensagem(chamado, None, "Olá! Sou a Helô.", is_ai=True))
    for autor, texto in autores_das_falas:
        db.add(_mensagem(chamado, autor, texto))
    await db.flush()

    return cliente, chamado


# ── Testes ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mensagem_do_tecnico_conta_como_humano_na_conversa(db):
    """O caso da correção: técnico respondeu sem ter assumido o chamado."""
    tecnico = _usuario(UserRole.technician, "Erick")
    db.add(tecnico)
    _, chamado = await _cenario(db, autores_das_falas=[(tecnico, "Qual o número de série?")])

    assert await _humano_ja_esta_na_conversa(db, chamado) is True


@pytest.mark.asyncio
async def test_mensagem_do_proprio_cliente_nao_conta(db):
    """
    A consulta precisa distinguir QUEM falou, e não apenas que alguém falou.

    Sem o filtro por papel o `EXISTS` casaria esta mensagem — que está sempre
    presente, porque é justamente a resposta que aciona a Helô. Ela ficaria
    muda em todo chamado, e nenhum teste de mock perceberia.
    """
    cliente, chamado = await _cenario(db)
    db.add(_mensagem(chamado, cliente, "O aparelho não liga desde ontem"))
    await db.flush()

    assert await _humano_ja_esta_na_conversa(db, chamado) is False


@pytest.mark.asyncio
async def test_a_fala_da_propria_helo_nao_conta(db):
    """Remetente nulo não casa a junção com o autor — ela não é um humano."""
    _, chamado = await _cenario(db)

    assert await _humano_ja_esta_na_conversa(db, chamado) is False


@pytest.mark.asyncio
async def test_mensagem_de_admin_tambem_conta(db):
    """A guarda é sobre a equipe, não sobre o cargo de técnico."""
    admin = _usuario(UserRole.admin, "Rickelme")
    db.add(admin)
    _, chamado = await _cenario(db, autores_das_falas=[(admin, "Já estou vendo aqui")])

    assert await _humano_ja_esta_na_conversa(db, chamado) is True


@pytest.mark.asyncio
async def test_tecnico_desativado_depois_continua_calando(db):
    """
    A assimetria com `_avisa_equipe_da_helo` é de propósito.

    Lá o filtro é `status == active`, porque não adianta chamar quem saiu.
    Aqui não há filtro de status: desativar a conta não desfaz a mensagem que
    a pessoa escreveu. A conversa teve um humano, e a Helô não volta a falar
    como se não tivesse tido.
    """
    tecnico = _usuario(UserRole.technician, "Erick")
    tecnico.status = UserStatus.inactive
    db.add(tecnico)
    _, chamado = await _cenario(db, autores_das_falas=[(tecnico, "Vou verificar aqui")])

    assert await _humano_ja_esta_na_conversa(db, chamado) is True


@pytest.mark.asyncio
async def test_mensagem_de_staff_em_outro_chamado_nao_cala_este(db):
    """O `EXISTS` é por chamado — senão a primeira resposta da equipe no dia calaria todos."""
    tecnico = _usuario(UserRole.technician, "Erick")
    db.add(tecnico)
    _, alheio = await _cenario(db, autores_das_falas=[(tecnico, "respondendo outro chamado")])
    _, meu = await _cenario(db)

    assert await _humano_ja_esta_na_conversa(db, alheio) is True
    assert await _humano_ja_esta_na_conversa(db, meu) is False


@pytest.mark.asyncio
async def test_responsavel_cala_mesmo_sem_ninguem_ter_falado(db):
    """Assumir o chamado não grava mensagem — só o campo denuncia o dono."""
    tecnico = _usuario(UserRole.technician, "Erick")
    _, chamado = await _cenario(db, responsavel=tecnico)

    assert await _humano_ja_esta_na_conversa(db, chamado) is True


@pytest.mark.asyncio
async def test_depois_do_tecnico_ela_nao_encerra_a_triagem(db, helo_ligada):
    """
    O cenário inteiro, ponta a ponta, contra o banco.

    Saudação dela (1ª fala), técnico escreve, cliente responde. Pela contagem
    ela ainda teria uma fala de crédito; pela guarda, não fala.
    """
    tecnico = _usuario(UserRole.technician, "Erick")
    db.add(tecnico)
    cliente, chamado = await _cenario(db, autores_das_falas=[(tecnico, "Consegue tirar uma foto?")])

    fala = await responde_triagem(db, chamado, cliente, "Segue a foto do visor")

    assert fala is None


@pytest.mark.asyncio
async def test_sem_a_equipe_ela_encerra_normalmente(db, helo_ligada):
    """A guarda oposta, contra o banco: sem humano na conversa ela ainda fala."""
    cliente, chamado = await _cenario(db)

    fala = await responde_triagem(db, chamado, cliente, "O aparelho não liga desde ontem")

    assert fala is not None
    assert "Registrei tudo aqui" in fala.mensagem.content
