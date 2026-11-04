"""
A célula de CSV que planilha nenhuma executa (SEC-12).

O CSV do relatório leva texto que veio de fora: o título do chamado é escrito
pelo cliente, a justificativa pelo técnico, o nome do responsável pela pessoa.
Aberto no Excel, um título `=HYPERLINK(...)` vira fórmula na máquina do admin.

Estes casos prendem a regra célula a célula (`celula_segura`) e o escritor que
a aplica antes de serializar (`EscritorCsvSeguro`). Que o export use o
escritor é provado contra o banco em `test_exportacao_csv_postgres.py`.
"""

import csv
import io

import pytest

from app.utils.csv_seguro import EscritorCsvSeguro, celula_segura, valor_original

# ── As fórmulas ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "valor",
    [
        "=1+1",
        "+1+1",
        "-1+1",
        "@SUM(1,1)",
        '=HYPERLINK("http://exemplo.test","clique")',
        "=cmd|' /C calc'!A0",
    ],
)
def test_formula_no_inicio_ganha_o_apostrofo(valor):
    assert celula_segura(valor) == "'" + valor


@pytest.mark.parametrize(
    "valor",
    [
        " =1+1",  # espaço
        "   +1+1",  # vários espaços
        "\t=1+1",  # tabulação
        "\x00=1+1",  # nulo
        "\x1f-1",  # controle
        " =1+1",  # espaço não separável
        "​=1+1",  # espaço de largura zero
        "﻿=1+1",  # BOM no meio do arquivo
        "　=1+1",  # espaço ideográfico
        " \t​ =1+1",  # tudo junto
    ],
)
def test_formula_escondida_atras_de_espaco_ou_controle(valor):
    """Planilha que apara o começo da célula acharia a fórmula logo depois."""
    assert celula_segura(valor) == "'" + valor


# ── Quebra de linha dentro da célula ─────────────────────────


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        # A linha do meio era executada pelo Excel pt-BR no clique duplo
        # (medido em 04/11/2026): ele não respeita a quebra entre aspas, e a
        # linha física vira célula própria. Por isso a regra vale por LINHA.
        ("a\r\n=1+1\r\nb", "a\r\n'=1+1\r\nb"),
        ("a\n+2+2\nb", "a\n'+2+2\nb"),
        ("a\r-3+3\rb", "a\r'-3+3\rb"),
        ("\n=1+1", "\n'=1+1"),
        ("\r=1+1", "\r'=1+1"),
        ("\r\n@SUM(1)", "\r\n'@SUM(1)"),
        (" \t \r\n =1+1", " \t \r\n' =1+1"),
        ("=1\n=2\r\n=3", "'=1\n'=2\r\n'=3"),
        ("linha 1\nlinha 2", "linha 1\nlinha 2"),
        ("ok\n'citação", "ok\n''citação"),
        ("\r", "\r"),
        ("\n\n", "\n\n"),
    ],
)
def test_cada_linha_da_celula_recebe_a_mesma_regra(valor, esperado):
    assert celula_segura(valor) == esperado


@pytest.mark.parametrize("valor", ["＝1+1", "＋1", "－1", "＠SUM(1)", "﹦1+1", "﹢1", "﹣1", "﹫x"])
def test_variantes_de_largura_total_tambem(valor):
    """Variantes que algum leitor pode normalizar para `= + - @` ASCII."""
    assert celula_segura(valor) == "'" + valor


@pytest.mark.parametrize("valor", ["\t", "\tqualquer coisa", "x\n\tlinha"])
def test_tabulacao_no_inicio_da_linha_basta_sozinha(valor):
    """
    A OWASP trata `\\t` e `\\r` iniciais como gatilho. O `\\r` aqui é quebra
    de linha, e a linha seguinte é que passa pela regra; o `\\t` é gatilho.
    """
    linhas = valor.split("\n")
    assert celula_segura(valor) == "\n".join(
        "'" + linha if linha.startswith("\t") else linha for linha in linhas
    )


# ── O que não muda ───────────────────────────────────────────


@pytest.mark.parametrize(
    "valor",
    [
        "Impressora não imprime",
        "Etilômetro BAF-2000 sem calibração",
        "Resolvido em 2 dias; peça trocada",
        "100% fora do ar",
        "Cliente pediu: troca = urgente",  # `=` no meio não é fórmula
        "a-b",
        "e-mail@empresa.com",
        "HS-2026-0001",
        "2026-10-01",
        "critical",
        "Ação — 日本語 — 🚑",
    ],
)
def test_texto_legitimo_passa_intacto(valor):
    assert celula_segura(valor) == valor


@pytest.mark.parametrize("valor", [None, "", 0, 7, -3, 75.0, -1.5, True])
def test_vazio_nulo_e_numero_passam_intactos(valor):
    """Número que o próprio relatório calcula não é texto de usuário: fica número."""
    assert celula_segura(valor) is valor


def test_espaco_puro_sem_formula_fica_como_esta():
    assert celula_segura("   ") == "   "
    assert celula_segura(" texto") == " texto"


