"""
SLA Engine — business-hours calculator and breach tracker.

Business hours: 08:00–17:00, Mon–Fri, America/Sao_Paulo (9 h/day).
Holidays are not modelled in this version.

Public API
----------
add_business_hours(start, hours)  → datetime
    Adds N working hours to `start`, skipping nights/weekends.

add_business_days(start, days)  → datetime
    Same thing in units of whole working days (9 h each).

apply_sla_config(ticket, config, now)
    Stamps sla_config_id, sla_response_due_at, sla_resolve_due_at on a ticket.

pause_sla(ticket, now)
    Records that the SLA clock started pausing (awaiting_* states).

resume_sla(ticket, now)
    Accumulates elapsed pause time and restarts the clock.

business_minutes_between(inicio, fim)  → int
    Minutos ÚTEIS que faltam de `inicio` até `fim`. A volta de
    `add_business_minutes`, e o que a tela consome para contar prazo.

prazo_efetivo(due_at, total_paused_ms)  → datetime | None
    O prazo que o motor de fato compara. Uma definição só, lida por todo mundo.

estado_do_expediente(agora)  → (aberto, proxima_virada)
    Se o relógio corre agora e quando esse estado muda. É o que deixa a tela
    congelar o contador sem saber o que é feriado.

check_breaches(ticket, now)
    Flips sla_response_breach / sla_resolve_breach if deadlines have passed.

register_first_response(ticket, now, responder_id=..., is_ai=..., is_system=...)
    Stamps sla_first_response when someone other than the ticket's author
    speaks to the client for the first time.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytz

from app.models.models import SLAConfig, Ticket, TicketStatus
from app.utils.feriados import e_dia_util

# ── Constants ─────────────────────────────────────────────────

# Jornada e fuso são CONSTANTES de propósito, não configuração.
#
# 08:00–17:00 (9 h/dia) foi confirmado com o cliente em 05/08/2026 e é o que o
# RN-013 sempre disse — ver "SLA" em docs/decisoes-e-regras.md.
#
# Existiu um bloco SLA_* no config.py que ninguém lia e que dizia 18:00. Ligar
# aquilo aqui para "corrigir a divergência" mudaria o prazo de TODOS os chamados
# de uma vez, sem ninguém perceber. Se o horário precisar mudar um dia, muda
# aqui — e a decisão vai para o documento antes do código.
SP_TZ = pytz.timezone("America/Sao_Paulo")

# O NOME do fuso, para quem precisa formatar o prazo fora daqui.
# Derivado do `SP_TZ`, e nao um literal repetido: a tela mostra
# "Vence em 24/09/2026 as 12:11", e esse horario so faz sentido no fuso em
# que a jornada e definida. Com um segundo literal no frontend, mudar a
# jornada de fuso exigiria lembrar de dois lugares -- e o esquecido
# mostraria um horario que nao corresponde a jornada nenhuma.
FUSO_DA_JORNADA = str(SP_TZ)
_WORK_START = 8  # 08:00
_WORK_END = 17  # 17:00
_WORK_HOURS_PER_DAY = _WORK_END - _WORK_START  # 9 h

_PAUSE_STATUSES = frozenset({TicketStatus.awaiting_client, TicketStatus.awaiting_technical})
_TERMINAL_STATUSES = frozenset({TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled})


# ── Internal helpers ──────────────────────────────────────────


def _to_sp(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to America/Sao_Paulo."""
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(SP_TZ)


def _proximo_inicio_util(dt: datetime) -> datetime:
    """Início da jornada do próximo dia útil, pulando fim de semana e feriado.

    Uma função só, e não um laço repetido em cada ponto que precisa avançar.
    Havia três `while dt.weekday() >= 5` espalhados, e três lugares para alguém
    corrigir dois — que é como feriado entraria em dois caminhos e não no
    terceiro.
    """
    proximo = (dt + timedelta(days=1)).replace(hour=_WORK_START, minute=0, second=0, microsecond=0)
    while not e_dia_util(proximo.date()):
        proximo = (proximo + timedelta(days=1)).replace(
            hour=_WORK_START, minute=0, second=0, microsecond=0
        )
    return proximo


