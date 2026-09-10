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
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    ChatMessage,
    Company,
    Equipment,
    Group,
    Product,
    Ticket,
    TicketCategory,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
    ticket_equipments,
)
from app.services import helo
from app.services.helo import _humano_ja_esta_na_conversa, responde_triagem
from app.services.helo_prompt import monta_cadastro, monta_conversa
from app.utils.sla import SP_TZ

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
            # A extensão vem ANTES do create_all: `helo_chunks.embedding` é
            # `vector(1024)`, e num banco sem a extensão o create_all morre com
            # `type "vector" does not exist` — derrubando este módulo inteiro
            # por causa de uma tabela que ele nem usa. Em produção quem cria é
            # a migration; aqui não roda migration nenhuma.
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


@pytest.fixture
def helo_ligada(monkeypatch):
    monkeypatch.setattr(helo, "get_settings", lambda: MagicMock(helo_enabled=True))


@pytest.fixture
def modelo_diz(monkeypatch):
    """
    O banco é de verdade; o modelo e o embedding, não.

    `embute_um` devolvendo None é de propósito e não é preguiça: sem vetor a
    busca nem é tentada, e é isso que permite exercitar a montagem do contexto
    contra Postgres sem depender do serviço de embedding estar de pé.
    """

    def _diz(texto):
        espiao = AsyncMock(return_value=texto)
        monkeypatch.setattr(helo, "responde_como_helo", espiao)
        monkeypatch.setattr(helo, "embute_um", AsyncMock(return_value=None))
        return espiao

    return _diz


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


async def _com_cadastro_completo(db, com_empresa=True):
    """
    O caso real: cliente de uma empresa, produto escolhido e um aparelho com
    série. Cada um desses três sai de uma tabela diferente.

    `com_empresa=False` é o outro caso real: `User.company_id` é nulável, e
    pessoa física abre chamado.
    """
    grupo = Group(id=uuid.uuid4(), name="Grupo Sintético")
    empresa = Company(id=uuid.uuid4(), group_id=grupo.id, name="Transportes Aurora")
    produto = Product(id=uuid.uuid4(), name="Titan", is_active=True)
    db.add_all([grupo, empresa, produto])
    await db.flush()

    cliente = _usuario(UserRole.client, "Suelen")
    cliente.company_id = empresa.id if com_empresa else None
    db.add(cliente)

    chamado = _chamado(cliente)
    chamado.product_id = produto.id
    db.add(chamado)
    await db.flush()

    aparelho = Equipment(
        id=uuid.uuid4(),
        product_id=produto.id,
        # Nome DIFERENTE do produto de propósito: com os dois iguais, um
        # teste que só procura "Titan" no bloco continuaria verde depois de
        # a consulta do produto sumir — o equipamento cobriria o buraco.
        name="Bafômetro do pátio",
        serial_number="WATFR01-73041",
        is_active=True,
    )
    db.add(aparelho)
    await db.flush()
    await db.execute(
        ticket_equipments.insert().values(ticket_id=chamado.id, equipment_id=aparelho.id)
    )

    return cliente, chamado, aparelho


async def _chamado_antigo(db, criador, aparelho, titulo):
    """Um chamado já fechado daquele aparelho, mais velho que o de agora."""
    antigo = _chamado(criador)
    antigo.title = titulo
    antigo.status = TicketStatus.closed
    antigo.created_at = _AGORA - timedelta(days=40)
    db.add(antigo)
    await db.flush()
    await db.execute(
        ticket_equipments.insert().values(ticket_id=antigo.id, equipment_id=aparelho.id)
    )
    return antigo


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
async def test_depois_do_tecnico_ela_nao_fala(db, helo_ligada, modelo_diz):
    """
    O cenário inteiro, ponta a ponta, contra o banco.

    Saudação dela (1ª fala), técnico escreve, cliente responde. Pela contagem
    ela ainda teria crédito de sobra; pela guarda, não fala — e a guarda vem
    antes do modelo, que é o que o espião afirma. Chamar o LLM para descobrir
    que não era para falar seria gastar dinheiro para chegar ao mesmo silêncio.
    """
    espiao = modelo_diz("não devia chegar aqui")
    tecnico = _usuario(UserRole.technician, "Erick")
    db.add(tecnico)
    cliente, chamado = await _cenario(db, autores_das_falas=[(tecnico, "Consegue tirar uma foto?")])

    fala = await responde_triagem(db, chamado, cliente, "Segue a foto do visor")

    assert fala is None
    espiao.assert_not_awaited()


