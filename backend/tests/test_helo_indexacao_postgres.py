"""
A indexação da base da Helô, contra PostgreSQL de verdade.

Por que contra banco, e não com mock: tudo que importa aqui é o que o banco
guarda entre duas rodadas — o hash, os trechos velhos que ficam quando o
serviço cai, a limpeza do artigo que saiu. Mock afirmaria que `db.add` foi
chamado e passaria com a varredura apagando a base inteira a cada rodada.

O serviço de embedding é o único dublê: `embute` devolve vetores sintéticos, e
é contando as chamadas a ele que se prova o que custa dinheiro — embutir de
novo texto que não mudou.

Como o banco aparece: `TEST_POSTGRES_URL` (o CI), senão `pgserver`. Sem nenhum
dos dois, pula.
"""

import asyncio
import shutil
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import (
    Base,
    HeloChunk,
    HeloIndexacao,
    KBArticle,
    KBArticleStatus,
    TicketCategory,
    User,
    UserRole,
    UserStatus,
)
from app.services import helo_indexacao
from app.services.helo_texto import MARCA_DE_SENHA_REDIGIDA
from tests.test_dashboard_postgres import _sobe_postgres

_DIM = 1024
_ANTIGO = datetime(2020, 1, 1, tzinfo=UTC)


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
    """
    Sessão numa transação revertida no fim, com `commit` que vira SAVEPOINT.

    A varredura dá `commit` por artigo e `rollback` quando um artigo falha. Sem
    `create_savepoint`, esse `rollback` desfaria a transação EXTERNA — e com
    ela os artigos que o próprio teste acabou de criar.
    """
    motor = create_async_engine(url_do_banco)
    async with motor.connect() as conn:
        transacao = await conn.begin()
        fabrica = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with fabrica() as sessao:
            yield sessao
        await transacao.rollback()
    await motor.dispose()


class _Embedding:
    """O serviço de embedding, dublado: conta chamadas e pode estar fora do ar."""

    def __init__(self) -> None:
        self.chamadas = 0
        self.fora = False

    async def __call__(self, textos, *, timeout=None):
        self.chamadas += 1
        if self.fora:
            return None
        return [[1.0, float(i) / 100] + [0.0] * (_DIM - 2) for i, _ in enumerate(textos)]


@pytest.fixture
def embedding(monkeypatch):
    dublê = _Embedding()
    monkeypatch.setattr(helo_indexacao, "embute", dublê)
    return dublê


async def _autor(db) -> User:
    u = User(
        id=uuid.uuid4(),
        name="Autora",
        email=f"{uuid.uuid4().hex[:8]}@t.com",
        password="x",
        role=UserRole.technician,
        status=UserStatus.active,
        lgpd_consent=True,
        email_verified=True,
        onboarding_completed=True,
    )
    db.add(u)
    await db.flush()
    return u


_TEXTO = (
    "## 1. Ligar\n"
    "Pressione o botão lateral por três segundos até a tela acender.\n\n"
    "## 8. Configurações\n\n"
    "### 8.1 Ajustar Data e Hora\n"
    "Menu principal, Settings, Date e Time, e confirme com o botão.\n"
)


async def _artigo(db, autor, *, status=KBArticleStatus.published, pode=True, conteudo=_TEXTO):
    agora = datetime.now(UTC)
    a = KBArticle(
        id=uuid.uuid4(),
        title=f"Manual {uuid.uuid4().hex[:6]}",
        content=conteudo,
        slug=f"manual-{uuid.uuid4().hex}",
        category=TicketCategory.hardware,
        tags=[],
        status=status,
        helo_pode_ler=pode,
        author_id=autor.id,
        view_count=0,
        helpful=0,
        not_helpful=0,
        created_at=agora,
        updated_at=agora,
    )
    db.add(a)
    # `commit`, e não só `flush`: a varredura dá `rollback` quando um artigo
    # falha, e com o SAVEPOINT de `create_savepoint` esse rollback levaria
    # junto tudo que ainda não foi commitado — inclusive os artigos que o
    # próprio teste acabou de criar. Em produção os artigos estão commitados
    # muito antes da rodada; isto só reproduz esse estado.
    await db.commit()
    return a


async def _trechos(db, artigo_id):
    return (
        (
            await db.execute(
                select(HeloChunk).where(HeloChunk.article_id == artigo_id).order_by(HeloChunk.ordem)
            )
        )
        .scalars()
        .all()
    )


