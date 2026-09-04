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
    """Não basta escapar a saudação: qualquer campo pode carregar dado de fora."""
    html = em_html(_mensagem(**{campo: valor}))

    assert "<b>" not in html
    assert "<img" not in html
    assert "<i>" not in html
    assert "<u>" not in html


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