def _advance_to_business_hours(dt: datetime) -> datetime:
    """
    If `dt` is outside working hours, return the next moment that IS inside
    working hours (keeping the SP timezone).

    "Fora da jornada" passou a incluir FERIADO, e não só noite e fim de semana.
    """
    dt = _to_sp(dt)

    if not e_dia_util(dt.date()):
        return _proximo_inicio_util(dt)

    if dt.hour < _WORK_START:
        return dt.replace(hour=_WORK_START, minute=0, second=0, microsecond=0)

    if dt.hour >= _WORK_END:
        return _proximo_inicio_util(dt)

    return dt


# ── Public API ────────────────────────────────────────────────


def add_business_minutes(start: datetime, minutes: int) -> datetime:
    """
    Devolve o instante que fica `minutes` minutos ÚTEIS depois de `start`.

    É a entrada canônica desde que os prazos de SLA passaram a ser guardados em
    minutos. Delega para `add_business_hours`, que já trabalhava em ponto
    flutuante internamente — meia hora não exigiu tocar na aritmética, só parar
    de arredondá-la na borda.
    """
    return add_business_hours(start, minutes / 60)


def add_business_hours(start: datetime, hours: float) -> datetime:
    """
    Return a datetime that is exactly `hours` business hours after `start`.
    Result is in America/Sao_Paulo timezone.

    Aceita fração: `0.5` são 30 minutos úteis. A anotação dizia `int` enquanto
    todo prazo era hora cheia, mas o laço abaixo sempre foi float — a mudança é
    de contrato declarado, não de comportamento.
    """
    current = _advance_to_business_hours(start)
    remaining: float = hours

    while remaining > 0:
        end_of_day = current.replace(hour=_WORK_END, minute=0, second=0, microsecond=0)
        hours_left_today = (end_of_day - current).total_seconds() / 3600

        if remaining <= hours_left_today:
            current = current + timedelta(hours=remaining)
            remaining = 0
        else:
            remaining -= hours_left_today
            current = _proximo_inicio_util(current)

    return current


def business_minutes_between(inicio: datetime, fim: datetime) -> int:
    """Quantos minutos ÚTEIS faltam de `inicio` até `fim`. Nunca negativo.

    A VOLTA de `add_business_minutes`, e a razão de ela existir: o relógio da
    tela subtraía `fim - agora` em tempo corrido, então um prazo de 12h úteis
    carimbado às 09:11 aparecia como "27h" — a conta incluía as 15 horas em que
    ninguém atende. Quem pergunta "quanto falta" precisa da mesma régua que
    respondeu "quando vence".

    Percorre jornada a jornada com as MESMAS peças da ida — `_proximo_inicio_util`
    e `_advance_to_business_hours`, que já sabem de noite, fim de semana e
    feriado. Nenhuma regra de calendário nasce aqui: se nascesse, seriam duas
    verdades sobre dia útil, e elas divergiriam no primeiro feriado que alguém
    lembrasse de pôr só num lado.

    Devolve ZERO quando `fim` já passou, e não um número negativo: "faltam -40
    minutos" não é informação que alguma tela queira mostrar, e quem precisa
    saber que venceu tem o próprio zero para ler.
    """
    atual = _advance_to_business_hours(inicio)
    alvo = _to_sp(fim)

    if alvo <= atual:
        return 0

    total = 0.0
    while atual < alvo:
        fim_do_dia = atual.replace(hour=_WORK_END, minute=0, second=0, microsecond=0)
        limite = min(fim_do_dia, alvo)
        if limite > atual:
            total += (limite - atual).total_seconds() / 60
        if alvo <= fim_do_dia:
            break
        atual = _proximo_inicio_util(atual)

    # `round`, e nao `int`: a ida faz aritmetica em ponto flutuante (meia hora
    # util existe desde que os prazos viraram minutos), e truncar 239,9999
    # devolveria 239 -- quebrando a ida e volta por um minuto fantasma.
    return int(round(total))


