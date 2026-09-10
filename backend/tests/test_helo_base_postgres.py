"""
Os filtros da busca da Helô, executados contra PostgreSQL de verdade.

Por que este arquivo existe, e por que NÃO é mock
--------------------------------------------------
A garantia destes testes É uma cláusula `WHERE`. A lição já foi paga uma vez
neste projeto: o mock responde ao que a consulta pediria com um valor
combinado de antemão, sem olhar o `WHERE` — removendo o filtro de papel de um
`EXISTS`, os 39 testes mockados da Helô continuavam verdes. Aqui é a mesma
classe de defeito, com um dano maior: o filtro que falta manda o procedimento
do aparelho errado para quem opera um instrumento de medição legal.

Desde 10/09/2026 a fonte é a Base de Conhecimento
-------------------------------------------------
Os filtros mudaram de natureza com a mudança de fonte. O de TIPO morreu — as
fichas comerciais não entram na Base — e entraram dois: publicação e a
marcação `helo_pode_ler`. E o de produto INVERTEU: artigo sem vínculo vale
para todos os aparelhos.

Cada par abaixo fica à MESMA distância do vetor da pergunta, de propósito: se
dois trechos empatam na distância, só o filtro pode separá-los, e é isso que
cada teste afirma.

Os vetores são sintéticos. O que se testa aqui é filtro e ordenação, não
qualidade de embedding: um vetor de verdade não tornaria o teste mais
honesto, só mais lento e menos determinístico.
"""

import asyncio
import math
import shutil
import uuid
from contextlib import suppress

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    HeloChunk,
    KBArticle,
    KBArticleStatus,
    Product,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
    kb_article_products,
)
from app.services.helo_base import (
    NADA_ENCONTRADO,
    TETO_DE_DISTANCIA,
    busca_trechos,
    monta_base_tecnica,
)
from tests.test_dashboard_postgres import _sobe_postgres

_DIM = 1024


def _vetor(marca: float) -> list[float]:
    """
    Vetor sintético: a primeira posição é a assinatura, o resto é zero.

    Com isso a distância de cosseno entre dois vetores é previsível e o teste
    afirma ORDEM, não semelhança semântica.
    """
    v = [0.0] * _DIM
    v[0] = 1.0
    v[1] = marca
    return v


def _marca_para_distancia(distancia: float) -> float:
    """
    A marca que fica exatamente a `distancia` de `_vetor(0.0)`.

    Entre [1, 0, ...] e [1, m, 0, ...] o cosseno é 1/√(1+m²), então a distância
    é 1 − 1/√(1+m²) e a inversa é √((1/(1−d))² − 1). Existe para o teste dizer
    "um trecho a 0,30 de distância" em vez de plantar um 0,92 sem explicação —
    e para continuar legível se o teto mudar de valor.
    """
    return math.sqrt((1 / (1 - distancia)) ** 2 - 1)


@pytest.fixture(scope="module")
def url_do_banco():
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


# ── Dados sintéticos ──────────────────────────────────────────


def _pessoa(papel: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        name="Suelen" if papel is UserRole.client else "Autora",
        email=f"{uuid.uuid4().hex[:8]}@t.com",
        password="x",
        role=papel,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
    )


_artigos_por_titulo: dict[str, uuid.UUID] = {}
_ordem_por_artigo: dict[uuid.UUID, int] = {}


async def _trecho(
    db,
    *,
    titulo,
    secao,
    conteudo,
    marca,
    produtos=(),
    status=KBArticleStatus.published,
    pode=True,
    credencial=False,
):
    """
    Um trecho sob o artigo `titulo` — criado na primeira vez, com o estado e os
    produtos pedidos. `produtos` vazio é o artigo SEM vínculo, que vale para
    todos os aparelhos.
    """
    artigo_id = _artigos_por_titulo.get(titulo)
    if artigo_id is None or await db.get(KBArticle, artigo_id) is None:
        autora = _pessoa(UserRole.technician)
        db.add(autora)
        await db.flush()
        artigo = KBArticle(
            id=uuid.uuid4(),
            title=titulo,
            content="(os trechos deste teste são gravados direto)",
            slug=f"artigo-{uuid.uuid4().hex}",
            category=TicketCategory.hardware,
            tags=[],
            status=status,
            helo_pode_ler=pode,
            author_id=autora.id,
            view_count=0,
            helpful=0,
            not_helpful=0,
        )
        db.add(artigo)
        await db.flush()
        for produto_id in produtos:
            await db.execute(
                kb_article_products.insert().values(article_id=artigo.id, product_id=produto_id)
            )
        artigo_id = artigo.id
        _artigos_por_titulo[titulo] = artigo_id

    ordem = _ordem_por_artigo.get(artigo_id, 0)
    _ordem_por_artigo[artigo_id] = ordem + 1
    chunk = HeloChunk(
        id=uuid.uuid4(),
        article_id=artigo_id,
        secao=secao,
        ordem=ordem,
        conteudo=conteudo,
        exige_credencial_admin=credencial,
        embedding=_vetor(marca),
    )
    db.add(chunk)
    await db.flush()
    return chunk


