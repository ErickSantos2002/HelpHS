"""
O modelo em memória: tokenizar, rodar e agrupar.

Carrega UMA vez, no start do processo, e fica residente — medido, o piso é
864 MB e a carga leva 2,9 s. Carregar por requisição seria três segundos por
pergunta e nenhuma economia de memória que valha isso.
"""

import os
import threading
from pathlib import Path

import numpy as np

from servico_embedding.pooling import agrupa

# Onde o Dockerfile deixa o modelo. Configurável para rodar fora do contêiner,
# porque quem for mexer nisto precisa conseguir rodar na própria máquina.
PASTA_DO_MODELO = Path(os.environ.get("HELO_MODELO_DIR", "/modelo"))

# O mesmo teto do cliente do lado da API (`TETO_DO_LOTE`), repetido aqui de
# propósito: o serviço não pode confiar em quem chama. Um cliente antigo, um
# script errado ou um `curl` à mão mandariam setenta e quatro textos e o pico
# iria a 3,7 GB numa máquina com 5,1 GB livres.
TETO_DO_LOTE = 4


class ModeloNaoCarregouError(RuntimeError):
    """O processo subiu, o modelo não. É erro de serviço, não da requisição."""


class Embutidor:
    """
    Guarda a sessão ONNX e o tokenizador.

    A sessão do onnxruntime não é declarada como thread-safe para escrita, e o
    uvicorn atende em mais de uma thread quando o handler é síncrono. O lock
    serializa o `run` — que é o que se quer de qualquer jeito: dois cálculos ao
    mesmo tempo dobrariam o pico de memória, e o pico é o que aperta aqui.
    """

    def __init__(self, pasta: Path = PASTA_DO_MODELO) -> None:
        self.pasta = pasta
        self._sessao = None
        self._tok = None
        self._erro: str | None = None
        self._trava = threading.Lock()

    def carrega(self) -> None:
        """Chamado no start. Guarda o erro em vez de derrubar o processo."""
        try:
            # Os arquivos ANTES da biblioteca, e a ordem importa para o log.
            # Modelo faltando é a falha que pode acontecer em produção (volume
            # não montado, build de imagem antigo); onnxruntime faltando seria
            # falha de build, que nunca chega a subir. Importar primeiro fazia
            # a mensagem falar da biblioteca mesmo quando o problema era o
            # arquivo.
            onnx = self.pasta / "model_quantized.onnx"
            tok = self.pasta / "tokenizer.json"
            faltando = [p.name for p in (onnx, tok) if not p.is_file()]
            if faltando:
                raise FileNotFoundError(
                    f"{', '.join(faltando)} não está em {self.pasta} — o modelo entra na imagem "
                    "no build (`baixa_modelo.py`), e esta pasta deveria vir pronta"
                )

            import onnxruntime as ort
            from tokenizers import Tokenizer

            opcoes = ort.SessionOptions()
            # Um núcleo por operação. A máquina tem 4 e divide com todo o resto
            # do projeto; deixar o onnxruntime pegar todos faria o cálculo de
            # embedding competir com a API e com o Postgres na mesma caixa.
            opcoes.intra_op_num_threads = int(os.environ.get("HELO_THREADS", "1"))
            self._sessao = ort.InferenceSession(
                str(onnx), opcoes, providers=["CPUExecutionProvider"]
            )
            self._tok = Tokenizer.from_file(str(tok))
            self._erro = None
        except Exception as exc:  # noqa: BLE001
            # NÃO derruba o processo. Um contêiner em crashloop não diz o que
            # houve — ele some. De pé, o /health responde o motivo e o
            # /embeddings devolve 503 com a mesma frase, que é o que chega ao
            # log de quem está procurando.
            self._erro = f"{type(exc).__name__}: {exc}"

    @property
    def pronto(self) -> bool:
        return self._sessao is not None and self._erro is None

    @property
    def motivo(self) -> str:
        return self._erro or "carregado"

    def embute(self, textos: list[str]) -> list[list[float]]:
        if not self.pronto:
            raise ModeloNaoCarregouError(self._erro or "modelo não carregado")
        if len(textos) > TETO_DO_LOTE:
            raise ValueError(
                f"lote de {len(textos)} textos acima do teto de {TETO_DO_LOTE}. "
                "O pico de memória cresce com o lote: 74 de uma vez foram medidos em 3,7 GB, "
                "numa máquina com ~5,1 GB livres."
            )

        encs = [self._tok.encode(t) for t in textos]
        maior = max(len(e.ids) for e in encs)
        ids = np.zeros((len(encs), maior), dtype=np.int64)
        mascara = np.zeros((len(encs), maior), dtype=np.int64)
        for i, e in enumerate(encs):
            ids[i, : len(e.ids)] = e.ids
            mascara[i, : len(e.ids)] = e.attention_mask

        with self._trava:
            saida = self._sessao.run(None, {"input_ids": ids, "attention_mask": mascara})[0]

        return [v.tolist() for v in agrupa(saida, mascara)]