def prazo_efetivo(due_at: datetime | None, total_paused_ms: int | None) -> datetime | None:
    """O prazo que o motor DE FATO compara: o carimbado mais a pausa acumulada.

    Existe para que o prazo tenha uma definição só. A expressão
    `due_at + timedelta(milliseconds=total_paused_ms)` estava escrita à mão em
    `check_breaches` e em `violacao_ao_resolver`, e o chip da tela não a fazia
    de jeito nenhum — ele comparava contra o `due_at` cru e, num chamado que
    ficou três horas em "Aguardando cliente", escrevia "Vencido" três horas
    antes de o motor concordar.

    ⚠️ O acumulado é tempo CORRIDO somado a um prazo calculado em horas ÚTEIS.
    Uma pausa das 16:00 às 09:00 acrescenta 17 horas a um prazo que só perdeu 1
    hora de atendimento. É inconsistência conhecida, registrada em
    `docs/decisoes-e-regras.md`, e NÃO é o que esta função conserta: ela
    reproduz fielmente a regra de hoje, para que a tela e o motor digam a mesma
    coisa. Corrigir a regra muda vencimento e indicador, e é frente própria.
    """
    if due_at is None:
        return None
    return due_at + timedelta(milliseconds=total_paused_ms or 0)


def minutos_uteis_de_dias(dias: int) -> int:
    """Dias úteis → minutos úteis. Um dia é a JORNADA inteira, 9 h.

    Função, e não constante multiplicada na mão, porque a jornada é definida
    num lugar só (`_WORK_HOURS_PER_DAY`). Se ela mudar um dia, a extensão de
    "3 dias úteis" acompanha sem ninguém lembrar de procurar o 540.
    """
    return int(dias * _WORK_HOURS_PER_DAY * 60)


def inicio_do_ciclo_de_resolucao(ticket: Ticket) -> datetime:
    """Quando começou o ciclo de resolução VIGENTE.

    Existe porque o prazo de resolução é recomeçado na reabertura e o `created_at`
    não: um chamado com dez dias úteis de vida, reaberto agora, tinha `total`
    contado da abertura ORIGINAL contra um prazo do ciclo NOVO. Medido em
    25/09/2026: 5400 minutos úteis de total contra 540 de restante — **90% de
    consumo no instante da reabertura**, e a inflação cresce com a idade do
    chamado. O texto que saía se contradizia sozinho: "90% do prazo consumido,
    restam 540 minutos úteis" — 540 úteis É o ciclo inteiro.

    `reopened_at` é gravado em `reopen_ticket`, na mesma linha em que
    `reopen_count` incrementa, e é o ÚNICO lugar do sistema que o escreve. Por
    isso não foi preciso criar coluna: ele já é, com outro nome, o "início do
    ciclo". Um campo novo criaria uma segunda fonte para a mesma pergunta, e
    duas fontes divergem na primeira escrita que atualizar uma e não a outra —
    foi o que aconteceu entre o `warning_threshold` e o 80 fixo do frontend.

    As quatro semânticas que ele satisfaz, sem código adicional:

    * **primeiro ciclo / triagem** → `created_at`. O RN-013 fica intacto: a
      triagem continua carimbando `apply_sla_config(..., ticket.created_at)`, e
      chamado nunca reaberto tem `reopened_at` nulo;
    * **troca de prioridade no mesmo ciclo** → não muda. O endpoint da triagem
      não escreve `reopened_at`;
    * **reabertura** → o instante da reabertura, literalmente;
    * **pausa/resume e extensão** → não mudam. Nenhum dos dois toca o campo.

    ⚠️ **Não vale para o prazo de PRIMEIRA RESPOSTA.** A reabertura não
    recarimba `sla_response_due_at` — ele tem um ciclo só, e `created_at` é o
    início dele. Ancorar a resposta aqui introduziria um defeito onde não havia.
    """
    return ticket.reopened_at or ticket.created_at


def prazo_efetivo_de_resposta(ticket: Ticket) -> datetime | None:
    """O prazo de PRIMEIRA RESPOSTA que o motor compara.

    Base mais pausa acumulada. **Extensão não entra aqui**, e essa é a razão
    de existirem duas portas em vez de um argumento opcional: com um
    parâmetro, bastava alguém passá-lo na chamada errada para o prazo de
    resposta esticar em silêncio. Aqui não existe onde escrever isso.
    """
    return prazo_efetivo(ticket.sla_response_due_at, ticket.sla_total_paused_ms)


