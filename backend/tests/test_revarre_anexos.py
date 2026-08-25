"""
Decisão do script de revarredura de anexos (`scripts/revarre_anexos.py`).

O que se prende aqui é a tradução da resposta do ClamAV em situação — é ela
que decide o que vira "examinado" no banco. Marcar como examinado um anexo que
o ClamAV não conseguiu ler seria inventar resultado, e é justamente o erro que
um script de limpeza apressado comete.

O script em si é avulso e roda à mão; o que dá para prender com teste é esta
função, que é onde mora a decisão.
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.revarre_anexos import varre_um  # noqa: E402


def _clam(resposta):
    ok = resposta == "clean"
    return AsyncMock(return_value=(ok, resposta))


@pytest.mark.asyncio
async def test_arquivo_limpo_vira_examinado(tmp_path: Path):
    alvo = tmp_path / "laudo.pdf"
    alvo.write_bytes(b"conteudo")

    with patch("scripts.revarre_anexos.antivirus.scan_bytes", new=_clam("clean")):
        r = await varre_um("id-1", "laudo.pdf", alvo, "clamav", 3310)

    assert r.situacao == "limpo"
    assert r.grava is True
    assert r.limpo is True


@pytest.mark.asyncio
async def test_arquivo_infectado_e_examinado_mas_nao_limpo(tmp_path: Path):
    """Infectado precisa ficar marcado — e o arquivo NÃO é apagado pelo script."""
    alvo = tmp_path / "boleto.pdf"
    alvo.write_bytes(b"conteudo")

    with patch("scripts.revarre_anexos.antivirus.scan_bytes", new=_clam("Virus: Eicar-Test")):
        r = await varre_um("id-2", "boleto.pdf", alvo, "clamav", 3310)

    assert r.situacao == "infectado"
    assert r.grava is True
    assert r.limpo is False
    assert alvo.exists(), "o script não pode apagar anexo: é prova de um chamado"


@pytest.mark.asyncio
async def test_clamav_sem_veredito_nao_marca_como_examinado(tmp_path: Path):
    """
    O erro que este teste existe para impedir: tratar "unavailable" como se
    fosse aprovação. O anexo continua sem exame, para ser varrido de novo.
    """
    alvo = tmp_path / "foto.png"
    alvo.write_bytes(b"conteudo")

    for resposta in ("unavailable", "error: resposta estranha"):
        with patch("scripts.revarre_anexos.antivirus.scan_bytes", new=_clam(resposta)):
            r = await varre_um("id-3", "foto.png", alvo, "clamav", 3310)

        assert r.situacao == "sem_resposta", resposta
        assert r.grava is False, f"{resposta!r} não pode virar exame"


@pytest.mark.asyncio
async def test_arquivo_que_sumiu_do_disco_e_so_relatado(tmp_path: Path):
    ausente = tmp_path / "nunca-gravado.pdf"

    with patch("scripts.revarre_anexos.antivirus.scan_bytes", new=_clam("clean")) as scan:
        r = await varre_um("id-4", "nunca-gravado.pdf", ausente, "clamav", 3310)

    assert r.situacao == "sem_arquivo"
    assert r.grava is False
    scan.assert_not_awaited(), "não faz sentido varrer o que não existe"


# ═══════════════════════════════════════════════════════════════
# ping: o boot precisa saber se o antivírus responde
# ═══════════════════════════════════════════════════════════════


async def _clamd_falso(resposta: bytes):
    """Sobe um servidor que responde como o clamd e devolve (host, port)."""
    import asyncio

    async def _atende(reader, writer):
        await reader.read(64)
        writer.write(resposta)
        await writer.drain()
        writer.close()

    servidor = await asyncio.start_server(_atende, "127.0.0.1", 0)
    porta = servidor.sockets[0].getsockname()[1]
    return servidor, porta


@pytest.mark.asyncio
async def test_ping_reconhece_o_pong():
    from app.services import antivirus

    servidor, porta = await _clamd_falso(b"PONG\n")
    try:
        assert await antivirus.ping("127.0.0.1", porta) is True
    finally:
        servidor.close()


@pytest.mark.asyncio
async def test_ping_nao_aceita_porta_aberta_por_outro_servico():
    """
    Abrir e fechar a conexão provaria menos: uma porta ocupada por qualquer
    outro processo passaria por antivírus no ar. É o PONG que prova.
    """
    from app.services import antivirus

    servidor, porta = await _clamd_falso(b"HTTP/1.1 200 OK\r\n")
    try:
        assert await antivirus.ping("127.0.0.1", porta) is False
    finally:
        servidor.close()


@pytest.mark.asyncio
async def test_ping_com_ninguem_escutando_e_falso():
    from app.services import antivirus

    assert await antivirus.ping("127.0.0.1", 1, timeout=2) is False
