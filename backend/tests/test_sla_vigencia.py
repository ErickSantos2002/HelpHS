"""
Vigência dos prazos de SLA: quem nasceu antes mantém o prazo com que nasceu.

O SGI aprovou cortar cada prazo pela metade. A regra de transição é que a
mudança vale para chamado **aberto a partir da vigência**; os anteriores
continuam com o prazo de origem.

O sistema já satisfaz isso por construção, e é por isso que estes testes
existem: uma propriedade que ninguém escreveu é uma propriedade que ninguém
protege. `sla_response_due_at` e `sla_resolve_due_at` são COLUNAS do chamado,
carimbadas uma vez na criação. Editar `sla_configs` depois não alcança linha
que já existe — desde que nenhum caminho recalcule na leitura.

É essa última condição que o teste estrutural aqui guarda. Comparar duas datas
provaria pouco: passaria mesmo num sistema que recalculasse, porque o teste
não chamaria o recálculo. Contar QUEM ESCREVE os dois campos, no código-fonte
inteiro, pega a regressão de verdade — alguém acrescentar um recálculo no
caminho de leitura.

A EXCEÇÃO CONSCIENTE
--------------------
Reabrir chamado recalcula o prazo de resolução com a configuração VIGENTE, e
não com a de origem. Decisão do operador em 08/09/2026: a reabertura começa um
ciclo novo, e ciclo novo segue a regra de hoje. Congelar exigiria versionar
`sla_configs`, porque `sla_config_id` aponta para a linha atual — já editada.
O teste abaixo fixa esse comportamento para que ele seja mudado de propósito,
nunca por acidente.
"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.models.models import SLAConfig, Ticket
from app.utils.sla import add_business_minutes, apply_sla_config, check_breaches

_SP = ZoneInfo("America/Sao_Paulo")
_APP = Path(__file__).resolve().parent.parent / "app"


def _sp(*args: int) -> datetime:
    return datetime(*args, tzinfo=_SP)


def _config(resposta_min: int, resolucao_min: int) -> MagicMock:
    c = MagicMock(spec=SLAConfig)
    c.id = uuid.uuid4()
    c.response_time_minutes = resposta_min
    c.resolve_time_minutes = resolucao_min
    return c


def _ticket() -> MagicMock:
    t = MagicMock(spec=Ticket)
    t.sla_response_due_at = None
    t.sla_resolve_due_at = None
    t.sla_first_response_at = None
    t.sla_response_breach = False
    t.sla_resolve_breach = False
    t.sla_paused_at = None
    t.sla_total_paused_ms = 0
    t.resolved_at = None
    return t


# ═══════════════════════════════════════════════════════════════
# A regra de transição
# ═══════════════════════════════════════════════════════════════


def test_editar_a_configuracao_nao_alcanca_chamado_que_ja_existe():
    """
    O caso que a regra descreve: chamado aberto com o prazo antigo, e a
    configuração cortada pela metade depois. O prazo dele não se move.
    """
    ticket = _ticket()
    config = _config(resposta_min=240, resolucao_min=2880)  # 4 h / 48 h
    abertura = _sp(2026, 9, 8, 9, 0)  # terça, 09:00

    apply_sla_config(ticket, config, abertura)
    prazo_de_origem = (ticket.sla_response_due_at, ticket.sla_resolve_due_at)

    # O SGI entra em vigência: cada prazo pela metade, na mesma linha da tabela.
    config.response_time_minutes = 120
    config.resolve_time_minutes = 1440

    # E o caminho que roda a cada escrita não recalcula nada.
    check_breaches(ticket, _sp(2026, 9, 8, 11, 0))

    assert (ticket.sla_response_due_at, ticket.sla_resolve_due_at) == prazo_de_origem


def test_chamado_aberto_depois_da_vigencia_nasce_com_o_prazo_novo():
    """A outra metade da regra: quem nasce depois recebe o valor aprovado."""
    ticket = _ticket()
    abertura = _sp(2026, 9, 8, 9, 0)

    apply_sla_config(ticket, _config(resposta_min=120, resolucao_min=1440), abertura)

    # 120 min úteis a partir de terça 09:00 = terça 11:00.
    assert ticket.sla_response_due_at == _sp(2026, 9, 8, 11, 0)


def test_so_a_criacao_e_a_reabertura_escrevem_os_prazos():
    """
    O guarda de verdade da regra de transição.

    Se um caminho de LEITURA passar a recalcular o prazo, a regra morre em
    silêncio: chamado antigo começaria a ser exibido com o prazo novo, e
    nenhum teste de data pegaria isso — porque o teste não chamaria o
    recálculo. Este conta quem escreve os dois campos no código inteiro.

    Ao ver este teste falhar: escrita nova em `apply_sla_config` ou no caminho
    de reabertura é esperada. Em qualquer outro lugar, a pergunta é se aquele
    trecho roda em leitura — se rodar, a regra de vigência foi quebrada.
    """
    escritas: dict[str, int] = {}
    for arquivo in _APP.rglob("*.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        n = len(re.findall(r"\.sla_(?:response|resolve)_due_at\s*=(?!=)", fonte))
        if n:
            escritas[arquivo.relative_to(_APP).as_posix()] = n

    assert escritas == {
        "utils/sla.py": 2,  # apply_sla_config, na criação
        "routers/tickets.py": 1,  # reabertura, exceção documentada
    }, f"quem escreve os prazos de SLA mudou: {escritas}"


# ═══════════════════════════════════════════════════════════════
# A exceção: reabertura usa a regra de hoje
# ═══════════════════════════════════════════════════════════════


def test_a_reabertura_usa_a_configuracao_vigente_e_isso_e_intencional():
    """
    Fixa a exceção. Não é o comportamento que a regra de transição descreve, e
    sim o que foi decidido para o ciclo novo — ver o cabeçalho deste arquivo.

    Quem quiser mudar isso precisa versionar `sla_configs`; até lá, este teste
    existe para que a mudança seja deliberada.
    """
    reabertura = _sp(2026, 9, 8, 9, 0)
    vigente = _config(resposta_min=120, resolucao_min=1440)  # já pela metade

    # É o que `routers/tickets.py` faz na reabertura: prazo novo a partir de
    # agora, com o valor que está valendo na tabela.
    prazo = add_business_minutes(reabertura, vigente.resolve_time_minutes)

    # 1440 min = 24 h úteis. Terça 09:00 tem 8 h até as 17:00; quarta dá 9 h
    # cheias; sobram 7 h, que caem na quinta a partir das 08:00.
    assert prazo > reabertura
    assert prazo == _sp(2026, 9, 10, 15, 0)


# ═══════════════════════════════════════════════════════════════
# A unidade nova, e o valor que forçou a troca
# ═══════════════════════════════════════════════════════════════


def test_meia_hora_e_representavel_e_era_o_motivo_da_troca():
    """
    Metade da resposta do nível crítico é 30 min. Enquanto o prazo era hora
    inteira, esse valor não existia — não por regra de negócio, por tipo de
    coluna.
    """
    prazo = add_business_minutes(_sp(2026, 9, 8, 9, 0), 30)

    assert prazo == _sp(2026, 9, 8, 9, 30)


def test_a_semente_carrega_os_valores_aprovados_pelo_sgi():
    """
    Cada prazo anterior pela metade. O teste escreve os dois lados da conta
    para que a tabela do PR e o código não possam divergir em silêncio.
    """
    from app.seeds import SLA_CONFIGS

    antes_em_horas = {
        "critical": (1, 4),
        "high": (2, 8),
        "medium": (4, 24),
        "low": (8, 48),
    }

    for config in SLA_CONFIGS:
        resposta_h, resolucao_h = antes_em_horas[config["level"].value]
        assert config["response_time_minutes"] == resposta_h * 60 // 2
        assert config["resolve_time_minutes"] == resolucao_h * 60 // 2


@pytest.mark.parametrize(
    ("minutos", "hora_esperada", "minuto_esperado"),
    [
        (30, 9, 30),  # crítico: meia hora
        (60, 10, 0),
        (480, 17, 0),  # a jornada inteira cai no fim do expediente
        # 9 h úteis a partir das 09:00: sobra 1 h para o dia seguinte, e a
        # jornada começa às 08:00 — logo, 09:00 de quarta, não 08:00.
        (540, 9, 0),
    ],
)
def test_o_calculo_em_minutos_respeita_a_jornada(minutos, hora_esperada, minuto_esperado):
    """A janela é 08:00–17:00; minuto que passa do fim do dia cai no próximo."""
    prazo = add_business_minutes(_sp(2026, 9, 8, 9, 0), minutos)

    assert (prazo.hour, prazo.minute) == (hora_esperada, minuto_esperado)


def test_a_hora_util_nao_conta_fim_de_semana():
    """Sexta 16:00 + 120 min úteis não cai no sábado."""
    prazo = add_business_minutes(_sp(2026, 9, 11, 16, 0), 120)

    assert prazo.weekday() == 0, "deveria cair na segunda"
    assert (prazo.hour, prazo.minute) == (9, 0)


# ═══════════════════════════════════════════════════════════════
# A ponte com a tela antiga
# ═══════════════════════════════════════════════════════════════


def test_a_tela_antiga_manda_horas_e_o_backend_grava_minutos():
    from app.schemas.sla import SLAConfigUpdate

    payload = SLAConfigUpdate(response_time_hours=3)

    assert payload.campos_para_gravar() == {"response_time_minutes": 180}


def test_mandar_hora_e_minuto_juntos_e_recusado():
    """Adivinhar qual vale seria escolher no escuro pelo cliente da API."""
    from pydantic import ValidationError

    from app.schemas.sla import SLAConfigUpdate

    with pytest.raises(ValidationError, match="nunca os dois"):
        SLAConfigUpdate(response_time_hours=3, response_time_minutes=180)


def test_a_leitura_devolve_hora_so_quando_e_hora_cheia():
    """
    30 min não vira "1 h" na resposta: vira `null`. Número plausível e errado
    é pior do que ausência — a tela desenha o errado sem ninguém questionar.
    """
    from app.schemas.sla import SLAConfigResponse

    def _resposta(resposta_min: int, resolucao_min: int) -> SLAConfigResponse:
        return SLAConfigResponse(
            id=uuid.uuid4(),
            level="critical",
            response_time_minutes=resposta_min,
            resolve_time_minutes=resolucao_min,
            warning_threshold=80,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    exata = _resposta(120, 240)
    assert (exata.response_time_hours, exata.resolve_time_hours) == (2, 4)

    quebrada = _resposta(30, 240)
    assert quebrada.response_time_hours is None
    assert quebrada.resolve_time_hours == 4
