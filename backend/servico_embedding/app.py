"""
A camada HTTP do serviço de embedding.

Duas rotas e nada mais. Este contêiner não fala com banco, não sabe o que é um
chamado e não conhece a Helô — ele recebe texto e devolve vetor. Manter assim é
o que permite reiniciá-lo sem pensar em mais nada.

O CONTRATO, o mesmo que `app/services/helo_embedding.py` do outro lado espera:

    POST /embeddings  {"textos": ["..."]}  ->  200 {"vetores": [[...1024...]]}
    GET  /health                           ->  200 | 503
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from servico_embedding.modelo import TETO_DO_LOTE, Embutidor, ModeloNaoCarregouError

embutidor = Embutidor()


@asynccontextmanager
async def ciclo(app: FastAPI):
    # Carrega no start, e uma vez só: são 2,9 s de carga e 864 MB residentes.
    embutidor.carrega()
    yield


app = FastAPI(title="Embedding da Helô", lifespan=ciclo)


class Pedido(BaseModel):
    textos: list[str] = Field(min_length=1, max_length=TETO_DO_LOTE)


class Resposta(BaseModel):
    vetores: list[list[float]]


@app.get("/health")
def health() -> dict:
    """
    Diz se o MODELO está de pé, não se o processo está.

    A distinção é o ponto: o processo sobe mesmo quando o modelo falha, de
    propósito — contêiner em crashloop não conta o que houve, ele some. Aqui o
    motivo fica legível para quem for procurar.
    """
    if not embutidor.pronto:
        raise HTTPException(status_code=503, detail=f"modelo não carregou: {embutidor.motivo}")
    return {"status": "ok", "dimensao": 1024, "teto_do_lote": TETO_DO_LOTE}


@app.post("/embeddings", response_model=Resposta)
def embeddings(pedido: Pedido) -> Resposta:
    """
    Texto para vetor.

    Síncrono de propósito: o cálculo é CPU, e num handler `async` ele
    bloquearia o event loop deste serviço do mesmo jeito que bloquearia o da
    API — que é justamente o defeito que motivou separar os dois. Com `def`, o
    FastAPI o joga num threadpool.
    """
    try:
        return Resposta(vetores=embutidor.embute(pedido.textos))
    except ModeloNaoCarregouError as erro:
        # 503, e não 500: é estado do serviço, não culpa da requisição. Do
        # outro lado, o cliente da API trata qualquer HTTP de erro como falha
        # do LLM — devolve None, a busca não acontece e a Helô escala com
        # mensagem neutra. Nenhum chamado fica preso por causa disto.
        raise HTTPException(status_code=503, detail=f"modelo não carregou: {erro}") from erro
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
