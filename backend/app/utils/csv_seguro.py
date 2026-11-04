"""
CSV que planilha nenhuma executa (SEC-12).

O CSV do relatório leva texto escrito por gente de fora do sistema: o título do
chamado vem do cliente, a justificativa do técnico, o nome do responsável da
própria pessoa. Aberto no Excel, um título `=HYPERLINK(...)` vira fórmula na
máquina de quem baixou — e as aspas do CSV não impedem isso: elas delimitam o
campo, não dizem à planilha que ele é texto.

A defesa é por CÉLULA e ANTES da serialização: o texto que a planilha poderia
ler como fórmula ganha um apóstrofo na frente, e só depois o `csv` do Python
cuida de aspas, vírgulas e quebras de linha. É a recomendação da OWASP para
"CSV Injection", com três acréscimos:

- **A regra vale para CADA LINHA da célula, não só para o começo dela.** O
  Excel em pt-BR, no clique duplo, não respeita a quebra de linha entre aspas:
  a linha física seguinte vira célula própria. Medido em 04/11/2026 no Excel
  16: `"a⏎=1+1⏎b"` executava a linha do meio, com ou sem apóstrofo no começo
  da célula.
- **Espaço e controle antes da fórmula também contam.** Leitor que apara o
  começo da célula acharia `=` logo depois de ` `, `\\t`, `\\u200b`, BOM...
- **Apóstrofo original também ganha prefixo.** Assim a volta é uma regra só —
  tirar UM apóstrofo do começo de cada linha, se houver (`valor_original`) — e
  `'=x` escrito pelo usuário nunca se confunde com `=x` neutralizado.

O que NÃO muda: número, nulo e texto cujas linhas não começam por gatilho. O
banco não é tocado — a neutralização vive só no arquivo gerado.

O custo é visível e aceito: quem abre o arquivo vê o apóstrofo na frente
dessas linhas (o Excel, ao abrir CSV, não o esconde como faz na digitação). O
dado não se perde; ele fica inerte.
"""

import csv
import re
import unicodedata
from typing import Any

PREFIXO = "'"

# `= + - @` e as variantes de largura total e pequena, que algum leitor pode
# normalizar para o ASCII antes de decidir se é fórmula.
_GATILHOS = frozenset("=+-@＝＋－＠﹦﹢﹣﹫")

# O `\\t` sozinho no começo já é gatilho, na lista da OWASP. O `\\r` da mesma
# lista é tratado como quebra de linha: a linha depois dele passa pela regra.
_TABULACAO = "\t"

# As quebras que as planilhas reconhecem. O grupo faz o `split` devolver os
# separadores, para a célula ser remontada byte a byte.
_QUEBRA_DE_LINHA = re.compile(r"(\r\n|\r|\n)")

# Categorias Unicode que um leitor pode descartar no começo da célula: controle
# (Cc), formato invisível como o espaço de largura zero e o BOM (Cf) e os
# separadores de espaço, linha e parágrafo (Zs, Zl, Zp).
_DESCARTAVEIS = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})


def _primeiro_visivel(texto: str) -> str:
    for caractere in texto:
        if not (caractere.isspace() or unicodedata.category(caractere) in _DESCARTAVEIS):
            return caractere
    return ""


def _linha_segura(linha: str) -> str:
    if linha and (
        linha[0] == PREFIXO or linha[0] == _TABULACAO or _primeiro_visivel(linha) in _GATILHOS
    ):
        return PREFIXO + linha
    return linha


def celula_segura(valor: Any) -> Any:
    """A célula como deve ir para o CSV: cada linha perigosa ganha o apóstrofo."""
    if not isinstance(valor, str) or not valor:
        return valor
    partes = _QUEBRA_DE_LINHA.split(valor)
    # Índices pares são linhas; ímpares, as quebras entre elas.
    return "".join(_linha_segura(p) if i % 2 == 0 else p for i, p in enumerate(partes))


def valor_original(celula: str) -> str:
    """Desfaz `celula_segura`: tira UM apóstrofo do começo de cada linha, se houver."""
    partes = _QUEBRA_DE_LINHA.split(celula)
    return "".join(
        p[1:] if i % 2 == 0 and p.startswith(PREFIXO) else p for i, p in enumerate(partes)
    )


class EscritorCsvSeguro:
    """`csv.writer` que passa cada célula por `celula_segura` antes de escrever."""

    def __init__(self, destino: Any) -> None:
        self._escritor = csv.writer(destino)

    def writerow(self, linha: list[Any]) -> None:
        self._escritor.writerow([celula_segura(celula) for celula in linha])