def prazo_efetivo_de_resolucao(ticket: Ticket) -> datetime | None:
    """O prazo de RESOLUÇÃO que o motor compara.

    Três camadas, nesta ordem: **base → pausa → extensão**.

    A ordem não é estética. A pausa é tempo CORRIDO somado ao prazo (dívida
    conhecida, registrada em `docs/decisoes-e-regras.md` e fora do escopo
    desta entrega); a extensão é tempo ÚTIL contado a partir do resultado.
    Inverter daria outro instante, porque somar minutos úteis a partir de
    pontos diferentes pula jornadas diferentes.

    A extensão é o ACUMULADO (`sla_resolve_extension_total_min`), e não um
    prazo já calculado. É o que torna duas concessões de +3 e +1 idênticas a
    uma de +4: o prazo é sempre recomputado da base, então conceder é
    associativo e a conta nunca depende de quando a anterior foi feita.
    """
    com_pausa = prazo_efetivo(ticket.sla_resolve_due_at, ticket.sla_total_paused_ms)
    if com_pausa is None:
        return None
    extensao = ticket.sla_resolve_extension_total_min or 0
    if extensao <= 0:
        return com_pausa
    return add_business_minutes(com_pausa, extensao)


def atualiza_prazo_efetivo(ticket: Ticket) -> None:
    """Materializa o prazo efetivo de resolução na coluna que o SQL consome.

    O painel e os relatórios decidem violação em SQL agregado — eles não
    passam pelo motor. Até aqui comparavam a coluna CRUA contra `now()`, e
    por isso já discordavam do chamado sempre que havia pausa. Com a
    extensão, discordariam também de todo prazo prorrogado.

    A saída é materializar: esta função é a ÚNICA escritora de
    `sla_resolve_effective_due_at`, e ela copia exatamente o que
    `prazo_efetivo_de_resolucao` devolve.

    É determinística porque os três insumos são campos PERSISTIDOS — prazo
    base, pausa acumulada e extensão acumulada. A pausa EM CURSO
    (`sla_paused_at`) não participa: o motor nunca a considerou, e é isso que
    permite guardar o resultado em vez de recalcular a cada leitura.

    Chamada de `apply_sla_config` e `resume_sla` — que são duas das cinco
    escritas dos insumos — e explicitamente na reabertura e na extensão, que
    escrevem os campos direto no router.
    """
    ticket.sla_resolve_effective_due_at = prazo_efetivo_de_resolucao(ticket)


def estado_do_expediente(agora: datetime) -> tuple[bool, datetime]:
    """Diz se o relógio corre AGORA e quando esse estado muda.

    Devolve `(aberto, proxima_virada)`. É o par que deixa a tela congelar o
    contador sem saber o que é feriado: enquanto `aberto`, ela desconta um
    minuto por minuto até a `proxima_virada`; a partir dali, para.

    Fora da jornada, a virada é o próximo instante ÚTIL — que já pula noite,
    fim de semana e feriado, porque é o mesmo `_advance_to_business_hours` que
    o cálculo de prazo usa.
    """
    agora_sp = _to_sp(agora)
    proximo_util = _advance_to_business_hours(agora_sp)

    if proximo_util == agora_sp:
        fecha = agora_sp.replace(hour=_WORK_END, minute=0, second=0, microsecond=0)
        return True, fecha

    return False, proximo_util


def add_business_days(start: datetime, days: int) -> datetime:
    """
    Return a datetime that is exactly `days` business days after `start`.

    A business day is the 9 h journey itself, so this is just a convenience
    wrapper over add_business_hours — a deadline set on Friday afternoon lands
    on the middle of the following week, not on Monday morning.
    """
    return add_business_hours(start, days * _WORK_HOURS_PER_DAY)


