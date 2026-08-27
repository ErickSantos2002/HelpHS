"""
Helô — o atendimento por IA que fala com o cliente.

Fase 1: acolher e triar. Ela não resolve problema técnico, não promete prazo e
não continua a conversa depois de entregar o chamado para um humano.

Este módulo começa pelo interruptor, e não pela conversa, de propósito: uma IA
que fala com cliente sem ter como ser calada é a única parte disto que não tem
volta. Ver o desenho em
`docs/superpowers/specs/2026-08-11-helo-atendimento-ia-design.md`.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import (
    ChatMessage,
    Equipment,
    Product,
    Ticket,
    TicketStatus,
    User,
)

# O cálculo de horário comercial vem do motor de SLA, inclusive sendo privado.
# Uma cópia da regra aqui é o defeito que este projeto já pagou caro: doze
# cópias de "é seu?" espalhadas em quatro arquivos. Se um dia a jornada mudar,
# ela muda num lugar e a Helô acompanha sozinha.
from app.utils.sla import _advance_to_business_hours, _to_sp

_DIAS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

# Como o cliente pede para falar com gente. A lista é de trechos, não de frases
# inteiras: ninguém digita a frase que o programador imaginou.
#
# Deliberadamente generosa — errar para o lado de escalar é barato (um humano
# atende alguém que talvez seguisse com a triagem), e errar para o outro lado é
# o robô que não aceita "não", que o desenho chama de pior que robô nenhum.
_PEDIDOS_DE_HUMANO = (
    "falar com um humano",
    "falar com humano",
    "falar com uma pessoa",
    "falar com pessoa",
    "falar com alguem",
    "falar com alguém",
    "falar com atendente",
    "falar com um atendente",
    "falar com o atendente",
    "quero um atendente",
    "quero atendente",
    "me passa pro atendente",
    "me passa para o atendente",
    "passa pro atendente",
    "passa para o atendente",
    "quero um humano",
    "quero falar com gente",
    "atendimento humano",
    "nao quero robo",
    "não quero robô",
    "nao quero falar com robo",
    "não quero falar com robô",
)

# Por que uma função e não três `if` espalhados: a mesma pergunta — "a Helô
# pode falar aqui?" — vai ser feita na criação do chamado, na resposta do
# cliente e em qualquer entrada futura. Copiada, ela vira as doze cópias de
# `ensure_ticket_visible` que custaram uma rodada inteira para reunir.


def helo_pode_falar(ticket: Ticket, cliente: User) -> bool:
    """
    Os três níveis de desligamento, em conjunção.

    Qualquer chave desligada cala a Helô. **Não existe religar num nível mais
    específico**: o técnico não reativa a IA num chamado de cliente que pediu
    para não ser atendido por robô, e a flag global vence os dois. É a única
    semântica em que "eu desliguei" continua verdade depois — com precedência
    invertida, quem desligou precisaria vigiar os outros níveis para sempre.

    Args:
        ticket: o chamado em questão — `ai_enabled` é o interruptor do técnico.
        cliente: o autor do chamado — `ai_enabled` é a preferência dele (ou da
            empresa dele, quando o nível por CNPJ existir).

    Returns:
        True quando os três níveis estão ligados.
    """
    if not get_settings().helo_enabled:
        return False
    if not ticket.ai_enabled:
        return False
    return bool(cliente.ai_enabled)


def _primeiro_nome(nome: str) -> str:
    """
    "Suelen Fernandes" -> "Suelen".

    Nome vazio ou só espaços devolve vazio, e quem chama decide o que fazer —
    saudar alguém de "Olá, !" é pior do que não usar o nome.
    """
    partes = nome.strip().split()
    return partes[0] if partes else ""


def _frase_do_aparelho(produto: str | None, series: Sequence[str]) -> str:
    """
    A frase que mostra que o sistema reconhece o aparelho.

    É o ganho que a Helô do WhatsApp nunca teve: lá ela precisava PEDIR modelo e
    número de série, porque não havia cadastro. Aqui o cliente já escolheu os
    dois no formulário, e perguntar de novo faria o sistema parecer burro na
    primeira frase.

    Sem produto no chamado a frase inteira sai de cena — inventar "seu
    equipamento" para não deixar buraco é pior do que ir direto às perguntas.
    """
    if not produto:
        return ""

    limpos = [s.strip() for s in series if s and s.strip()]
    if not limpos:
        return f"Vi que seu chamado é sobre o {produto}."
    if len(limpos) == 1:
        return f"Vi que seu chamado é sobre o {produto} (série {limpos[0]})."
    return f"Vi que seu chamado é sobre o {produto} (séries {', '.join(limpos)})."


def monta_saudacao(*, cliente_nome: str, produto: str | None, series: Sequence[str]) -> str:
    """
    A primeira mensagem — montada com dado do cadastro, SEM chamar o LLM.

    Três ganhos, e nenhum deles é economia: é **previsível** (a primeira coisa
    que o cliente lê nunca sai errada), é **instantânea** (não espera resposta
    de API) e é **grátis** — some metade das chamadas de LLM do fluxo.

    O LLM entra só depois, para interpretar o que o cliente responder.
    """
    nome = _primeiro_nome(cliente_nome)
    abertura = f"Olá, {nome}! " if nome else "Olá! "

    linhas = [f"{abertura}Sou a Helô, assistente da Health & Safety."]

    aparelho = _frase_do_aparelho(produto, series)
    if aparelho:
        linhas.append(aparelho)

    linhas.append("Para adiantar o atendimento, me conta:")
    linhas.append("1. O que exatamente está acontecendo com o aparelho?")
    linhas.append("2. Quando o problema começou?")
    linhas.append("3. Você já tentou alguma coisa?")

    return "\n".join(linhas)


def monta_encerramento(agora: datetime) -> str:
    """
    A despedida da triagem, que muda só na última frase.

    Dentro do horário, um atendente assume em seguida. Fora dele, a mensagem
    diz QUANDO — e o dia é calculado, nunca "amanhã" fixo: quem abre chamado na
    sexta à noite precisa ler "segunda-feira", e nenhuma frase bonita conserta
    isso depois que o cliente esperou o fim de semana achando que era amanhã.

    O cálculo é o do motor de SLA, então feriado não entra — decisão do cliente
    em 26/08, registrada no desenho. Na véspera de um feriado ela promete um dia
    em que ninguém atende.
    """
    agora_sp = _to_sp(agora)
    proximo = _advance_to_business_hours(agora_sp)

    if proximo == agora_sp:
        return "Obrigada! Registrei tudo aqui. Um atendente já vai assumir seu chamado."

    # "Ainda hoje" cobre a madrugada: quem abre às 6h da manhã de uma
    # terça-feira é atendido no mesmo dia, e dizer "na terça-feira" para quem
    # está vivendo a terça-feira soa como espera de uma semana.
    if proximo.date() == agora_sp.date():
        quando = "ainda hoje"
    else:
        quando = f"na {_DIAS[proximo.weekday()]}"

    return (
        "Obrigada! Registrei tudo aqui. Nossa equipe atende de segunda a sexta, "
        f"das 8h às 17h. {quando.capitalize()} pela manhã um atendente entra em contato."
    )


def quer_humano(texto: str) -> bool:
    """
    O cliente pediu para falar com uma pessoa.

    A regra mais importante do desenho do ponto de vista de experiência: pediu,
    a Helô **para a triagem na hora** e escala, sem insistir e sem perguntar o
    motivo. Um robô que não aceita "não" é pior do que robô nenhum.
    """
    limpo = texto.strip().lower()
    return any(pedido in limpo for pedido in _PEDIDOS_DE_HUMANO)


async def abre_triagem(
    db: AsyncSession,
    ticket: Ticket,
    cliente: User,
    equipamentos: Sequence[Equipment],
) -> bool:
    """
    A Helô se apresenta no chamado recém-aberto e faz as três perguntas.

    Grava a mensagem e move o chamado para "Em andamento". **Não** dá commit —
    quem abriu a transação é o `create_ticket`, e a saudação precisa nascer no
    mesmo commit do chamado: metade das duas coisas gravada é um chamado que
    diz "Em andamento" sem ninguém ter falado, ou uma fala em chamado que não
    existe.

    Args:
        equipamentos: os aparelhos já carregados pelo chamado. Vêm de fora
            porque acessar `ticket.equipments` aqui dispararia lazy load, que
            em SQLAlchemy async estoura com MissingGreenlet.

    Returns:
        True se ela falou. False quando qualquer interruptor está desligado —
        e aí o chamado segue "Aberto", exatamente como antes dela existir.
    """
    if not helo_pode_falar(ticket, cliente):
        return False

    produto = None
    if ticket.product_id is not None:
        # SELECT explícito em vez de `ticket.product`: o relacionamento não foi
        # carregado, e o lazy load do async estoura em vez de consultar.
        produto = (
            await db.execute(select(Product.name).where(Product.id == ticket.product_id))
        ).scalar_one_or_none()

    db.add(
        ChatMessage(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            # Nulo, e não um usuário "Helô" no banco: ele apareceria na lista de
            # técnicos, poderia ser atribuído a chamado e receberia e-mail.
            sender_id=None,
            content=monta_saudacao(
                cliente_nome=cliente.name,
                produto=produto,
                series=[e.serial_number for e in equipamentos if e.serial_number],
            ),
            is_system=False,
            is_ai=True,
            created_at=datetime.now(UTC),
        )
    )

    # "Em andamento" por decisão do cliente em 26/08, em vez de um status novo
    # `ai_handling`. O efeito colateral está registrado no desenho: a coluna
    # passa a incluir chamado sem técnico atribuído.
    #
    # E NÃO se toca no SLA aqui: `register_first_response` ignora `is_ai`, então
    # o relógio de primeira resposta continua correndo até um humano falar. Se
    # a fala dela zerasse o relógio, o indicador viraria 100% permanente e
    # mediria a velocidade de um robô, que é sempre a mesma.
    ticket.status = TicketStatus.in_progress
    return True
