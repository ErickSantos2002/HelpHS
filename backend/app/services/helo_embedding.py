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

Em lote porque a ingestão embute dezenas de trechos, e uma viagem de rede por
trecho seria desperdício. **Mas o lote tem teto de quatro**, e o número saiu de
medição, não de gosto.

O pico de memória do serviço cresce com o lote, e cresce rápido — medido com o
`bge-m3` quantizado, com trechos do tamanho dos manuais reais:

    1 trecho    →  905 MB de pico  (+42 MB sobre o repouso)
    8 trechos   →  1,2 GB          (+336 MB)
    24 trechos  →  1,9 GB          (+1,1 GB)
    74 trechos  →  3,7 GB          (+2,8 GB)

O servidor tem ~5,1 GB livres, compartilhados com todos os projetos, e é o
MESMO que compila a própria imagem no deploy, porque não há registry. Mandar a
base inteira de uma vez comeria quase toda a folga da máquina para economizar
73 viagens de rede num script que roda à mão.

Quatro deixa o pico perto de 1 GB, com margem confortável. Quem pede mais
recebe menos: a função fatia sozinha, em vez de recusar — o chamador não tem
como saber quanta memória o serviço tem, e transformar isso em erro só moveria
o problema para ele.

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

# Quantos textos vão numa chamada. O número é medido, não escolhido: com quatro
# o pico do serviço fica perto de 1 GB; com os 74 da base inteira, em 3,7 GB —
# quase toda a folga de 5,1 GB da máquina, que também compila a própria imagem
# no deploy. Ver o cabeçalho para a tabela inteira.
TETO_DO_LOTE = 4


async def embute(
    textos: Sequence[str], *, timeout: float | None = None
) -> list[list[float]] | None:
    """
    Os vetores dos textos, na mesma ordem — ou None quando não deu.

    Fatia em lotes de `TETO_DO_LOTE` sozinha. Quem chama com setenta e quatro
    trechos recebe setenta e quatro vetores; o que muda é o número de viagens,
    e é isso que mantém o pico de memória do serviço dentro do orçamento.

    Args:
        timeout: sobrepõe o padrão, e vale POR LOTE. A ingestão usa um valor
            maior: o que é impaciência no chat é pressa desnecessária num
            script que roda à mão.

    Returns:
        Uma lista de vetores, um por texto. `None` em QUALQUER falha —
        serviço desligado, rede, timeout, HTTP de erro, resposta fora do
        contrato ou dimensão errada. Um lote que falha derruba a chamada
        inteira: meia lista de vetores seria pior do que nenhuma, porque o
        chamador casa vetor com trecho por posição.
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

    reunidos: list[list[float]] = []
    for inicio in range(0, len(textos), TETO_DO_LOTE):
        lote = list(textos[inicio : inicio + TETO_DO_LOTE])
        vetores = await _um_lote(url, lote, espera)
        if vetores is None:
            return None
        reunidos.extend(vetores)
    return reunidos


async def _um_lote(url: str, lote: list[str], espera: float) -> list[list[float]] | None:
    try:
        async with httpx.AsyncClient(timeout=espera) as client:
            resp = await client.post(url, json={"textos": lote})
        resp.raise_for_status()
        vetores = resp.json()["vetores"]
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Serviço de embedding da Helô falhou: {exc}")
        return None

    return _confere(vetores, esperados=len(lote))


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
