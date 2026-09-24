"""
Testes do layout de e-mail (`app/services/email_layout.py`).

O que estes testes protegem não é estética — é o que quebra em silêncio:

* **escape**: o nome do usuário entra no corpo. Em texto puro isso era
  inofensivo; em HTML é injeção, e ninguém percebe até alguém se cadastrar com
  um nome hostil;
* **paridade**: a parte de texto não é rascunho. Vários gateways corporativos
  entregam só ela, e filtro de spam penaliza HTML sem alternativa. Se as duas
  renderizações divergirem, metade dos destinatários lê outra coisa;
* **contraste**: branco sobre o azul da marca reprova o AA. O botão tem de usar
  o degrau 600, e é fácil alguém "corrigir" isso para a cor da marca achando que
  está sendo fiel à identidade.

Nada aqui envia e-mail nem toca SMTP.
"""

from __future__ import annotations

import re
from html import escape

import pytest

from app.services.email_layout import Mensagem, em_html, em_texto

_URL = "https://helphs.exemplo.com/confirmar-email?token=abc123&x=1"


def _mensagem(**ajustes) -> Mensagem:
    base = {
        "rotulo": "confirmação de conta",
        "titulo": "Confirme seu e-mail",
        "saudacao": "Olá, Welton.",
        "paragrafos": ("Recebemos o seu cadastro no HelpHS.",),
        "acao": ("Confirmar meu e-mail", _URL),
        "apoio": ("O link vale por 24 horas.",),
        "ressalva": "Se não foi você, ignore esta mensagem.",
    }
    base.update(ajustes)
    return Mensagem(**base)  # type: ignore[arg-type]


# ── Escape ────────────────────────────────────────────────────


def test_o_nome_do_usuario_nao_vira_html():
    """Cadastro com nome hostil não pode virar marcação dentro do e-mail."""
    hostil = '<script>alert("x")</script>'
    html = em_html(_mensagem(saudacao=f"Olá, {hostil}."))

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_a_url_e_escapada_no_atributo_href():
    """`&` cru no href quebra o XHTML e pode truncar a URL em cliente estrito."""
    html = em_html(_mensagem())

    assert 'href="https://helphs.exemplo.com/confirmar-email?token=abc123&amp;x=1"' in html


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("rotulo", "<b>rótulo</b>"),
        ("paragrafos", ("<img src=x onerror=1>",)),
        ("apoio", ("<i>apoio</i>",)),
        ("ressalva", "<u>ressalva</u>"),
        ("dados", (("<b>rot</b>", "<b>val</b>"),)),
    ],
)
def test_todo_campo_interpolado_e_escapado(campo, valor):
    """Não basta escapar a saudação: qualquer campo pode carregar dado de fora.

    A afirmação é sobre O VALOR, e não "o documento não contém `<img`". Era o
    segundo até 24/09/2026, e funcionava como atalho porque o layout não tinha
    imagem nenhuma — quando a logo por CID entrou, o atalho passou a acusar a
    própria faixa. A forma abaixo é mais estreita e mais forte: exige o valor
    escapado presente E o valor cru ausente, então continua caindo se alguém
    tirar o `escape`.
    """
    html = em_html(_mensagem(**{campo: valor}))

    crus = [valor] if isinstance(valor, str) else [p for t in valor for p in _partes(t)]
    for cru in crus:
        assert cru not in html, f"{campo} entrou cru no HTML: {cru}"
        assert escape(cru) in html, f"{campo} não apareceu escapado: {cru}"


def _partes(item):
    """Tuplas de `dados` são pares (rótulo, valor); o resto é string."""
    return item if isinstance(item, tuple) else (item,)


def test_a_unica_imagem_do_layout_e_a_logo():
    """A guarda que o teste acima deixou de fazer: nenhum `<img` inesperado.

    Um `<img>` a mais no documento é rastreador ou injeção — e é exatamente o
    que o atalho antigo pegava de graça. Aqui a conta é explícita.
    """
    from app.services.email_layout import CID_LOGO

    html = em_html(_mensagem(paragrafos=("<img src=x onerror=1>",)))

    imagens = re.findall(r"<img[^>]*>", html)
    assert len(imagens) == 1, f"imagem inesperada no layout: {imagens}"
    assert f"cid:{CID_LOGO}" in imagens[0]


# ── Paridade entre as duas versões ────────────────────────────


def test_o_texto_puro_carrega_a_url_inteira():
    """Quem receber só a parte de texto precisa de um caminho para o chamado."""
    texto = em_texto(_mensagem())

    assert _URL in texto


def test_as_duas_versoes_carregam_os_mesmos_paragrafos():
    m = _mensagem(paragrafos=("Primeiro parágrafo.", "Segundo parágrafo."))
    texto, html = em_texto(m), em_html(m)

    for p in m.paragrafos:
        assert p in texto
        assert p in html


def test_o_texto_puro_termina_com_a_assinatura():
    texto = em_texto(_mensagem())

    assert texto.rstrip().endswith("Health & Safety Tech")


def test_mensagem_sem_acao_nao_inventa_botao():
    """Notificação sem chamado associado não pode ganhar um botão para lugar nenhum."""
    m = _mensagem(acao=None)

    assert "Confirmar" not in em_html(m)
    assert "https://" not in em_texto(m)


# ── As decisões medidas ───────────────────────────────────────