_MANUAL_IBLOW = "Manual Técnico do iBlow 10 Pro"
_MANUAL_TITAN = "Manual Técnico do Titan"


async def _monta_corpus(db):
    """
    Dois produtos, e os pares que só um filtro separa — todos à MESMA distância.
    """
    cliente = _pessoa(UserRole.client)
    iblow = Product(id=uuid.uuid4(), name="iBlow 10 Pro")
    titan = Product(id=uuid.uuid4(), name="Titan")
    db.add_all([cliente, iblow, titan])
    await db.flush()

    await _trecho(
        db,
        titulo=_MANUAL_IBLOW,
        produtos=[iblow.id],
        secao="10. Conectividade Bluetooth",
        conteudo="O pareamento é feito pelo aplicativo i-SOBER.",
        marca=0.0,
    )
    await _trecho(
        db,
        titulo="Rascunho sobre o iBlow",
        produtos=[iblow.id],
        status=KBArticleStatus.draft,
        secao="Rascunho",
        conteudo="Texto ainda não revisado: pareia com o Health App.",
        marca=0.0,
    )
    await _trecho(
        db,
        titulo="Procedimento interno do iBlow",
        produtos=[iblow.id],
        pode=False,
        secao="Só para a equipe",
        conteudo="Valor da calibração para revenda: R$ 900,00.",
        marca=0.0,
    )
    await _trecho(
        db,
        titulo=_MANUAL_TITAN,
        produtos=[titan.id],
        secao="9. Integração com Aplicativo",
        conteudo="O Titan integra com o Health App.",
        marca=0.0,
    )
    await db.flush()
    return cliente, iblow, titan


def _chamado(cliente, produto_id):
    return Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-{uuid.uuid4().hex[:8]}",
        title="Não pareia",
        description="corpo",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.in_progress,
        creator_id=cliente.id,
        product_id=produto_id,
        ai_enabled=True,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        auto_closed=False,
        reopen_count=0,
    )


async def _documentos(db, cliente, produto_id):
    achados = await busca_trechos(db, _chamado(cliente, produto_id), _vetor(0.0))
    return sorted(t.documento for t in achados)


# ── Publicação ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rascunho_nao_entra_na_busca(db):
    """
    Publicado quer dizer que alguém já decidiu que o texto pode ser lido.

    O rascunho empata na distância com o manual publicado e ainda contradiz o
    manual ("Health App" contra "i-SOBER"): sem o filtro, a Helô citaria texto
    que ninguém revisou.
    """
    cliente, iblow, _ = await _monta_corpus(db)

    assert await _documentos(db, cliente, iblow.id) == [_MANUAL_IBLOW]


@pytest.mark.asyncio
async def test_artigo_marcado_para_fora_da_helo_nao_entra(db):
    """
    A marcação é o que mantém um artigo na barra lateral e FORA das respostas.

    Com as fichas comerciais fora da Base, é a proteção que sobrou contra preço
    na boca da Helô: o filtro de tipo morreu, e agora quem separa é isto.
    """
    cliente, iblow, _ = await _monta_corpus(db)

    achados = await busca_trechos(db, _chamado(cliente, iblow.id), _vetor(0.0))

    assert not any("R$" in t.conteudo for t in achados)


@pytest.mark.asyncio
async def test_despublicar_tira_o_texto_das_respostas_no_mesmo_instante(db):
    """
    O filtro é AO VIVO, na consulta — não espera varredura nenhuma.

    É o que torna a varredura periódica aceitável: ela só atrasa texto NOVO
    entrar. Tirar texto errado do ar não pode esperar cinco minutos.
    """
    cliente, _, titan = await _monta_corpus(db)
    artigo = (
        await db.execute(select(KBArticle).where(KBArticle.title == _MANUAL_TITAN))
    ).scalar_one()
    assert await _documentos(db, cliente, titan.id) == [_MANUAL_TITAN]

    artigo.status = KBArticleStatus.archived
    await db.flush()

    assert await _documentos(db, cliente, titan.id) == []


