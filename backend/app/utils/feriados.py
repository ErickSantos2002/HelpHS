"""
Dias em que o relógio do SLA não corre.

Até aqui só o fim de semana parava o relógio, e feriado contava como dia útil —
o sistema cobrava prazo sobre dia em que ninguém atendeu.

O QUE PARA, E O QUE NÃO PARA
----------------------------
**Só feriado NACIONAL.** Municipal do Recife não para: pelo menos um técnico
fica ativo. Estadual de Pernambuco também não — a "Revolução Pernambucana"
(6 de março) é o único que a biblioteca acrescenta em `subdiv="PE"`, e ele fica
de fora de propósito. Se um ano específico for exceção, ele entra na tabela
manual abaixo, com o decreto que o justifica.

O corte é o padrão da biblioteca, não uma manobra: `country_holidays("BR", years=…)` **sem
subdivisão** devolve exatamente os dez nacionais estatutários. Conferido na
0.65 para 2026 — Confraternização, Sexta-feira Santa, Tiradentes, Trabalhador,
Independência, Aparecida, Finados, Proclamação, Consciência Negra e Natal.

CARNAVAL É CALCULADO, NÃO DIGITADO
----------------------------------
Carnaval (segunda e terça) e quarta-feira de cinzas são dia parado, dia
inteiro. São móveis, mas derivam da Páscoa por deslocamento fixo, então
calcular é mais confiável do que uma tabela que alguém precisa alimentar.

Eles **não** vêm da `holidays`: no Brasil são ponto facultativo, não feriado
nacional em lei, então a biblioteca não os lista. Corpus Christi, pelo mesmo
motivo, também não vem — e por isso vive na tabela manual, já que observá-lo
depende de decreto.

A Páscoa vem de `dateutil.easter`, que já entra como dependência da `holidays`.
Deriva-la da "Sexta-feira Santa" que a `holidays` devolve funcionaria — foram
conferidos 2024, 2026 e 2027, e batem —, mas amarraria o cálculo ao TEXTO do
nome do feriado, que é tradução e muda de versão.
"""

from datetime import date, timedelta

import holidays
from dateutil.easter import easter
from loguru import logger

# ── A tabela manual ───────────────────────────────────────────
#
# ⚠️  ESTA LISTA PRECISA SER REVISTA TODO INÍCIO DE ANO.  ⚠️
#
# Corpus Christi, emenda e ponto facultativo por decreto não se adivinham: o
# governo do estado decide, e a decisão sai perto da data. Uma lista que
# termina em 2026 e é lida em 2027 não avisa que está incompleta — ela
# simplesmente devolve "nenhum feriado", e o prazo volta a ser cobrado sobre
# dia parado.
#
# Por isso `ANOS_CONFERIDOS` existe logo abaixo, e por isso há teste cobrando
# que o ano corrente esteja lá. Acrescentar um ano é editar duas linhas.
#
# Formato: data, o que é, e o ato que a justifica (com o ano do decreto).
_DIAS_PARADOS: tuple[tuple[date, str, str], ...] = (
    (
        date(2026, 6, 4),
        "Corpus Christi",
        "ponto facultativo estadual PE — decreto anual, confirmado para 2026",
    ),
)

# Anos cuja tabela manual foi conferida contra o decreto do estado.
#
# Ano ausente daqui NÃO é "ano sem feriado manual": é ano que ninguém olhou. A
# diferença entre os dois é a razão de esta constante existir separada da
# tabela — uma tabela vazia para 2027 e uma tabela não revista para 2027 são
# indistinguíveis olhando só os dados.
ANOS_CONFERIDOS: frozenset[int] = frozenset({2026})


# ── Cálculo ───────────────────────────────────────────────────

# Deslocamentos a partir do domingo de Páscoa. Fixos pela liturgia, não pelo
# calendário civil, então não mudam de ano para ano.
_CARNAVAL_SEGUNDA = -48
_CARNAVAL_TERCA = -47
_QUARTA_DE_CINZAS = -46


def _moveis_do_carnaval(ano: int) -> set[date]:
    """Segunda e terça de carnaval, mais a quarta-feira de cinzas."""
    domingo = easter(ano)
    return {
        domingo + timedelta(days=_CARNAVAL_SEGUNDA),
        domingo + timedelta(days=_CARNAVAL_TERCA),
        domingo + timedelta(days=_QUARTA_DE_CINZAS),
    }


def _manuais_do_ano(ano: int) -> set[date]:
    if ano not in ANOS_CONFERIDOS:
        # Aviso, e não exceção: levantar aqui derrubaria a abertura de chamado
        # na virada do ano, trocando um prazo generoso por uma indisponibilidade.
        # Quem precisa reagir a isto é quem lê log e quem roda a suíte, não o
        # cliente que está abrindo um chamado.
        logger.warning(
            f"Feriados: {ano} não está em ANOS_CONFERIDOS. Corpus Christi e emendas "
            f"por decreto NÃO serão considerados. Revise app/utils/feriados.py."
        )
    return {d for d, _, _ in _DIAS_PARADOS if d.year == ano}


def dias_parados(ano: int) -> dict[date, str]:
    """Todo dia do ano em que o relógio do SLA não corre, com o motivo.

    Devolve o motivo junto porque diagnóstico de prazo sempre termina em
    "por que este dia não contou?", e responder isso com um `set` exige abrir
    o código.
    """
    # `country_holidays` e nao `holidays.BR`: a biblioteca expoe os paises
    # dinamicamente, entao o atributo nao existe para o verificador de tipos. As
    # duas formas devolvem o mesmo conjunto, conferido para 2026.
    nacionais = holidays.country_holidays("BR", years=ano)  # sem subdivisao
    resultado: dict[date, str] = dict(nacionais.items())
    for d in _moveis_do_carnaval(ano):
        resultado[d] = "Carnaval / quarta-feira de cinzas"
    for d, descricao, ato in _DIAS_PARADOS:
        if d.year == ano:
            resultado[d] = f"{descricao} ({ato})"
    return resultado


# Um ano é consultado muitas vezes seguidas (todo chamado aberto no mesmo dia),
# e a `holidays` recalcula a cada chamada. O cache é por ano e nunca invalida —
# feriado de ano passado não muda, e a tabela manual só muda por deploy.
_CACHE: dict[int, frozenset[date]] = {}


def _do_ano(ano: int) -> frozenset[date]:
    if ano not in _CACHE:
        nacionais = set(holidays.country_holidays("BR", years=ano))
        _CACHE[ano] = frozenset(nacionais | _moveis_do_carnaval(ano) | _manuais_do_ano(ano))
    return _CACHE[ano]


def e_feriado(dia: date) -> bool:
    """O relógio para neste dia?"""
    return dia in _do_ano(dia.year)


def e_dia_util(dia: date) -> bool:
    """Dia em que o relógio do SLA corre: nem fim de semana, nem feriado.

    É a pergunta ÚNICA que o cálculo de horas úteis faz. Antes havia três
    laços separados perguntando `weekday() >= 5`, e três lugares para alguém
    corrigir dois.
    """
    return dia.weekday() < 5 and not e_feriado(dia)
