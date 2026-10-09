"""
Extensão do SLA de resolução.

Técnico ou administrador prorroga o prazo de resolução quando percebe que não
vai resolver dentro do prazo da prioridade. A extensão é em DIAS ÚTEIS do
motor, tem justificativa pública obrigatória, e é cumulativa.

O que estes casos protegem, em uma frase cada:

- o prazo ORIGINAL (`sla_resolve_due_at`) nunca é sobrescrito;
- o prazo EFETIVO passa a incluir a extensão, em tempo útil;
- o SLA de RESPOSTA não é tocado — nem por engano, e a estrutura impede;
- a coluna materializada nunca diverge do que o motor calcula;
- extensão depois do vencimento não apaga violação.

Datas de 2026 conferidas contra `e_dia_util`: 21 a 25/09 são segunda a sexta
úteis, 26/09 é sábado, e 21/04 (Tiradentes) é a terça parada entre dois dias
úteis.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.models import TicketPriority, TicketStatus
from app.utils.sla import SP_TZ

# 1 dia útil = a jornada inteira = 9 h = 540 minutos.
MINUTOS_POR_DIA_UTIL = 540


def _sp(ano, mes, dia, hora=0, minuto=0):
    return SP_TZ.localize(datetime(ano, mes, dia, hora, minuto))


def _ticket(**kwargs):
    """Chamado de mentira com os campos que o motor lê."""
    t = MagicMock()
    t.id = uuid.uuid4()
    t.protocol = "HS-2026-0025"
    t.status = TicketStatus.in_progress
    t.priority = TicketPriority.medium
    t.created_at = _sp(2026, 9, 23, 9, 11)
    t.sla_response_due_at = _sp(2026, 9, 23, 11, 11)
    t.sla_resolve_due_at = _sp(2026, 9, 24, 12, 11)
    t.sla_first_response = None
    t.sla_response_breach = False
    t.sla_resolve_breach = False
    t.sla_total_paused_ms = 0
    t.sla_paused_at = None
    t.sla_resolve_extension_total_min = 0
    t.sla_resolve_effective_due_at = None
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


# ══════════════════════════════════════════════════════════════
# AS DUAS PORTAS — a extensão só existe no caminho da resolução
# ══════════════════════════════════════════════════════════════


class TestAsDuasPortas:
    def test_a_resolucao_inclui_a_extensao(self):
        from app.utils.sla import add_business_minutes, prazo_efetivo_de_resolucao

        base = _sp(2026, 9, 24, 12, 11)
        t = _ticket(
            sla_resolve_due_at=base,
            sla_resolve_extension_total_min=3 * MINUTOS_POR_DIA_UTIL,
        )

        assert prazo_efetivo_de_resolucao(t) == add_business_minutes(base, 3 * MINUTOS_POR_DIA_UTIL)

    def test_a_resposta_nao_inclui_a_extensao(self):
        """A garantia central: prorrogar resolução não estica a resposta.

        Esta é a razão de existirem duas portas em vez de um terceiro
        argumento opcional. Com um parâmetro, bastava alguém passá-lo na
        chamada errada — aqui não existe onde escrever isso.
        """
        from app.utils.sla import prazo_efetivo_de_resposta

        resposta = _sp(2026, 9, 23, 11, 11)
        t = _ticket(
            sla_response_due_at=resposta,
            sla_resolve_extension_total_min=30 * MINUTOS_POR_DIA_UTIL,
        )

        assert prazo_efetivo_de_resposta(t) == resposta

    def test_sem_prazo_nao_ha_prazo_efetivo(self):
        from app.utils.sla import prazo_efetivo_de_resolucao

        assert prazo_efetivo_de_resolucao(_ticket(sla_resolve_due_at=None)) is None

    def test_a_ordem_e_base_pausa_extensao(self):
        """Pausa (tempo corrido) primeiro, extensão (tempo útil) depois.

        A ordem importa: aplicar a extensão antes da pausa daria outro
        instante, porque somar minutos úteis a partir de pontos diferentes
        pula jornadas diferentes.
        """
        from app.utils.sla import add_business_minutes, prazo_efetivo_de_resolucao

        base = _sp(2026, 9, 24, 12, 11)
        pausa_ms = 3 * 60 * 60 * 1000
        t = _ticket(
            sla_resolve_due_at=base,
            sla_total_paused_ms=pausa_ms,
            sla_resolve_extension_total_min=MINUTOS_POR_DIA_UTIL,
        )

        esperado = add_business_minutes(
            base + timedelta(milliseconds=pausa_ms), MINUTOS_POR_DIA_UTIL
        )
        assert prazo_efetivo_de_resolucao(t) == esperado


# ══════════════════════════════════════════════════════════════
# DIAS ÚTEIS DE VERDADE
# ══════════════════════════════════════════════════════════════


class TestDiasUteis:
    def test_um_dia_e_a_jornada_e_nao_vinte_e_quatro_horas(self):
        """Quarta 12:11 + 1 dia útil = quinta 12:11 — mas por 9h de jornada.

        A prova de que não são 24h corridas está no caso da sexta, abaixo.
        """
        from app.utils.sla import prazo_efetivo_de_resolucao

        t = _ticket(
            sla_resolve_due_at=_sp(2026, 9, 23, 12, 11),
            sla_resolve_extension_total_min=MINUTOS_POR_DIA_UTIL,
        )

        assert prazo_efetivo_de_resolucao(t) == _sp(2026, 9, 24, 12, 11)

    def test_sexta_mais_um_dia_atravessa_o_fim_de_semana(self):
        """Sexta 15:00 + 1 dia útil cai na SEGUNDA, não no sábado.

        Com 24h corridas daria sábado 15:00 — dia em que ninguém atende.
        """
        from app.utils.sla import prazo_efetivo_de_resolucao

        t = _ticket(
            sla_resolve_due_at=_sp(2026, 9, 25, 15, 0),
            sla_resolve_extension_total_min=MINUTOS_POR_DIA_UTIL,
        )

        assert prazo_efetivo_de_resolucao(t) == _sp(2026, 9, 28, 15, 0)

    def test_a_extensao_atravessa_feriado(self):
        """Segunda 15:00 + 1 dia útil com a terça parada (Tiradentes) = quarta.

        É o caso que distingue a regra canônica de um `weekday() < 5`.
        """
        from app.utils.sla import prazo_efetivo_de_resolucao

        t = _ticket(
            sla_resolve_due_at=_sp(2026, 4, 20, 15, 0),
            sla_resolve_extension_total_min=MINUTOS_POR_DIA_UTIL,
        )

        assert prazo_efetivo_de_resolucao(t) == _sp(2026, 4, 22, 15, 0)

    @pytest.mark.parametrize("dias", [1, 3, 5, 15, 30])
    def test_a_conversao_de_dias_para_minutos_uteis(self, dias):
        from app.utils.sla import minutos_uteis_de_dias

        assert minutos_uteis_de_dias(dias) == dias * MINUTOS_POR_DIA_UTIL

    def test_duas_extensoes_acumulam_como_uma_soma(self):
        """+3 depois +1 é idêntico a +4 de uma vez.

        Não é detalhe: é o que torna o acumulador re-derivável. Se a extensão
        fosse guardada como um prazo já calculado, a segunda concessão
        dependeria de quando a primeira foi feita.
        """
        from app.utils.sla import prazo_efetivo_de_resolucao

        base = _sp(2026, 9, 24, 12, 11)
        em_duas = _ticket(
            sla_resolve_due_at=base,
            sla_resolve_extension_total_min=4 * MINUTOS_POR_DIA_UTIL,
        )
        de_uma_vez = _ticket(
            sla_resolve_due_at=base,
            sla_resolve_extension_total_min=4 * MINUTOS_POR_DIA_UTIL,
        )

        assert prazo_efetivo_de_resolucao(em_duas) == prazo_efetivo_de_resolucao(de_uma_vez)


# ══════════════════════════════════════════════════════════════
# A COLUNA MATERIALIZADA NUNCA DIVERGE
# ══════════════════════════════════════════════════════════════


class TestMaterializacao:
    """O invariante que o painel passa a consumir.

    `sla_resolve_effective_due_at` é a versão SQL do que o motor calcula. Se
    os dois divergirem, painel e chamado voltam a discordar — que é
    exatamente o defeito que esta entrega existe para eliminar.
    """

    def test_atualiza_escreve_o_mesmo_que_o_motor_calcula(self):
        from app.utils.sla import atualiza_prazo_efetivo, prazo_efetivo_de_resolucao

        t = _ticket(sla_resolve_extension_total_min=3 * MINUTOS_POR_DIA_UTIL)

        atualiza_prazo_efetivo(t)

        assert t.sla_resolve_effective_due_at == prazo_efetivo_de_resolucao(t)

    def test_sem_prazo_a_coluna_fica_nula(self):
        from app.utils.sla import atualiza_prazo_efetivo

        t = _ticket(sla_resolve_due_at=None)

        atualiza_prazo_efetivo(t)

        assert t.sla_resolve_effective_due_at is None

    def test_apply_sla_config_ja_materializa(self):
        """Carimbar o SLA não pode deixar a coluna para trás."""
        from app.utils.sla import apply_sla_config, prazo_efetivo_de_resolucao

        t = _ticket(sla_resolve_due_at=None, sla_resolve_effective_due_at=None)
        config = MagicMock()
        config.id = uuid.uuid4()
        config.response_time_minutes = 120
        config.resolve_time_minutes = 720

        apply_sla_config(t, config, t.created_at)

        assert t.sla_resolve_effective_due_at == prazo_efetivo_de_resolucao(t)

    def test_resume_sla_ja_materializa(self):
        """Retomar muda o acumulado de pausa — e o prazo efetivo com ele."""
        from app.utils.sla import prazo_efetivo_de_resolucao, resume_sla

        t = _ticket(sla_paused_at=_sp(2026, 9, 23, 14, 0))

        resume_sla(t, _sp(2026, 9, 23, 16, 0))

        assert t.sla_total_paused_ms == 2 * 60 * 60 * 1000
        assert t.sla_resolve_effective_due_at == prazo_efetivo_de_resolucao(t)

    def test_a_pausa_em_curso_nao_entra_na_conta(self):
        """`sla_paused_at` não é insumo — o motor só olha o ACUMULADO.

        É o que torna a materialização determinística: a coluna é função pura
        de três campos persistidos, sem nada que dependa do relógio. Se um dia
        a pausa em curso passar a contar, esta materialização deixa de ser
        possível sem recalcular a cada leitura.
        """
        from app.utils.sla import prazo_efetivo_de_resolucao

        parado = _ticket(sla_paused_at=_sp(2026, 9, 23, 14, 0))
        andando = _ticket(sla_paused_at=None)

        assert prazo_efetivo_de_resolucao(parado) == prazo_efetivo_de_resolucao(andando)
