"""
O pooling, provado pela PROPRIEDADE e não pela forma.

Por que a forma não serve
--------------------------
Pooling errado devolve vetor de dimensão certa, tipo certo, sem exceção. Um
teste que confere `shape == (n, 1024)` passa com a máscara ignorada, com o CLS
no lugar da média e sem normalização. É a mesma classe do redator de senha:
falha sem ruído.

O que o teste faz em vez disso
-------------------------------
Usa a saída CRUA do modelo, guardada como fixture, agrupa com o código de
verdade, grava no Postgres e roda a BUSCA. O que se afirma é o resultado da
busca, não o formato do vetor.

⚠️ E aqui vai uma correção medida, porque a intuição erra: **a ordenação
sozinha NÃO discrimina**. O par "idioma" contra "reconhecimento facial" é
distante demais — com a máscara ignorada, com só o CLS ou sem normalizar, o
trecho certo continua ganhando. Medido, os quatro cenários acertam a ordem; o
que muda é a distância (0,2533 no certo, 0,4133 sem máscara, 0,4499 com CLS).

Então o teste afirma três coisas diferentes, cada uma pegando um defeito:

1. **Invariância sob preenchimento** — o vetor de um texto tem que ser o mesmo
   sozinho ou dentro de um lote com padding. É o discriminador da máscara, e
   não depende de limiar escolhido a dedo: com máscara dá 0,007; sem, 0,133
   para o texto mais preenchido.
2. **Ordem E distância na busca real** — o limiar separa 0,2533 (certo) de
   0,41+ (quebrado), com folga.
3. **Norma unitária** — esta É um teste de forma, e é assim de propósito:
   normalização não afeta distância de cosseno (medido: número idêntico), então
   nenhuma afirmação sobre busca poderia pegá-la.

A fixture é a saída do modelo `bge-m3` quantizado para quatro textos
SINTÉTICOS — paráfrases, nunca trecho de manual, que não entra no repositório.
Guardar a saída em vez do modelo tira uma dependência de 543 MB do teste.
"""

import asyncio
import json
import shutil
import uuid
from pathlib import Path

import numpy as np
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
from app.services.helo_base import busca_trechos
from servico_embedding.pooling import agrupa
from tests.test_dashboard_postgres import _sobe_postgres

_DADOS = Path(__file__).parent / "dados"

# Medidos com a fixture: pooling certo dá 0,2533 de distância entre a pergunta
# e o trecho certo; máscara ignorada dá 0,4133; só CLS dá 0,4499. O limiar fica
# no meio, longe dos dois.
_LIMIAR_DE_PROXIMIDADE = 0.32

# Com máscara, o mesmo texto sozinho ou em lote difere 0,007 (arredondamento de
# fp16 na fixture). Sem máscara, 0,133 no texto mais preenchido.
_TOLERANCIA_DE_INVARIANCIA = 0.02


@pytest.fixture(scope="module")
def lote():
    d = np.load(_DADOS / "lote_do_modelo.npz", allow_pickle=False)
    return {
        "tokens": d["tokens"].astype(np.float32),
        "mascara": d["mask"].astype(np.int64),
        "nomes": [str(x) for x in d["nomes"]],
    }


@pytest.fixture(scope="module")
def isolados():
    return np.load(_DADOS / "embutidos_isolados.npz", allow_pickle=False)


@pytest.fixture(scope="module")
def textos():
    return json.loads((_DADOS / "textos.json").read_text(encoding="utf-8"))


# ── 1. Invariância sob preenchimento: o teste da máscara ──────


