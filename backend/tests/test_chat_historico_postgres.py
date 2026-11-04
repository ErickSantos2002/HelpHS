"""
Histórico do chat, anexo da biblioteca e WebSocket contra PostgreSQL de verdade.

Por que este arquivo existe
---------------------------
O `test_chat.py` é inteiramente mockado, e mock não reproduz a falha que mais
pesava no chat: com um arquivo da biblioteca numa mensagem, o histórico
respondia 500. O relacionamento `ChatMessage.library_file` é carregado sob
demanda, e numa sessão assíncrona tocar num relacionamento não carregado
levanta `MissingGreenlet` em vez de consultar o banco. Só uma sessão
assíncrona real, "fria" como a de uma requisição nova, mostra isso.

O mesmo vale para a paginação: a ordem `(created_at, id)`, o empate de
`created_at` e a comparação de linha só valem alguma coisa contra o Postgres
que a executa.

Como o banco aparece
--------------------
Igual ao `test_dashboard_postgres.py`: `TEST_POSTGRES_URL` quando existe (o
CI), senão um Postgres efêmero via `pgserver`; sem nenhum dos dois, pula.

Duas formas de isolamento:

- `db`: transação revertida no fim. A sessão é esvaziada (`expunge_all`)
  antes de cada requisição, porque o mapa de identidade **esconde** a falha:
  com o `LibraryFile` já carregado na sessão, o lazy load de muitos-para-um
  resolve sem ir ao banco e o 500 não aparece. Cada requisição real começa
  com a sessão vazia.
- `banco_real`: commits de verdade, para concorrência e WebSocket, que usam
  mais de uma sessão. O que cada teste cria é apagado no fim, pelo id.
"""

import asyncio
import base64
import json
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.models import (
    Base,
    ChatMessage,
    LibraryFile,
    LibraryVisibility,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from tests._mensagem_sem_seq import sem_seq_intencional

_AGORA = datetime.now(UTC)


def _sobe_postgres() -> tuple[str, object] | tuple[None, None]:
    do_ambiente = os.environ.get("TEST_POSTGRES_URL")
    if do_ambiente:
        return do_ambiente.replace("postgresql://", "postgresql+asyncpg://"), None

    try:
        import pgserver
    except ImportError:
        return None, None

    pasta = tempfile.mkdtemp(prefix="helphs-testes-pg-")
    # "stop", e não None como nos outros arquivos: com None o `cleanup()` do
    # pgserver retorna sem parar o servidor, e cada execução deixava um
    # postgres vivo na máquina.
    servidor = pgserver.get_server(pasta, cleanup_mode="stop")
    servidor.psql("CREATE DATABASE chat_testes;")
    url = servidor.get_uri(database="chat_testes")
    return url.replace("postgresql://", "postgresql+asyncpg://"), (servidor, pasta)


@pytest.fixture(scope="module")
def url_do_banco():
    """Síncrona pelo mesmo motivo do `test_dashboard_postgres.py`: o laço do
    pytest-asyncio é por teste, e o schema é montado uma vez só."""
    url, recurso = _sobe_postgres()
    if url is None:
        pytest.skip("sem PostgreSQL: defina TEST_POSTGRES_URL ou instale pgserver")

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
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def db(url_do_banco):
    """Sessão numa transação revertida no fim."""
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        async with async_sessionmaker(bind=conn, expire_on_commit=False)() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


# ── Dados sintéticos ──────────────────────────────────────────


def _usuario(papel: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        name=f"{papel.value} {uuid.uuid4().hex[:4]}",
        email=f"{uuid.uuid4().hex[:10]}@chat-testes.com.br",
        password="x",
        role=papel,
        status=UserStatus.active,
        phone="+5581999999999",
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
        created_at=_AGORA,
        updated_at=_AGORA,
    )


def _chamado(criador: User, responsavel: User | None = None) -> Ticket:
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"CHAT-{uuid.uuid4().hex[:10]}",
        title="Chamado do chat",
        description="corpo",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.in_progress,
        creator_id=criador.id,
        assignee_id=responsavel.id if responsavel else None,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        auto_closed=False,
        reopen_count=0,
        # A Helô fica de fora: estes testes são do histórico, não da triagem.
        ai_enabled=False,
        created_at=_AGORA - timedelta(days=1),
        updated_at=_AGORA - timedelta(days=1),
    )