def test_o_botao_nao_usa_o_azul_da_marca():
    """Branco sobre #1f89ca dá 3,83:1 e reprova o AA. O botão usa #1a71a8 (5,29:1).

    Se alguém "corrigir" a cor do botão para a da marca achando que é fidelidade
    de identidade, este teste cai.
    """
    html = em_html(_mensagem())
    botao = re.search(r'bgcolor="(#[0-9a-fA-F]{6})"[^>]*border-radius:4px', html)

    assert botao is not None, "o botão precisa de bgcolor em atributo, para o Outlook"
    assert botao.group(1).lower() == "#1a71a8"


def test_o_botao_e_celula_de_tabela():
    """No Outlook o `<a>` não aceita padding nem background: âncora vira texto azul."""
    html = em_html(_mensagem())

    assert re.search(r"<td[^>]+bgcolor=\"#1a71a8\"", html), "o botão não é célula"


def test_a_url_aparece_tambem_em_texto_no_html():
    """Cliente que não pinta o botão precisa de um caminho visível."""
    html = em_html(_mensagem())

    assert (
        html.count(_URL.replace("&", "&amp;")) >= 2
    ), "a URL tem que aparecer no href E como texto abaixo do botão"


def test_o_html_nao_depende_de_folha_externa_nem_de_script():
    """Todo cliente remove `<link>` e `<script>`; o Gmail app descarta o `<head>`."""
    html = em_html(_mensagem())

    assert "<script" not in html
    assert "<link" not in html
    assert 'style="' in html, "a cor tem que estar inline, não só no bloco <style>"


def test_o_html_declara_charset_e_esquema_de_cor():
    """Sem charset o Outlook assume a codepage local e acentua errado."""
    html = em_html(_mensagem())

    assert "charset=utf-8" in html
    assert 'name="color-scheme"' in html
    assert 'name="supported-color-schemes"' in html


def test_o_html_cabe_no_corte_do_gmail():
    """O Gmail corta em ~102 KB e esconde tudo abaixo, inclusive o botão."""
    html = em_html(_mensagem(paragrafos=tuple(f"Parágrafo {i}." for i in range(12))))

    assert len(html.encode("utf-8")) < 60_000


# ── A logo por CID, e o que sobra sem ela ─────────────────────
#
# A logo entrou em 24/09/2026 como ANEXO por `cid:`, e não como `data:` nem
# apontando para um endereço público.
#
# A objeção de 04/09 contra imagem tinha duas metades, e só uma delas continua
# valendo. A que caiu: "100 KB em base64 estouram o corte de ~102 KB do Gmail"
# — isso vale para imagem embutida NO CORPO; o anexo por CID é parte MIME
# separada e não conta no tamanho do HTML (o teste acima mede o corpo, e ele
# continua abaixo de 60 KB). A que CONTINUA valendo: o PNG tem tinta escura
# sobre transparência, e em cliente que inverte cores à força a marca some.
#
# É por isso que a faixa mantém a marca TIPOGRÁFICA junto da imagem. Os três
# testes abaixo prendem as três pontas: o CID existe, a imagem tem texto
# alternativo, e o nome da casa sobrevive sem imagem nenhuma.


def test_o_html_referencia_a_logo_por_cid():
    from app.services.email_layout import CID_LOGO

    html = em_html(_mensagem())

    assert f'src="cid:{CID_LOGO}"' in html
    # `data:` foi recusado: ~100 KB em base64 dentro do corpo estouram o corte
    # do Gmail e escondem o botão.
    assert "data:image" not in html


def test_a_imagem_da_logo_tem_texto_alternativo():
    """Cliente que bloqueia imagem mostra o `alt` — e ele tem de dizer a casa."""
    html = em_html(_mensagem())

    imagem = re.search(r"<img[^>]*>", html)
    assert imagem, "a faixa perdeu a imagem"
    assert 'alt="HelpHS"' in imagem.group(0)


def test_sem_a_imagem_o_email_continua_dizendo_o_nome_da_casa():
    """A prova de que a logo é ACRÉSCIMO, não a única identificação.

    Remove toda tag `<img>` do HTML — é o que o leitor vê quando o cliente
    bloqueia imagem, ou quando a inversão de cores apaga a marca — e exige que
    o nome da casa continue legível por TEXTO.
    """
    sem_imagens = re.sub(r"<img[^>]*>", "", em_html(_mensagem()))

    assert "Help Desk" in sem_imagens
    assert "Health &amp; Safety" in sem_imagens


def test_o_texto_puro_nao_menciona_a_logo():
    """A parte de texto não tem imagem e não deve falar de uma."""
    texto = em_texto(_mensagem())

    assert "cid:" not in texto
    assert "Health & Safety" in texto


def test_o_asset_canonico_da_logo_existe_e_e_png():
    """O asset de e-mail vive no BACKEND, e é o canônico para mensagens.

    A cópia do frontend não serve: o `COPY . .` do Dockerfile tem
    `backend/` como contexto, então `frontend/src/assets/` não existe na
    imagem. E o arquivo de lá sai do bundle do Vite com hash no nome, sem
    endereço estável.
    """
    from app.services.email_layout import LOGO_EMAIL

    assert LOGO_EMAIL.is_file(), f"asset de e-mail ausente: {LOGO_EMAIL}"
    assert LOGO_EMAIL.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