@pytest.mark.asyncio
async def test_sem_a_equipe_ela_responde_normalmente(db, helo_ligada, modelo_diz):
    """
    A guarda oposta, contra o banco: sem humano na conversa ela atende.

    E o contexto que chega ao modelo sai do banco de verdade — é o que separa
    este teste de um que apenas verifica que alguém foi chamado.
    """
    espiao = modelo_diz("Confere se o cabo está firme e me conta.")
    cliente, chamado = await _cenario(db)

    fala = await responde_triagem(db, chamado, cliente, "O aparelho não liga desde ontem")

    assert fala is not None
    assert "cabo" in fala.mensagem.content
    _sistema, contexto = espiao.await_args.args
    assert "Chamado sintético" in contexto
    assert "O aparelho não liga desde ontem" in contexto


@pytest.mark.asyncio
async def test_a_saida_dela_persiste_no_banco_com_o_historico(db, helo_ligada, modelo_diz):
    """
    A coluna nova e a linha de histórico, contra o banco de verdade.

    Mock não prova que a coluna existe: `MagicMock` aceita `helo_saiu` sem
    piscar, e um modelo sem a migration correspondente passaria verde na suíte
    inteira e falharia no primeiro deploy. E o histórico é `INSERT` de fato —
    campo com tamanho, chave estrangeira, `user_id` nulo. Aqui isso é exercido.
    """
    modelo_diz("Isso precisa de um técnico.\nESCALAR: dano físico no visor")
    cliente, chamado = await _cenario(db)

    await responde_triagem(db, chamado, cliente, "a tela quebrou")
    await db.flush()

    salvo = (await db.execute(select(Ticket).where(Ticket.id == chamado.id))).scalar_one()
    assert salvo.helo_saiu is True
    assert salvo.ai_enabled is True, "o modelo escalou; o botão do técnico não é dele"

    linhas = (
        (await db.execute(select(TicketHistory).where(TicketHistory.ticket_id == chamado.id)))
        .scalars()
        .all()
    )
    (saida,) = [linha for linha in linhas if linha.field == "helo_saiu"]
    assert saida.user_id is None
    assert saida.comment == "dano físico no visor"


@pytest.mark.asyncio
async def test_pedido_de_humano_desliga_o_botao_no_banco(db, helo_ligada, modelo_diz):
    """A exceção, também contra o banco: aqui quem quis sair da IA foi o cliente."""
    modelo_diz("não deveria chegar ao modelo")
    cliente, chamado = await _cenario(db)

    await responde_triagem(db, chamado, cliente, "quero falar com uma pessoa")
    await db.flush()

    salvo = (await db.execute(select(Ticket).where(Ticket.id == chamado.id))).scalar_one()
    assert salvo.helo_saiu is True
    assert salvo.ai_enabled is False


@pytest.mark.asyncio
async def test_o_cadastro_traz_o_que_o_cliente_nao_precisa_repetir(db):
    """
    O bloco CADASTRO é a diferença entre esta Helô e a do WhatsApp.

    Lá ela PEDIA modelo e número de série porque não havia cadastro. Aqui os
    dois já foram escolhidos no formulário — e chegam por três junções
    diferentes: produto, empresa e equipamento. Mock não prova junção; é por
    isso que este teste mora aqui e não no arquivo de mock.
    """
    cliente, chamado, _ = await _com_cadastro_completo(db)

    bloco = await monta_cadastro(db, chamado, cliente)

    assert "Produto: Titan" in bloco
    assert "Bafômetro do pátio série WATFR01-73041" in bloco
    assert "Transportes Aurora" in bloco
    assert "Chamado sintético" in bloco
    assert chamado.category.value in bloco