def _arquivo(dono: User, visibilidade: LibraryVisibility = LibraryVisibility.client) -> LibraryFile:
    return LibraryFile(
        id=uuid.uuid4(),
        title="Manual",
        visibility=visibilidade,
        original_name="manual-do-equipamento.pdf",
        stored_name=f"{uuid.uuid4().hex}.pdf",
        mime_type="application/pdf",
        size_bytes=48_213,
        s3_key=f"biblioteca/{uuid.uuid4().hex}.pdf",
        s3_bucket="helphs-testes",
        uploaded_by=dono.id,
    )


def _mensagem(
    chamado: Ticket,
    remetente: User,
    quando: datetime,
    *,
    texto: str = "olá",
    arquivo: LibraryFile | None = None,
    id_: uuid.UUID | None = None,
) -> ChatMessage:
    return ChatMessage(
        id=id_ or uuid.uuid4(),
        ticket_id=chamado.id,
        sender_id=remetente.id,
        content=texto,
        is_system=False,
        is_ai=False,
        library_file_id=arquivo.id if arquivo else None,
        created_at=quando,
    )


async def _semeia(db, *objetos) -> None:
    """Grava e esvazia a sessão: a próxima leitura começa fria."""
    db.add_all(objetos)
    await db.flush()
    db.expunge_all()


async def _cenario(db):
    cliente = _usuario(UserRole.client)
    tecnico = _usuario(UserRole.technician)
    admin = _usuario(UserRole.admin)
    await _semeia(db, cliente, tecnico, admin)
    chamado = _chamado(cliente, tecnico)
    await _semeia(db, chamado)
    return cliente, tecnico, admin, chamado


async def _historico(db, ator: User, chamado_id: uuid.UUID, **params):
    """GET /tickets/{id}/messages como uma requisição nova: sessão vazia."""

    async def _db():
        db.expunge_all()
        yield db

    async def _ator():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _ator
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            return await c.get(f"/api/v1/tickets/{chamado_id}/messages", params=params)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _todas_as_paginas(db, ator, chamado_id, limite: int) -> list[dict]:
    """Percorre o histórico para trás até o fim; devolve em ordem de leitura."""
    paginas: list[list[dict]] = []
    params: dict = {"limit": limite}
    for _ in range(1000):
        r = await _historico(db, ator, chamado_id, **params)
        assert r.status_code == 200, r.text
        corpo = r.json()
        paginas.append(corpo["items"])
        if not corpo["has_more"]:
            assert corpo["next_before"] is None
            break
        assert corpo["next_before"]
        params = {"limit": limite, "before": corpo["next_before"]}
    # A página mais antiga vem por último; a conversa se lê do começo.
    return [m for pagina in reversed(paginas) for m in pagina]


# ── O 500 do anexo da biblioteca ──────────────────────────────


@pytest.mark.asyncio
async def test_historico_com_anexo_da_biblioteca_nao_da_500(db):
    """A reprodução: uma mensagem com arquivo derrubava o histórico inteiro."""
    cliente, tecnico, _, chamado = await _cenario(db)
    arquivo = _arquivo(tecnico)
    await _semeia(db, arquivo)
    await _semeia(db, _mensagem(chamado, tecnico, _AGORA, texto="segue o manual", arquivo=arquivo))

    r = await _historico(db, cliente, chamado.id)

    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["library_file_id"] == str(arquivo.id)
    assert item["library_file_name"] == "manual-do-equipamento.pdf"
    assert item["library_file_mime"] == "application/pdf"
    assert item["library_file_size"] == 48_213
    assert item["library_file_unavailable"] is False


@pytest.mark.asyncio
async def test_arquivo_que_virou_interno_some_para_o_cliente(db):
    """Anexado quando era do cliente, fechado depois: o cliente não lê mais o
    nome, o tipo, o tamanho nem o id — só que havia um arquivo."""
    cliente, tecnico, _, chamado = await _cenario(db)
    arquivo = _arquivo(tecnico, LibraryVisibility.client)
    await _semeia(db, arquivo)
    await _semeia(db, _mensagem(chamado, tecnico, _AGORA, arquivo=arquivo))
    await db.execute(
        LibraryFile.__table__.update()
        .where(LibraryFile.id == arquivo.id)
        .values(visibility=LibraryVisibility.internal)
    )

    item = (await _historico(db, cliente, chamado.id)).json()["items"][0]

    assert item["library_file_unavailable"] is True
    assert item["library_file_id"] is None
    assert item["library_file_name"] is None
    assert item["library_file_mime"] is None
    assert item["library_file_size"] is None
    assert item["content"] == "olá", "o texto da mensagem continua sendo do cliente"


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.admin])
async def test_arquivo_interno_continua_inteiro_para_a_equipe(db, papel):
    cliente, tecnico, admin, chamado = await _cenario(db)
    arquivo = _arquivo(tecnico, LibraryVisibility.internal)
    await _semeia(db, arquivo)
    await _semeia(db, _mensagem(chamado, tecnico, _AGORA, arquivo=arquivo))
    ator = tecnico if papel is UserRole.technician else admin

    item = (await _historico(db, ator, chamado.id)).json()["items"][0]

    assert item["library_file_unavailable"] is False
    assert item["library_file_id"] == str(arquivo.id)
    assert item["library_file_name"] == "manual-do-equipamento.pdf"


