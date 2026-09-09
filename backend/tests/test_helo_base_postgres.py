"""
Os dois filtros da busca da Helô, executados contra PostgreSQL de verdade.

Por que este arquivo existe, e por que NÃO é mock
--------------------------------------------------
A garantia destes testes É uma cláusula `WHERE`. A lição já foi paga uma vez
neste projeto: o mock responde ao que a consulta pediria com um valor
combinado de antemão, sem olhar o `WHERE` — removendo o filtro de papel de um
`EXISTS`, os 39 testes mockados da Helô continuavam verdes. Aqui é a mesma
classe de defeito, com um dano maior: o filtro que falta manda o procedimento
do aparelho errado para quem opera um instrumento de medição legal.

O caso central é o iBlow 10 Pro
--------------------------------
É o único produto do corpus com DOIS documentos — a ficha comercial e o manual
técnico — e é exatamente o par que se contradiz: a ficha diz que o aparelho
pareia com o "Health App"; o manual diz "i-SOBER". Sem o filtro de tipo, os
dois trechos entram na mesma recuperação e a Helô responde citando a ficha
comercial como fonte técnica.

Os vetores são sintéticos. O que se testa aqui é filtro e ordenação, não
qualidade de embedding: um vetor de verdade não tornaria o teste mais
honesto, só mais lento e menos determinístico.
"""

import asyncio
import math
import shutil
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    HeloChunk,
    HeloDocType,
    HeloDocument,
    Product,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
    helo_chunk_products,
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
        try:
            servidor.cleanup()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(pasta, ignore_errors=True)


@pytest_asyncio.fixture
async def db(url_do_banco):
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        async with async_sessionmaker(bind=conn, expire_on_commit=False)() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


# `ordem` é única por documento — o índice do banco recusa duplicata, e é ele
# que pegou o primeiro rascunho deste arquivo. Um contador por documento é o
# que o script de ingestão também faz.
_ordem_por_documento: dict[str, int] = {}


async def _trecho(db, *, produto, tipo, documento, secao, conteudo, marca, credencial=False):
    doc = (
        await db.execute(
            text("SELECT id FROM helo_documents WHERE filename = :f"), {"f": documento}
        )
    ).scalar_one_or_none()
    if doc is None:
        doc = uuid.uuid4()
        db.add(
            HeloDocument(
                id=doc,
                filename=documento,
                title=documento,
                doc_type=tipo,
                content_hash=uuid.uuid4().hex,
            )
        )
        await db.flush()

    chunk = HeloChunk(
        id=uuid.uuid4(),
        document_id=doc,
        secao=secao,
        ordem=_ordem_por_documento.setdefault(documento, 0),
        conteudo=conteudo,
        exige_credencial_admin=credencial,
        embedding=_vetor(marca),
    )
    _ordem_por_documento[documento] += 1
    db.add(chunk)
    await db.flush()
    await db.execute(helo_chunk_products.insert().values(chunk_id=chunk.id, product_id=produto))
    return chunk


async def _monta_corpus(db):
    """Dois produtos, e o iBlow com ficha E manual — como no corpus real."""
    cliente = User(
        id=uuid.uuid4(),
        name="Suelen",
        email=f"{uuid.uuid4().hex[:8]}@t.com",
        password="x",
        role=UserRole.client,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
    )
    iblow = Product(id=uuid.uuid4(), name="iBlow 10 Pro")
    titan = Product(id=uuid.uuid4(), name="Titan")
    db.add_all([cliente, iblow, titan])
    await db.flush()

    await _trecho(
        db,
        produto=iblow.id,
        tipo=HeloDocType.tecnico,
        documento="Manual_Tecnico_iBlow10Pro.txt",
        secao="10. Conectividade Bluetooth",
        conteudo="O pareamento é feito pelo aplicativo i-SOBER.",
        marca=0.0,
    )
    await _trecho(
        db,
        produto=iblow.id,
        tipo=HeloDocType.comercial,
        documento="iblow10pro.txt",
        secao="Informações Comerciais",
        conteudo="Pareia com o Health App. Valor do aparelho: R$ 4.900,00.",
        marca=0.0,  # MESMA distância do técnico: só o filtro os separa
    )
    await _trecho(
        db,
        produto=titan.id,
        tipo=HeloDocType.tecnico,
        documento="Manual Tecnico Titan.txt",
        secao="9. Integração com Aplicativo",
        conteudo="O Titan integra com o Health App.",
        marca=0.0,  # MESMA distância: só o filtro de produto os separa
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


# ── O filtro de TIPO ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_ficha_comercial_nao_entra_na_busca_tecnica(db):
    """
    O caso que motivou o filtro ter a mesma força do de produto.

    O iBlow 10 Pro é o único produto com ficha E manual, e os dois se
    contradizem sobre o aplicativo: "Health App" na ficha, "i-SOBER" no
    manual. Os dois trechos estão à MESMA distância do vetor da pergunta — é o
    filtro, e só ele, que decide qual a Helô cita.
    """
    cliente, iblow, _ = await _monta_corpus(db)

    achados = await busca_trechos(db, _chamado(cliente, iblow.id), _vetor(0.0))

    assert [t.documento for t in achados] == ["Manual_Tecnico_iBlow10Pro.txt"]
    assert "i-SOBER" in achados[0].conteudo
    assert not any("Health App" in t.conteudo for t in achados)


@pytest.mark.asyncio
async def test_preco_nunca_chega_na_resposta(db):
    """
    A Helô cotando aparelho para quem abriu chamado técnico é o pior resultado.

    O preço vive só nas fichas comerciais, e o filtro de tipo é o que o mantém
    fora do contexto do modelo.
    """
    cliente, iblow, _ = await _monta_corpus(db)

    achados = await busca_trechos(db, _chamado(cliente, iblow.id), _vetor(0.0))

    assert not any("R$" in t.conteudo for t in achados)


# ── O filtro de PRODUTO ───────────────────────────────────────


@pytest.mark.asyncio
async def test_chamado_de_titan_nunca_recebe_trecho_de_iblow(db):
    """
    Todos os manuais falam de sopro, LED e calibração.

    Sem o filtro, a busca traz o aparelho errado justamente onde os textos se
    parecem — que é onde ela mais erra.
    """
    cliente, _, titan = await _monta_corpus(db)

    achados = await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0))

    assert [t.documento for t in achados] == ["Manual Tecnico Titan.txt"]


