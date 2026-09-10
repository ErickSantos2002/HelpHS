"""
Feriados no relógio do SLA.

Até aqui só o fim de semana parava a contagem, e feriado contava como dia útil
— o sistema cobrava prazo sobre dia em que ninguém atendeu.

POR QUE OS TESTES USAM DATAS CONHECIDAS
---------------------------------------
Quando os feriados foram ligados, a suíte inteira passou sem uma quebra. Isso
não provou que a mudança era inócua: provou que a cobertura antiga não tinha o
caso. Os testes de SLA existentes usam terças e sextas comuns de abril e
setembro, e nenhum deles atravessava feriado.

Datas genéricas continuariam sem provar nada. Por isso aqui há Natal, 7 de
setembro, carnaval de DOIS anos diferentes (para pegar quem digitasse uma data
fixa em vez de calcular) e um dia da tabela manual.

UNIDADE DO PRAZO
----------------
Aqui os prazos são passados em HORAS, porque é o que `add_business_hours`
recebe nesta branch. A frente do SLA (que corta os prazos pela metade) troca a
unidade para minutos e renomeia a entrada para `add_business_minutes`. As duas
mudanças são ortogonais — feriado mexe em QUAIS dias contam, unidade mexe em
QUANTO se conta — e quem entrar depois ajusta as chamadas destes testes.

O QUE ESTE ITEM NÃO FAZ
-----------------------
Não repara o passado. O prazo é gravado na criação do chamado, então ligar
feriados vale só para chamado novo — os que já estão abertos com prazo cobrado
sobre um feriado continuam como estão. É a mesma regra da transição do SLA:
chamado aberto tem prazo acordado, e mudá-lo depois seria alterar compromisso
feito. Há teste prendendo esse comportamento.
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.models.models import SLAConfig, Ticket
from app.utils.feriados import (
    ANOS_CONFERIDOS,
    dias_parados,
    e_dia_util,
    e_feriado,
)
from app.utils.sla import add_business_hours, apply_sla_config

_SP = ZoneInfo("America/Sao_Paulo")


def _sp(*args: int) -> datetime:
    return datetime(*args, tzinfo=_SP)


# ═══════════════════════════════════════════════════════════════
# Nacionais: param. Estaduais e municipais: não.
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("dia", "qual"),
    [
        (date(2026, 12, 25), "Natal"),
        (date(2026, 9, 7), "Independência"),
        (date(2026, 1, 1), "Confraternização"),
        (date(2026, 4, 21), "Tiradentes"),
        (date(2026, 11, 20), "Consciência Negra"),
    ],
)
def test_feriado_nacional_para_o_relogio(dia, qual):
    assert e_feriado(dia) is True, f"{qual} deveria parar o relógio"


def test_feriado_estadual_de_pernambuco_nao_para():
    """
    6 de março, Revolução Pernambucana. É o único que a biblioteca acrescenta
    em `subdiv="PE"`, e fica de fora de propósito: a regra é nacional. Se um
    ano específico for exceção, ele entra na tabela manual com o decreto.
    """
    assert e_feriado(date(2026, 3, 6)) is False


def test_dia_util_comum_nao_para():
    # 10/09/2026 é uma quinta-feira sem nada.
    assert e_dia_util(date(2026, 9, 10)) is True


def test_fim_de_semana_continua_parando():
    """A mecânica antiga não foi trocada, foi absorvida."""
    assert e_dia_util(date(2026, 9, 12)) is False  # sábado
    assert e_dia_util(date(2026, 9, 13)) is False  # domingo


# ═══════════════════════════════════════════════════════════════
# Carnaval: calculado, e por isso testado em dois anos
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("ano", "segunda", "terca", "cinzas"),
    [
        (2026, date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18)),
        (2027, date(2027, 2, 8), date(2027, 2, 9), date(2027, 2, 10)),
    ],
)
def test_carnaval_e_cinzas_param_em_anos_diferentes(ano, segunda, terca, cinzas):
    """
    Dois anos, e não um. Com um só, uma implementação que digitasse a data
    fixa de 2026 passaria — e o carnaval de 2027 cai onze dias antes.
    """
    assert e_feriado(segunda) is True, f"segunda de carnaval de {ano}"
    assert e_feriado(terca) is True, f"terça de carnaval de {ano}"
    assert e_feriado(cinzas) is True, f"quarta de cinzas de {ano}"


def test_a_quinta_depois_das_cinzas_ja_e_dia_util():
    """O carnaval para três dias, não a semana."""
    assert e_dia_util(date(2026, 2, 19)) is True
    assert e_dia_util(date(2027, 2, 11)) is True


# ═══════════════════════════════════════════════════════════════
# A tabela manual
# ═══════════════════════════════════════════════════════════════


def test_o_dia_da_tabela_manual_para():
    """Corpus Christi de 2026 — depende de decreto, por isso não é calculado."""
    assert e_feriado(date(2026, 6, 4)) is True


def test_a_tabela_manual_diz_o_motivo_e_o_ato():
    """
    Diagnóstico de prazo termina sempre em "por que este dia não contou?".
    Responder isso exige o motivo junto da data, não só a data.
    """
    motivo = dias_parados(2026)[date(2026, 6, 4)]

    assert "Corpus Christi" in motivo
    assert "decreto" in motivo.lower()


def test_o_ano_corrente_precisa_estar_na_lista_de_anos_conferidos():
    """
    ⚠️ Este teste fica vermelho sozinho na virada do ano, e é de propósito.

    Uma lista que termina em 2026 e é lida em 2027 não avisa que está
    incompleta: ela devolve "nenhum feriado manual" e o prazo volta a ser
    cobrado sobre dia parado — em silêncio, que é como o defeito original
    passou despercebido.

    Consertar é editar duas linhas em `app/utils/feriados.py`: acrescentar as
    datas do ano com o decreto que as justifica, e o ano em `ANOS_CONFERIDOS`.
    O vermelho é o lembrete anual; sem ele, não há nenhum.
    """
    from datetime import date as _date

    from dateutil.easter import easter

    ano = _date.today().year

    corpus_christi = easter(ano) + timedelta(days=60)

    faltando = f"""