@pytest.mark.asyncio
async def test_arquivo_excluido_da_biblioteca_nao_derruba_o_historico(db):
    """A FK é `SET NULL`: excluído, o arquivo deixa a mensagem sem vínculo
    nenhum. Não há como dizer que ali houve um arquivo — o histórico só
    precisa continuar abrindo."""
    cliente, tecnico, _, chamado = await _cenario(db)
    arquivo = _arquivo(tecnico)
    await _semeia(db, arquivo)
    await _semeia(db, _mensagem(chamado, tecnico, _AGORA, arquivo=arquivo))
    await db.execute(delete(LibraryFile).where(LibraryFile.id == arquivo.id))

    r = await _historico(db, cliente, chamado.id)

    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["library_file_id"] is None
    assert item["library_file_name"] is None
    assert item["library_file_unavailable"] is False


@pytest.mark.asyncio
async def test_caminho_que_esquecer_o_carregamento_perde_o_arquivo_e_nao_a_conversa(db):
    """A rede de segurança de `_arquivo_da_mensagem`: uma consulta futura sem
    `selectinload(ChatMessage.library_file)` não pode voltar a dar 500 — sai a
    mensagem com o arquivo "indisponível", e o aviso vai para o log."""
    from loguru import logger

    from app.routers.chat import _msg_to_response

    _, tecnico, _, chamado = await _cenario(db)
    arquivo = _arquivo(tecnico)
    await _semeia(db, arquivo)
    await _semeia(db, _mensagem(chamado, tecnico, _AGORA, arquivo=arquivo))
    # O remetente vem, como em todo caminho real; só o arquivo é esquecido.
    sem_carregar = (
        await db.execute(
            select(ChatMessage)
            .options(selectinload(ChatMessage.sender))
            .where(ChatMessage.ticket_id == chamado.id)
        )
    ).scalar_one()
    avisos: list[str] = []
    gancho = logger.add(lambda m: avisos.append(str(m)), level="WARNING")
    try:
        resposta = _msg_to_response(sem_carregar, ve_arquivo_interno=True)
    finally:
        logger.remove(gancho)

    assert resposta.library_file_unavailable is True
    assert resposta.library_file_id is None
    assert any("sem o arquivo da biblioteca carregado" in a for a in avisos)


def test_vinculo_carregado_como_nulo_e_indisponivel():
    """Id preenchido e relacionamento carregado VAZIO (o arquivo sumiu entre
    as duas consultas do `selectinload`): indisponível, sem quebrar."""
    from app.routers.chat import _msg_to_response

    dono = _usuario(UserRole.technician)
    msg = _mensagem(_chamado(dono), dono, _AGORA, arquivo=_arquivo(dono))
    msg.sender = dono
    msg.library_file = None
    msg.library_file_id = uuid.uuid4()

    resposta = _msg_to_response(msg, ve_arquivo_interno=True)

    assert resposta.library_file_unavailable is True
    assert resposta.library_file_name is None


# ── Paginação por cursor ──────────────────────────────────────


@pytest.mark.asyncio
async def test_abre_nas_cem_mais_recentes_em_ordem_cronologica(db):
    cliente, tecnico, _, chamado = await _cenario(db)
    mensagens = [
        _mensagem(chamado, tecnico, _AGORA - timedelta(minutes=150 - i), texto=f"m{i:03d}")
        for i in range(150)
    ]
    await _semeia(db, *mensagens)

    corpo = (await _historico(db, cliente, chamado.id)).json()

    textos = [m["content"] for m in corpo["items"]]
    assert textos == [f"m{i:03d}" for i in range(50, 150)], "não são as 100 mais recentes"
    assert corpo["total"] == 150
    assert corpo["limit"] == 100
    assert corpo["has_more"] is True
    assert corpo["next_before"]


