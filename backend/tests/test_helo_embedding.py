"""
O cliente do serviço de embedding — e, sobretudo, como ele FALHA.

A regra que este arquivo guarda é uma só: **nenhum chamado fica preso porque um
serviço de apoio caiu**. Toda falha devolve `None`, e `None` faz a busca não
acontecer, o bloco receber `NADA ENCONTRADO` e a Helô escalar com mensagem
neutra — o mesmo destino de uma pergunta que a base simplesmente não responde.

O serviço não existe aqui: o transporte é trocado por um duplo. O que se testa
é o contrato e o comportamento na falha, que é o que o chamador depende.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.models.models import HELO_EMBEDDING_DIM
from app.services import helo_embedding
from app.services.helo_embedding import embute, embute_um


def _vetor(valor: float = 0.1) -> list[float]:
    return [valor] * HELO_EMBEDDING_DIM


@pytest.fixture
def servico_ligado(monkeypatch):
    monkeypatch.setattr(
        helo_embedding,
        "get_settings",
        lambda: MagicMock(
            helo_embedding_url="http://embed:8080",
            helo_embedding_timeout_seconds=10,
        ),
    )


@pytest.fixture
def servico_desligado(monkeypatch):
    monkeypatch.setattr(
        helo_embedding,
        "get_settings",
        lambda: MagicMock(helo_embedding_url="", helo_embedding_timeout_seconds=10),
    )


def _transporte(monkeypatch, *, resposta=None, erro=None):
    """Troca o httpx.AsyncClient por um duplo que devolve ou estoura."""
    cliente = MagicMock()
    cliente.__aenter__ = AsyncMock(return_value=cliente)
    cliente.__aexit__ = AsyncMock(return_value=False)
    if erro is not None:
        cliente.post = AsyncMock(side_effect=erro)
    else:
        cliente.post = AsyncMock(return_value=resposta)
    monkeypatch.setattr(helo_embedding.httpx, "AsyncClient", lambda **k: cliente)
    return cliente


def _resposta(payload, status=200):
    r = MagicMock()
    r.json = MagicMock(return_value=payload)
    if status >= 400:
        r.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("erro", request=MagicMock(), response=MagicMock())
        )
    else:
        r.raise_for_status = MagicMock()
    return r


# ── O caminho feliz ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_devolve_os_vetores_na_ordem_dos_textos(monkeypatch, servico_ligado):
    """A ordem é o contrato: o chamador casa vetor com trecho por posição."""
    _transporte(monkeypatch, resposta=_resposta({"vetores": [_vetor(0.1), _vetor(0.2)]}))

    vetores = await embute(["um", "dois"])

    assert len(vetores) == 2
    assert vetores[0][0] == pytest.approx(0.1)
    assert vetores[1][0] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_manda_os_textos_em_lote_numa_chamada_so(monkeypatch, servico_ligado):
    """
    A ingestão embute dezenas de trechos de uma vez.

    Uma chamada por trecho seriam dezenas de viagens de rede para um trabalho
    que o serviço faz melhor junto.
    """
    cliente = _transporte(monkeypatch, resposta=_resposta({"vetores": [_vetor()] * 3}))

    await embute(["a", "b", "c"])

    assert cliente.post.await_count == 1
    assert cliente.post.await_args.kwargs["json"] == {"textos": ["a", "b", "c"]}


@pytest.mark.asyncio
async def test_lista_vazia_nao_chama_o_servico(monkeypatch, servico_ligado):
    """Nada a embutir é resposta, não viagem de rede."""
    cliente = _transporte(monkeypatch, resposta=_resposta({"vetores": []}))

    assert await embute([]) == []
    assert cliente.post.await_count == 0


# ── Como ele falha ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sem_url_devolve_none_em_silencio(monkeypatch, servico_desligado):
    """
    É o estado de produção com a Helô desligada, não uma anormalidade.

    Mesmo critério do `llm.py` sem chave: nada de log de aviso a cada chamado
    aberto.
    """
    cliente = _transporte(monkeypatch, resposta=_resposta({"vetores": [_vetor()]}))

    assert await embute(["oi"]) is None
    assert cliente.post.await_count == 0


@pytest.mark.asyncio
async def test_timeout_devolve_none_sem_levantar(monkeypatch, servico_ligado):
    """
    Serviço lento não pode virar exceção subindo pelo caminho do chat.

    Exceção aqui prenderia o chamado; None faz a Helô escalar.
    """
    _transporte(monkeypatch, erro=httpx.ReadTimeout("demorou"))

    assert await embute(["oi"]) is None


@pytest.mark.asyncio
async def test_servico_fora_do_ar_devolve_none(monkeypatch, servico_ligado):
    """Contêiner reiniciando é o caso mais provável de todos."""
    _transporte(monkeypatch, erro=httpx.ConnectError("recusou"))

    assert await embute(["oi"]) is None


@pytest.mark.asyncio
async def test_http_de_erro_devolve_none(monkeypatch, servico_ligado):
    _transporte(monkeypatch, resposta=_resposta({}, status=500))

    assert await embute(["oi"]) is None


@pytest.mark.asyncio
async def test_resposta_fora_do_contrato_devolve_none(monkeypatch, servico_ligado):
    """Chave errada no JSON é serviço trocado ou versão incompatível."""
    _transporte(monkeypatch, resposta=_resposta({"embeddings": [_vetor()]}))

    assert await embute(["oi"]) is None


@pytest.mark.asyncio
async def test_quantidade_diferente_da_pedida_devolve_none(monkeypatch, servico_ligado):
    """
    Dois textos e um vetor de volta desalinha tudo pela posição.

    O chamador casa vetor com trecho por índice: aceitar isso gravaria o
    embedding de um trecho em cima de outro, e nada acusaria.
    """
    _transporte(monkeypatch, resposta=_resposta({"vetores": [_vetor()]}))

    assert await embute(["um", "dois"]) is None


# ── A dimensão ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dimensao_errada_devolve_none(monkeypatch, servico_ligado):
    """
    Trocar o modelo do serviço é uma linha de configuração daquele contêiner.

    Um modelo de outra dimensão devolveria vetores válidos e inúteis: o INSERT
    estouraria no meio da ingestão e a BUSCA falharia dentro de uma consulta,
    longe daqui, num erro que não diz "trocaram o modelo". Conferir aqui
    transforma isso numa linha de log com a dimensão que veio.
    """
    _transporte(monkeypatch, resposta=_resposta({"vetores": [[0.1] * 768]}))

    assert await embute(["oi"]) is None


@pytest.mark.asyncio
async def test_a_dimensao_conferida_e_a_da_coluna(monkeypatch, servico_ligado):
    """
    A conferência precisa usar a MESMA constante do model.

    Um número solto aqui e outro no `models.py` divergiriam no dia da troca, e
    a conferência passaria a aprovar o que a coluna recusa.
    """
    _transporte(monkeypatch, resposta=_resposta({"vetores": [[0.1] * HELO_EMBEDDING_DIM]}))

    assert await embute(["oi"]) is not None
    assert HELO_EMBEDDING_DIM == 1024


# ── O caminho de um texto só ──────────────────────────────────


@pytest.mark.asyncio
async def test_embute_um_devolve_o_vetor_direto(monkeypatch, servico_ligado):
    """É o caminho do chat: uma pergunta, um vetor."""
    _transporte(monkeypatch, resposta=_resposta({"vetores": [_vetor(0.7)]}))

    vetor = await embute_um("como troco o idioma?")

    assert vetor[0] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_embute_um_devolve_none_quando_o_servico_cai(monkeypatch, servico_ligado):
    """O caminho do chat precisa da mesma garantia: nada de exceção."""
    _transporte(monkeypatch, erro=httpx.ConnectError("caiu"))

    assert await embute_um("oi") is None
