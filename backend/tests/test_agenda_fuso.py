"""
O fuso da agenda: a janela do mês e as bordas do dia inteiro.

Estes casos são de função pura e rodam sem banco. Existem separados do
`test_calendar.py` porque lá o banco é mockado — nenhum caso de lá consegue
provar QUAIS eventos a janela devolve, só que a rota respondeu 200. O que
decide se um evento cai em janeiro ou em fevereiro é a aritmética daqui, e é
aqui que ela é medida. A ponta com Postgres de verdade está em
`test_calendar_postgres.py`.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.utils.agenda import (
    FUSO_PADRAO,
    bordas_do_dia_inteiro,
    janela_do_mes,
    resolve_fuso,
)

RECIFE = ZoneInfo("America/Recife")


# ── O fuso ────────────────────────────────────────────────────


def test_sem_informacao_o_fuso_e_recife():
    """O padrão não é UTC.

    Quem opera o sistema está em Recife, e um cliente antigo que não mande o
    fuso precisa ver o mês que ele esperaria ver — não o mês deslocado três
    horas. Cair em UTC por omissão seria escolher o fuso de ninguém.
    """
    assert resolve_fuso(None) is FUSO_PADRAO
    assert str(FUSO_PADRAO) == "America/Recife"


def test_recife_nao_tem_horario_de_verao():
    """A premissa da conta, medida em vez de suposta.

    Pernambuco nunca entrou no horário de verão, nem antes de ele acabar no
    país em 2019 — o decreto alcançava Sul, Sudeste e Centro-Oeste. Por isso a
    janela do mês pode ser somada com um deslocamento fixo. Se algum dia esta
    asserção quebrar, a aritmética de `janela_do_mes` precisa ser revista
    junto: um mês teria 3 h de um lado e 2 h do outro.
    """
    janeiro = datetime(2026, 1, 15, 12, tzinfo=RECIFE)
    julho = datetime(2026, 7, 15, 12, tzinfo=RECIFE)
    assert janeiro.utcoffset() == julho.utcoffset()
    assert janeiro.utcoffset().total_seconds() == -3 * 3600


def test_fuso_conhecido_e_aceito():
    assert resolve_fuso("UTC") == ZoneInfo("UTC")
    assert resolve_fuso("America/Sao_Paulo") == ZoneInfo("America/Sao_Paulo")


def test_fuso_inexistente_e_recusado():
    """Recusa, e não volta calado para o padrão.

    Cair no padrão faria um cliente com o fuso escrito errado receber o mês de
    outro lugar e nunca descobrir — o sintoma seria "alguns eventos somem", meses
    depois, sem nada apontando para a letra trocada.
    """
    with pytest.raises(ValueError, match="Marte/Olimpo"):
        resolve_fuso("Marte/Olimpo")


# ── A janela do mês ───────────────────────────────────────────


def test_janela_de_janeiro_em_recife_comeca_as_tres_da_manha_em_utc():
    """Meia-noite em Recife é 03:00Z, e a janela é essa, não a de UTC."""
    inicio, fim = janela_do_mes(2026, 1, RECIFE)

    assert inicio == datetime(2026, 1, 1, 3, tzinfo=UTC)
    assert fim == datetime(2026, 2, 1, 3, tzinfo=UTC)


def test_dezembro_vira_o_ano():
    inicio, fim = janela_do_mes(2026, 12, RECIFE)

    assert inicio == datetime(2026, 12, 1, 3, tzinfo=UTC)
    assert fim == datetime(2027, 1, 1, 3, tzinfo=UTC)


def test_em_utc_a_janela_e_a_de_antes():
    """Quem pedir UTC recebe o comportamento anterior, sem surpresa."""
    inicio, fim = janela_do_mes(2026, 1, ZoneInfo("UTC"))

    assert inicio == datetime(2026, 1, 1, tzinfo=UTC)
    assert fim == datetime(2026, 2, 1, tzinfo=UTC)


def test_a_janela_e_sempre_devolvida_em_utc():
    """O que vai para a consulta é UTC, porque a coluna é `timestamptz`.

    Devolver com o fuso original funcionaria — o Postgres converteria —, mas
    deixaria a comparação dependendo de uma conversão implícita que não está
    escrita em lugar nenhum.
    """
    inicio, fim = janela_do_mes(2026, 6, RECIFE)

    assert inicio.tzinfo is UTC
    assert fim.tzinfo is UTC


def test_o_evento_das_22h_de_31_01_cai_em_janeiro_e_nao_em_fevereiro():
    """O caso que motivou a mudança.

    22:00 do dia 31 em Recife é 01:00Z do dia 1º de fevereiro. Com a janela
    calculada em UTC — como era antes — o mês de janeiro terminava às 00:00Z do
    dia 1º, e este evento ficava de fora: a pessoa criava em janeiro e ele
    aparecia em fevereiro.

    A sobreposição aqui é a mesma que o SQL expressa:
    `start < fim_da_janela AND end >= inicio_da_janela`.
    """
    inicio_evento = datetime(2026, 1, 31, 22, tzinfo=RECIFE)
    fim_evento = datetime(2026, 1, 31, 23, tzinfo=RECIFE)

    jan_ini, jan_fim = janela_do_mes(2026, 1, RECIFE)
    assert inicio_evento < jan_fim and fim_evento >= jan_ini, "sumiu de janeiro"

    fev_ini, fev_fim = janela_do_mes(2026, 2, RECIFE)
    assert not (inicio_evento < fev_fim and fim_evento >= fev_ini), "vazou para fevereiro"

    # E a prova de que a janela antiga reprovaria: em UTC ele cai fora de
    # janeiro. Sem esta linha o caso passaria mesmo com a correção desfeita.
    jan_utc_ini, jan_utc_fim = janela_do_mes(2026, 1, ZoneInfo("UTC"))
    assert not (inicio_evento < jan_utc_fim and fim_evento >= jan_utc_ini)


# ── As bordas do dia inteiro ──────────────────────────────────


def test_dia_inteiro_de_um_dia_so_vai_de_zero_a_quase_meia_noite():
    inicio, fim = bordas_do_dia_inteiro(
        datetime(2026, 1, 15, tzinfo=UTC), datetime(2026, 1, 15, tzinfo=UTC)
    )

    assert inicio == datetime(2026, 1, 15, 0, 0, 0, 0, tzinfo=UTC)
    assert fim == datetime(2026, 1, 15, 23, 59, 59, 999999, tzinfo=UTC)


def test_dia_inteiro_de_varios_dias_cobre_do_primeiro_ao_ultimo():
    inicio, fim = bordas_do_dia_inteiro(
        datetime(2026, 1, 15, tzinfo=UTC), datetime(2026, 1, 17, tzinfo=UTC)
    )

    assert inicio == datetime(2026, 1, 15, tzinfo=UTC)
    assert fim == datetime(2026, 1, 17, 23, 59, 59, 999999, tzinfo=UTC)


def test_a_hora_que_veio_junto_e_descartada():
    """Dia inteiro é dia: a hora que o cliente mandou não sobrevive.

    Sem isto, marcar "dia inteiro" num evento que já tinha 14:30 guardaria
    14:30 e a chave diria outra coisa — o registro passaria a se contradizer,
    e quem lesse a coluna sem ler a chave veria um evento de meia tarde.
    """
    inicio, fim = bordas_do_dia_inteiro(
        datetime(2026, 1, 15, 14, 30, 45, tzinfo=UTC),
        datetime(2026, 1, 15, 17, 0, tzinfo=UTC),
    )

    assert inicio == datetime(2026, 1, 15, tzinfo=UTC)
    assert fim == datetime(2026, 1, 15, 23, 59, 59, 999999, tzinfo=UTC)


def test_o_dia_do_evento_de_dia_inteiro_e_o_dia_em_utc():
    """Dia inteiro é data FLUTUANTE, e é isso que salva os eventos antigos.

    Todo evento que já existe foi gravado como `00:00:00Z`–`23:59:59Z` pela
    tela, que só tinha campo de data. Se "dia inteiro" fosse ancorado no fuso de
    quem olha, cada um deles passaria a começar às 21:00 do dia ANTERIOR em
    Recife — a agenda inteira andaria um dia para trás sem que ninguém tivesse
    editado nada.

    Ancorando em UTC, a data guardada continua sendo a data que a pessoa
    escolheu, e o recálculo que o operador proibiu não precisa existir. A tela
    desenha evento de dia inteiro pela DATA, não pelo instante — é o mesmo
    modelo do `VALUE=DATE` do iCalendar.
    """
    inicio, fim = bordas_do_dia_inteiro(
        datetime(2026, 1, 15, 22, tzinfo=RECIFE),  # = 2026-01-16T01:00Z
        datetime(2026, 1, 15, 22, tzinfo=RECIFE),
    )

    assert inicio.date() == datetime(2026, 1, 16).date()
    assert inicio == datetime(2026, 1, 16, tzinfo=UTC)
    assert fim == datetime(2026, 1, 16, 23, 59, 59, 999999, tzinfo=UTC)
