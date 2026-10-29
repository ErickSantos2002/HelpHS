"""
A janela dos relatórios, sem banco: datas de Recife viram instantes UTC com
fim exclusivo, e cada intervalo sabe com o que se compara (F1-B-03a).

O relógio é fixo — `agora` entra como argumento —, e por isso nenhum destes
testes depende do dia em que roda.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.utils.periodo_relatorio import (
    INTERVALO_MAXIMO_DIAS,
    NOME_DO_FUSO,
    deslocamento_do_fuso,
    dia_local,
    intervalo_sql_do_fuso,
    meia_noite_local,
    resolve_janela,
)

# 29/10/2026, 12:00 em Recife.
AGORA = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
HOJE = date(2026, 10, 29)


def _datas(inicio: date, fim: date, agora: datetime = AGORA):
    return resolve_janela(30, inicio, fim, agora=agora)


def test_o_fuso_dos_relatorios_e_recife():
    assert NOME_DO_FUSO == "America/Recife"


def test_recife_tem_deslocamento_fixo_e_o_sql_usa_esse_intervalo():
    """A premissa do agrupamento no SQL: sem horário de verão, um intervalo
    fixo basta. Se um dia o fuso tiver horário de verão, este teste cai antes
    de o gráfico mentir."""
    fuso = ZoneInfo(NOME_DO_FUSO)
    for mes in range(1, 13):
        assert datetime(2026, mes, 15, tzinfo=fuso).utcoffset() == timedelta(hours=-3)
    assert deslocamento_do_fuso() == timedelta(hours=-3)
    assert intervalo_sql_do_fuso() == "INTERVAL '-03:00'"
    assert intervalo_sql_do_fuso(timedelta(hours=5, minutes=30)) == "INTERVAL '+05:30'"


def test_meia_noite_de_recife_e_tres_da_manha_em_utc():
    """Recife é UTC−3 o ano inteiro: nunca teve horário de verão."""
    assert meia_noite_local(date(2026, 1, 15)) == datetime(2026, 1, 15, 3, tzinfo=UTC)
    assert meia_noite_local(date(2026, 7, 15)) == datetime(2026, 7, 15, 3, tzinfo=UTC)


# ── Os filtros da tela ────────────────────────────────────────


def test_hoje_vai_da_meia_noite_local_a_meia_noite_seguinte():
    j = _datas(HOJE, HOJE)
    assert j.inicio == datetime(2026, 10, 29, 3, tzinfo=UTC)
    assert j.fim == datetime(2026, 10, 30, 3, tzinfo=UTC)
    assert j.dias == 1
    assert j.dias_do_grafico() == [HOJE]


def test_ontem_e_o_dia_anterior_completo_e_compara_com_anteontem():
    ontem = HOJE - timedelta(days=1)
    j = _datas(ontem, ontem)
    assert j.inicio == datetime(2026, 10, 28, 3, tzinfo=UTC)
    assert j.fim == datetime(2026, 10, 29, 3, tzinfo=UTC)
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (date(2026, 10, 27),) * 2


def test_ultimos_7_dias_sao_sete_dias_do_calendario_incluindo_hoje():
    j = _datas(HOJE - timedelta(days=6), HOJE)
    assert j.dias == 7
    assert j.dias_do_grafico()[0] == date(2026, 10, 23)
    assert j.dias_do_grafico()[-1] == HOJE
    assert len(j.dias_do_grafico()) == 7
    # A comparação são os 7 dias imediatamente antes, sem sobreposição.
    assert j.anterior_fim == j.inicio
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (
        date(2026, 10, 16),
        date(2026, 10, 22),
    )


def test_mes_passado_compara_com_o_mes_civil_anterior_inteiro():
    """D6: setembro (30 dias) se compara com agosto (31), não com 30 dias."""
    j = _datas(date(2026, 9, 1), date(2026, 9, 30))
    assert j.dias == 30
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )
    assert j.anterior_inicio == meia_noite_local(date(2026, 8, 1))
    assert j.anterior_fim == j.inicio


def test_mes_parcial_compara_com_a_mesma_quantidade_de_dias():
    """ "Este mês" (dia 1º até hoje) não é mês civil completo."""
    j = _datas(date(2026, 10, 1), HOJE)
    assert j.dias == 29
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (
        date(2026, 9, 2),
        date(2026, 9, 30),
    )


def test_personalizado_respeita_exatamente_as_datas_escolhidas():
    j = _datas(date(2026, 3, 10), date(2026, 3, 12))
    assert j.por_datas
    assert j.inicio == meia_noite_local(date(2026, 3, 10))
    assert j.fim == meia_noite_local(date(2026, 3, 13))
    assert j.dias_do_grafico() == [date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 12)]


# ── Viradas ───────────────────────────────────────────────────


def test_virada_de_ano_janeiro_compara_com_dezembro_do_ano_anterior():
    j = _datas(date(2026, 1, 1), date(2026, 1, 31))
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )


def test_dezembro_inteiro_termina_na_meia_noite_local_de_1o_de_janeiro():
    j = _datas(date(2025, 12, 1), date(2025, 12, 31))
    assert j.fim == datetime(2026, 1, 1, 3, tzinfo=UTC)
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (
        date(2025, 11, 1),
        date(2025, 11, 30),
    )


def test_virada_de_mes_intervalo_que_atravessa_meses_nao_e_mes_civil():
    j = _datas(date(2026, 9, 25), date(2026, 10, 5))
    assert j.dias == 11
    assert j.dias_do_grafico()[0] == date(2026, 9, 25)
    assert j.dias_do_grafico()[-1] == date(2026, 10, 5)
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (
        date(2026, 9, 14),
        date(2026, 9, 24),
    )


def test_fevereiro_bissexto_inteiro_e_mes_civil_completo():
    agora = datetime(2028, 3, 10, 15, tzinfo=UTC)
    j = _datas(date(2028, 2, 1), date(2028, 2, 29), agora=agora)
    assert j.dias == 29
    assert (j.anterior_primeiro_dia, j.anterior_ultimo_dia) == (
        date(2028, 1, 1),
        date(2028, 1, 31),
    )


# ── UTC × Recife ──────────────────────────────────────────────


def test_as_duas_da_manha_utc_ainda_e_ontem_em_recife():
    """02:00Z do dia 30 é 23:00 do dia 29 em Recife: "hoje" é 29."""
    agora = datetime(2026, 10, 30, 2, tzinfo=UTC)
    assert dia_local(agora) == date(2026, 10, 29)
    # O dia 30 ainda está no futuro para quem está em Recife.
    with pytest.raises(ValueError, match="futuro"):
        resolve_janela(30, date(2026, 10, 30), date(2026, 10, 30), agora=agora)
    resolve_janela(30, date(2026, 10, 29), date(2026, 10, 29), agora=agora)


# ── Validações ────────────────────────────────────────────────


@pytest.mark.parametrize("inicio, fim", [(date(2026, 10, 1), None), (None, date(2026, 10, 1))])
def test_data_sozinha_e_recusada(inicio, fim):
    with pytest.raises(ValueError, match="data inicial e a data final"):
        resolve_janela(30, inicio, fim, agora=AGORA)


def test_inicio_depois_do_fim_e_recusado():
    with pytest.raises(ValueError, match="posterior"):
        _datas(date(2026, 10, 10), date(2026, 10, 9))


def test_fim_no_futuro_e_recusado():
    with pytest.raises(ValueError, match="futuro"):
        _datas(HOJE, HOJE + timedelta(days=1))


def test_366_dias_passam_e_367_nao():
    fim = HOJE
    _datas(fim - timedelta(days=INTERVALO_MAXIMO_DIAS - 1), fim)
    with pytest.raises(ValueError, match="366"):
        _datas(fim - timedelta(days=INTERVALO_MAXIMO_DIAS), fim)


# ── `period` legado ───────────────────────────────────────────


def test_period_legado_mantem_o_significado_de_sempre():
    """N dias contados de agora, sem limite superior, comparado aos N antes."""
    j = resolve_janela(7, None, None, agora=AGORA)
    assert not j.por_datas
    assert j.inicio == AGORA - timedelta(days=7)
    assert j.fim is None
    assert j.dias == 7
    assert j.anterior_inicio == AGORA - timedelta(days=14)
    assert j.anterior_fim == j.inicio
    # A primeira barra é o dia local do início; a última, hoje.
    assert j.dias_do_grafico()[0] == date(2026, 10, 22)
    assert j.dias_do_grafico()[-1] == HOJE


def test_datas_tem_prioridade_sobre_period():
    j = resolve_janela(90, date(2026, 10, 1), date(2026, 10, 2), agora=AGORA)
    assert j.por_datas
    assert j.dias == 2