def test_o_vetor_nao_muda_por_causa_do_preenchimento(lote, isolados):
    """
    O discriminador da máscara de atenção, e ele não usa número escolhido a dedo.

    O lote é preenchido até o texto mais longo. Se o preenchimento entrar na
    média, o vetor de um texto passa a depender de com QUEM ele foi embutido —
    a mesma pergunta daria vetores diferentes conforme o lote, e a busca
    passaria a devolver coisas diferentes para a mesma pergunta.

    Com a máscara, o vetor é o mesmo dos dois jeitos. Medido: 0,007 de
    diferença (arredondamento de fp16 da fixture) contra 0,133 sem a máscara,
    no texto mais preenchido.
    """
    agrupados = agrupa(lote["tokens"], lote["mascara"])

    for nome in ("pergunta_idioma", "titan_idioma", "phoebus_facial"):
        i = lote["nomes"].index(nome)
        sozinho = isolados[f"{nome}__tokens"].astype(np.float32)[None, :, :]
        mascara_cheia = isolados[f"{nome}__mask"].astype(np.int64)[None, :]
        esperado = agrupa(sozinho, mascara_cheia)[0]

        distancia = 1 - float(np.dot(agrupados[i], esperado))
        assert distancia < _TOLERANCIA_DE_INVARIANCIA, (
            f"{nome}: o vetor mudou {distancia:.4f} por estar num lote com preenchimento — "
            "a máscara de atenção está sendo ignorada"
        )


def test_sem_a_mascara_o_preenchimento_contamina(lote, isolados):
    """
    A prova de que o teste acima discrimina.

    Sem esta contraprova, `test_o_vetor_nao_muda...` poderia estar passando
    porque a propriedade é trivial, e não porque o código a garante.
    """
    tokens = lote["tokens"]
    i = lote["nomes"].index("pergunta_idioma")  # o mais preenchido: 39 de 49

    # Pooling SEM máscara: média sobre o comprimento inteiro do lote.
    sem_mascara = tokens[i].mean(axis=0)
    sem_mascara = sem_mascara / np.linalg.norm(sem_mascara)

    sozinho = isolados["pergunta_idioma__tokens"].astype(np.float32)[None, :, :]
    esperado = agrupa(sozinho, isolados["pergunta_idioma__mask"].astype(np.int64)[None, :])[0]

    assert 1 - float(np.dot(sem_mascara, esperado)) > _TOLERANCIA_DE_INVARIANCIA * 3


# ── 3. Norma: o único teste de forma, e o porquê ──────────────


def test_o_vetor_sai_normalizado(lote):
    """
    Este É um teste de forma, e é o único jeito de pegar este defeito.

    Normalização NÃO muda distância de cosseno — medido, o número sai idêntico,
    porque o cosseno normaliza por dentro. Nenhuma afirmação sobre o resultado
    da busca conseguiria pegar a falta dela.

    Ela continua valendo: com vetor normalizado, trocar o operador da busca
    para L2 ou produto interno preserva a ordem. É seguro contra uma mudança
    futura, e é honesto dizer que é só isso.
    """
    normas = np.linalg.norm(agrupa(lote["tokens"], lote["mascara"]), axis=1)

    assert np.allclose(normas, 1.0, atol=1e-5)


def test_o_divisor_da_media_nao_muda_o_vetor_final(lote):
    """
    Registra uma NÃO-diferença, porque ela parece um defeito e não é.

    Eu escrevi este teste primeiro afirmando o contrário — que dividir pelo
    comprimento do lote em vez dos tokens reais estragaria o vetor. A mutação
    provou que não: a diferença é um fator de escala, e a normalização o apaga.
    Os dois divisores dão exatamente o mesmo vetor final.

    O teste fica invertido, prendendo a verdade: para ninguém "consertar" o
    divisor achando que achou um defeito, e para ninguém gastar teste tentando
    prender uma diferença que não existe. Só voltaria a importar se a
    normalização saísse — e ela tem teste próprio logo acima.
    """
    i = lote["nomes"].index("pergunta_idioma")
    reais = int(lote["mascara"][i].sum())
    comprimento = lote["tokens"].shape[1]
    assert reais < comprimento, "a fixture precisa ter preenchimento para este teste valer"

    soma = (lote["tokens"][i] * lote["mascara"][i][:, None]).sum(0)
    por_reais = soma / reais
    por_comprimento = soma / comprimento

    assert not np.allclose(por_reais, por_comprimento), "antes de normalizar, são diferentes"
    assert np.allclose(
        por_reais / np.linalg.norm(por_reais),
        por_comprimento / np.linalg.norm(por_comprimento),
        atol=1e-6,
    ), "depois de normalizar, são o mesmo vetor"


# ── 2. A busca real, contra Postgres ──────────────────────────


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


