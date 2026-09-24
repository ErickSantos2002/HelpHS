"""
Tempo ÚTIL restante — a volta de `add_business_minutes`.

O chip de prazo mostrava tempo CORRIDO: um prazo de 12h úteis carimbado às
09:11 aparecia como "27h", porque a subtração contava também 17:00→08:00.
Estes casos prendem a função que responde a pergunta certa — quantos minutos
ÚTEIS faltam — e os limites onde ela pode errar.

Datas escolhidas em 2026 e conferidas contra `e_dia_util`: 21 a 25/09 são
segunda a sexta úteis, 26/09 é sábado, e 21/04 (Tiradentes) é a terça parada
entre dois dias úteis.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.models import TicketCategory, TicketStatus, UserRole
from app.utils.sla import SP_TZ


def _sp(ano, mes, dia, hora=0, minuto=0):
    """Instante no fuso da jornada."""
    return SP_TZ.localize(datetime(ano, mes, dia, hora, minuto))


# ══════════════════════════════════════════════════════════════
# business_minutes_between
# ══════════════════════════════════════════════════════════════


class TestBusinessMinutesBetween:
    def test_durante_o_expediente_conta_o_relogio_comum(self):
        """Dentro da jornada, minuto útil e minuto corrido são a mesma coisa."""
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 9, 23, 9, 11), _sp(2026, 9, 23, 13, 11)) == 240

    def test_as_dezessete_em_ponto_o_relogio_ja_parou(self):
        """17:00 é o fim da jornada: daí até 08:00 do dia seguinte não corre nada."""
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 9, 23, 17, 0), _sp(2026, 9, 24, 8, 0)) == 0

    def test_a_noite_nao_conta(self):
        """22:00 de um dia até 09:00 do outro são 60 minutos úteis, não 660."""
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 9, 23, 22, 0), _sp(2026, 9, 24, 9, 0)) == 60

    def test_antes_das_oito_o_relogio_ainda_nao_comecou(self):
        """De madrugada o contador só passa a correr às 08:00."""
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 9, 24, 6, 0), _sp(2026, 9, 24, 9, 0)) == 60

    def test_sexta_para_segunda_pula_o_fim_de_semana(self):
        """Sexta 16:00 → segunda 09:00: 1h da sexta mais 1h da segunda."""
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 9, 25, 16, 0), _sp(2026, 9, 28, 9, 0)) == 120

    def test_feriado_nao_conta(self):
        """Segunda 16:00 → quarta 09:00 com a terça parada (Tiradentes): 120.

        Sem o feriado seriam 660 — as 9h da terça entrariam no meio. É o caso
        que distingue `e_dia_util` de um simples `weekday() < 5`.
        """
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 4, 20, 16, 0), _sp(2026, 4, 22, 9, 0)) == 120

    def test_prazo_que_cabe_no_resto_do_mesmo_dia(self):
        """Nada de especial quando começo e fim moram na mesma jornada."""
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 9, 23, 9, 11), _sp(2026, 9, 23, 12, 0)) == 169

    def test_o_caso_real_que_motivou_a_entrega(self):
        """12h úteis carimbadas às 09:11 vencem às 12:11 do dia seguinte.

        E no instante do carimbo faltam 12h ÚTEIS — não as 27h corridas que o
        chip mostrava.
        """
        from app.utils.sla import add_business_minutes, business_minutes_between

        triagem = _sp(2026, 9, 23, 9, 11)
        vence = add_business_minutes(triagem, 720)

        assert vence == _sp(2026, 9, 24, 12, 11)
        assert business_minutes_between(triagem, vence) == 720
        # A conta corrida que o chip fazia dava 27 horas.
        assert (vence - triagem).total_seconds() / 3600 == pytest.approx(27.0)

    def test_prazo_ja_vencido_devolve_zero(self):
        """Fim no passado não devolve negativo — devolve zero, e o chip diz Vencido."""
        from app.utils.sla import business_minutes_between

        assert business_minutes_between(_sp(2026, 9, 23, 15, 0), _sp(2026, 9, 23, 10, 0)) == 0

    def test_inicio_e_fim_iguais(self):
        from app.utils.sla import business_minutes_between

        agora = _sp(2026, 9, 23, 10, 0)
        assert business_minutes_between(agora, agora) == 0

    @pytest.mark.parametrize(
        "inicio",
        [
            _sp(2026, 9, 23, 9, 11),  # meio do expediente
            _sp(2026, 9, 23, 22, 0),  # noite
            _sp(2026, 9, 26, 10, 0),  # sábado
            _sp(2026, 4, 20, 16, 30),  # véspera de feriado
        ],
    )
    @pytest.mark.parametrize("minutos", [30, 120, 720, 1440])
    def test_ida_e_volta(self, inicio, minutos):
        """`between(t, add(t, n)) == n` — a propriedade que amarra as duas.

        É o teste que cai se alguém mexer numa das funções e não na outra: elas
        são a ida e a volta do MESMO calendário, e divergir é o defeito que
        esta entrega existe para evitar.
        """
        from app.utils.sla import add_business_minutes, business_minutes_between

        assert business_minutes_between(inicio, add_business_minutes(inicio, minutos)) == minutos


# ══════════════════════════════════════════════════════════════
# prazo_efetivo — uma definição só, a mesma do motor
# ══════════════════════════════════════════════════════════════


class TestPrazoEfetivo:
    def test_sem_pausa_e_o_proprio_prazo(self):
        from app.utils.sla import prazo_efetivo

        prazo = _sp(2026, 9, 24, 12, 11)
        assert prazo_efetivo(prazo, 0) == prazo
        assert prazo_efetivo(prazo, None) == prazo

    def test_a_pausa_estica_o_prazo(self):
        from app.utils.sla import prazo_efetivo

        prazo = _sp(2026, 9, 24, 12, 11)
        tres_horas = 3 * 60 * 60 * 1000
        assert prazo_efetivo(prazo, tres_horas) == prazo + timedelta(hours=3)

    def test_sem_prazo_nao_ha_prazo_efetivo(self):
        from app.utils.sla import prazo_efetivo

        assert prazo_efetivo(None, 999) is None

    def test_e_o_mesmo_prazo_que_o_check_breaches_usa(self):
        """A prova de que o chip não pode discordar da regra de violação.

        `check_breaches` marca violado quando `now` passa do prazo efetivo. O
        caso põe `now` um minuto antes e um minuto depois DESSE instante e
        exige que a marca acompanhe — se alguém reintroduzir um segundo cálculo
        num dos dois lados, ele cai.
        """
        from app.utils.sla import check_breaches, prazo_efetivo

        ticket = MagicMock()
        ticket.sla_response_due_at = _sp(2026, 9, 23, 10, 0)
        ticket.sla_resolve_due_at = None
        ticket.sla_first_response = None
        ticket.sla_total_paused_ms = 3 * 60 * 60 * 1000
        ticket.sla_response_breach = False
        ticket.sla_resolve_breach = False
        ticket.status = TicketStatus.open

        efetivo = prazo_efetivo(ticket.sla_response_due_at, ticket.sla_total_paused_ms)

        check_breaches(ticket, efetivo - timedelta(minutes=1))
        assert ticket.sla_response_breach is False, "violou antes do prazo efetivo"

        check_breaches(ticket, efetivo + timedelta(minutes=1))
        assert ticket.sla_response_breach is True, "nao violou depois do prazo efetivo"


# ══════════════════════════════════════════════════════════════
# estado_do_expediente — o que deixa o front congelar sem calendário
# ══════════════════════════════════════════════════════════════


class TestEstadoDoExpediente:
    def test_dentro_da_jornada_esta_aberto_e_fecha_as_dezessete(self):
        from app.utils.sla import estado_do_expediente

        aberto, virada = estado_do_expediente(_sp(2026, 9, 23, 9, 11))
        assert aberto is True
        assert virada == _sp(2026, 9, 23, 17, 0)

    def test_a_noite_esta_fechado_e_reabre_as_oito(self):
        from app.utils.sla import estado_do_expediente

        aberto, virada = estado_do_expediente(_sp(2026, 9, 23, 22, 0))
        assert aberto is False
        assert virada == _sp(2026, 9, 24, 8, 0)

    def test_as_dezessete_em_ponto_ja_fechou(self):
        """O minuto do fechamento pertence ao lado de fora — mesma borda do
        `add_business_hours`, que às 17:00 já joga para o dia seguinte."""
        from app.utils.sla import estado_do_expediente

        aberto, virada = estado_do_expediente(_sp(2026, 9, 23, 17, 0))
        assert aberto is False
        assert virada == _sp(2026, 9, 24, 8, 0)

    def test_no_sabado_reabre_na_segunda(self):
        from app.utils.sla import estado_do_expediente

        aberto, virada = estado_do_expediente(_sp(2026, 9, 26, 10, 0))
        assert aberto is False
        assert virada == _sp(2026, 9, 28, 8, 0)

    def test_na_vespera_de_feriado_reabre_depois_dele(self):
        from app.utils.sla import estado_do_expediente

        aberto, virada = estado_do_expediente(_sp(2026, 4, 20, 18, 0))
        assert aberto is False
        assert virada == _sp(2026, 4, 22, 8, 0)


def test_o_fuso_da_jornada_e_publicado_e_bate_com_o_motor():
    """O front formata o prazo no fuso que o MOTOR define, não num literal seu.

    Se a jornada mudar de fuso um dia, muda em `sla.py` e a tela acompanha
    sozinha — a regra fica num lugar só.
    """
    from app.utils.sla import FUSO_DA_JORNADA, SP_TZ

    assert FUSO_DA_JORNADA == str(SP_TZ)


# ══════════════════════════════════════════════════════════════
# O CONTRATO QUE A TELA CONSOME
# ══════════════════════════════════════════════════════════════


def _ticket_com_prazo(**kwargs):
    """Chamado de mentira com os campos que o serializador lê."""
    t = MagicMock()
    t.id = uuid.uuid4()
    t.protocol = "HS-2026-0001"
    t.title = "Equipamento com falha"
    t.description = "corpo"
    t.status = TicketStatus.open
    t.priority = None
    t.category = TicketCategory.hardware
    t.creator_id = uuid.uuid4()
    t.assignee_id = None
    t.product_id = None
    t.equipments = []
    t.tags = []
    t.sla_response_due_at = None
    t.sla_resolve_due_at = None
    t.sla_first_response = None
    t.sla_response_breach = False
    t.sla_resolve_breach = False
    t.sla_total_paused_ms = 0
    t.sla_resolve_extension_total_min = 0
    t.sla_resolve_effective_due_at = None
    t.closed_at = None
    t.resolved_at = None
    t.auto_closed = False
    t.reopened_at = None
    t.reopen_count = 0
    t.created_at = _sp(2026, 9, 23, 9, 11)
    t.updated_at = t.created_at
    t.ai_enabled = True
    t.ai_classification = None
    t.ai_confidence = None
    t.ai_summary = None
    t.ai_conversation_summary = None
    t.assignee_name = None
    t.product_name = None
    t.client_observation = None
    t.resolution_note = None
    t.technician_notes = None
    # Sem valor explicito o MagicMock devolve um objeto no lugar de None e o
    # `model_validate` recusa -- a mesma armadilha que o `_mock_ticket` do
    # `test_tickets.py` ja registra. Os campos novos entram na mesma lista.
    t.sla_response_vence_em = None
    t.sla_resolve_vence_em = None
    t.sla_response_restante_min = None
    t.sla_resolve_restante_min = None
    t.sla_response_total_min = None
    t.sla_resolve_total_min = None
    t.expediente = None
    t.reopen_deadline = None
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


# O relogio e o assunto desta classe. `_serialize_ticket` passou a exigir o
# ator porque e ele que decide se a nota interna sai na resposta -- ver
# `tests/test_notas_internas_nao_vazam.py`. Staff foi escolhido de proposito:
# um ator `client` tambem zeraria `technician_notes` e mudaria o objeto que
# estes testes medem. Com staff a resposta e identica a de antes da guarda.
_ATOR = MagicMock()
_ATOR.role = UserRole.technician


class TestContratoDoRelogio:
    """O que a resposta leva para a tela poder contar sem ter calendário."""

    def test_sem_prazo_nao_ha_contador(self):
        """Chamado sem triagem: nada de prazo, nada de restante."""
        from app.routers.tickets import _serialize_ticket

        r = _serialize_ticket(_ticket_com_prazo(), actor=_ATOR)

        assert r.sla_resolve_vence_em is None
        assert r.sla_resolve_restante_min is None

    def test_o_restante_vem_em_minutos_uteis(self):
        """12h úteis carimbadas às 09:11, lidas às 09:39: faltam 11h32m."""
        from app.routers.tickets import _serialize_ticket
        from app.utils.sla import add_business_minutes

        abertura = _sp(2026, 9, 23, 9, 11)
        t = _ticket_com_prazo(sla_resolve_due_at=add_business_minutes(abertura, 720))

        r = _serialize_ticket(t, agora=_sp(2026, 9, 23, 9, 39), actor=_ATOR)

        assert r.sla_resolve_restante_min == 692  # 11h32m
        assert r.sla_resolve_vence_em == _sp(2026, 9, 24, 12, 11)

    def test_o_vence_em_e_o_prazo_efetivo_com_a_pausa(self):
        """A tela recebe o mesmo instante que decide a violação, não o cru."""
        from app.routers.tickets import _serialize_ticket

        prazo = _sp(2026, 9, 23, 15, 0)
        t = _ticket_com_prazo(
            sla_resolve_due_at=prazo,
            sla_total_paused_ms=3 * 60 * 60 * 1000,
        )

        r = _serialize_ticket(t, agora=_sp(2026, 9, 23, 10, 0), actor=_ATOR)

        assert r.sla_resolve_vence_em == prazo + timedelta(hours=3)

    def test_fora_do_expediente_o_restante_nao_encolhe(self):
        """Duas leituras na mesma madrugada devolvem o MESMO restante."""
        from app.routers.tickets import _serialize_ticket
        from app.utils.sla import add_business_minutes

        t = _ticket_com_prazo(sla_resolve_due_at=add_business_minutes(_sp(2026, 9, 23, 9, 11), 720))

        meia_noite = _serialize_ticket(t, agora=_sp(2026, 9, 24, 0, 0), actor=_ATOR)
        quatro_da_manha = _serialize_ticket(t, agora=_sp(2026, 9, 24, 4, 0), actor=_ATOR)

        assert meia_noite.sla_resolve_restante_min == quatro_da_manha.sla_resolve_restante_min

    def test_o_total_e_o_denominador_da_barra(self):
        """A barra da lista precisa do tamanho do prazo em minutos ÚTEIS.

        Sem ele ela calcula `(agora - abertura) / (vence - abertura)` em tempo
        corrido, e enche sozinha durante a noite e o fim de semana.
        """
        from app.routers.tickets import _serialize_ticket
        from app.utils.sla import add_business_minutes

        abertura = _sp(2026, 9, 23, 9, 11)
        t = _ticket_com_prazo(
            created_at=abertura,
            sla_resolve_due_at=add_business_minutes(abertura, 720),
        )

        r = _serialize_ticket(t, agora=_sp(2026, 9, 23, 9, 39), actor=_ATOR)

        assert r.sla_resolve_total_min == 720
        # 28 minutos úteis consumidos de 720 — e não de 27 horas corridas.
        assert r.sla_resolve_total_min - r.sla_resolve_restante_min == 28

    def test_prazo_vencido_zera_o_contador(self):
        from app.routers.tickets import _serialize_ticket

        t = _ticket_com_prazo(sla_resolve_due_at=_sp(2026, 9, 23, 10, 0))

        r = _serialize_ticket(t, agora=_sp(2026, 9, 23, 14, 0), actor=_ATOR)

        assert r.sla_resolve_restante_min == 0

    def test_o_detalhe_leva_o_expediente_junto(self):
        """Uma tela só, uma requisição só: o chip precisa saber se congela."""
        from app.routers.tickets import _serialize_ticket
        from app.utils.sla import FUSO_DA_JORNADA

        r = _serialize_ticket(_ticket_com_prazo(), agora=_sp(2026, 9, 23, 9, 39), actor=_ATOR)

        assert r.expediente is not None
        assert r.expediente.aberto is True
        assert r.expediente.proxima_virada == _sp(2026, 9, 23, 17, 0)
        assert r.expediente.fuso == FUSO_DA_JORNADA

    def test_o_item_da_lista_nao_repete_o_expediente(self):
        """Na lista ele vem uma vez no topo — 50 cópias do mesmo relógio é lixo."""
        from app.routers.tickets import _serialize_ticket

        r = _serialize_ticket(_ticket_com_prazo(), com_expediente=False, actor=_ATOR)

        assert r.expediente is None