def apply_sla_config(ticket: Ticket, config: SLAConfig, now: datetime) -> None:
    """Stamp SLA deadlines on a ticket at creation time."""
    ticket.sla_config_id = config.id
    ticket.sla_response_due_at = add_business_minutes(now, config.response_time_minutes)
    ticket.sla_resolve_due_at = add_business_minutes(now, config.resolve_time_minutes)
    # Carimbar o prazo base muda o efetivo: materializa junto, para o painel
    # nunca ler um prazo mais velho que o do chamado.
    atualiza_prazo_efetivo(ticket)


def pause_sla(ticket: Ticket, now: datetime) -> None:
    """
    Start the pause clock.  Safe to call even if already paused
    (subsequent calls are no-ops).
    """
    if ticket.sla_paused_at is None:
        ticket.sla_paused_at = now


def resume_sla(ticket: Ticket, now: datetime) -> None:
    """
    Stop the pause clock and accumulate the elapsed pause duration into
    sla_total_paused_ms.  The accumulated time will later be used to extend
    the effective deadlines.
    """
    if ticket.sla_paused_at is not None:
        paused_ms = int((now - ticket.sla_paused_at).total_seconds() * 1000)
        ticket.sla_total_paused_ms = (ticket.sla_total_paused_ms or 0) + paused_ms
        ticket.sla_paused_at = None
        # O acumulado de pausa entra no prazo efetivo — a coluna acompanha.
        atualiza_prazo_efetivo(ticket)


def violacao_ao_resolver(ticket: Ticket, now: datetime) -> tuple[bool, bool]:
    """
    Diz se o SLA está violado NO INSTANTE em que alguém vai resolver o chamado.

    Devolve `(resposta_violada, resolucao_violada)`.

    Por que não basta ler `sla_response_breach` / `sla_resolve_breach`
    ---------------------------------------------------------------------
    As duas marcas são gravadas por outros caminhos, e nenhuma delas está
    garantidamente em dia no momento da resolução:

    **A de resolução não é marcada ao resolver.** `check_breaches` pula o teste
    quando o chamado está em estado terminal, e os dois caminhos que resolvem
    já colocaram o status em `resolved` quando o chamam. Um chamado que passou
    do prazo e ficou quieto até ser resolvido chega aqui com a marca em `False`
    — que são justamente os casos que uma exigência de justificativa existe
    para pegar.

    **A de resposta pode estar prestes a mudar.** Quando a própria nota de
    resolução é a primeira resposta, quem marca é o `register_first_response`,
    que roda depois desta verificação. Ler a marca aqui veria o passado.

    Por isso as duas são calculadas da DATA, com o mesmo deslocamento de pausa
    que o `check_breaches` usa — e a marca existente é respeitada quando já
    estiver ligada, para não desfazer o que outro caminho já concluiu.

    Esta função NÃO escreve nada. Ela é consultada antes de qualquer mutação,
    para que a recusa não deixe rastro pela metade.
    """
    efetivo_resposta = prazo_efetivo_de_resposta(ticket)
    efetivo_resolucao = prazo_efetivo_de_resolucao(ticket)

    resposta = bool(ticket.sla_response_breach)
    if not resposta and efetivo_resposta and ticket.sla_first_response is None:
        resposta = now > efetivo_resposta

    resolucao = bool(ticket.sla_resolve_breach)
    if not resolucao and efetivo_resolucao:
        resolucao = now > efetivo_resolucao

    return resposta, resolucao


def marca_violacao_ao_resolver(ticket: Ticket, now: datetime) -> None:
    """Carimba as marcas de violação no instante em que o chamado é resolvido.

    Existe porque `check_breaches` não alcança este momento: ele pula o teste de
    resolução quando o chamado está em estado terminal, e os dois caminhos que
    resolvem já colocaram o status em `resolved` quando o chamam. Chamado que
    passou do prazo e ficou **quieto** até ser resolvido chegava com a marca em
    `False` — e o indicador agregado, que conta a marca, o dava como cumprido.

    **Só acrescenta, nunca desmarca.** Marca já ligada por outro caminho fica
    ligada, mesmo que a conta pela data discorde: desfazer conclusão alheia é
    outra decisão, e não esta.

    Por que não consertar o `check_breaches` em vez desta função: a guarda de
    terminal lá existe para que chamado fechado pare de acumular violação a cada
    escrita. Tirá-la marcaria chamado encerrado em qualquer atualização futura,
    que é um problema maior do que o resolvido.

    A conta é a de `violacao_ao_resolver`, com o mesmo deslocamento de pausa do
    resto do sistema — a mesma que a exigência de justificativa já usa, para que
    exigir o motivo e contar a violação nunca discordem.
    """
    resposta_violada, resolucao_violada = violacao_ao_resolver(ticket, now)

    if resposta_violada:
        ticket.sla_response_breach = True
    if resolucao_violada:
        ticket.sla_resolve_breach = True