@pytest.mark.asyncio
async def test_150_mensagens_sem_duplicata_nem_lacuna(db):
    cliente, tecnico, _, chamado = await _cenario(db)
    mensagens = [
        _mensagem(chamado, tecnico, _AGORA - timedelta(seconds=150 - i), texto=f"m{i:03d}")
        for i in range(150)
    ]
    await _semeia(db, *mensagens)

    lidas = await _todas_as_paginas(db, cliente, chamado.id, limite=100)

    assert [m["content"] for m in lidas] == [f"m{i:03d}" for i in range(150)]
    assert len({m["id"] for m in lidas}) == 150


@pytest.mark.asyncio
async def test_pagina_exata_nao_promete_pagina_anterior_vazia(db):
    """Exatamente `limit` mensagens: não há página anterior, e dizer que há
    faria a tela pedir uma página vazia."""
    cliente, tecnico, _, chamado = await _cenario(db)
    await _semeia(
        db, *[_mensagem(chamado, tecnico, _AGORA - timedelta(seconds=i)) for i in range(3)]
    )

    corpo = (await _historico(db, cliente, chamado.id, limit=3)).json()

    assert len(corpo["items"]) == 3
    assert corpo["has_more"] is False
    assert corpo["next_before"] is None


@pytest.mark.asyncio
async def test_empate_de_created_at_desempata_pelo_id(db):
    """Sete mensagens no MESMO instante, páginas de três: o `id` decide, e
    nenhuma se repete ou se perde na fronteira entre páginas."""
    cliente, tecnico, _, chamado = await _cenario(db)
    instante = _AGORA - timedelta(minutes=5)
    mensagens = [_mensagem(chamado, tecnico, instante, texto=f"e{i}") for i in range(7)]
    antes = _mensagem(chamado, tecnico, instante - timedelta(seconds=1), texto="antes")
    depois = _mensagem(chamado, tecnico, instante + timedelta(seconds=1), texto="depois")
    await _semeia(db, antes, *mensagens, depois)

    lidas = await _todas_as_paginas(db, cliente, chamado.id, limite=3)

    esperado = ["antes"] + [m.content for m in sorted(mensagens, key=lambda m: m.id)] + ["depois"]
    assert [m["content"] for m in lidas] == esperado
    assert len({m["id"] for m in lidas}) == 9


@pytest.mark.asyncio
async def test_cursor_carrega_o_chamado_e_o_ponto_exato(db):
    cliente, tecnico, _, chamado = await _cenario(db)
    m = _mensagem(chamado, tecnico, _AGORA)
    await _semeia(db, m, _mensagem(chamado, tecnico, _AGORA - timedelta(seconds=1)))

    corpo = (await _historico(db, cliente, chamado.id, limit=1)).json()
    bruto = corpo["next_before"]
    conteudo = json.loads(base64.urlsafe_b64decode(bruto + "=" * (-len(bruto) % 4)))

    assert conteudo["tk"] == str(chamado.id)
    assert conteudo["id"] == str(m.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cursor",
    [
        "isto-nao-e-base64!!",
        base64.urlsafe_b64encode(b"nao e json").decode().rstrip("="),
        base64.urlsafe_b64encode(b'{"tk": "x"}').decode().rstrip("="),
        base64.urlsafe_b64encode(b"[1, 2, 3]").decode().rstrip("="),
        base64.urlsafe_b64encode(
            json.dumps({"tk": str(uuid.uuid4()), "t": "ontem", "id": str(uuid.uuid4())}).encode()
        )
        .decode()
        .rstrip("="),
        "",
    ],
    ids=["nao-base64", "nao-json", "faltam-campos", "nao-objeto", "data-ruim", "vazio"],
)
async def test_cursor_invalido_e_422(db, cursor):
    cliente, tecnico, _, chamado = await _cenario(db)
    await _semeia(db, _mensagem(chamado, tecnico, _AGORA))

    r = await _historico(db, cliente, chamado.id, before=cursor)

    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_cursor_sem_fuso_e_422_mesmo_do_chamado_certo(db):
    """O `tk` é o do próprio chamado: só a falta de fuso pode recusar este.
    Sem fuso, a comparação com `timestamptz` dependeria do fuso da sessão."""
    cliente, tecnico, _, chamado = await _cenario(db)
    await _semeia(db, _mensagem(chamado, tecnico, _AGORA))
    cursor = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"tk": str(chamado.id), "t": "2026-10-30T12:00:00", "id": str(uuid.uuid4())}
            ).encode()
        )
        .decode()
        .rstrip("=")
    )

    r = await _historico(db, cliente, chamado.id, before=cursor)

    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_cursor_de_outro_chamado_e_recusado(db):
    """Os dois chamados são do técnico: não é falta de permissão, é cursor
    trocado — e ele não pode virar uma página silenciosa do chamado errado."""
    cliente, tecnico, _, chamado = await _cenario(db)
    outro = _chamado(cliente, tecnico)
    await _semeia(db, outro)
    await _semeia(
        db,
        _mensagem(chamado, tecnico, _AGORA),
        _mensagem(chamado, tecnico, _AGORA - timedelta(seconds=1)),
        _mensagem(outro, tecnico, _AGORA),
    )
    cursor_do_primeiro = (await _historico(db, tecnico, chamado.id, limit=1)).json()["next_before"]

    r = await _historico(db, tecnico, outro.id, before=cursor_do_primeiro)

    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_offset_e_before_juntos_e_422(db):
    cliente, tecnico, _, chamado = await _cenario(db)
    await _semeia(
        db,
        _mensagem(chamado, tecnico, _AGORA),
        _mensagem(chamado, tecnico, _AGORA - timedelta(seconds=1)),
    )
    cursor = (await _historico(db, cliente, chamado.id, limit=1)).json()["next_before"]

    r = await _historico(db, cliente, chamado.id, before=cursor, offset=0)

    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_offset_explicito_mantem_o_contrato_antigo(db):
    """Quem pagina por `offset` continua lendo do começo, 50 por página."""
    cliente, tecnico, _, chamado = await _cenario(db)
    await _semeia(
        db,
        *[
            _mensagem(chamado, tecnico, _AGORA - timedelta(seconds=150 - i), texto=f"m{i:03d}")
            for i in range(150)
        ],
    )

    primeira = (await _historico(db, cliente, chamado.id, offset=0)).json()
    ultima = (await _historico(db, cliente, chamado.id, offset=140)).json()

    assert [m["content"] for m in primeira["items"]] == [f"m{i:03d}" for i in range(50)]
    assert primeira["limit"] == 50
    assert primeira["offset"] == 0
    assert primeira["has_more"] is True
    assert primeira["next_before"] is None
    assert [m["content"] for m in ultima["items"]] == [f"m{i:03d}" for i in range(140, 150)]
    assert ultima["has_more"] is False


