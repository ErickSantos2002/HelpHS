"""
O `DELETE /users/{id}` deixando o PostgreSQL executar o `ON DELETE` que ele
já sabe fazer — contra Postgres de verdade.

Por que este arquivo existe
---------------------------
Medido em produção: um técnico `inactive`, sem NENHUMA das 13 referências
`NO ACTION` (a lista que `_REFERENCIAS_QUE_BLOQUEIAM` confere), mas com **8**
notificações. `notifications.user_id -> users.id ON DELETE CASCADE` no banco.
O `DELETE` mesmo assim voltou 409, via `IntegrityError`.

A causa não é o banco — é o ORM tentando resolver a relação ANTES de deixar o
Postgres agir. `User.notifications` não tinha `passive_deletes`, e o cascade
padrão do SQLAlchemy (`save-update, merge`, sem `delete`) faz o unit-of-work
tentar **anular** `user_id` em cada notificação carregada antes de emitir o
`DELETE FROM users`. `notifications.user_id` é `NOT NULL` — o `UPDATE ... SET
user_id = NULL` colide com essa constraint, e é ESSE `IntegrityError`, não o
`ON DELETE CASCADE`, que cai no `except` genérico do endpoint.

O endpoint fez o certo ao abortar: nada foi corrompido, e é o comportamento
seguro por padrão. O defeito é que o usuário deveria ter sido excluído, e não
foi — o `ON DELETE CASCADE` do banco nunca chegou a ser exercitado.

O mapeamento inteiro, e por que só DUAS relações mudam
--------------------------------------------------------
`User` declara onze `relationship()`. Cruzando cada uma contra o mapa de FKs
para `users.id` medido em 29/09/2026 (22 FKs: 13 `NO ACTION`, 7 `SET NULL`, 2
`CASCADE`), só DUAS apontam para uma FK que o banco de fato trata sozinho:

    User.notifications  -> notifications.user_id   ON DELETE CASCADE
    User.equipments      -> equipments.owner_id      ON DELETE SET NULL

As outras oito (`created_tickets`, `assigned_tickets`, `ticket_histories`,
`chat_messages`, `attachments`, `kb_articles`, `satisfaction_given`,
`audit_logs`) apontam para FKs `NO ACTION` — o banco não tem regra de
deleção para elas, e são EXATAMENTE as 13 que `_REFERENCIAS_QUE_BLOQUEIAM`
confere antes de chegar em `db.delete()`. Dar `passive_deletes` a essas oito
seria semanticamente errado: diria ao SQLAlchemy "confie no ON DELETE do
banco", e não existe ON DELETE nenhum ali para confiar — a proteção correta
para elas é a pré-checagem continuar bloqueando antes do `commit()`.

⚠️ A sessão precisa estar presa ao ENGINE, não a uma conexão+savepoint
------------------------------------------------------------------------
Os outros `*_postgres.py` desta casa usam sessão presa a uma `Connection`
com `join_transaction_mode="create_savepoint"`, para o teardown dar
`rollback()` de graça. **Medido**: com esse arranjo, o cenário do CASCADE
sobe `sqlalchemy.exc.MissingGreenlet` em vez do `IntegrityError` relatado em
produção — o carregamento *lazy* da coleção durante o `flush()` do
`commit()` não roda dentro do greenlet certo nessa configuração. Com a
sessão presa ao ENGINE (exatamente `AsyncSessionLocal`, em
`app/core/database.py`), o MESMO cenário reproduz o 409 tal como relatado.
Por isso este arquivo NÃO reaproveita aquele fixture: sem transação externa
para desfazer, cada teste limpa explicitamente o que criou.

⚠️ Depois de um `rollback()`, nunca leia `.atributo` do objeto Python — leia
o ID capturado antes
---------------------------------------------------------------------------
Achado ao escrever este arquivo, e vale para qualquer teste futuro que force
um `IntegrityError` de propósito: `delete_user` chama `await db.rollback()`
no `except`, e rollback EXPIRA os atributos de todo objeto da sessão —
`expire_on_commit=False` só protege o lado do `commit()`, não o do
`rollback()`. Se o teste, DEPOIS disso, escrever `alvo.id` (acesso de
atributo Python comum, fora de qualquer `await`), o SQLAlchemy dispara um
refresh *lazy* SÍNCRONO para repopular o atributo expirado — e essa IO
implícita, fora do greenlet do `await`, sobe `MissingGreenlet`. A correção é
capturar `alvo_id = alvo.id` como UUID simples ANTES do primeiro
commit/rollback, e usar essa variável — nunca mais `alvo.id` — depois disso.
Todos os testes abaixo seguem esse padrão, mesmo os que não rollback, por
consistência.

Nada aqui envia e-mail, e nenhum usuário real é tocado — tudo roda contra o
Postgres efêmero de teste.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    AuditAction,
    AuditLog,
    Base,
    Equipment,
    Group,
    GroupNote,
    Notification,
    NotificationType,
    Product,
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


@pytest.fixture(scope="module")
def url_do_banco():
    import asyncio

    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL à mão")

    async def _monta() -> None:
        motor = create_async_engine(url)
        async with motor.begin() as conn:
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
        import shutil

        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def db(url_do_banco):
    """Sessão presa ao ENGINE — a mesma configuração de `AsyncSessionLocal`.

    Deliberadamente NÃO é conexão+savepoint: ver o cabeçalho do arquivo. Sem
    transação externa, cada teste é responsável por apagar o que criou.
    """
    motor = create_async_engine(url_do_banco)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as sessao:
        yield sessao
    await motor.dispose()


def _pessoa(papel=UserRole.technician, status=UserStatus.inactive, nome="Alvo") -> User:
    return User(
        id=uuid.uuid4(),
        name=nome,
        email=f"{uuid.uuid4().hex[:10]}@test.invalid",
        password="x",
        role=papel,
        status=status,
        lgpd_consent=True,
        email_verified=(status == UserStatus.active),
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _admin() -> User:
    """O ator que chama o endpoint — precisa existir na mesma sessão."""
    return _pessoa(UserRole.admin, UserStatus.active, "Admin")


async def _existe(db, user_id) -> bool:
    resultado = await db.execute(select(User.id).where(User.id == user_id))
    return resultado.scalar_one_or_none() is not None


async def _limpa(db, *pares) -> None:
    """Apaga por id, na ordem em que os pares são passados — quem chama é
    responsável por passar filho antes de pai.

    `**kwargs` não serve aqui: a chave de um kwarg é sempre STRING em Python,
    nunca a classe — `_limpa(db, User=[...])` chegaria como `{"User": [...]}`,
    e `"User".id` não existe. Por isso são pares posicionais `(Modelo, ids)`.
    """
    for modelo, ids in pares:
        vivos = [i for i in ids if i is not None]
        if vivos:
            await db.execute(delete(modelo).where(modelo.id.in_(vivos)))
    await db.commit()


async def _limpa_auditoria_de(db, entity_id) -> None:
    """`AuditLog` não tem id previsível para o `_limpa` genérico — filtra por
    `entity_id`.

    Necessário sempre que o teste chega a `db.delete(user)` com sucesso:
    `_audit()` grava `AuditLog(user_id=actor.id, entity_id=alvo_id)` ANTES do
    delete, e essa linha referencia o ADMIN por `audit_logs.user_id` — que é
    uma das 13 FKs `NO ACTION`. Sem apagar o audit log primeiro, apagar o
    admin no teardown bate na própria constraint que esta correção existe
    para respeitar.
    """
    await db.execute(delete(AuditLog).where(AuditLog.entity_id == entity_id))
    await db.commit()


# ══════════════════════════════════════════════════════════════
# 1. CASCADE — a regressão exata medida em produção
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_apaga_o_usuario_e_suas_notificacoes_em_cascata(db):
    from app.routers.users import delete_user

    admin = _admin()
    alvo = _pessoa()
    admin_id, alvo_id = admin.id, alvo.id
    db.add_all([admin, alvo])
    await db.flush()

    for _ in range(8):
        db.add(
            Notification(
                id=uuid.uuid4(),
                user_id=alvo_id,
                type=NotificationType.system,
                title="x",
                message="x",
            )
        )
    await db.commit()

    antes = (
        await db.execute(
            select(func.count()).select_from(Notification).where(Notification.user_id == alvo_id)
        )
    ).scalar_one()
    assert antes == 8, "a premissa do teste: oito notificações, como em produção"

    try:
        # Não pode levantar HTTPException — é a regressão exata: 409 quando
        # devia ser 204.
        await delete_user(alvo_id, db, admin)

        assert not await _existe(db, alvo_id), "o usuário deveria ter sido excluído"
        depois = (
            await db.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == alvo_id)
            )
        ).scalar_one()
        assert depois == 0, "o ON DELETE CASCADE do banco deveria ter apagado as notificações"
    finally:
        await _limpa_auditoria_de(db, alvo_id)
        await _limpa(db, (User, [admin_id]))


# ══════════════════════════════════════════════════════════════
# 2. SET NULL — não pode ser "sabotado" pelo ORM no sentido contrário
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_zera_o_owner_do_equipamento_sem_apagar_o_equipamento(db):
    from app.routers.users import delete_user

    admin = _admin()
    alvo = _pessoa()
    admin_id, alvo_id = admin.id, alvo.id
    produto = Product(id=uuid.uuid4(), name="Bafômetro Teste", description="x")
    produto_id = produto.id
    db.add_all([admin, alvo, produto])
    await db.flush()

    equipamento = Equipment(
        id=uuid.uuid4(),
        product_id=produto_id,
        name="Unidade 1",
        owner_id=alvo_id,
    )
    equipamento_id = equipamento.id
    db.add(equipamento)
    await db.commit()

    # Instrumentação: com `owner_id` nullable, o RESULTADO final é idêntico
    # com ou sem `passive_deletes` — é por isso que a mutação que remove o
    # `passive_deletes=True` de `equipments` não muda nenhuma asserção de
    # resultado abaixo. O que muda é o MECANISMO: sem `passive_deletes`, o
    # SQLAlchemy carrega `alvo.equipments` (um SELECT) e emite ele mesmo o
    # `UPDATE equipments SET owner_id = NULL` ANTES do `DELETE FROM users`. Com
    # `passive_deletes=True`, nenhum dos dois sai — só o `DELETE FROM users`,
    # e é o Postgres quem zera `owner_id` via `ON DELETE SET NULL`.
    instrucoes: list[str] = []
    bruta = await db.connection()

    def _grava(_conn, _cursor, instrucao, *_resto):
        instrucoes.append(" ".join(instrucao.split()).lower())

    event.listen(bruta.sync_connection.engine, "before_cursor_execute", _grava)
    try:
        await delete_user(alvo_id, db, admin)
    finally:
        event.remove(bruta.sync_connection.engine, "before_cursor_execute", _grava)

    try:
        assert not any(
            "update equipments" in i for i in instrucoes
        ), "o SQLAlchemy tentou gerenciar equipments pelo ORM — passive_deletes não está agindo"
        assert not any(
            "from equipments" in i for i in instrucoes
        ), "o SQLAlchemy carregou a coleção de equipments — passive_deletes não está agindo"

        assert not await _existe(db, alvo_id)
        owner_depois = (
            await db.execute(select(Equipment.owner_id).where(Equipment.id == equipamento_id))
        ).scalar_one_or_none()
        assert owner_depois is None, "SET NULL deveria ter zerado owner_id"
        ainda_existe = (
            await db.execute(
                select(func.count()).select_from(Equipment).where(Equipment.id == equipamento_id)
            )
        ).scalar_one()
        assert ainda_existe == 1, "o equipamento não pode ter sido apagado — SET NULL não é CASCADE"
    finally:
        await _limpa_auditoria_de(db, alvo_id)
        await _limpa(db, (Equipment, [equipamento_id]), (Product, [produto_id]), (User, [admin_id]))


# ══════════════════════════════════════════════════════════════
# 3. As 13 referências NO ACTION continuam bloqueando — de ponta a ponta
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_continua_bloqueado_por_historico_no_action(db):
    """`passive_deletes` só foi dado a `notifications` e `equipments`. Uma
    referência SEM ondelete continua parando o usuário na pré-checagem, antes
    de qualquer `db.delete()` — end-to-end, contra o banco de verdade, não o
    mock que já cobre isto em `test_users.py`."""
    from app.routers.users import delete_user

    admin = _admin()
    alvo = _pessoa()
    cliente = _pessoa(UserRole.client, UserStatus.active, "Cliente")
    cliente.phone = "+5581999999999"
    admin_id, alvo_id, cliente_id = admin.id, alvo.id, cliente.id
    db.add_all([admin, alvo, cliente])
    await db.flush()

    ticket = Ticket(
        id=uuid.uuid4(),
        protocol="HS-ONDEL-0001",
        title="x",
        description="x",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.resolved,
        creator_id=cliente_id,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    ticket_id = ticket.id
    db.add(ticket)
    await db.flush()
    historico = TicketHistory(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        user_id=alvo_id,
        field="status",
        old_value="open",
        new_value="resolved",
    )
    historico_id = historico.id
    db.add(historico)
    await db.commit()

    try:
        with pytest.raises(HTTPException) as excinfo:
            await delete_user(alvo_id, db, admin)
        assert excinfo.value.status_code == 409

        assert await _existe(db, alvo_id), "o usuário bloqueado não pode ter sido excluído"
    finally:
        await _limpa(
            db,
            (TicketHistory, [historico_id]),
            (Ticket, [ticket_id]),
            (User, [alvo_id, cliente_id, admin_id]),
        )


# ══════════════════════════════════════════════════════════════
# 4. Rollback — nenhum resíduo quando o commit falha de verdade
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_rollback_nao_deixa_auditlog_orfao_quando_o_commit_falha(db):
    """Reproduz o MESMO tipo de lacuna que causou a regressão histórica de
    `library_files`/`ticket_sla_extensions`: uma tabela `NO ACTION` que a
    pré-checagem AINDA NÃO CONHECE — removendo `group_notes` da lista só
    dentro deste teste, com o alvo tendo uma linha exatamente ali.

    Precisa ser uma coluna `NOT NULL`. `group_notes.author_id` é — sem
    `passive_deletes`, o SQLAlchemy tentaria `UPDATE group_notes SET
    author_id = NULL` antes do `DELETE FROM users`, e a constraint `NOT
    NULL` recusaria. Com uma coluna NULLABLE (como `ticket_history.user_id`)
    a mesma lacuna não levantaria exceção nenhuma — ver o achado no teste
    seguinte.

    O que ESTE teste prova: `_audit()` e `db.delete()` estão na MESMA
    transação do `commit()` que falha, então o rollback desfaz os dois —
    nenhum `AuditLog` de exclusão sobrevive, e a linha bloqueadora continua
    intacta.

    ⚠️ Depois do `pytest.raises`, só se lê `alvo_id` (capturado ANTES do
    commit) — nunca `alvo.id`. Ver o cabeçalho do arquivo: `delete_user`
    chama `db.rollback()` no `except`, isso expira os atributos do objeto
    Python `alvo`, e ler `.id` dele depois dispara um refresh lazy síncrono
    que sobe `MissingGreenlet` sob o executor do pytest-asyncio.
    """
    from app.routers import users as modulo_users
    from app.routers.users import delete_user

    admin = _admin()
    alvo = _pessoa()
    grupo = Group(id=uuid.uuid4(), name="Grupo de teste")
    admin_id, alvo_id, grupo_id = admin.id, alvo.id, grupo.id
    db.add_all([admin, alvo, grupo])
    await db.flush()

    nota = GroupNote(
        id=uuid.uuid4(),
        group_id=grupo_id,
        author_id=alvo_id,
        content="nota interna de teste",
    )
    nota_id = nota.id
    db.add(nota)
    await db.commit()

    lista_sem_notas_de_grupo = tuple(
        item for item in modulo_users._REFERENCIAS_QUE_BLOQUEIAM if item[1] is not GroupNote
    )
    assert len(lista_sem_notas_de_grupo) == len(modulo_users._REFERENCIAS_QUE_BLOQUEIAM) - 1

    try:
        with patch.object(modulo_users, "_REFERENCIAS_QUE_BLOQUEIAM", lista_sem_notas_de_grupo):
            with pytest.raises(HTTPException) as excinfo:
                await delete_user(alvo_id, db, admin)
        assert excinfo.value.status_code == 409

        assert await _existe(db, alvo_id), "deleção parcial: o usuário sumiu apesar do 409"

        auditoria_de_exclusao = (
            await db.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == AuditAction.delete, AuditLog.entity_id == alvo_id)
            )
        ).scalar_one()
        assert (
            auditoria_de_exclusao == 0
        ), "AuditLog órfão: a exclusão falhou mas deixou rastro de que aconteceu"

        nota_sobrevive = (
            await db.execute(
                select(func.count()).select_from(GroupNote).where(GroupNote.id == nota_id)
            )
        ).scalar_one()
        assert nota_sobrevive == 1, "a linha bloqueadora não pode ter sido tocada"
    finally:
        await _limpa(
            db,
            (GroupNote, [nota_id]),
            (Group, [grupo_id]),
            (User, [alvo_id, admin_id]),
        )


# ══════════════════════════════════════════════════════════════
# 5. Achado — uma lacuna em coluna NULLABLE apaga histórico em silêncio
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_achado_lacuna_em_coluna_nullable_apaga_historico_em_silencio(db):
    """NÃO é uma regressão desta correção — é um achado sobre o desenho
    atual, registrado em teste porque é onde fica mais difícil de esquecer.

    `ticket_history.user_id` é NULLABLE. Se a pré-checagem um dia tiver uma
    lacuna sobre ELA — do mesmo jeito que teve sobre `library_files` e
    `ticket_sla_extensions` —, a consequência NÃO é um 409: é o SQLAlchemy
    conseguir `UPDATE ticket_history SET user_id = NULL` com sucesso antes do
    `DELETE FROM users`, e o usuário sai excluído mesmo tendo histórico —
    apagando em silêncio QUEM fez aquela mudança. Mais grave que um 409 de
    sobra, porque não há exceção nenhuma para avisar.

    Esta correção NÃO estende `passive_deletes` a `ticket_histories` (nem às
    outras sete relações `NO ACTION`) porque isso está fora do escopo pedido
    — só as relações que JÁ têm `ON DELETE` no banco. Fica registrado aqui
    para quem decidir se vale uma frente própria: dar `passive_deletes` às
    oito relações `NO ACTION` trocaria este modo de falha (apagar em
    silêncio) pelo mesmo que `notifications`/`equipments` já tinham antes —
    deixar o Postgres recusar com `IntegrityError`, que é o que a
    pré-checagem espera capturar.
    """
    from app.routers import users as modulo_users
    from app.routers.users import delete_user

    admin = _admin()
    alvo = _pessoa()
    cliente = _pessoa(UserRole.client, UserStatus.active, "Cliente")
    cliente.phone = "+5581999999999"
    admin_id, alvo_id, cliente_id = admin.id, alvo.id, cliente.id
    db.add_all([admin, alvo, cliente])
    await db.flush()

    ticket = Ticket(
        id=uuid.uuid4(),
        protocol="HS-ONDEL-0003",
        title="x",
        description="x",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.resolved,
        creator_id=cliente_id,
        created_at=_AGORA,
        updated_at=_AGORA,
    )
    ticket_id = ticket.id
    db.add(ticket)
    await db.flush()
    historico = TicketHistory(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        user_id=alvo_id,
        field="status",
        old_value="open",
        new_value="resolved",
    )
    historico_id = historico.id
    db.add(historico)
    await db.commit()

    lista_sem_historico = tuple(
        item for item in modulo_users._REFERENCIAS_QUE_BLOQUEIAM if item[1] is not TicketHistory
    )

    try:
        with patch.object(modulo_users, "_REFERENCIAS_QUE_BLOQUEIAM", lista_sem_historico):
            # Não levanta — é exatamente o achado: sucesso onde devia bloquear.
            await delete_user(alvo_id, db, admin)

        assert not await _existe(db, alvo_id), "confirma que o DELETE de fato passou"
        autor_apagado = (
            await db.execute(select(TicketHistory.user_id).where(TicketHistory.id == historico_id))
        ).scalar_one()
        assert autor_apagado is None, "a autoria da linha de histórico foi anulada em silêncio"
    finally:
        await _limpa_auditoria_de(db, alvo_id)
        await _limpa(
            db,
            (TicketHistory, [historico_id]),
            (Ticket, [ticket_id]),
            (User, [cliente_id, admin_id]),
        )
