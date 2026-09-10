"""
O serviço de embedding: o contrato e, principalmente, o modelo que não carregou.

O modelo de verdade não entra aqui — são 543 MB, e o que este arquivo testa não
depende dele. O que se prova é o comportamento do serviço quando o modelo falta,
quando o lote passa do teto e quando tudo dá certo.

A ponte com o lado da API está no `test_helo_embedding.py`: lá o cliente é
testado contra qualquer HTTP de erro, e o 503 daqui é um deles. Junto, os dois
fecham o caminho: modelo não carrega → 503 → cliente devolve None → busca não
acontece → bloco recebe NADA ENCONTRADO → a Helô escala. Nenhum chamado preso.
"""

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from servico_embedding import app as modulo_app
from servico_embedding.modelo import TETO_DO_LOTE, Embutidor, ModeloNaoCarregouError


class _EmbutidorFalso:
    """Duplo do modelo: mesma superfície, sem os 864 MB."""

    def __init__(self, *, pronto=True, motivo="carregado"):
        self._pronto, self._motivo = pronto, motivo
        self.pedidos: list[list[str]] = []

    @property
    def pronto(self):
        return self._pronto

    @property
    def motivo(self):
        return self._motivo

    def embute(self, textos):
        if not self._pronto:
            raise ModeloNaoCarregouError(self._motivo)
        if len(textos) > TETO_DO_LOTE:
            raise ValueError(f"lote de {len(textos)} acima do teto de {TETO_DO_LOTE}")
        self.pedidos.append(list(textos))
        return [[0.1] * 1024 for _ in textos]


def _cliente(embutidor) -> TestClient:
    """
    Monta o app SEM o `lifespan`, que carregaria o modelo de verdade.

    Reusa as rotas do módulo: o que se testa é o handler, não a fiação do
    FastAPI.
    """
    modulo_app.embutidor = embutidor
    app = FastAPI()
    app.add_api_route("/health", modulo_app.health, methods=["GET"])
    app.add_api_route("/embeddings", modulo_app.embeddings, methods=["POST"])
    return TestClient(app, raise_server_exceptions=False)


# ── O caminho feliz ───────────────────────────────────────────


def test_devolve_um_vetor_por_texto():
    c = _cliente(_EmbutidorFalso())

    r = c.post("/embeddings", json={"textos": ["um", "dois"]})

    assert r.status_code == 200
    assert len(r.json()["vetores"]) == 2
    assert len(r.json()["vetores"][0]) == 1024


def test_health_diz_a_dimensao_e_o_teto():
    """
    Quem for ligar o serviço precisa conferir a dimensão SEM adivinhar.

    A coluna é `vector(1024)`; um serviço com outro modelo responderia outra
    dimensão, e isso tem que ser legível antes de gravar setenta e quatro
    vetores errados.
    """
    r = _cliente(_EmbutidorFalso()).get("/health")

    assert r.status_code == 200
    assert r.json()["dimensao"] == 1024
    assert r.json()["teto_do_lote"] == TETO_DO_LOTE


# ── O modelo que não carregou ─────────────────────────────────


def test_sem_modelo_o_health_responde_503_com_o_motivo():
    """
    O processo sobe mesmo assim, de propósito.

    Contêiner em crashloop não conta o que houve — ele some, e o EasyPanel
    mostra "reiniciando" sem mais nada. De pé, o motivo fica legível para quem
    for procurar.
    """
    c = _cliente(_EmbutidorFalso(pronto=False, motivo="FileNotFoundError: model_quantized.onnx"))

    r = c.get("/health")

    assert r.status_code == 503
    assert "model_quantized.onnx" in r.json()["detail"]


def test_sem_modelo_o_embeddings_responde_503_e_nao_500():
    """
    503 e não 500, e a diferença não é cosmética.

    500 diria "a requisição quebrou o serviço"; 503 diz "o serviço não está
    servindo". Do outro lado, o cliente da API trata qualquer HTTP de erro como
    falha do LLM: devolve None, a busca não acontece e a Helô escala com
    mensagem neutra.
    """
    c = _cliente(_EmbutidorFalso(pronto=False, motivo="onnx corrompido"))

    r = c.post("/embeddings", json={"textos": ["oi"]})

    assert r.status_code == 503
    assert "onnx corrompido" in r.json()["detail"]


# ── O teto, do lado do servidor ───────────────────────────────