# ── Autorização ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cliente_alheio_recebe_o_mesmo_404_com_ou_sem_cursor(db):
    """A autorização vem ANTES do cursor: um cursor válido não muda a recusa,
    e um inválido não vira um 422 que confirmaria que o chamado existe."""
    cliente, tecnico, _, chamado = await _cenario(db)
    intruso = _usuario(UserRole.client)
    await _semeia(db, intruso)
    await _semeia(
        db,
        _mensagem(chamado, tecnico, _AGORA),
        _mensagem(chamado, tecnico, _AGORA - timedelta(seconds=1)),
    )
    cursor = (await _historico(db, cliente, chamado.id, limit=1)).json()["next_before"]

    sem = await _historico(db, intruso, chamado.id)
    com = await _historico(db, intruso, chamado.id, before=cursor)
    lixo = await _historico(db, intruso, chamado.id, before="lixo")
    inexistente = await _historico(db, intruso, uuid.uuid4())

    respostas = {(r.status_code, r.json()["detail"]) for r in (sem, com, lixo, inexistente)}
    assert len(respostas) == 1, respostas
    assert sem.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.admin])
async def test_equipe_le_o_historico_de_qualquer_chamado(db, papel):
    cliente, tecnico, admin, chamado = await _cenario(db)
    outro_tecnico = _usuario(UserRole.technician)
    await _semeia(db, outro_tecnico)
    await _semeia(db, _mensagem(chamado, cliente, _AGORA))
    ator = outro_tecnico if papel is UserRole.technician else admin

    r = await _historico(db, ator, chamado.id)

    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 1


# ── Commits de verdade: concorrência e WebSocket ──────────────


@pytest.fixture
def banco_real(url_do_banco):
    """Fábrica de sessões com commit real; apaga no fim o que o teste criou.

    `NullPool`: cada uso abre a conexão no laço em que roda — o TestClient do
    WebSocket roda o app noutro laço, noutra thread.
    """
    motor = create_async_engine(url_do_banco, poolclass=NullPool)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    criados: dict[str, set[uuid.UUID]] = {"users": set(), "tickets": set(), "library_files": set()}

    yield fabrica, criados

    async def _limpa() -> None:
        alvos = {nome: ids for nome, ids in criados.items() if ids}
        if not alvos:
            return
        async with motor.begin() as conn:
            for tabela in reversed(Base.metadata.sorted_tables):
                condicoes = []
                for coluna in tabela.columns:
                    for fk in coluna.foreign_keys:
                        ids = alvos.get(fk.column.table.name)
                        if ids:
                            condicoes.append(coluna.in_(ids))
                if tabela.name in alvos:
                    condicoes.append(tabela.c.id.in_(alvos[tabela.name]))
                if condicoes:
                    await conn.execute(tabela.delete().where(or_(*condicoes)))
        await motor.dispose()

    asyncio.run(_limpa())