# ── Produto ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chamado_de_titan_nunca_recebe_trecho_de_iblow(db):
    """
    Todos os manuais falam de sopro, LED e calibração.

    Sem o filtro, a busca traz o aparelho errado justamente onde os textos se
    parecem — que é onde ela mais erra.
    """
    cliente, _, titan = await _monta_corpus(db)

    assert await _documentos(db, cliente, titan.id) == [_MANUAL_TITAN]


@pytest.mark.asyncio
async def test_artigo_sem_produto_vale_para_todos_os_aparelhos(db):
    """
    A regra que INVERTEU com a mudança de fonte.

    Na ingestão por arquivo, vínculo ausente era casamento falhado — fatal. No
    artigo, é escolha de quem escreveu, e é como a barra lateral já funciona.
    O mesmo teste prende a outra metade: o artigo sem vínculo aparece nos dois
    chamados, e o vinculado continua só no dele.
    """
    cliente, iblow, titan = await _monta_corpus(db)
    await _trecho(
        db,
        titulo="Como higienizar o bocal",
        secao="Higienização",
        conteudo="Lave o bocal com água morna e sabão neutro.",
        marca=0.0,
    )

    assert await _documentos(db, cliente, titan.id) == sorted(
        ["Como higienizar o bocal", _MANUAL_TITAN]
    )
    assert await _documentos(db, cliente, iblow.id) == sorted(
        ["Como higienizar o bocal", _MANUAL_IBLOW]
    )


@pytest.mark.asyncio
async def test_chamado_sem_produto_nao_recebe_nem_o_artigo_universal(db):
    """
    Todos os aparelhos não é o mesmo que nenhum aparelho.

    Sem saber qual é o aparelho, nem o texto universal tem como ser conferido
    contra o que o cliente tem na mão. Mantido como era antes da mudança de
    fonte — abrir isto é decisão, e não consequência dela.
    """
    cliente, _, _ = await _monta_corpus(db)
    await _trecho(
        db,
        titulo="Como higienizar o bocal",
        secao="Higienização",
        conteudo="Lave o bocal com água morna e sabão neutro.",
        marca=0.0,
    )

    assert await busca_trechos(db, _chamado(cliente, None), _vetor(0.0)) == []


# ── Embedding ausente ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_trecho_sem_embedding_fica_de_fora(db):
    """Ordenar por distância nula colocaria trecho não embutido no topo."""
    cliente, _, titan = await _monta_corpus(db)
    chunk = await _trecho(
        db,
        titulo=_MANUAL_TITAN,
        secao="1. Nada",
        conteudo="ainda não embutido",
        marca=0.0,
    )
    chunk.embedding = None
    await db.flush()

    achados = await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0))

    assert all(t.secao != "1. Nada" for t in achados)


# ── O bloco de contexto ───────────────────────────────────────


def test_sem_achado_o_bloco_recebe_a_string_literal():
    """
    Bloco vazio o modelo lê como "não recebi contexto" e responde do bolso.

    A string explícita casa com a regra do prompt e produz escalada — que é o
    comportamento que a Fase 2 inteira depende de ter.
    """
    assert monta_base_tecnica([]) == NADA_ENCONTRADO
    assert NADA_ENCONTRADO == "NADA ENCONTRADO"


@pytest.mark.asyncio
async def test_o_bloco_leva_a_fonte_de_cada_trecho(db):
    """A resposta cita, e a fonte — o título do artigo — viaja com o trecho."""
    cliente, _, titan = await _monta_corpus(db)

    bloco = monta_base_tecnica(await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0)))

    assert f"Fonte: {_MANUAL_TITAN}, 9. Integração com Aplicativo" in bloco
    assert "O Titan integra com o Health App." in bloco


@pytest.mark.asyncio
async def test_o_bloco_avisa_quando_o_procedimento_exige_senha(db):
    """
    A marca precisa chegar ao modelo em TEXTO — o que ele lê é o que obedece.

    Sem a linha, ele entregaria o procedimento redigido e a escalada seria
    cega: nem ele nem o técnico saberiam por que o cliente não conseguiu.
    """
    cliente, _, titan = await _monta_corpus(db)
    await _trecho(
        db,
        titulo=_MANUAL_TITAN,
        secao="8.5 Configuração Avançada",
        conteudo="Digite a senha: [REDIGIDO — senha de administrador]",
        marca=0.0,
        credencial=True,
    )

    bloco = monta_base_tecnica(await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0)))

    assert "exige senha de administrador" in bloco
    assert "NÃO possui" in bloco