def test_o_teto_de_lote_e_recusado_pelo_servico_tambem():
    """
    O serviço não confia em quem chama.

    O cliente da API fatia em quatro, mas um script errado, um cliente antigo
    ou um `curl` à mão mandariam setenta e quatro — e o pico iria a 3,7 GB
    numa máquina com ~5,1 GB livres.
    """
    c = _cliente(_EmbutidorFalso())

    r = c.post("/embeddings", json={"textos": ["t"] * (TETO_DO_LOTE + 1)})

    assert r.status_code == 422


def test_lista_vazia_e_recusada():
    """Pedido sem texto é erro de quem chamou, não trabalho para o modelo."""
    assert _cliente(_EmbutidorFalso()).post("/embeddings", json={"textos": []}).status_code == 422


# ── O carregamento, sem o modelo real ─────────────────────────


def test_o_carregamento_guarda_o_erro_em_vez_de_estourar(tmp_path):
    """
    `carrega()` não pode levantar: quem chama é o start do processo.

    Levantar ali derruba o contêiner antes de qualquer rota existir, e o motivo
    vira uma linha de traceback num log que ninguém está lendo naquele momento.
    """
    embutidor = Embutidor(pasta=tmp_path)

    embutidor.carrega()  # não levanta

    assert embutidor.pronto is False
    assert "model_quantized.onnx" in embutidor.motivo


def test_embutir_sem_modelo_levanta_o_erro_proprio(tmp_path):
    """O handler depende deste tipo para escolher o 503."""
    embutidor = Embutidor(pasta=tmp_path)
    embutidor.carrega()

    with pytest.raises(ModeloNaoCarregouError):
        embutidor.embute(["oi"])


# ── A versão do modelo ────────────────────────────────────────


def test_o_modelo_esta_preso_por_revisao_e_hash():
    """
    Nome não é versão.

    "bge-m3 quantizado" hoje e daqui a seis meses podem ser arquivos
    diferentes, e embedding de um modelo não é comparável com o de outro: os
    vetores gravados continuariam no banco e as distâncias passariam a ser
    entre dois espaços. A busca pioraria sem um erro sequer.
    """
    from servico_embedding import baixa_modelo

    assert len(baixa_modelo.REVISAO) == 40, "revisão precisa ser o commit inteiro"
    for nome, info in baixa_modelo.ARQUIVOS.items():
        assert len(info["sha256"]) == 64, f"{nome} sem SHA-256"
        assert info["bytes"] > 0, f"{nome} sem tamanho esperado"
    assert baixa_modelo.REVISAO in (
        f"https://huggingface.co/{baixa_modelo.REPO}/resolve/{baixa_modelo.REVISAO}/x"
    )


def test_a_dimensao_do_servico_e_a_da_coluna():
    """Um número solto aqui e outro no models.py divergem no dia da troca."""
    from app.models.models import HELO_EMBEDDING_DIM

    r = _cliente(_EmbutidorFalso()).get("/health")

    assert r.json()["dimensao"] == HELO_EMBEDDING_DIM


# ── O pooling entra de verdade no caminho ─────────────────────


def test_o_embutidor_usa_o_pooling_do_repositorio(monkeypatch, tmp_path):
    """
    A fiação: `Embutidor.embute` tem que passar pelo `agrupa`, não por uma
    média própria escrita ali dentro.

    Sem isto, os testes de pooling provariam uma função que ninguém chama.
    """
    from servico_embedding import modelo as modulo_modelo

    chamou = {}

    def _espia(tokens, mascara):
        chamou["sim"] = (tokens.shape, mascara.shape)
        return np.ones((tokens.shape[0], 1024), dtype=np.float32)

    monkeypatch.setattr(modulo_modelo, "agrupa", _espia)

    embutidor = Embutidor(pasta=tmp_path)
    embutidor._sessao = type(
        "S", (), {"run": lambda self, *a: [np.zeros((2, 5, 1024), dtype=np.float32)]}
    )()
    embutidor._tok = type(
        "T",
        (),
        {
            "encode": lambda self, t: type(
                "E", (), {"ids": [1, 2, 3], "attention_mask": [1, 1, 1]}
            )()
        },
    )()
    embutidor._erro = None

    embutidor.embute(["a", "b"])

    assert chamou, "o Embutidor não passou pelo pooling do repositório"