@pytest.mark.asyncio
async def test_chamado_sem_produto_nao_recupera_nada(db):
    """
    `Ticket.product_id` é nulável, e sem produto não há como garantir o aparelho.

    Buscar em tudo seria a versão sem filtro do defeito que este módulo existe
    para impedir. Nada encontrado faz a Helô escalar, que é o certo para uma
    pergunta que ela não pode responder com segurança.
    """
    cliente, _, _ = await _monta_corpus(db)

    assert await busca_trechos(db, _chamado(cliente, None), _vetor(0.0)) == []


# ── Embedding ausente ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_trecho_sem_embedding_fica_de_fora(db):
    """Ordenar por distância nula colocaria trecho não embutido no topo."""
    cliente, _, titan = await _monta_corpus(db)
    doc = uuid.uuid4()
    db.add(
        HeloDocument(
            id=doc,
            filename="Sem embedding.txt",
            title="Sem embedding",
            doc_type=HeloDocType.tecnico,
            content_hash=uuid.uuid4().hex,
        )
    )
    await db.flush()
    chunk = HeloChunk(
        id=uuid.uuid4(),
        document_id=doc,
        secao="1. Nada",
        ordem=0,
        conteudo="ainda não embutido",
        embedding=None,
    )
    db.add(chunk)
    await db.flush()
    await db.execute(helo_chunk_products.insert().values(chunk_id=chunk.id, product_id=titan.id))
    await db.flush()

    achados = await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0))

    assert all(t.secao != "1. Nada" for t in achados)


# ── O bloco de contexto ───────────────────────────────────────


@pytest.mark.asyncio
async def test_sem_achado_o_bloco_recebe_a_string_literal(db):
    """
    Bloco vazio o modelo lê como "não recebi contexto" e responde do bolso.

    A string explícita casa com a regra do prompt e produz escalada — que é o
    comportamento que a Fase 2 inteira depende de ter.
    """
    assert monta_base_tecnica([]) == NADA_ENCONTRADO
    assert NADA_ENCONTRADO == "NADA ENCONTRADO"


@pytest.mark.asyncio
async def test_o_bloco_leva_a_fonte_de_cada_trecho(db):
    """A resposta cita, e a fonte precisa viajar com o trecho até o modelo."""
    cliente, _, titan = await _monta_corpus(db)

    bloco = monta_base_tecnica(await busca_trechos(db, _chamado(cliente, titan.id), _vetor(0.0)))

    assert "Fonte: Manual Tecnico Titan.txt, 9. Integração com Aplicativo" in bloco
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
        produto=titan.id,
        tipo=HeloDocType.tecnico,
        documento="Manual Tecnico Titan.txt",
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
    cliente, iblow, titan = await _monta_corpus(db)
    await _trecho(
        db,
        produto=titan.id,
        tipo=HeloDocType.tecnico,
        documento="Manual Tecnico Titan.txt",
        secao="99. Assunto sem relação",
        conteudo="Texto que nada tem a ver com a pergunta.",
        marca=_marca_para_distancia(0.40),
    )
    await db.flush()

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
            produto=titan.id,
            tipo=HeloDocType.tecnico,
            documento="Manual Tecnico Titan.txt",
            secao=secao,
            conteudo="corpo",
            marca=_marca_para_distancia(distancia),
        )
    await db.flush()

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
    cliente = User(
        id=uuid.uuid4(),
        name="Suelen",
        email=f"{uuid.uuid4().hex[:8]}@t.com",
        password="x",
        role=UserRole.client,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
    )
    produto = Product(id=uuid.uuid4(), name="Só longe")
    db.add_all([cliente, produto])
    await db.flush()
    await _trecho(
        db,
        produto=produto.id,
        tipo=HeloDocType.tecnico,
        documento="Manual.txt",
        secao="1. Único trecho, e longe",
        conteudo="corpo",
        marca=_marca_para_distancia(0.45),
    )
    await db.flush()

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
    então tirar a guarda passa despercebido contra Postgres de verdade
    (conferido: a mutação sobreviveu ao arquivo inteiro).

    O que a guarda compra é a resposta deixar de depender da semântica de NULL
    do SQL. No dia em que alguém trocar o `==` por um `IN (...)` ou por um
    LEFT JOIN, `NULL` volta a casar coisa — e a Helô passa a responder sobre
    um aparelho que o chamado nunca disse qual era.
    """

    class SessaoQueRecusa:
        async def execute(self, *args, **kwargs):
            raise AssertionError("buscou no banco mesmo sem produto no chamado")

    cliente = User(id=uuid.uuid4(), name="x", email="x@t.com", password="x", role=UserRole.client)

    assert await busca_trechos(SessaoQueRecusa(), _chamado(cliente, None), _vetor(0.0)) == []