# ── Reversível ───────────────────────────────────────────────


def test_apostrofo_original_tambem_ganha_prefixo_para_a_volta_ser_unica():
    """
    Sem isto, `'=x` escrito pelo usuário e `=x` neutralizado sairiam iguais. Com
    o prefixo em todo valor que já começa por apóstrofo, a volta é uma regra
    só: tira UM apóstrofo do começo, se houver.
    """
    assert celula_segura("'=x") == "''=x"
    assert celula_segura("'citação'") == "''citação'"


@pytest.mark.parametrize(
    "valor",
    [
        "=1+1",
        "'=1+1",
        "''",
        "'",
        " =x",
        "\t",
        "texto",
        "Ação — 日本語",
        "",
        "-1",
        "linha 1\nlinha 2",
        "a\r\n=1+1\r\nb",
        "'x\n'=y\r''z",
        "\r\n\n\r",
        " \t \r\n =1+1",
    ],
)
def test_valor_original_desfaz_exatamente(valor):
    assert valor_original(celula_segura(valor)) == valor


# ── O escritor ───────────────────────────────────────────────


def _escreve(*linhas):
    buf = io.StringIO()
    escritor = EscritorCsvSeguro(buf)
    for linha in linhas:
        escritor.writerow(linha)
    return buf.getvalue()


def test_escritor_neutraliza_cada_celula_e_preserva_colunas():
    texto = _escreve(
        ["Protocolo", "Título", "Prioridade", "Resolvido em", "Responsável", "Motivo"],
        ["HS-1", "=1+1", "high", "01/10/2026 10:00", "@Ana", "-atraso"],
    )

    linhas = list(csv.reader(io.StringIO(texto)))
    assert linhas == [
        ["Protocolo", "Título", "Prioridade", "Resolvido em", "Responsável", "Motivo"],
        ["HS-1", "'=1+1", "high", "01/10/2026 10:00", "'@Ana", "'-atraso"],
    ]


def test_quebra_de_linha_nao_cria_registro_novo():
    """
    O ataque clássico de separador: um título com `\\r\\n` e vírgulas tentando
    abrir uma linha nova que comece por fórmula. O `csv` põe o campo entre
    aspas e a linha segue sendo UMA, com as mesmas colunas.
    """
    malicioso = 'ok"\r\n=1+1,"=2+2"\n@x'
    texto = _escreve(["HS-1", malicioso, "fim"])

    linhas = list(csv.reader(io.StringIO(texto)))
    assert len(linhas) == 1
    assert len(linhas[0]) == 3
    assert linhas[0][1] == 'ok"\r\n\'=1+1,"=2+2"\n\'@x'
    assert valor_original(linhas[0][1]) == malicioso


@pytest.mark.parametrize(
    "valor",
    [
        "a\r\n=1+1\r\nb",
        "a\n+2+2\nb",
        "a\r-3+3\rb",
        'x\r\n=1+1,"=2"\n@y',
        "x\n \t=1",
        "x\n​@y",
    ],
)
def test_nenhuma_linha_fisica_do_arquivo_comeca_por_formula(valor):
    """
    O que o leitor que ignora as aspas enxerga: cada linha física do arquivo
    como o começo de uma célula. Nenhuma pode abrir com gatilho.
    """
    texto = _escreve(["HS-1", valor, "fim"])

    for fisica in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        visivel = fisica.lstrip(" \t​ ﻿").lstrip('"')
        assert not visivel.startswith(("=", "+", "-", "@")), repr(fisica)


def test_aspas_virgulas_e_ponto_e_virgula_sao_serializados_corretamente():
    valores = ['Diz "olá", tchau', "a;b;c", "x,y", '"=1+1"']
    texto = _escreve(valores)

    (linha,) = list(csv.reader(io.StringIO(texto)))
    # `"=1+1"` começa com aspas: não é gatilho, e as aspas são do valor.
    assert linha == valores


def test_aspas_do_csv_nao_bastam_por_isso_o_prefixo_vem_antes():
    """Fórmula com vírgula sai entre aspas E com apóstrofo: aspas sozinhas não protegem."""
    texto = _escreve(['=HYPERLINK("http://x.test","a")'])

    assert texto.startswith("\"'=HYPERLINK(")
    (linha,) = list(csv.reader(io.StringIO(texto)))
    assert linha == ['\'=HYPERLINK("http://x.test","a")']


def test_unicode_atravessa_o_escritor():
    texto = _escreve(["Ação", "日本語", "🚑", "=Ação"])

    (linha,) = list(csv.reader(io.StringIO(texto)))
    assert linha == ["Ação", "日本語", "🚑", "'=Ação"]


def test_linha_vazia_e_celula_nula():
    texto = _escreve([], ["a", None, "", 3])

    linhas = list(csv.reader(io.StringIO(texto)))
    assert linhas == [[], ["a", "", "", "3"]]


def test_o_escritor_nao_altera_a_lista_recebida():
    linha = ["=1+1", "ok"]
    _escreve(linha)
    assert linha == ["=1+1", "ok"]
