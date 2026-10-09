"""
A audiência operacional — quem é "a equipe" — contra PostgreSQL de verdade.

Por que este arquivo NÃO é mock
-------------------------------
A garantia inteira desta função é uma cláusula `WHERE`. O projeto já pagou
essa lição uma vez: o cabeçalho de `test_helo_base_postgres.py` registra que,
removendo o filtro de papel de um `EXISTS`, os 39 testes mockados da Helô
continuavam verdes — porque o mock devolve o que foi combinado de antemão, sem
olhar o `WHERE`.

Aqui a classe de defeito é a mesma e o dano é direto: audiência larga manda
e-mail de chamado novo para cliente; audiência com o filtro de status
desligado manda para quem foi desativado ou anonimizado. Nenhum mock separa
esses casos, porque nenhum mock executa o `WHERE`.

As seis linhas que este arquivo planta cobrem o produto cartesiano que
importa: os dois papéis operacionais e o papel de cliente, cada um em ativo e
em não-ativo, mais o `anonymized` que a LGPD criou.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Base, User, UserRole, UserStatus
from app.services.notifications import audiencia_operacional
from tests.test_dashboard_postgres import _sobe_postgres


@pytest.fixture(scope="module")
def url_do_banco():
    """SÍNCRONA, pelo mesmo motivo do `test_dashboard_postgres`: o servidor sobe
    uma vez, num laço próprio, e cada teste abre a conexão no laço dele."""
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

    import asyncio

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        await motor.dispose()

    asyncio.run(_monta())
    yield url

    if recurso is not None:
        import shutil
        from contextlib import suppress

        servidor, pasta = recurso
        with suppress(Exception):
            servidor.cleanup()
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


def _pessoa(papel: UserRole, situacao: UserStatus, nome: str) -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:8]}@t.com",
        password="x",
        role=papel,
        status=situacao,
        # Cliente ATIVO precisa de telefone desde a Fase 1C
        # (ck_users_cliente_ativo_tem_telefone). O `create_all` monta o schema
        # pelo model, então o fixture nasce conforme a regra de domínio.
        phone="+5581999999999",
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
    )


async def _planta_todo_mundo(db) -> dict[str, User]:
    """As seis situações que decidem a audiência, numa só transação."""
    pessoas = {
        "tecnico_ativo": _pessoa(UserRole.technician, UserStatus.active, "Tecnico Ativo"),
        "admin_ativo": _pessoa(UserRole.admin, UserStatus.active, "Admin Ativo"),
        "cliente_ativo": _pessoa(UserRole.client, UserStatus.active, "Cliente Ativo"),
        "tecnico_inativo": _pessoa(UserRole.technician, UserStatus.inactive, "Tecnico Inativo"),
        "admin_inativo": _pessoa(UserRole.admin, UserStatus.inactive, "Admin Inativo"),
        "tecnico_anonimizado": _pessoa(
            UserRole.technician, UserStatus.anonymized, "Tecnico Anonimizado"
        ),
    }
    for p in pessoas.values():
        db.add(p)
    await db.flush()
    return pessoas


# ── Quem ENTRA ────────────────────────────────────────────────


async def test_tecnico_ativo_entra(db):
    pessoas = await _planta_todo_mundo(db)
    ids = {u.id for u in await audiencia_operacional(db)}
    assert pessoas["tecnico_ativo"].id in ids


async def test_admin_ativo_entra(db):
    pessoas = await _planta_todo_mundo(db)
    ids = {u.id for u in await audiencia_operacional(db)}
    assert pessoas["admin_ativo"].id in ids


# ── Quem NÃO entra ────────────────────────────────────────────


async def test_cliente_ativo_nao_entra(db):
    """O cliente não é operação. Sem isto, abrir chamado avisaria a base inteira
    de clientes — e entregaria a cada um o título do chamado dos outros."""
    pessoas = await _planta_todo_mundo(db)
    ids = {u.id for u in await audiencia_operacional(db)}
    assert pessoas["cliente_ativo"].id not in ids


async def test_tecnico_inativo_nao_entra(db):
    pessoas = await _planta_todo_mundo(db)
    ids = {u.id for u in await audiencia_operacional(db)}
    assert pessoas["tecnico_inativo"].id not in ids


async def test_admin_inativo_nao_entra(db):
    pessoas = await _planta_todo_mundo(db)
    ids = {u.id for u in await audiencia_operacional(db)}
    assert pessoas["admin_inativo"].id not in ids


async def test_anonimizado_nao_entra(db):
    """`anonymized` é conta apagada pela LGPD: o e-mail dela não é mais de
    ninguém. Não basta `!= inactive`; o filtro é `== active`."""
    pessoas = await _planta_todo_mundo(db)
    ids = {u.id for u in await audiencia_operacional(db)}
    assert pessoas["tecnico_anonimizado"].id not in ids


# ── A audiência inteira, de uma vez ───────────────────────────


async def test_a_audiencia_e_exatamente_os_dois_ativos(db):
    """A afirmação forte: a audiência é IGUAL ao conjunto esperado.

    Os seis testes acima verificam uma linha cada; este fecha a porta para
    alguém que passe a devolver gente que nenhum deles nomeia.
    """
    pessoas = await _planta_todo_mundo(db)
    ids = {u.id for u in await audiencia_operacional(db)}
    assert ids == {pessoas["tecnico_ativo"].id, pessoas["admin_ativo"].id}


# ── A Helô continua atingindo exatamente a mesma gente ────────
#
# Esta é a REDE DE REGRESSÃO da migração do `_avisa_equipe_da_helo` para a
# fonte única. Ela passa ANTES e DEPOIS da migração, de propósito: a consulta
# inline que ela tinha já estava certa, e o que se afirma aqui é que trocar de
# fonte não mudou quem é avisado.
#
# Contra Postgres, e não mock, pelo mesmo motivo do resto do arquivo: os testes
# mockados de `test_chat.py` combinam a lista de antemão e continuariam verdes
# com qualquer `WHERE`.


async def test_a_helo_avisa_exatamente_os_dois_ativos(db):
    from app.models.models import Notification, Ticket, TicketCategory, TicketStatus
    from app.routers.chat import _avisa_equipe_da_helo
    from app.services.helo import MOTIVO_TRIAGEM_CONCLUIDA

    pessoas = await _planta_todo_mundo(db)
    chamado = Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-{uuid.uuid4().hex[:8]}",
        title="Impressora sem conexao",
        description="corpo",
        category=TicketCategory.hardware,
        status=TicketStatus.in_progress,
        creator_id=pessoas["cliente_ativo"].id,
        ai_enabled=True,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        sla_resolve_extension_total_min=0,
        auto_closed=False,
        reopen_count=0,
    )
    db.add(chamado)
    await db.flush()

    await _avisa_equipe_da_helo(db, chamado, motivo=MOTIVO_TRIAGEM_CONCLUIDA)
    await db.flush()

    linhas = (await db.execute(select(Notification))).scalars().all()
    assert {n.user_id for n in linhas} == {
        pessoas["tecnico_ativo"].id,
        pessoas["admin_ativo"].id,
    }
    # Uma por pessoa, não duas.
    assert len(linhas) == 2