@pytest.mark.asyncio
async def test_o_cadastro_lembra_o_chamado_anterior_do_mesmo_aparelho(db):
    """
    "Vi que este mesmo aparelho abriu chamado sobre bateria" — a memória que o
    WhatsApp nunca teve, e que já estava no banco de graça.

    O chamado ATUAL não pode entrar na própria lista: ela leria "chamados
    anteriores deste equipamento: o que você está abrindo agora".
    """
    cliente, chamado, aparelho = await _com_cadastro_completo(db)
    await _chamado_antigo(db, cliente, aparelho, "Bateria não carregava")

    bloco = await monta_cadastro(db, chamado, cliente)

    assert "Bateria não carregava" in bloco
    assert bloco.count("Chamado sintético") == 1, "o chamado atual não é anterior a si mesmo"


@pytest.mark.asyncio
async def test_o_chamado_do_colega_da_mesma_empresa_conta(db):
    """
    O caso que dá valor à memória, e o motivo de o recorte ser por EMPRESA.

    Numa frota, o aparelho é da empresa e quem abre chamado é quem estava com
    ele naquele dia. Recortar por pessoa apagaria quase todo o histórico
    justamente no cliente em que ele mais serve.
    """
    cliente, chamado, aparelho = await _com_cadastro_completo(db)
    colega = _usuario(UserRole.client, "Marcos")
    colega.company_id = cliente.company_id
    db.add(colega)
    await db.flush()
    await _chamado_antigo(db, colega, aparelho, "Visor apagando sozinho")

    bloco = await monta_cadastro(db, chamado, cliente)

    assert "Visor apagando sozinho" in bloco


@pytest.mark.asyncio
async def test_o_chamado_de_outra_empresa_no_mesmo_aparelho_nao_vaza(db):
    """
    O aparelho é único por PRODUTO desde 26/08, não por dono.

    Ou seja: o mesmo registro de equipamento pode ter atendido duas empresas ao
    longo da vida. Sem o recorte, o título do chamado de uma entraria no prompt
    da outra e sairia pela boca da Helô — um vazamento por um caminho que
    nenhuma tela do sistema abre, e que o cliente leria como fato verificado,
    porque é isso que o bloco CADASTRO diz que ele é.
    """
    cliente, chamado, aparelho = await _com_cadastro_completo(db)
    outro_grupo = Group(id=uuid.uuid4(), name="Outro grupo")
    outra_empresa = Company(id=uuid.uuid4(), group_id=outro_grupo.id, name="Concorrente Ltda")
    db.add_all([outro_grupo, outra_empresa])
    await db.flush()
    estranho = _usuario(UserRole.client, "Cliente de outra empresa")
    estranho.company_id = outra_empresa.id
    db.add(estranho)
    await db.flush()
    await _chamado_antigo(db, estranho, aparelho, "Sigilo da outra empresa")

    bloco = await monta_cadastro(db, chamado, cliente)

    assert "Sigilo da outra empresa" not in bloco
    assert "Chamados anteriores deste equipamento: nenhum" in bloco


@pytest.mark.asyncio
async def test_chamado_de_outro_aparelho_da_mesma_empresa_nao_entra(db):
    """
    "Chamados anteriores DESTE equipamento" — a frase que o bloco escreve.

    Sem o filtro por equipamento a consulta ainda devolve linhas, e linhas
    plausíveis: chamados da mesma empresa, com títulos que combinam. A Helô
    diria "vi que este aparelho já teve problema de bateria" sobre um aparelho
    que nunca teve. Um teste que só olhasse "veio alguma coisa" ficaria verde.
    """
    cliente, chamado, _ = await _com_cadastro_completo(db)
    outro = Equipment(
        id=uuid.uuid4(),
        product_id=chamado.product_id,
        name="Bafômetro da recepção",
        serial_number="WATFR01-99999",
        is_active=True,
    )
    db.add(outro)
    await db.flush()
    await _chamado_antigo(db, cliente, outro, "Problema do outro aparelho")

    bloco = await monta_cadastro(db, chamado, cliente)

    assert "Problema do outro aparelho" not in bloco