@pytest.mark.asyncio
async def test_a_busca_devolve_o_trecho_de_idioma_e_nao_o_de_reconhecimento_facial(
    db, lote, textos
):
    """
    A propriedade, ponta a ponta: pooling → banco → busca.

    "Como coloco o aparelho em português" tem que trazer a seção de idioma, e
    não a de reconhecimento facial nem a de impressora — e tem que trazê-la
    PERTO. O limiar é o que discrimina: com o pooling certo a distância é
    0,2533; com a máscara ignorada, 0,4133; com só o CLS, 0,4499.
    """
    vetores = agrupa(lote["tokens"], lote["mascara"])
    indice = {n: i for i, n in enumerate(lote["nomes"])}

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
    produto = Product(id=uuid.uuid4(), name="Titan")
    documento = HeloDocument(
        id=uuid.uuid4(),
        filename="manual.txt",
        title="Manual Técnico",
        doc_type=HeloDocType.tecnico,
        content_hash=uuid.uuid4().hex,
    )
    db.add_all([cliente, produto, documento])
    await db.flush()

    for ordem, nome in enumerate(("titan_idioma", "phoebus_facial", "phoebus_impressora")):
        trecho = HeloChunk(
            id=uuid.uuid4(),
            document_id=documento.id,
            secao=nome,
            ordem=ordem,
            conteudo=textos[nome],
            embedding=vetores[indice[nome]].tolist(),
        )
        db.add(trecho)
        await db.flush()
        await db.execute(
            helo_chunk_products.insert().values(chunk_id=trecho.id, product_id=produto.id)
        )
    await db.flush()

    chamado = Ticket(
        id=uuid.uuid4(),
        protocol=f"HS-{uuid.uuid4().hex[:8]}",
        title="idioma",
        description="corpo",
        priority=TicketPriority.medium,
        category=TicketCategory.hardware,
        status=TicketStatus.in_progress,
        creator_id=cliente.id,
        product_id=produto.id,
        ai_enabled=True,
        sla_response_breach=False,
        sla_resolve_breach=False,
        sla_total_paused_ms=0,
        auto_closed=False,
        reopen_count=0,
    )

    achados = await busca_trechos(db, chamado, vetores[indice["pergunta_idioma"]].tolist())

    assert [t.secao for t in achados][
        0
    ] == "titan_idioma", "a seção de idioma tinha que vir primeiro para a pergunta sobre idioma"
    assert achados[0].distancia < _LIMIAR_DE_PROXIMIDADE, (
        f"distância {achados[0].distancia:.4f} acima do limiar {_LIMIAR_DE_PROXIMIDADE} — "
        "o pooling está degradando o vetor (máscara ignorada dá 0,41; só CLS dá 0,45)"
    )
    assert achados[1].distancia > achados[0].distancia


# ── As guardas de forma ───────────────────────────────────────


def test_recusa_saida_que_nao_e_por_token():
    """
    Passar um vetor já agrupado por engano daria média de médias, em silêncio.

    O modelo devolve `(textos, tokens, dim)`. Quem chamar com `(textos, dim)`
    está agrupando duas vezes, e o resultado seria um vetor plausível e errado.
    """
    with pytest.raises(ValueError, match="esperava"):
        agrupa(np.zeros((2, 1024), dtype=np.float32), np.ones((2, 1), dtype=np.int64))


def test_recusa_mascara_que_nao_casa_com_os_tokens():
    """Máscara de outro lote alinharia preenchimento com conteúdo."""
    with pytest.raises(ValueError, match="não casa"):
        agrupa(np.zeros((2, 5, 1024), dtype=np.float32), np.ones((2, 7), dtype=np.int64))


def test_recusa_texto_sem_token_real():
    """
    Máscara toda zero daria divisão por zero e um vetor de NaN.

    NaN no banco não estoura: ele fica lá e a distância de cosseno contra ele
    vira NaN, que o Postgres ordena por último — o trecho some da busca sem
    ninguém saber por quê.
    """
    with pytest.raises(ValueError, match="sem nenhum token real"):
        agrupa(np.ones((1, 5, 1024), dtype=np.float32), np.zeros((1, 5), dtype=np.int64))