def check_breaches(ticket: Ticket, now: datetime) -> None:
    """
    Update sla_response_breach and sla_resolve_breach.

    O prazo efetivo vem do `prazo_efetivo` — a MESMA função que a tela consome
    para montar o contador. Era uma expressão escrita à mão aqui e outra igual
    no `violacao_ao_resolver`, e o chip não fazia nenhuma das duas: dois
    lugares para corrigir um, mais um terceiro que discordava em silêncio.
    """
    efetivo_resposta = prazo_efetivo_de_resposta(ticket)
    efetivo_resolucao = prazo_efetivo_de_resolucao(ticket)

    if efetivo_resposta and ticket.sla_first_response is None:
        if now > efetivo_resposta:
            ticket.sla_response_breach = True

    if efetivo_resolucao and ticket.status not in _TERMINAL_STATUSES:
        if now > efetivo_resolucao:
            ticket.sla_resolve_breach = True


def register_first_response(
    ticket: Ticket,
    now: datetime,
    *,
    responder_id: uuid.UUID | None,
    is_ai: bool = False,
    is_system: bool = False,
) -> bool:
    """
    Carimba a primeira resposta do SLA. Devolve True se carimbou agora.

    Primeira resposta é a primeira fala dirigida ao cliente por alguém que não
    é o autor do chamado — não é "o chamado saiu do estado inicial". A regra
    não olha para status nenhum, de propósito: assumir, atribuir ou cancelar
    um chamado marcava resposta sem uma palavra ter sido dita, e chamado que
    nasce fora de `open` (a Helô) nunca marcava.

    O critério de "não é o autor" é o mesmo que o chat já usa para decidir a
    quem notificar (`_notify_other_party`) — mesma pergunta, uma só resposta.
    Vale também na resolução: quando quem abre e quem resolve são a mesma
    pessoa, não houve ninguém do outro lado esperando, e um tempo de resposta
    de zero segundo só sujaria a média de uma conversa que não existiu.

    **A fala da Helô CARIMBA** — decisão do cliente em 28/08/2026, revertendo
    o desenho original. O argumento dele: quando ela responde, o atendimento
    começou de fato, e mostrar "aguardando primeira resposta" para um cliente
    que acabou de ser respondido é o indicador mentindo para o lado contrário.

    O preço está registrado aqui porque ele é real e não aparece sozinho: com
    a Helô ligada, todo chamado passa a ter primeira resposta em segundos, e
    este indicador vira ~100% permanente. Ele deixa de medir a equipe e passa
    a medir o robô, que é sempre rápido. Se um dia fizer falta saber quanto o
    cliente esperou por um HUMANO, esse número não existe mais — seria uma
    coluna nova, não um filtro sobre esta.

    `is_system` continua sem carimbar: mensagem automática de mudança de
    status não é alguém falando com o cliente.

    A violação é avaliada ANTES do carimbo porque `check_breaches` só olha o
    prazo enquanto `sla_first_response` é nulo — na ordem inversa, a resposta
    atrasada apagava a própria violação.
    """
    if ticket.sla_first_response is not None:
        return False
    if is_system:
        return False
    # A Helô não tem `responder_id` — ela fala com remetente nulo. A checagem
    # de autor abaixo existe para gente, e sem esta saída ela recusaria o
    # carimbo justamente no caso que o cliente pediu.
    if not is_ai and (responder_id is None or responder_id == ticket.creator_id):
        return False

    efetivo = prazo_efetivo_de_resposta(ticket)
    if efetivo and now > efetivo:
        ticket.sla_response_breach = True

    ticket.sla_first_response = now
    return True
