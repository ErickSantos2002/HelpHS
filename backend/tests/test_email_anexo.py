"""
A árvore MIME do e-mail, e o anexo da logo por `cid:`.

Por que este arquivo existe
---------------------------
Um `src="cid:..."` no HTML não faz nada sozinho: ele precisa de uma parte MIME
com o cabeçalho `Content-ID` correspondente, e essa parte precisa estar no lugar
certo da árvore. Errar o lugar não dá erro nenhum — só entrega um e-mail com um
retângulo vazio no lugar da marca.

A ÁRVORE CERTA, E O RISCO QUE ELA EVITA
---------------------------------------
O que se quer é::

    multipart/related
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    └── image/png  (Content-ID, inline)

O que NÃO se quer é a imagem como irmã do texto dentro do `alternative`. Pela
RFC 2046 o cliente escolhe a ÚLTIMA parte que sabe renderizar de um
`multipart/alternative` — com a imagem ali, um cliente poderia legitimamente
mostrar só a logo e descartar o HTML e o texto.

A `fastapi_mail` acerta isso por dentro: o `attach_alternative` envolve o
`multipart/alternative` num `multipart/related`, e o anexo entra no `related`.
Mas isso é comportamento de biblioteca de terceiro, verificado por leitura e
MEDIDO aqui — não é contrato documentado. Se uma atualização mudar a montagem,
este arquivo é o que avisa.

Nada aqui toca SMTP: a mensagem é capturada antes do envio e a árvore é montada
pela própria biblioteca, em memória.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.services.email_layout import CID_LOGO, LOGO_EMAIL


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",
        smtp_from_email="naoresponda@test.com",
        smtp_user="naoresponda@test.com",
    )


async def _captura(**kwargs):
    """Chama `send_email` e devolve o `MessageSchema` que chegaria ao SMTP."""
    from app.services import email as servico

    with patch.object(servico.FastMail, "send_message", new=AsyncMock()) as enviar:
        ok = await servico.send_email(settings=_settings(), **kwargs)
    assert ok is True, "o envio foi recusado antes de montar a mensagem"
    return enviar.await_args.args[0]


async def _arvore(**kwargs):
    """A árvore MIME de verdade, montada pela própria fastapi_mail."""
    from fastapi_mail.msg import MailMsg

    mensagem = await _captura(**kwargs)
    raiz = await MailMsg(mensagem)._message("HelpHS <naoresponda@test.com>")

    def achata(parte, profundidade=0):
        itens = [(profundidade, parte)]
        if parte.is_multipart():
            for sub in parte.get_payload():
                itens.extend(achata(sub, profundidade + 1))
        return itens

    return achata(raiz)


_CORPO = {"to_email": "destino@test.com", "subject": "[HelpHS] Teste", "body": "texto puro"}
_HTML = f'<html><body><img src="cid:{CID_LOGO}" alt="HelpHS"></body></html>'


# ── O anexo ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_com_html_a_logo_vai_anexada():
    mensagem = await _captura(**_CORPO, html=_HTML)

    assert len(mensagem.attachments) == 1, "a logo não foi anexada"


@pytest.mark.asyncio
async def test_o_content_id_do_anexo_casa_com_o_src_do_html():
    """Os `<>` entram no cabeçalho e NÃO no `src`. Trocar um sem o outro
    quebra a imagem sem erro nenhum."""
    mensagem = await _captura(**_CORPO, html=_HTML)

    arquivo, meta = mensagem.attachments[0]
    assert meta["headers"]["Content-ID"] == f"<{CID_LOGO}>"
    assert f'src="cid:{CID_LOGO}"' in _HTML


@pytest.mark.asyncio
async def test_o_anexo_e_inline_e_nao_arquivo_para_baixar():
    """Sem `inline`, o cliente mostra um clipe de anexo e não pinta a imagem."""
    mensagem = await _captura(**_CORPO, html=_HTML)

    _, meta = mensagem.attachments[0]
    assert meta["headers"]["Content-Disposition"].startswith("inline")
    assert meta["mime_type"] == "image"
    assert meta["mime_subtype"] == "png"


@pytest.mark.asyncio
async def test_sem_html_nao_vai_anexo_nenhum():
    """E-mail em texto puro não carrega 75 KB de imagem que ninguém vai ver."""
    mensagem = await _captura(**_CORPO)

    assert mensagem.attachments == []


# ── A árvore ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_arvore_e_related_envolvendo_alternative():
    tipos = [(d, p.get_content_type()) for d, p in await _arvore(**_CORPO, html=_HTML)]

    assert tipos[0] == (0, "multipart/related")
    assert (1, "multipart/alternative") in tipos
    assert (2, "text/plain") in tipos
    assert (2, "text/html") in tipos


@pytest.mark.asyncio
async def test_a_imagem_e_irma_do_alternative_e_nao_parte_dele():
    """O ponto central deste arquivo.

    Dentro do `alternative`, a RFC 2046 permite ao cliente escolher a imagem e
    descartar o HTML — o leitor receberia só a logo.
    """
    arvore = await _arvore(**_CORPO, html=_HTML)
    imagens = [(d, p) for d, p in arvore if p.get_content_type() == "image/png"]

    assert len(imagens) == 1
    profundidade, imagem = imagens[0]
    assert profundidade == 1, "a imagem entrou DENTRO do multipart/alternative"
    assert imagem.get("Content-ID") == f"<{CID_LOGO}>"


@pytest.mark.asyncio
async def test_o_texto_puro_vem_antes_do_html_no_alternative():
    """Ordem crescente de preferência: quem só lê texto pega o primeiro."""
    arvore = await _arvore(**_CORPO, html=_HTML)
    dentro = [p.get_content_type() for d, p in arvore if d == 2]

    assert dentro == ["text/plain", "text/html"]


# ── O asset ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_o_anexo_carrega_os_bytes_do_asset_canonico():
    mensagem = await _captura(**_CORPO, html=_HTML)

    arquivo, _ = mensagem.attachments[0]
    assert arquivo.file.read() == LOGO_EMAIL.read_bytes()
