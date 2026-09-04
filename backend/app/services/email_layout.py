"""
O layout dos e-mails: uma mensagem, duas renderizações.

Por que existe
--------------
Até 04/09/2026 todo e-mail saía em texto puro, sem cor, sem marca e sem botão —
e o link ia como URL nua no meio do parágrafo. Este módulo dá a eles a
identidade da Health & Safety.

A `Mensagem` é a fonte única. `em_texto` e `em_html` a renderizam, e é por isso
que as duas versões não podem divergir: quem acrescentar um parágrafo o
acrescenta uma vez só. Isso importa porque a parte de texto NÃO é decorativa —
filtro de spam penaliza HTML sem alternativa, e gateway corporativo às vezes
entrega só ela.

As decisões que não são estéticas
---------------------------------
**Tabela, não div.** O Outlook clássico renderiza com o motor do Word: não
conhece flex, grid, float nem `max-width`. Todo o esqueleto é
`<table role="presentation">` aninhada, com `width` em atributo.

**CSS no atributo `style`, nunca em folha.** O app do Gmail com conta não-Google
descarta o `<head>` inteiro. O bloco `<style>` existe só para o que não dá para
inlinear: a media query e o esquema de cor.

**Botão é célula de tabela.** No Outlook o `<a>` não aceita padding nem
background: âncora estilizada vira texto azul sublinhado. E abaixo do botão vai
sempre a URL em texto, porque quem estiver num cliente que não pinta o botão
precisa de um caminho.

**O azul da marca não pinta o botão.** Branco sobre `#1f89ca` dá 3,83:1 e
reprova o AA para texto normal. O botão usa `#1a71a8` (5,29:1). A faixa do topo
fica com o azul da marca porque ali o texto é grande e negrito, onde o limiar é
3:1 — e por isso mesmo NÃO cabe rótulo pequeno sobre ela.

**Marca tipográfica, não imagem.** O logo do projeto é PNG com transparência e
tinta escura: no Gmail e Outlook do celular, que invertem cores à força, o fundo
escurece e os pixels não, e a marca some. Além disso, 75 KB viram ~100 KB em
base64 e estouram sozinhos o corte de ~102 KB do Gmail, que esconde tudo abaixo
— inclusive o botão. Texto nunca é bloqueado, não pesa e não depende de o
backend passar a servir arquivo estático.

**Tudo escapado.** `html.escape` em cada valor interpolado. Hoje o nome do
usuário entra no corpo e, em texto puro, isso é inofensivo; em HTML seria
injeção.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

# ── Paleta, lida do design system da Health & Safety ──────────
# frontend/src/design-system/tokens/colors.css. Os contrastes ao lado saem da
# fórmula WCAG 2.x, sem arredondar para cima.
_MARCA = "#1f89ca"  # primary-500 — só faixa, com texto grande
_ACAO = "#1a71a8"  # primary-600 — branco por cima: 5,29:1
_TINTA = "#0f172a"  # slate-900   — sobre branco: 17,85:1
_APOIO = "#475569"  # slate-600   — sobre branco:  7,58:1
_MOLDURA = "#f8fafc"  # slate-50
_LINHA = "#e2e8f0"  # slate-200   — decorativa, nunca informativa
_BRANCO = "#ffffff"

_FONTE = "'Plus Jakarta Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"

ASSINATURA = "Health &amp; Safety Tech"
ASSINATURA_TEXTO = "Health & Safety Tech"


@dataclass(frozen=True)
class Mensagem:
    """O conteúdo de um e-mail, antes de virar texto ou HTML."""

    rotulo: str
    """Categoria em maiúsculas, acima do título. Ex.: "confirmação de conta"."""

    titulo: str
    saudacao: str | None = None
    paragrafos: tuple[str, ...] = ()
    acao: tuple[str, str] | None = None
    """(rótulo do botão, URL). O texto sempre repete a URL abaixo."""

    apoio: tuple[str, ...] = ()
    """Notas depois do botão — prazo, uso único."""

    ressalva: str | None = None
    """A nota de segurança do rodapé ("se não foi você...")."""

    dados: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    """Pares rótulo/valor num cartão. Ex.: ("protocolo", "HS-2026-0042")."""


# ── Texto puro ────────────────────────────────────────────────


def em_texto(m: Mensagem) -> str:
    """A versão que vai na parte `text/plain` — e que não é rascunho.

    Vários gateways corporativos entregam só esta. Ela carrega a mesma
    informação, inclusive a URL inteira.
    """
    linhas: list[str] = []
    if m.saudacao:
        linhas.append(m.saudacao)
        linhas.append("")
    linhas.extend(_intercala(m.paragrafos))

    for rotulo, valor in m.dados:
        linhas.append(f"{rotulo}: {valor}")
    if m.dados:
        linhas.append("")

    if m.acao:
        _, url = m.acao
        linhas.append(url)
        linhas.append("")

    linhas.extend(_intercala(m.apoio))

    if m.ressalva:
        linhas.append(m.ressalva)
        linhas.append("")

    linhas.append(ASSINATURA_TEXTO)
    return "\n".join(linhas).strip() + "\n"


def _intercala(paragrafos: tuple[str, ...]) -> list[str]:
    saida: list[str] = []
    for p in paragrafos:
        saida.append(p)
        saida.append("")
    return saida


# ── HTML ──────────────────────────────────────────────────────


def em_html(m: Mensagem) -> str:
    """A versão que vai na parte `text/html`.

    Escrita para o pior cliente, não para o navegador: tabela aninhada, estilo
    no atributo, botão em célula, largura em atributo. Nenhuma das quebras que
    isto evita aparece abrindo o arquivo no Chrome.
    """
    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" \
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="pt-BR">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light dark" />
<meta name="supported-color-schemes" content="light dark" />
<title>{escape(m.titulo)}</title>
<!--[if mso]>
<xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml>
<style>*{{font-family:'Segoe UI',Arial,sans-serif !important;}}</style>
<![endif]-->
<style>
  @media only screen and (max-width:620px) {{
    .caixa {{ width:100% !important; }}
    .respiro {{ padding-left:20px !important; padding-right:20px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background-color:{_MOLDURA};">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"
       style="background-color:{_MOLDURA};">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" class="caixa"
       style="width:600px;max-width:600px;background-color:{_BRANCO};
              border:1px solid {_LINHA};border-radius:6px;">

  <tr>
    <td align="center" bgcolor="{_MARCA}"
        style="background-color:{_MARCA};padding:20px 24px;border-radius:6px 6px 0 0;">
      <span style="font-family:{_FONTE};font-size:19px;line-height:24px;
                   font-weight:700;color:{_BRANCO};">Help Desk
        <span style="font-weight:400;">Health &amp; Safety</span></span>
    </td>
  </tr>

  <tr>
    <td class="respiro" style="padding:28px 32px 8px 32px;font-family:{_FONTE};">
      <div style="font-size:11px;line-height:16px;letter-spacing:1.2px;
                  text-transform:uppercase;color:{_APOIO};">{escape(m.rotulo)}</div>
    </td>
  </tr>
{_saudacao_html(m)}{_paragrafos_html(m)}{_dados_html(m)}{_acao_html(m)}{_apoio_html(m)}
  <tr>
    <td class="respiro" style="padding:8px 32px 28px 32px;"></td>
  </tr>
{_rodape_html(m)}
</table>

</td></tr>
</table>
</body>
</html>
"""