@pytest.mark.asyncio
async def test_cliente_sem_empresa_ainda_tem_o_proprio_historico(db):
    """Pessoa física também abre chamado: `User.company_id` é nulável."""
    cliente, chamado, aparelho = await _com_cadastro_completo(db, com_empresa=False)
    await _chamado_antigo(db, cliente, aparelho, "Já tinha dado erro 3")

    bloco = await monta_cadastro(db, chamado, cliente)

    assert "Já tinha dado erro 3" in bloco
    assert "(sem empresa)" in bloco


@pytest.mark.asyncio
async def test_dois_clientes_sem_empresa_nao_compartilham_historico(db):
    """
    O caso que só existe porque o SQLAlchemy é gentil demais.

    Sem o desvio no `de_quem`, o recorte de pessoa física vira
    `User.company_id == None` — e o SQLAlchemy traduz isso para `IS NULL`, que
    casa. Parece funcionar: o cliente vê o próprio histórico e o teste acima
    passa verde. Só que `IS NULL` casa TODA pessoa física do banco, e o
    histórico de um aparelho que trocou de dono iria inteiro para o dono novo.

    É o mesmo vazamento do teste da outra empresa, pela porta que a comparação
    com NULL abre sozinha.
    """
    cliente, chamado, aparelho = await _com_cadastro_completo(db, com_empresa=False)
    dono_antigo = _usuario(UserRole.client, "Dono anterior")
    db.add(dono_antigo)
    await db.flush()
    await _chamado_antigo(db, dono_antigo, aparelho, "Sigilo do dono anterior")

    bloco = await monta_cadastro(db, chamado, cliente)

    assert "Sigilo do dono anterior" not in bloco


@pytest.mark.parametrize(
    "aberto_em,esperado",
    [
        (datetime(2026, 8, 25, 10, 0, tzinfo=SP_TZ), "dentro do horário comercial"),
        (datetime(2026, 8, 28, 22, 0, tzinfo=SP_TZ), "fora do horário comercial"),
    ],
)
@pytest.mark.asyncio
async def test_o_cadastro_diz_se_o_chamado_nasceu_dentro_do_expediente(db, aberto_em, esperado):
    """
    O dado que impede a promessa errada.

    Sem essa linha o modelo não tem como saber que são dez da noite de sexta, e
    "um técnico já vai te atender" sai igual — o cliente espera o fim de semana
    achando que era logo mais. O desenho manda não suavizar esse caso, e a
    matéria-prima para não suavizar é esta.

    Datas fixas de propósito: a mesma conta que o motor de SLA faz, e um teste
    que usasse "agora" trocaria de resposta conforme o dia em que rodasse.
    """
    cliente, chamado, _ = await _com_cadastro_completo(db)
    chamado.created_at = aberto_em

    bloco = await monta_cadastro(db, chamado, cliente)

    assert esperado in bloco


