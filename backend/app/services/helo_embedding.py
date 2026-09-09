"""
O cliente do serviço de embedding da Helô.

Este módulo NÃO calcula embedding. Ele conversa por HTTP com um contêiner
separado que calcula — e a separação é consequência de um número medido, não
gosto de arquitetura.

POR QUE UM SERVIÇO, E NÃO UMA BIBLIOTECA AQUI DENTRO
----------------------------------------------------
O backend roda com `--workers 1` (`start.sh:40`). Trabalho de CPU síncrono no
event loop congela a API para todo mundo, e isso já aconteceu neste sistema:
uma requisição pesada ocupou o processo por 151 segundos e parou o resto
(`mudanças.md:50`). Um modelo de embedding rodando aqui dentro seria esse mesmo
defeito, de propósito, a cada turno de conversa.

Com o cálculo em outro contêiner, o que sobra aqui é espera de rede — que é
justamente o que um event loop faz bem. E o serviço reinicia sem derrubar a
API, e o modelo troca sem rebuild do backend.

O CONTRATO
----------
    POST {helo_embedding_url}/embeddings
        {"textos": ["...", "..."]}
    200 {"vetores": [[...1024 floats...], [...]]}

Em lote porque a ingestão precisa embutir dezenas de trechos de uma vez, e uma
chamada por trecho seria dezenas de viagens de rede para um trabalho que o
serviço faz melhor junto.

COMO ELE FALHA
--------------
Nunca levanta exceção. Devolve `None`, exatamente como o `llm.py` faz — e pelo
mesmo motivo: **nenhum chamado pode ficar preso** porque um serviço de apoio
caiu. Sem vetor não há busca; sem busca o bloco recebe `NADA ENCONTRADO` e a
Helô escala com mensagem neutra. Falha de embedding é indistinguível, para o
cliente, de uma pergunta que a base não responde — e as duas terminam do jeito
certo, com um humano.
"""

from collections.abc import Sequence

import httpx
from loguru import logger

from app.core.config import get_settings
from app.models.models import HELO_EMBEDDING_DIM


async def embute(
    textos: Sequence[str], *, timeout: float | None = None
) -> list[list[float]] | None:
    """
    Os vetores dos textos, na mesma ordem — ou None quando não deu.

    Args:
        timeout: sobrepõe o padrão. A ingestão usa um valor maior: ela manda
            dezenas de trechos de uma vez, e o que é impaciência no chat é
            pressa desnecessária num script que roda à mão.

    Returns:
        Uma lista de vetores, um por texto. `None` em QUALQUER falha —
        serviço desligado, rede, timeout, HTTP de erro, resposta fora do
        contrato ou dimensão errada.
    """
    settings = get_settings()
    if not settings.helo_embedding_url:
        # Silêncio, sem log. É o estado de produção com a Helô desligada, e não
        # é anormalidade que mereça uma linha de aviso a cada chamado aberto —
        # o mesmo critério do `llm.py`.
        return None

    if not textos:
        return []

    url = f"{settings.helo_embedding_url.rstrip('/')}/embeddings"
    espera = timeout if timeout is not None else settings.helo_embedding_timeout_seconds

    try:
        async with httpx.AsyncClient(timeout=espera) as client:
            resp = await client.post(url, json={"textos": list(textos)})
        resp.raise_for_status()
        vetores = resp.json()["vetores"]
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Serviço de embedding da Helô falhou: {exc}")
        return None

    return _confere(vetores, esperados=len(textos))


def _confere(vetores: object, *, esperados: int) -> list[list[float]] | None:
    """
    Recusa resposta fora do contrato — e a dimensão é o que mais importa.

    O modelo vive do outro lado da rede, e trocá-lo é uma linha na configuração
    daquele contêiner. Um modelo de dimensão diferente devolveria vetores
    perfeitamente válidos e perfeitamente inúteis: o `INSERT` na coluna
    `vector(1024)` estouraria com erro de Postgres no meio da ingestão, e a
    BUSCA — que é o caminho quente — falharia dentro de uma consulta, longe
    daqui, num erro que não diz "trocaram o modelo".

    Conferir aqui transforma isso numa linha de log com a dimensão que veio.
    """
    if not isinstance(vetores, list) or len(vetores) != esperados:
        logger.warning(
            f"Serviço de embedding devolveu {type(vetores).__name__} com tamanho inesperado "
            f"(esperava {esperados} vetores)"
        )
        return None

    for vetor in vetores:
        if not isinstance(vetor, list) or len(vetor) != HELO_EMBEDDING_DIM:
            tamanho = len(vetor) if isinstance(vetor, list) else "não-lista"
            logger.warning(
                f"Serviço de embedding devolveu vetor de dimensão {tamanho}, e a coluna é "
                f"vector({HELO_EMBEDDING_DIM}). Trocaram o modelo do serviço? A dimensão é "
                "tipo de coluna: mudá-la exige migration, não só configuração."
            )
            return None

    return [[float(x) for x in vetor] for vetor in vetores]


async def embute_um(texto: str, *, timeout: float | None = None) -> list[float] | None:
    """A pergunta do cliente — o caminho de um texto só, que é o do chat."""
    vetores = await embute([texto], timeout=timeout)
    return vetores[0] if vetores else None
