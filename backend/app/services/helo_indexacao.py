"""
A indexação da base da Helô: artigo publicado vira trecho com vetor.

Desde 10/09/2026 a fonte da Helô é a Base de Conhecimento — os mesmos artigos
da barra lateral. Este módulo é o que mantém a base vetorial em dia com eles,
sem ninguém rodar nada.

POR QUE VARREDURA, E NÃO GATILHO NO SALVAR
------------------------------------------
Indexar dentro do `PATCH` do artigo acoplaria a falha: com o serviço de
embedding fora, o suporte não conseguiria salvar texto por causa de um
acessório do atendimento. Latência não é o motivo — embedding é espera de
rede, e o worker único atende as outras requisições enquanto espera.

A varredura periódica é AUTO-CURATIVA: deploy no meio, serviço de embedding
fora, rede caindo — a rodada seguinte conserta. Não há fila, e não há estado de
"pendente" para alguém ter de entender quando algo trava.

O QUE DEPENDE DA VARREDURA, E O QUE NÃO
---------------------------------------
Despublicar, arquivar, desmarcar `helo_pode_ler` ou trocar o produto têm
efeito IMEDIATO: a busca filtra isso ao vivo, na consulta (`helo_base.py`).
Só texto novo ou editado espera a próxima rodada para entrar. A limpeza dos
trechos de artigo que saiu também acontece aqui, e é arrumação — a busca já
não os devolvia.

O MOLDE
-------
É o do fechamento automático (`app/services/ticket_lifecycle.py`): laço
subido no `lifespan`, trava no Redis para quando forem dois workers, rodada
pulada se o Redis cair, e rodada que levanta não mata o laço.
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Literal

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import HeloChunk, HeloIndexacao, KBArticle, KBArticleStatus
from app.services.helo_embedding import embute
from app.services.helo_texto import CredencialNaoRedigidaError, Trecho, corta_artigo

_LOCK_KEY = "helphs:lock:helo-indexacao"

# Por LOTE de quatro trechos, e bem maior que os 10 s do chat. Medido na
# ingestão por arquivo: um trecho de 459 tokens custa 5,8 s num núcleo, e o
# serviço roda com um. O que é impaciência no chat é pressa desnecessária num
# laço de fundo, que não segura cliente nenhum esperando.
_ESPERA_POR_LOTE = 300.0

Resultado = Literal["inalterado", "indexado", "sem_embedding"]


def hash_do_corte(trechos: list[Trecho]) -> str:
    """
    SHA-256 dos trechos que seriam gravados — do RESULTADO, não do texto cru.

    Hashear o `content` do artigo parecia natural e repetiria o defeito que a
    ingestão por arquivo já pagou: consertar o corte ou a redação com o texto
    igual deixaria a base com o corte velho, porque nada teria "mudado". O hash
    do resultado muda sozinho com qualquer mudança de receita.
    """
    h = hashlib.sha256()
    for t in trechos:
        h.update(f"{t.ordem}\x00{t.secao}\x00{t.exige_credencial}\x00{t.conteudo}\x00".encode())
    return h.hexdigest()


async def indexa_artigo(
    db: AsyncSession, artigo_id: uuid.UUID, titulo: str, conteudo: str
) -> Resultado:
    """
    Um artigo: corta, compara com o que já está indexado, e embute se mudou.

    Recebe os campos, e não o objeto do ORM, de propósito: a varredura dá
    `commit` por artigo e `rollback` quando um falha, e objeto expirado lido
    fora de contexto síncrono estoura `MissingGreenlet` no meio da rodada.

    Não dá `commit` — quem chama decide, artigo por artigo. E não grava NADA se o
    serviço de embedding não responder: o trecho velho fica no lugar, o hash
    fica o velho, e a próxima rodada tenta de novo. Trecho sem vetor seria
    invisível para a busca e ainda marcaria o artigo como indexado.

    Levanta `CredencialNaoRedigidaError` quando o detector largo vê algo com
    cara de senha que o redator não redigiu.
    """
    trechos, _descartes = corta_artigo(titulo, conteudo)
    novo = hash_do_corte(trechos)

    atual = await db.get(HeloIndexacao, artigo_id)
    if atual is not None and atual.content_hash == novo:
        return "inalterado"

    vetores: list[list[float]] = []
    if trechos:
        resposta = await embute([t.conteudo for t in trechos], timeout=_ESPERA_POR_LOTE)
        if resposta is None:
            return "sem_embedding"
        vetores = resposta

    # O DELETE é instrução Core e executa na hora: os trechos novos reusam as
    # mesmas posições (`article_id`, `ordem`), e o índice único recusaria o
    # INSERT se os velhos ainda estivessem lá.
    await db.execute(delete(HeloChunk).where(HeloChunk.article_id == artigo_id))
    for t, vetor in zip(trechos, vetores, strict=True):
        db.add(
            HeloChunk(
                article_id=artigo_id,
                secao=t.secao,
                ordem=t.ordem,
                conteudo=t.conteudo,
                exige_credencial_admin=t.exige_credencial,
                embedding=vetor,
            )
        )

    agora = datetime.now(UTC)
    if atual is None:
        db.add(HeloIndexacao(article_id=artigo_id, content_hash=novo, indexado_em=agora))
    else:
        atual.content_hash = novo
        atual.indexado_em = agora
    return "indexado"


async def varre(db: AsyncSession) -> dict[str, int]:
    """
    Uma passada pela base inteira. Devolve a contagem do que aconteceu.

    `commit` por artigo: com a rodada inteira numa transação só, uma queda no
    décimo artigo jogaria fora os nove que já tinham ficado prontos — e a base
    nunca terminaria de indexar se o décimo sempre caísse.

    Serviço de embedding fora encerra a rodada no primeiro artigo que precisava
    dele. Seguir seria pagar um timeout por artigo para chegar ao mesmo lugar.
    """
    contagem = {"indexado": 0, "inalterado": 0, "sem_embedding": 0, "credencial": 0, "limpos": 0}

    elegiveis = (
        await db.execute(
            select(KBArticle.id, KBArticle.title, KBArticle.content)
            .where(
                KBArticle.status == KBArticleStatus.published,
                KBArticle.helo_pode_ler.is_(True),
            )
            .order_by(KBArticle.created_at)
        )
    ).all()

    for artigo_id, titulo, conteudo in elegiveis:
        try:
            resultado = await indexa_artigo(db, artigo_id, titulo, conteudo)
        except CredencialNaoRedigidaError as exc:
            await db.rollback()
            contagem["credencial"] += 1
            # ERRO, e toda rodada, até alguém mexer no artigo. É o único jeito de
            # uma senha na tela da Base de Conhecimento não passar calada: a
            # página é da KB e não é desta varredura protegê-la, mas quem ler o
            # log fica sabendo que ela está lá.
            logger.error(
                f"Artigo {artigo_id} ('{titulo}') NÃO foi indexado para a Helô: parece "
                f"conter credencial não redigida — e, se está publicado, ela está "
                f"visível na Base de Conhecimento. {exc}"
            )
            continue

        if resultado == "sem_embedding":
            await db.rollback()
            contagem["sem_embedding"] += 1
            logger.warning(
                "Indexação da Helô: o serviço de embedding não respondeu. A rodada "
                "para aqui; o que já estava indexado continua valendo, e a próxima "
                "rodada tenta de novo."
            )
            break

        await db.commit()
        contagem[resultado] += 1

    # Arrumação: indexado que deixou de ser elegível. A busca já não devolvia
    # esses trechos — ela filtra publicação e marcação ao vivo —, mas deixá-los
    # aqui seria acumular vetor de artigo arquivado para sempre.
    ids = {artigo_id for artigo_id, _, _ in elegiveis}
    orfaos = [
        a
        for a in (await db.execute(select(HeloIndexacao.article_id))).scalars().all()
        if a not in ids
    ]
    if orfaos:
        await db.execute(delete(HeloChunk).where(HeloChunk.article_id.in_(orfaos)))
        await db.execute(delete(HeloIndexacao).where(HeloIndexacao.article_id.in_(orfaos)))
        await db.commit()
        contagem["limpos"] = len(orfaos)

    return contagem


async def _rodada() -> None:
    """Uma rodada, protegida por trava para não repetir entre workers."""
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis

    settings = get_settings()
    ttl = max(60, settings.helo_indexacao_intervalo_segundos - 60)

    try:
        redis = await get_redis()
        pegou = await redis.set(_LOCK_KEY, "1", nx=True, ex=ttl)
    except Exception as exc:  # noqa: BLE001 — Redis fora do ar não pode derrubar a API
        logger.warning(f"Indexação da Helô pulada (Redis indisponível): {exc}")
        return

    if not pegou:
        # Outro worker está com a rodada.
        return

    async with AsyncSessionLocal() as db:
        contagem = await varre(db)

    if contagem["indexado"] or contagem["limpos"] or contagem["credencial"]:
        logger.info(f"Indexação da Helô: {contagem}")


async def helo_indexacao_loop() -> None:
    settings = get_settings()
    intervalo = settings.helo_indexacao_intervalo_segundos

    # Um respiro depois do boot: migrations e seeds ainda podem estar rodando.
    await asyncio.sleep(min(60, intervalo))

    while True:
        try:
            await _rodada()
        except asyncio.CancelledError:
            # Redundante por construção — CancelledError é BaseException —, e
            # escrito pelo mesmo motivo do fechamento automático: para que o
            # `except` de baixo nunca seja alargado sem alguém ver que o
            # shutdown travaria.
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Rodada de indexação da Helô levantou; o laço segue: {exc}")

        await asyncio.sleep(intervalo)


def start_helo_indexacao_worker() -> asyncio.Task | None:
    """Sobe o laço em background. None quando não há o que ele possa fazer."""
    settings = get_settings()
    if settings.helo_indexacao_intervalo_segundos <= 0:
        logger.info("Indexação da Helô desligada (intervalo = 0)")
        return None
    if not settings.helo_embedding_url:
        # Sem o serviço, toda rodada terminaria no primeiro artigo sem vetor
        # nenhum. Subir o laço seria só produzir aviso a cada intervalo.
        logger.info("Indexação da Helô parada: HELO_EMBEDDING_URL não configurada")
        return None

    logger.info(
        f"Indexação da Helô ativa, varrendo a cada "
        f"{settings.helo_indexacao_intervalo_segundos}s"
    )
    return asyncio.create_task(helo_indexacao_loop(), name="helo-indexacao")