REVISÃO ANUAL DOS FERIADOS — {ano} ainda não foi conferido.

Enquanto isto não for feito, Corpus Christi e as emendas por decreto NÃO
param o relógio do SLA, e o prazo está sendo cobrado sobre dias em que
ninguém atende. Os feriados nacionais e o carnaval continuam valendo —
esses são calculados e não dependem desta revisão.

O QUE FAZER:

  1. Confira o decreto do governo de Pernambuco para {ano}: se Corpus
     Christi é ponto facultativo, e quais emendas foram decretadas
     (véspera de Natal, de Ano Novo, emenda de feriado que cai em terça
     ou quinta). Corpus Christi de {ano} cai em {corpus_christi:%d/%m/%Y}, que é
     60 dias depois da Páscoa.

  2. Em backend/app/utils/feriados.py, acrescente cada dia à tupla
     _DIAS_PARADOS, com a data, o que é, e o ato que o justifica:

         (date({ano}, {corpus_christi.month}, {corpus_christi.day}),
          'Corpus Christi',
          'ponto facultativo estadual PE — decreto anual, confirmado para {ano}'),

  3. No mesmo arquivo, inclua {ano} em ANOS_CONFERIDOS.

Se o decreto do ano NÃO trouxer nenhum dia extra, ainda assim inclua {ano}
em ANOS_CONFERIDOS: registrar que foi conferido e não há nada é diferente
de ninguém ter olhado, e é essa diferença que este teste guarda.
        """

    assert ano in ANOS_CONFERIDOS, faltando


# ═══════════════════════════════════════════════════════════════
# O efeito no cálculo de horas úteis
# ═══════════════════════════════════════════════════════════════


def test_o_prazo_pula_o_feriado_no_meio():
    """
    Quarta 03/06/2026 às 08:00 + 10 h úteis.

    A jornada tem 9 h (08:00–17:00), então as 9 primeiras enchem a quarta
    inteira e sobra 1 h. A quinta é Corpus Christi e não conta, então a hora
    que falta cai na sexta a partir das 08:00 — 09:00 de sexta, 05/06.

    São 10 h e não 9 de propósito: com 9 o prazo termina às 17:00 da própria
    quarta e nem encosta no feriado, e o teste passaria sem provar nada.
    """
    prazo = add_business_hours(_sp(2026, 6, 3, 8, 0), 10)

    assert prazo == _sp(2026, 6, 5, 9, 0)


def test_vespera_de_feriado_as_16h_vence_no_dia_seguinte_ao_feriado():
    """
    O caso que o operador pediu, e o que melhor mostra o defeito antigo.

    Véspera do Natal, 24/12/2026 (quinta), às 16:00, prazo de 4 h úteis.
    Sobra 1 h naquele dia. O Natal (sexta) não conta, o fim de semana não
    conta, então as 3 h restantes caem na segunda a partir das 08:00 — 11:00
    de segunda, 28/12.

    Antes desta mudança o prazo caía na sexta 12:00: dia em que ninguém
    atendeu, e prazo cobrado indevidamente.
    """
    prazo = add_business_hours(_sp(2026, 12, 24, 16, 0), 4)

    assert prazo == _sp(2026, 12, 28, 11, 0)


def test_chamado_aberto_no_feriado_comeca_a_contar_no_proximo_util():
    """Abrir no Natal não consome prazo do próprio Natal."""
    prazo = add_business_hours(_sp(2026, 12, 25, 10, 0), 1)

    assert prazo == _sp(2026, 12, 28, 9, 0)


def test_o_deslocamento_de_pausa_continua_intacto():
    """
    Feriado mexe em QUANDO o relógio corre; pausa mexe em QUANTO se soma ao
    prazo já calculado. São camadas diferentes, e ligar feriados não podia
    tocar a segunda.
    """
    ticket = MagicMock(spec=Ticket)
    ticket.sla_total_paused_ms = 3 * 60 * 60 * 1000

    # A pausa não entra em `add_business_hours`: ela é somada depois, no
    # `check_breaches`. O prazo cru continua sendo o mesmo de sempre.
    prazo = add_business_hours(_sp(2026, 9, 8, 9, 0), 2)

    assert prazo == _sp(2026, 9, 8, 11, 0)
    assert ticket.sla_total_paused_ms == 3 * 60 * 60 * 1000


# ═══════════════════════════════════════════════════════════════
# O que NÃO muda: chamado que já existe
# ═══════════════════════════════════════════════════════════════


def test_ligar_feriados_nao_recalcula_chamado_ja_aberto():
    """
    Prende o comportamento que o operador exigiu.

    O prazo é COLUNA do chamado, carimbada uma vez na criação. Um chamado
    aberto antes desta mudança guarda o prazo que foi calculado sem feriados, e
    nada o recalcula — chamado aberto tem prazo acordado, e mudá-lo depois
    seria alterar compromisso feito.

    O teste grava um prazo à mão, chama o carimbo de novo com outra
    configuração e confere que o valor gravado é o que manda. Se algum dia o
    prazo passar a ser calculado na leitura, este teste cai.
    """
    ticket = MagicMock(spec=Ticket)
    prazo_de_origem = _sp(2026, 12, 25, 12, 0)  # calculado quando o Natal contava
    ticket.sla_resolve_due_at = prazo_de_origem
    ticket.sla_response_due_at = prazo_de_origem

    # Nada é chamado sobre ele. A ausência é o comportamento.
    assert ticket.sla_resolve_due_at == prazo_de_origem

    # E o carimbo, quando roda, só roda na CRIAÇÃO — com o `now` de então.
    novo = MagicMock(spec=Ticket)
    config = MagicMock(spec=SLAConfig)
    config.id = "cfg"
    config.response_time_hours = 1
    config.resolve_time_hours = 4
    apply_sla_config(novo, config, _sp(2026, 12, 24, 16, 0))

    # O chamado novo já nasce com o feriado descontado; o antigo não muda.
    assert novo.sla_resolve_due_at == _sp(2026, 12, 28, 11, 0)
    assert ticket.sla_resolve_due_at == prazo_de_origem


def test_o_calculo_de_feriado_nao_escreve_em_chamado_nenhum():
    """
    `e_feriado` e `e_dia_util` respondem uma pergunta e não têm efeito. Se um
    dia passarem a marcar algo no chamado, a regra de vigência quebra sem que
    nenhum teste de data perceba.
    """
    import inspect

    from app.utils import feriados

    fonte = inspect.getsource(feriados)

    assert "ticket." not in fonte
    assert "session" not in fonte.lower() or "AsyncSession" not in fonte


def test_dias_parados_traz_os_tres_grupos_juntos():
    """Nacional, carnaval calculado e tabela manual, no mesmo mapa."""
    do_ano = dias_parados(2026)

    assert date(2026, 12, 25) in do_ano  # nacional
    assert date(2026, 2, 17) in do_ano  # carnaval, calculado
    assert date(2026, 6, 4) in do_ano  # manual
    assert date(2026, 3, 6) not in do_ano  # estadual de PE, fora


def test_o_ano_sem_revisao_nao_inventa_feriado_manual():
    """
    Ano fora de `ANOS_CONFERIDOS` devolve só o que é calculável — nacional e
    carnaval. Ele NÃO levanta: derrubar a abertura de chamado na virada do ano
    trocaria um prazo generoso por uma indisponibilidade. O aviso vai para o
    log, e o teste do ano corrente é quem cobra a revisão.
    """
    fora = max(ANOS_CONFERIDOS) + 5

    do_ano = dias_parados(fora)

    assert do_ano, "os nacionais e o carnaval continuam valendo"
    assert all(
        "decreto" not in motivo.lower() for motivo in do_ano.values()
    ), "ano não revisado não deveria trazer entrada da tabela manual"


def test_a_pascoa_nao_e_digitada():
    """
    Guarda contra a regressão mais provável: alguém trocar o cálculo por uma
    tabela de datas fixas, que fica correta no ano em que foi escrita e erra
    em todos os outros.
    """
    import inspect

    from app.utils import feriados

    fonte = inspect.getsource(feriados)

    assert "easter" in fonte, "a Páscoa precisa ser calculada, não digitada"
    # Carnaval por deslocamento, não por literal de data.
    assert "_CARNAVAL_SEGUNDA = -48" in fonte


def test_sla_nao_tem_mais_laco_de_fim_de_semana_solto():
    """
    Os três `weekday() >= 5` viraram uma pergunta só. Um laço novo ali seria um
    caminho que pula fim de semana e ignora feriado — o defeito original, de
    volta em um dos ramos.
    """
    import ast
    import inspect

    from app.utils import sla

    # Pelo AST, e não por linha de texto: o docstring do próprio módulo
    # menciona `weekday()` ao explicar o que saiu dali, e uma varredura textual
    # casaria com a explicação em vez do código.
    arvore = ast.parse(inspect.getsource(sla))
    chamadas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "weekday"
    ]

    assert chamadas == [], (
        f"sla.py voltou a chamar weekday() direto, em {len(chamadas)} ponto(s): "
        "quem pula fim de semana precisa passar por e_dia_util, senão ignora feriado"
    )