async def _grava(fabrica, criados, *objetos) -> None:
    # Semeadura direta pelo ORM: a mensagem que entra aqui é o legado (ou a
    # imagem antiga) de propósito, sem `seq`. Ver tests/_mensagem_sem_seq.py.
    with sem_seq_intencional():
        async with fabrica() as s:
            s.add_all(objetos)
            await s.commit()
    for o in objetos:
        nome = o.__table__.name
        if nome in criados:
            criados[nome].add(o.id)


def test_gravacoes_concorrentes_entram_todas_uma_vez(banco_real):
    """Vinte POSTs ao mesmo tempo, de duas pessoas, cada um na sua sessão: o
    histórico devolve as vinte, cada uma uma vez, na ordem de `created_at`."""
    fabrica, criados = banco_real

    async def _cena():
        cliente, tecnico = _usuario(UserRole.client), _usuario(UserRole.technician)
        await _grava(fabrica, criados, cliente, tecnico)
        chamado = _chamado(cliente, tecnico)
        await _grava(fabrica, criados, chamado)

        async def _db():
            async with fabrica() as s:
                yield s

        atores = {"cliente": cliente, "tecnico": tecnico}

        async def _ator_da_vez(request: Request):
            return atores[request.headers["x-ator"]]

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = _ator_da_vez

        async def _post(i: int):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                return await c.post(
                    f"/api/v1/tickets/{chamado.id}/messages",
                    json={"content": f"c{i:02d}"},
                    headers={"x-ator": "tecnico" if i % 2 else "cliente"},
                )

        async def _sem_rede(*a, **k):
            return None

        try:
            with patch("app.routers.chat.chat_backplane.publicar", _sem_rede):
                respostas = await asyncio.gather(*[_post(i) for i in range(20)])
            assert all(r.status_code == 201 for r in respostas), [r.text for r in respostas]

            async with fabrica() as s:
                lidas = await _todas_as_paginas_sessao(s, cliente, chamado.id)
            return respostas, lidas
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)

    respostas, lidas = asyncio.run(_cena())

    criadas = {r.json()["id"] for r in respostas}
    assert [m["id"] for m in lidas if m["content"].startswith("c")] == [
        m["id"]
        for m in sorted(lidas, key=lambda m: (m["created_at"], m["id"]))
        if m["content"].startswith("c")
    ]
    assert {m["id"] for m in lidas} >= criadas
    assert len([m for m in lidas if m["id"] in criadas]) == 20


async def _todas_as_paginas_sessao(sessao, ator, chamado_id) -> list[dict]:
    """`_todas_as_paginas` com uma sessão de commit real, páginas de sete."""

    async def _db():
        sessao.expunge_all()
        yield sessao

    async def _ator():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _ator
    paginas: list[list[dict]] = []
    params: dict = {"limit": 7}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        while True:
            corpo = (await c.get(f"/api/v1/tickets/{chamado_id}/messages", params=params)).json()
            paginas.append(corpo["items"])
            if not corpo["has_more"]:
                break
            params = {"limit": 7, "before": corpo["next_before"]}
    return [m for pagina in reversed(paginas) for m in pagina]