@pytest.mark.asyncio
async def test_falha_de_banco_dentro_dela_nao_leva_a_mensagem_do_cliente(
    db, helo_ligada, modelo_diz, monkeypatch
):
    """
    A guarda do router, e a razão de ela não ser só um `except`.

    A busca vetorial já tem SAVEPOINT próprio. Esta é a outra metade: qualquer
    OUTRA consulta dela — montar o cadastro, montar a conversa, contar as falas
    — pode falhar do mesmo jeito, e em PostgreSQL isso aborta a transação
    inteira. Um `except` que só engole a exceção deixa a sessão em pedaços, e o
    `commit` seguinte morre levando junto a mensagem do cliente. Ficaria
    idêntico a não ter guarda, com o agravante de parecer protegido.

    O `flush` no fim é a prova. Sem o SAVEPOINT ele morre com "current
    transaction is aborted", e a mutação que tira o `begin_nested` derruba
    exatamente este teste.
    """
    from app.routers.chat import _fala_da_helo_sem_derrubar

    modelo_diz("não deveria chegar ao modelo")

    async def _cadastro_que_estoura(sessao, chamado, quem):
        await sessao.execute(text("SELECT * FROM tabela_que_nunca_existiu"))

    monkeypatch.setattr(helo, "monta_cadastro", _cadastro_que_estoura)
    cliente, chamado = await _cenario(db)

    # Na ordem do router: a mensagem do cliente vai para o banco ANTES de ela
    # falar (o `_notify_other_party` consulta e o autoflush a empurra), e só
    # então a Helô roda. É isso que a deixa fora do SAVEPOINT dela.
    do_cliente = _mensagem(chamado, cliente, "não liga desde ontem")
    db.add(do_cliente)
    await db.flush()

    fala = await _fala_da_helo_sem_derrubar(db, chamado, cliente, "não liga desde ontem")

    assert fala is None, "sem fala dela, mas o chamado segue"
    # A prova é uma CONSULTA, e não um `flush` vazio: `flush` sem nada pendente
    # não toca no banco e passaria com a transação em pedaços. Sem o SAVEPOINT
    # este `execute` morre com "current transaction is aborted".
    ainda_la = (
        await db.execute(select(ChatMessage).where(ChatMessage.id == do_cliente.id))
    ).scalar_one_or_none()
    assert ainda_la is not None, "a mensagem do cliente sobreviveu à falha dela"


@pytest.mark.asyncio
async def test_busca_quebrada_nao_leva_junto_a_mensagem_do_cliente(
    db, helo_ligada, modelo_diz, monkeypatch
):
    """
    O pior defeito que este módulo pode ter, e o que nenhum mock enxerga.

    A mensagem do cliente ainda não foi commitada quando a Helô roda: ela nasce
    no mesmo commit da resposta. Em PostgreSQL, uma consulta que estoura aborta
    a transação INTEIRA — e daí não adianta `except`: o `db.add` seguinte ainda
    parece funcionar, e o commit morre levando junto o que o cliente escreveu.
    O sintoma seria "mandei mensagem e ela sumiu", com 500 na tela.

    O `flush` no fim é a prova: sem o SAVEPOINT ele morre com "current
    transaction is aborted".
    """
    modelo_diz("Vou chamar um colega.\nESCALAR: sem base técnica")
    monkeypatch.setattr(helo, "embute_um", AsyncMock(return_value=[0.0] * 1024))

    async def _consulta_que_estoura(sessao, chamado, vetor):
        await sessao.execute(text("SELECT * FROM tabela_que_nunca_existiu"))

    monkeypatch.setattr(helo, "busca_trechos", _consulta_que_estoura)
    cliente, chamado = await _cenario(db)

    fala = await responde_triagem(db, chamado, cliente, "não liga desde ontem")

    assert fala is not None
    assert fala.escalou is True
    await db.flush()


@pytest.mark.asyncio
async def test_a_conversa_termina_na_mensagem_que_acabou_de_chegar(db):
    """
    A fala nova ainda não está no banco quando isto roda: ela nasce no mesmo
    commit da resposta. Sem entrar por parâmetro, o modelo responderia à
    penúltima frase do cliente — o defeito mais difícil de enxergar num log,
    porque a resposta faz sentido, só está uma mensagem atrasada.

    De quebra, o aviso de sistema fica de fora: "status alterado para em
    andamento" não é fala de ninguém, e ocupa contexto pago.
    """
    cliente, chamado = await _cenario(db)
    dele = _mensagem(chamado, cliente, "não liga desde ontem")
    dele.created_at = _AGORA + timedelta(minutes=1)
    aviso = _mensagem(chamado, None, "Status alterado para em andamento")
    aviso.is_system = True
    aviso.created_at = _AGORA + timedelta(minutes=2)
    db.add_all([dele, aviso])
    await db.flush()

    bloco = await monta_conversa(db, chamado, "já troquei o cabo")

    assert bloco.index("Olá! Sou a Helô.") < bloco.index("não liga desde ontem")
    assert bloco.rstrip().endswith("Cliente: já troquei o cabo")
    assert "Status alterado" not in bloco