# ── O caminho feliz ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_artigo_publicado_vira_trecho_com_vetor(db, embedding):
    artigo = await _artigo(db, await _autor(db))
    artigo_id = artigo.id

    contagem = await helo_indexacao.varre(db)

    trechos = await _trechos(db, artigo_id)
    assert [t.secao for t in trechos] == ["1. Ligar", "8. Configurações → 8.1 Ajustar Data e Hora"]
    assert all(t.embedding is not None for t in trechos)
    assert contagem["indexado"] == 1
    assert await db.get(HeloIndexacao, artigo_id) is not None


@pytest.mark.parametrize("status", [KBArticleStatus.draft, KBArticleStatus.archived])
@pytest.mark.asyncio
async def test_rascunho_e_arquivado_nao_entram(db, embedding, status):
    """Publicado quer dizer que alguém já decidiu que o texto pode ser lido."""
    artigo = await _artigo(db, await _autor(db), status=status)
    artigo_id = artigo.id

    await helo_indexacao.varre(db)

    assert await _trechos(db, artigo_id) == []


@pytest.mark.asyncio
async def test_artigo_marcado_para_fora_da_helo_nao_entra(db, embedding):
    """A marcação mantém o artigo na barra lateral e fora das respostas da IA."""
    artigo = await _artigo(db, await _autor(db), pode=False)
    artigo_id = artigo.id

    await helo_indexacao.varre(db)

    assert await _trechos(db, artigo_id) == []
    assert embedding.chamadas == 0


# ── O que custa dinheiro ──────────────────────────────────────


@pytest.mark.asyncio
async def test_visualizar_o_artigo_nao_paga_embedding_de_novo(db, embedding):
    """
    O argumento que decidiu hash e não `updated_at`, MEDIDO em vez de suposto.

    A tela incrementa `view_count` com um UPDATE a cada visualização, e a coluna
    `updated_at` tem `onupdate`. Este teste prova as duas metades: o carimbo
    MUDA com a visualização — ou seja, reindexar por carimbo pagaria embedding
    por clique —, e a varredura não embute de novo, porque olha o hash.

    O carimbo é comparado com uma data PLANTADA, e não com o valor de antes: o
    `now()` do Postgres é o início da transação, e este teste inteiro roda numa
    transação só. Antes e depois podem dar o mesmo instante — ou o depois pode
    até sair ANTERIOR ao antes, se o antes veio do relógio do Python.
    """
    artigo = await _artigo(db, await _autor(db))
    artigo_id = artigo.id
    await helo_indexacao.varre(db)
    chamadas = embedding.chamadas
    await db.execute(update(KBArticle).where(KBArticle.id == artigo_id).values(updated_at=_ANTIGO))
    await db.commit()

    await db.execute(
        update(KBArticle)
        .where(KBArticle.id == artigo_id)
        .values(view_count=KBArticle.view_count + 1)
    )
    await db.commit()
    carimbo = (
        await db.execute(select(KBArticle.updated_at).where(KBArticle.id == artigo_id))
    ).scalar_one()

    await helo_indexacao.varre(db)

    assert carimbo != _ANTIGO, "o carimbo muda com a visualização — é por isso que não serve"
    assert embedding.chamadas == chamadas, "texto igual não pode pagar embedding de novo"


@pytest.mark.asyncio
async def test_texto_editado_reindexa(db, embedding):
    artigo = await _artigo(db, await _autor(db))
    artigo_id = artigo.id
    await helo_indexacao.varre(db)

    artigo.content = "## 1. Ligar\nSegure o botão lateral até ouvir dois bipes curtos e soltar.\n"
    await db.commit()
    await helo_indexacao.varre(db)

    trechos = await _trechos(db, artigo_id)
    assert [t.secao for t in trechos] == ["1. Ligar"]
    assert "dois bipes" in trechos[0].conteudo


# ── Auto-curativa ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_servico_fora_deixa_o_velho_no_lugar_e_a_proxima_rodada_conserta(db, embedding):
    """
    O requisito que escolheu a varredura: uma base que ninguém olha precisa se
    consertar sozinha. Com o serviço fora, NADA é gravado — trecho sem vetor
    seria invisível para a busca e ainda marcaria o artigo como indexado.
    """
    artigo = await _artigo(db, await _autor(db))
    # O id sai AGORA: a rodada com o serviço fora dá `rollback`, que expira os
    # objetos da sessão, e ler atributo de objeto expirado fora de contexto
    # síncrono é `MissingGreenlet`.
    artigo_id = artigo.id
    await helo_indexacao.varre(db)
    hash_velho = (await db.get(HeloIndexacao, artigo_id)).content_hash

    artigo.content = "## 1. Ligar\nSegure o botão lateral até ouvir dois bipes curtos e soltar.\n"
    await db.commit()
    embedding.fora = True
    contagem = await helo_indexacao.varre(db)

    assert contagem["sem_embedding"] == 1
    assert "três segundos" in (await _trechos(db, artigo_id))[0].conteudo, "o velho fica"
    assert (await db.get(HeloIndexacao, artigo_id)).content_hash == hash_velho

    embedding.fora = False
    await helo_indexacao.varre(db)

    assert "dois bipes" in (await _trechos(db, artigo_id))[0].conteudo