def test_commit_tardio_cai_atras_do_cursor_e_so_a_pagina_recente_o_recupera(banco_real):
    """CARACTERIZAÇÃO do limite que o diagnóstico apontou — não é defeito a
    consertar aqui, é o contrato que o front da B-04b precisa respeitar.

    `created_at` é carimbado ANTES do commit (no POST, antes da Helô e da
    notificação). Uma mensagem A carimbada às 10:00:00 que comita DEPOIS de B
    (10:00:01) não existia quando a tela leu a página; e voltar com `before`
    nunca a devolve, porque ela é mais NOVA que o cursor. Quem a entrega é o
    tempo real — ou reler a página MAIS RECENTE, que a traz no lugar certo
    enquanto ela couber nessa página.
    """
    fabrica, criados = banco_real

    async def _cena():
        cliente, tecnico = _usuario(UserRole.client), _usuario(UserRole.technician)
        await _grava(fabrica, criados, cliente, tecnico)
        chamado = _chamado(cliente, tecnico)
        await _grava(fabrica, criados, chamado)
        base = datetime.now(UTC) - timedelta(minutes=1)
        antigas = [
            _mensagem(chamado, tecnico, base - timedelta(seconds=10 - i), texto=f"v{i}")
            for i in range(3)
        ]
        await _grava(fabrica, criados, *antigas)

        # A sessão de A abre e carimba primeiro; B comita no meio.
        sessao_a = fabrica()
        a = _mensagem(chamado, cliente, base, texto="A, carimbada antes")
        sessao_a.add(a)
        await sessao_a.flush()
        b = _mensagem(chamado, tecnico, base + timedelta(seconds=1), texto="B, comitada antes")
        await _grava(fabrica, criados, b)

        async with fabrica() as leitura:
            pagina = await _uma_pagina(leitura, cliente, chamado.id, limit=2)
        with sem_seq_intencional():  # o legado: A comita tarde, sem número
            await sessao_a.commit()
        await sessao_a.close()

        async with fabrica() as leitura:
            para_tras = await _uma_pagina(
                leitura, cliente, chamado.id, limit=50, before=pagina["next_before"]
            )
        async with fabrica() as leitura:
            recente = await _uma_pagina(leitura, cliente, chamado.id, limit=2)
        return pagina, para_tras, recente

    try:
        pagina, para_tras, recente = asyncio.run(_cena())
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert [m["content"] for m in pagina["items"]] == ["v2", "B, comitada antes"]
    assert "A, carimbada antes" not in [m["content"] for m in para_tras["items"]]
    assert [m["content"] for m in recente["items"]] == ["A, carimbada antes", "B, comitada antes"]


async def _uma_pagina(sessao, ator, chamado_id, **params) -> dict:
    async def _db():
        yield sessao

    async def _ator():
        return ator

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _ator
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/v1/tickets/{chamado_id}/messages", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ── WebSocket com banco de verdade ────────────────────────────


def _ws_ambiente(fabrica):
    """O handler abre `AsyncSessionLocal` na mão: aponta para o banco do teste.
    O token é o id da pessoa — a autenticação por JWT tem testes próprios."""

    async def _auth(token, sessao):
        try:
            return await sessao.get(User, uuid.UUID(token))
        except ValueError:
            return None

    async def _sem_rede(*a, **k):
        return None

    return (
        patch("app.routers.chat.AsyncSessionLocal", fabrica),
        patch("app.routers.chat._authenticate_ws", _auth),
        patch("app.routers.chat.chat_backplane.publicar", _sem_rede),
    )


def _fechamento_depois_do_aceite(chamado_id, token) -> tuple[int, str]:
    """Entrar no `with` prova que houve `accept`: fechado antes do handshake,
    o TestClient levantaria já ali — e o navegador veria 1006, sem código."""
    with TestClient(app).websocket_connect(f"/api/v1/ws/tickets/{chamado_id}?token={token}") as ws:
        with pytest.raises(WebSocketDisconnect) as fechou:
            ws.receive_text()
    return fechou.value.code, fechou.value.reason


def test_ws_4004_chega_ao_navegador_igual_para_alheio_e_inexistente(banco_real):
    fabrica, criados = banco_real
    dono, intruso, tecnico = (_usuario(UserRole.client) for _ in range(3))
    chamado = _chamado(dono)
    asyncio.run(_grava(fabrica, criados, dono, intruso, tecnico))
    asyncio.run(_grava(fabrica, criados, chamado))

    p1, p2, p3 = _ws_ambiente(fabrica)
    with p1, p2, p3:
        alheio = _fechamento_depois_do_aceite(chamado.id, intruso.id)
        inexistente = _fechamento_depois_do_aceite(uuid.uuid4(), intruso.id)

    assert alheio == inexistente
    assert alheio[0] == 4004


@pytest.mark.parametrize("papel", [UserRole.technician, UserRole.admin])
def test_ws_equipe_em_chamado_inexistente_tambem_recebe_4004(banco_real, papel):
    """Equipe passa pela visibilidade, mas não por chamado que não existe: a
    sala de um id qualquer não pode abrir para ninguém."""
    fabrica, criados = banco_real
    pessoa = _usuario(papel)
    asyncio.run(_grava(fabrica, criados, pessoa))

    p1, p2, p3 = _ws_ambiente(fabrica)
    with p1, p2, p3:
        codigo, _ = _fechamento_depois_do_aceite(uuid.uuid4(), pessoa.id)

    assert codigo == 4004