def _celula(conteudo: str, *, topo: int = 0, base: int = 12) -> str:
    return (
        f'  <tr><td class="respiro" '
        f'style="padding:{topo}px 32px {base}px 32px;font-family:{_FONTE};">'
        f"{conteudo}</td></tr>\n"
    )


def _saudacao_html(m: Mensagem) -> str:
    if not m.saudacao:
        return ""
    return _celula(
        f'<div style="font-size:16px;line-height:24px;color:{_TINTA};">'
        f"{escape(m.saudacao)}</div>",
        topo=4,
    )


def _paragrafos_html(m: Mensagem) -> str:
    return "".join(
        _celula(f'<div style="font-size:15px;line-height:23px;color:{_TINTA};">{escape(p)}</div>')
        for p in m.paragrafos
    )


def _dados_html(m: Mensagem) -> str:
    if not m.dados:
        return ""
    linhas = "".join(
        f'<div style="font-size:11px;line-height:16px;letter-spacing:1px;'
        f'text-transform:uppercase;color:{_APOIO};padding-top:{8 if i else 0}px;">'
        f"{escape(rotulo)}</div>"
        f'<div style="font-size:15px;line-height:22px;font-weight:600;color:{_TINTA};">'
        f"{escape(valor)}</div>"
        for i, (rotulo, valor) in enumerate(m.dados)
    )
    return _celula(
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"'
        f' style="background-color:{_MOLDURA};border:1px solid {_LINHA};border-radius:4px;">'
        f'<tr><td style="padding:14px 16px;font-family:{_FONTE};">{linhas}</td></tr></table>'
    )


def _acao_html(m: Mensagem) -> str:
    if not m.acao:
        return ""
    texto, url = m.acao
    seguro = escape(url, quote=True)
    botao = (
        f'<table role="presentation" border="0" cellpadding="0" cellspacing="0">'
        f'<tr><td align="center" bgcolor="{_ACAO}" '
        f'style="background-color:{_ACAO};border-radius:4px;">'
        f'<a href="{seguro}" style="display:inline-block;padding:13px 28px;'
        f"font-family:{_FONTE};font-size:15px;line-height:20px;font-weight:600;"
        f'color:{_BRANCO};text-decoration:none;">{escape(texto)}</a>'
        f"</td></tr></table>"
    )
    alternativa = (
        f'<div style="font-size:13px;line-height:20px;color:{_APOIO};padding-top:16px;">'
        f"Se o botão não funcionar, copie e cole este endereço no navegador:</div>"
        f'<div style="font-size:12px;line-height:19px;color:{_ACAO};'
        f'word-break:break-all;padding-top:4px;">{escape(url)}</div>'
    )
    return _celula(botao + alternativa, topo=8, base=4)


def _apoio_html(m: Mensagem) -> str:
    return "".join(
        _celula(
            f'<div style="font-size:13px;line-height:20px;color:{_APOIO};">{escape(p)}</div>',
            base=8,
        )
        for p in m.apoio
    )


def _rodape_html(m: Mensagem) -> str:
    ressalva = (
        f'<div style="font-size:12px;line-height:19px;color:{_APOIO};padding-bottom:10px;">'
        f"{escape(m.ressalva)}</div>"
        if m.ressalva
        else ""
    )
    return (
        f'  <tr><td class="respiro" bgcolor="{_MOLDURA}" '
        f'style="background-color:{_MOLDURA};border-top:1px solid {_LINHA};'
        f'border-radius:0 0 6px 6px;padding:16px 32px;font-family:{_FONTE};">'
        f"{ressalva}"
        f'<div style="font-size:12px;line-height:19px;color:{_APOIO};">'
        f"{ASSINATURA} &middot; e-mail automático do sistema de chamados.</div>"
        f"</td></tr>\n"
    )
