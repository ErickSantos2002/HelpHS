"""
Leitura de upload com limite (`app/utils/uploads.py`).

O que se prova aqui é o que NÃO acontece: o servidor não pode materializar o
arquivo inteiro para só então medi-lo. Enquanto o limite era aplicado sobre
`await file.read()`, mandar 2 GB fazia o processo alocar 2 GB antes de recusar
— e não há middleware de tamanho de corpo na aplicação (o único middleware é o
CORS).

Por isso os testes contam **quantos bytes foram entregues**, e não só o status
da recusa: um teste que afirmasse apenas o 413 continuaria verde com a versão
que lê tudo primeiro.
"""

import pytest
from fastapi import HTTPException

from app.utils.uploads import ler_ate_o_limite


class _ArquivoFalso:
    """UploadFile o suficiente para o helper — e que conta o que entregou."""

    def __init__(self, tamanho: int, filename: str = "anexo.pdf"):
        self._restante = tamanho
        self.filename = filename
        self.bytes_entregues = 0

    async def read(self, size: int = -1) -> bytes:
        if self._restante <= 0:
            return b""
        quanto = self._restante if size == -1 else min(size, self._restante)
        self._restante -= quanto
        self.bytes_entregues += quanto
        return b"x" * quanto


@pytest.mark.asyncio
async def test_arquivo_dentro_do_limite_passa_inteiro():
    arquivo = _ArquivoFalso(1000)
    dados = await ler_ate_o_limite(arquivo, max_bytes=2000, rotulo="2 KB")
    assert len(dados) == 1000
    assert arquivo.bytes_entregues == 1000


@pytest.mark.asyncio
async def test_arquivo_exatamente_no_limite_passa():
    """A fronteira: igual ao limite não é 'acima do limite'."""
    arquivo = _ArquivoFalso(2000)
    dados = await ler_ate_o_limite(arquivo, max_bytes=2000, rotulo="2 KB")
    assert len(dados) == 2000


@pytest.mark.asyncio
async def test_um_byte_acima_do_limite_e_recusado():
    arquivo = _ArquivoFalso(2001)
    with pytest.raises(HTTPException) as exc:
        await ler_ate_o_limite(arquivo, max_bytes=2000, rotulo="2 KB")
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_arquivo_enorme_e_abortado_sem_ser_materializado():
    """
    O ponto do achado: 2 GB não podem virar 2 GB de memória antes da recusa.
    O helper para logo depois de cruzar o limite — sobra no máximo um bloco.
    """
    limite = 64 * 1024
    arquivo = _ArquivoFalso(2 * 1024 * 1024 * 1024)  # 2 GB

    with pytest.raises(HTTPException) as exc:
        await ler_ate_o_limite(arquivo, max_bytes=limite, rotulo="64 KB")

    assert exc.value.status_code == 413
    folga = limite + 64 * 1024  # limite + um bloco
    assert arquivo.bytes_entregues <= folga, (
        f"leu {arquivo.bytes_entregues} bytes antes de recusar — "
        f"esperava parar perto de {limite}"
    )


@pytest.mark.asyncio
async def test_a_recusa_diz_o_limite_em_portugues():
    """O front mostra o `detail` quando existe; em inglês seria texto cru."""
    arquivo = _ArquivoFalso(5000)
    with pytest.raises(HTTPException) as exc:
        await ler_ate_o_limite(arquivo, max_bytes=100, rotulo="100 bytes")
    assert "100 bytes" in exc.value.detail
    assert "anexo.pdf" in exc.value.detail


@pytest.mark.asyncio
async def test_arquivo_vazio_nao_quebra():
    arquivo = _ArquivoFalso(0)
    assert await ler_ate_o_limite(arquivo, max_bytes=2000, rotulo="2 KB") == b""