def test_ws_chamado_excluido_com_a_sala_aberta_fecha_4004(banco_real):
    """Antes, o laço só saía (`break`) e a tela via uma queda comum, que ela
    trata reconectando. O 4004 diz que não há mais o que reabrir."""
    fabrica, criados = banco_real
    dono = _usuario(UserRole.client)
    chamado = _chamado(dono)
    asyncio.run(_grava(fabrica, criados, dono))
    asyncio.run(_grava(fabrica, criados, chamado))

    async def _exclui():
        async with fabrica() as s:
            await s.execute(delete(Ticket).where(Ticket.id == chamado.id))
            await s.commit()

    p1, p2, p3 = _ws_ambiente(fabrica)
    with p1, p2, p3:
        url = f"/api/v1/ws/tickets/{chamado.id}?token={dono.id}"
        with TestClient(app).websocket_connect(url) as ws:
            ws.send_text("isto não é json")
            assert ws.receive_json()["type"] == "error"
            asyncio.run(_exclui())
            ws.send_text(json.dumps({"content": "ainda está aí?"}))
            with pytest.raises(WebSocketDisconnect) as fechou:
                ws.receive_text()

    assert fechou.value.code == 4004


def test_ws_4001_chega_ao_navegador(banco_real):
    fabrica, criados = banco_real
    dono = _usuario(UserRole.client)
    chamado = _chamado(dono)
    asyncio.run(_grava(fabrica, criados, dono))
    asyncio.run(_grava(fabrica, criados, chamado))

    p1, p2, p3 = _ws_ambiente(fabrica)
    with p1, p2, p3:
        codigo, _ = _fechamento_depois_do_aceite(chamado.id, "nao-e-ninguem")

    assert codigo == 4001


@pytest.mark.parametrize("quem", ["dono", "tecnico", "admin"])
def test_ws_quem_pode_ver_continua_entrando(banco_real, quem):
    fabrica, criados = banco_real
    dono, tecnico, admin = (
        _usuario(UserRole.client),
        _usuario(UserRole.technician),
        _usuario(UserRole.admin),
    )
    chamado = _chamado(dono)
    asyncio.run(_grava(fabrica, criados, dono, tecnico, admin))
    asyncio.run(_grava(fabrica, criados, chamado))
    ator = {"dono": dono, "tecnico": tecnico, "admin": admin}[quem]

    p1, p2, p3 = _ws_ambiente(fabrica)
    with p1, p2, p3:
        url = f"/api/v1/ws/tickets/{chamado.id}?token={ator.id}"
        with TestClient(app).websocket_connect(url) as ws:
            # Socket aberto responde: JSON inválido volta como erro, não fecha.
            ws.send_text("isto não é json")
            assert ws.receive_json()["type"] == "error"


def test_mensagem_com_anexo_chega_pelo_tempo_real_com_o_arquivo(banco_real):
    """FUN-31: o POST com arquivo transmitia a mensagem sem ele, e só um F5 o
    mostrava — e o F5 dava 500. O quadro agora leva o arquivo."""
    fabrica, criados = banco_real
    cliente, tecnico = _usuario(UserRole.client), _usuario(UserRole.technician)
    chamado = _chamado(cliente, tecnico)
    arquivo = _arquivo(tecnico)
    asyncio.run(_grava(fabrica, criados, cliente, tecnico))
    asyncio.run(_grava(fabrica, criados, chamado, arquivo))

    async def _db():
        async with fabrica() as s:
            yield s

    async def _tecnico():
        return tecnico

    p1, p2, p3 = _ws_ambiente(fabrica)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _tecnico
    try:
        with p1, p2, p3:
            tc = TestClient(app)
            with tc.websocket_connect(f"/api/v1/ws/tickets/{chamado.id}?token={cliente.id}") as ws:
                r = tc.post(
                    f"/api/v1/tickets/{chamado.id}/messages",
                    json={"content": "segue o manual", "library_file_id": str(arquivo.id)},
                )
                assert r.status_code == 201, r.text
                quadro = ws.receive_json()
                while quadro["type"] != "message":
                    quadro = ws.receive_json()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    dados = quadro["data"]
    assert dados["library_file_id"] == str(arquivo.id)
    assert dados["library_file_name"] == "manual-do-equipamento.pdf"
    assert dados["library_file_mime"] == "application/pdf"
    assert dados["library_file_size"] == 48_213
    assert dados["library_file_unavailable"] is False
    assert r.json()["library_file_name"] == "manual-do-equipamento.pdf"

    async def _confere():
        async with fabrica() as s:
            return (
                await s.execute(select(ChatMessage).where(ChatMessage.ticket_id == chamado.id))
            ).scalar_one()

    assert asyncio.run(_confere()).library_file_id == arquivo.id