@pytest.mark.asyncio
async def test_despublicar_limpa_os_trechos_na_varredura(db, embedding):
    """A busca já não os devolvia — ela filtra ao vivo. Isto é arrumação."""
    artigo = await _artigo(db, await _autor(db))
    artigo_id = artigo.id
    await helo_indexacao.varre(db)

    artigo.status = KBArticleStatus.archived
    await db.commit()
    contagem = await helo_indexacao.varre(db)

    assert contagem["limpos"] == 1
    assert await _trechos(db, artigo_id) == []
    assert await db.get(HeloIndexacao, artigo_id) is None


@pytest.mark.asyncio
async def test_servico_fora_encerra_a_rodada_no_primeiro_artigo(db, embedding):
    """
    Seguir seria pagar um timeout por artigo para chegar ao mesmo lugar: com o
    serviço fora, o segundo artigo falharia exatamente como o primeiro.
    """
    autor = await _autor(db)
    await _artigo(db, autor)
    await _artigo(db, autor)
    embedding.fora = True

    contagem = await helo_indexacao.varre(db)

    assert embedding.chamadas == 1
    assert contagem["sem_embedding"] == 1


# ── A senha ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_senha_nao_redigida_nao_e_indexada_e_nao_derruba_os_outros(db, embedding):
    """
    Numa varredura de fundo não há quem parar: o artigo com cara de senha fica
    de fora, com ERRO no log a cada rodada até alguém mexer nele, e os outros
    seguem. Parar a rodada inteira deixaria a base toda desatualizada por causa
    de um artigo.
    """
    autor = await _autor(db)
    ruim = await _artigo(
        db, autor, conteudo="## Menu\nDigite a senha 987654 e confirme a entrada.\n"
    )
    bom = await _artigo(db, autor)
    ruim_id, bom_id = ruim.id, bom.id

    with patch.object(helo_indexacao, "logger") as log:
        contagem = await helo_indexacao.varre(db)

    assert await _trechos(db, ruim_id) == []
    assert len(await _trechos(db, bom_id)) == 2
    assert contagem["credencial"] == 1
    log.error.assert_called_once()
    assert "987654" not in str(log.error.call_args), "o log não transcreve a senha"


@pytest.mark.asyncio
async def test_a_marca_da_importacao_vira_aviso_no_trecho(db, embedding):
    artigo = await _artigo(
        db,
        await _autor(db),
        conteudo=f"## 7. Menu avançado\nSenha de configuração: {MARCA_DE_SENHA_REDIGIDA}\n"
        "Escolha a opção de exibição do resultado e confirme.\n",
    )
    artigo_id = artigo.id

    await helo_indexacao.varre(db)

    assert (await _trechos(db, artigo_id))[0].exige_credencial_admin is True


# ── O laço ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rodada_que_levanta_nao_mata_o_laco():
    """
    Sem o `except` em volta da rodada, uma exceção encerra a task e a base para
    de acompanhar a Base de Conhecimento até o próximo restart — calada.
    """
    chamadas: list[int] = []
    segunda = asyncio.Event()

    async def _rodada_falsa():
        chamadas.append(len(chamadas))
        if len(chamadas) == 1:
            raise RuntimeError("banco respondeu bobagem no meio da rodada")
        segunda.set()

    settings = MagicMock(helo_indexacao_intervalo_segundos=0)
    with (
        patch.object(helo_indexacao, "_rodada", new=_rodada_falsa),
        patch.object(helo_indexacao, "get_settings", return_value=settings),
    ):
        tarefa = asyncio.create_task(helo_indexacao.helo_indexacao_loop())
        try:
            await asyncio.wait_for(segunda.wait(), timeout=5)
        finally:
            tarefa.cancel()
            with suppress(asyncio.CancelledError):
                await tarefa

    assert len(chamadas) >= 2


@pytest.mark.parametrize(
    ("intervalo", "url"),
    [(0, "http://helphs-embedding:8080"), (300, "")],
)
def test_o_laco_nao_sobe_quando_nao_tem_o_que_fazer(intervalo, url):
    """Intervalo zero desliga; sem o serviço, toda rodada terminaria sem vetor nenhum."""
    settings = MagicMock(helo_indexacao_intervalo_segundos=intervalo, helo_embedding_url=url)

    with patch.object(helo_indexacao, "get_settings", return_value=settings):
        assert helo_indexacao.start_helo_indexacao_worker() is None