# ── O teto de distância ───────────────────────────────────────


@pytest.mark.asyncio
async def test_trecho_longe_demais_nao_chega_ao_modelo(db):
    """
    O defeito que o teto existe para fechar, medido no corpus real.

    "Como conecto na impressora" num Titan — que não tem impressora — devolvia
    "6. Passo a Passo para Utilização" a 0,2789, e o modelo recebia isso num
    bloco que o prompt chama de "sua única fonte de verdade técnica". Sem teto
    a busca SEMPRE devolve os quatro mais próximos, por mais longe que estejam:
    ordenar não é o mesmo que filtrar.
    """
    cliente, _, titan = await _monta_corpus(db)
    await _trecho(
        db,
        titulo=_MANUAL_TITAN,
        secao="99. Assunto sem relação",
        conteudo="Texto que nada tem a ver com a pergunta.",
        marca=_marca_para_distancia(0.40),
    )

    achados = await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0))

    assert all(t.distancia <= TETO_DE_DISTANCIA for t in achados)
    assert not any("sem relação" in t.secao for t in achados)


@pytest.mark.asyncio
async def test_o_teto_e_este_e_nao_outro(db):
    """
    Prende o VALOR, e não só a existência do corte.

    Os dois trechos ficam de lados opostos de 0,25 por dez milésimos cada. Um
    teto mais frouxo (0,30) deixaria o de fora entrar; um mais apertado (0,20)
    mataria o de dentro. O número saiu de medição contra o corpus real — ver o
    comentário em `helo_base.py` —, e um número medido que ninguém prende volta
    a ser chute na primeira refatoração.
    """
    cliente, _, titan = await _monta_corpus(db)
    for secao, distancia in (("Dentro por pouco", 0.24), ("Fora por pouco", 0.26)):
        await _trecho(
            db,
            titulo=_MANUAL_TITAN,
            secao=secao,
            conteudo="corpo",
            marca=_marca_para_distancia(distancia),
        )

    secoes = [t.secao for t in await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0))]

    assert "Dentro por pouco" in secoes
    assert "Fora por pouco" not in secoes


@pytest.mark.asyncio
async def test_tudo_longe_cai_no_mesmo_nada_encontrado(db):
    """
    Não existe estado novo para "achei, mas está longe".

    Um terceiro estado só daria ao modelo mais uma coisa para interpretar
    errado. Busca vazia e busca toda cortada desembocam no mesmo literal, que é
    o que o prompt reconhece e o que produz escalada.
    """
    cliente = _pessoa(UserRole.client)
    produto = Product(id=uuid.uuid4(), name="Só longe")
    db.add_all([cliente, produto])
    await db.flush()
    await _trecho(
        db,
        titulo="Manual do Só Longe",
        produtos=[produto.id],
        secao="1. Único trecho, e longe",
        conteudo="corpo",
        marca=_marca_para_distancia(0.45),
    )

    achados = await busca_trechos(db, _chamado(cliente, produto.id), _vetor(0.0))

    assert achados == []
    assert monta_base_tecnica(achados) == NADA_ENCONTRADO


@pytest.mark.asyncio
async def test_chamado_sem_produto_nem_chega_a_consultar_o_banco():
    """
    Este é o único teste do arquivo que NÃO usa Postgres, e por um bom motivo.

    A propriedade aqui é "não tocou no banco", não "o WHERE filtrou certo" —
    e contra o banco ela é invisível: com `product_id = None`, o SQL vira
    `= NULL`, que não casa com nada. O resultado sai vazio de qualquer jeito,
    então tirar a guarda passa despercebido contra Postgres de verdade.

    E agora ela vale mais do que valia: com a regra invertida, o artigo SEM
    vínculo casa com qualquer chamado pelo `NOT EXISTS` — inclusive, sem a
    guarda, com o chamado que nunca disse qual é o aparelho.
    """

    class SessaoQueRecusa:
        async def execute(self, *args, **kwargs):
            raise AssertionError("buscou no banco mesmo sem produto no chamado")

    cliente = User(id=uuid.uuid4(), name="x", email="x@t.com", password="x", role=UserRole.client)

    assert await busca_trechos(SessaoQueRecusa(), _chamado(cliente, None), _vetor(0.0)) == []
