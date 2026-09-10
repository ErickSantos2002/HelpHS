"""
Helô — o atendimento por IA que fala com o cliente.

Ela acolhe, tria e — desde a Fase 2 — **resolve o que está documentado**,
consultando os manuais por busca vetorial. O que ela continua não fazendo:
inventar procedimento, prometer prazo, falar de preço, e continuar a conversa
depois de entregar o chamado para um humano.

A SAUDAÇÃO NÃO USA LLM, e isso é decisão, não sobra da Fase 1. Ela é montada
com dado do cadastro: previsível (a primeira coisa que o cliente lê nunca sai
errada), instantânea (não espera API) e grátis. O modelo entra a partir do
SEGUNDO turno, para interpretar o que o cliente responder.

Este módulo começa pelo interruptor, e não pela conversa, de propósito: uma IA
que fala com cliente sem ter como ser calada é a única parte disto que não tem
volta. Ver o desenho em
`docs/superpowers/specs/2026-08-11-helo-atendimento-ia-design.md`.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import NamedTuple

from loguru import logger
from sqlalchemy import exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import (
    ChatMessage,
    Equipment,
    Product,
    Ticket,
    TicketStatus,
    User,
    UserRole,
)
from app.services.helo_base import TrechoRecuperado, busca_trechos, monta_base_tecnica
from app.services.helo_embedding import embute_um
from app.services.helo_prompt import (
    SISTEMA,
    le_resposta,
    monta_cadastro,
    monta_conversa,
    monta_prompt,
)
from app.services.llm import responde_como_helo
from app.utils.history import registra_historico

# O cálculo de horário comercial vem do motor de SLA, inclusive sendo privado.
# Uma cópia da regra aqui é o defeito que este projeto já pagou caro: doze
# cópias de "é seu?" espalhadas em quatro arquivos. Se um dia a jornada mudar,
# ela muda num lugar e a Helô acompanha sozinha.
from app.utils.sla import _advance_to_business_hours, _to_sp, register_first_response

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

    O `helo_saiu` entra aqui e NÃO é um quarto nível de desligamento — é o fim
    da conversa dela naquele chamado. A diferença importa para quem for
    mexer: os três interruptores são de quem quer a IA fora; este é ela mesma
    tendo dito que acabou. Ninguém religa pela tela, porque não é botão.

    Args:
        ticket: o chamado em questão — `ai_enabled` é o interruptor do técnico,
            `helo_saiu` é a conversa dela já encerrada ali.
        cliente: o autor do chamado — `ai_enabled` é a preferência dele (ou da
            empresa dele, quando o nível por CNPJ existir).

    Returns:
        True quando os três níveis estão ligados e ela ainda não saiu.
    """
    if not get_settings().helo_enabled:
        return False
    if not ticket.ai_enabled:
        return False
    if ticket.helo_saiu:
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
    ticket.status = TicketStatus.in_progress

    # A saudação dela CARIMBA a primeira resposta — decisão do cliente em
    # 28/08, revertendo o desenho. Para quem está do outro lado, o atendimento
    # começou: dizer "aguardando primeira resposta" a quem acabou de ser
    # respondido é o indicador mentindo para o outro lado.
    #
    # O preço está escrito em `register_first_response`, e é real: este número
    # vira ~100% permanente e para de medir a equipe.
    register_first_response(ticket, datetime.now(UTC), responder_id=None, is_ai=True)
    return True


# Quantas vezes ela responde DEPOIS da saudação.
#
# Na Fase 1 o teto era de duas FALAS — a saudação e o encerramento — porque a
# conversa não existia: ela dizia uma coisa e saía. Com o LLM, a conversa
# cresce, e o teto passa a ser de TROCAS, que é o que o prompt dela promete:
# "se a conversa passar de seis trocas sem sair do lugar: escale".
#
# O teto é a rede embaixo do modelo, não o mecanismo principal. O prompt manda
# escalar sozinho quando não resolve em duas tentativas; isto aqui é o que
# acontece quando ele não obedece — e modelo que não obedece é o caso comum,
# não a exceção. Sem o teto, o cliente conversaria para sempre com alguém que
# não vai resolver.
TROCAS_MAXIMAS = 6

# Mantido: reprocessar não pode fazer a saudação sair duas vezes. Um chamado
# onde ela nunca falou é um chamado em que ela não entra no meio.
FALAS_MAXIMAS = TROCAS_MAXIMAS + 1


# Os motivos de escalada, e a razão de serem constantes e não frases soltas.
#
# Na Fase 1 havia uma saída só — o cliente pediu uma pessoa —, e a notificação
# da equipe podia dizer isso com segurança. Agora são quatro caminhos, e três
# deles nada têm a ver com o cliente ter pedido gente: o modelo decidiu, o teto
# de trocas estourou, ou a IA não respondeu. Mandar "o cliente pediu para falar
# com uma pessoa" nos quatro casos apaga a única informação que muda a ordem da
# fila — se tem alguém do outro lado esperando gente ou não.
MOTIVO_PEDIU_HUMANO = "o cliente pediu para falar com uma pessoa"
MOTIVO_TETO_DE_TROCAS = f"a conversa passou de {TROCAS_MAXIMAS} trocas sem sair do lugar"
MOTIVO_IA_MUDA = "a IA não respondeu"
MOTIVO_SEM_MOTIVO = "o modelo escalou sem dizer o motivo"


class FalaDaHelo(NamedTuple):
    """
    O que ela falou, e — quando saiu de cena — por quê.

    `motivo` viaja junto porque não dá para recuperá-lo depois: quem precisa
    dele é a notificação da equipe, e deduzi-lo relendo o texto do cliente no
    router seria uma segunda cópia da decisão que este módulo já tomou. As duas
    cópias concordariam no caso do `quer_humano` e discordariam nos outros
    três, que é justamente onde a equipe precisa de informação boa.

    `None` quer dizer que ela respondeu e continua na conversa.
    """

    mensagem: ChatMessage
    motivo: str | None

    @property
    def escalou(self) -> bool:
        """Escalar é ter motivo. Um campo separado poderia divergir do outro."""
        return self.motivo is not None


def monta_escalada() -> str:
    """
    A saída quando o cliente pede uma pessoa.

    Sem "posso te ajudar com mais alguma coisa?", sem perguntar o motivo, sem
    pedir para ele confirmar. Um robô que não aceita "não" é pior do que robô
    nenhum, e insistir aqui é o que transforma um atendimento ruim em uma
    reclamação.
    """
    return (
        "Sem problema! Já estou passando seu chamado para um atendente. "
        "Pode escrever aqui o que precisar — a equipe vai ler tudo."
    )


async def _quantas_vezes_ela_falou(db: AsyncSession, ticket_id: uuid.UUID) -> int:
    consulta = (
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.ticket_id == ticket_id, ChatMessage.is_ai.is_(True))
    )
    return int((await db.execute(consulta)).scalar_one())


async def _humano_ja_esta_na_conversa(db: AsyncSession, ticket: Ticket) -> bool:
    """
    Duas condições, porque cada uma sozinha cala a Helô tarde demais.

    O **responsável** não passa pelo chat: assumir o chamado grava histórico e
    notificação, nunca uma mensagem. Quem pegou o chamado às 8h e ainda não
    digitou é invisível para qualquer varredura de conversa — e ela anunciaria
    que "um atendente já vai assumir" um chamado que já tem nome.

    A **fala da equipe** não passa pela atribuição: técnico e admin escrevem em
    qualquer chamado sem serem os responsáveis (`_get_ticket_visivel` só
    submete o não-staff à regra de dono), e responder antes de assumir é o
    caminho normal da triagem da manhã. Pior: `assignee_id` é revogável — o
    endpoint de atribuição aceita nulo e desatribui. Se só ele valesse, tirar o
    responsável de um chamado ressuscitaria a Helô no meio de uma conversa que
    um humano já começou. Mensagem é append-only; atribuição não é.

    A frase que ela diria — *"um atendente já vai assumir seu chamado"* — é
    mentira nas duas situações. A guarda é a união delas.

    O responsável vem primeiro por ser de graça: já está carregado no chamado,
    e a consulta só acontece em chamado sem dono.

    A conferência é pelo PAPEL de quem falou, e não pelo atalho "remetente que
    não é o autor do chamado". O atalho só funciona porque hoje a visibilidade
    é um "é seu?" cru; quando a frente de empresa/CNPJ deixar colegas da mesma
    empresa entrarem no chamado, ele calaria a Helô pelo motivo errado e sem
    avisar.
    """
    if ticket.assignee_id is not None:
        return True

    consulta = select(
        exists().where(
            ChatMessage.ticket_id == ticket.id,
            ChatMessage.sender_id == User.id,
            User.role.in_((UserRole.admin, UserRole.technician)),
        )
    )
    return bool((await db.execute(consulta)).scalar())


async def responde_triagem(
    db: AsyncSession,
    ticket: Ticket,
    cliente: User,
    texto_do_cliente: str,
) -> FalaDaHelo | None:
    """
    O turno da Helô: ela busca na base, responde, ou escala.

    A ORDEM DAS GUARDAS É O DESENHO. As quatro primeiras não dependem do modelo
    e vêm antes dele, de propósito — cada uma resolve um caso em que chamar o
    LLM seria errado, caro, ou os dois:

    1. Os três interruptores. Desligada é desligada, e não existe religar num
       nível mais específico.
    2. Um humano já está na conversa. O chamado é dele.
    3. A saudação nunca aconteceu, ou o teto de trocas estourou.
    4. **O cliente pediu uma pessoa.** Esta roda ANTES do LLM e não dentro
       dele: se o modelo estiver fora do ar, o pedido de humano precisa
       funcionar do mesmo jeito. É a regra que o desenho chama de mais
       importante do ponto de vista de experiência, e ela não pode depender de
       um serviço externo estar de pé.

    Só depois disso o modelo entra. E se ele falhar de qualquer maneira —
    serviço fora, timeout, resposta vazia — ela escala com mensagem neutra.
    Nenhum chamado fica preso porque uma IA não respondeu.

    Não dá commit — quem abriu a transação é o `create_message`, e a fala dela
    precisa nascer no mesmo commit da fala do cliente. Metade gravada seria uma
    pergunta sem resposta ou uma resposta sem pergunta.

    Returns:
        A fala dela e se escalou, para quem precisa transmiti-la (o WebSocket)
        e para quem precisa avisar a equipe. None quando ela não deve falar.
    """
    if not helo_pode_falar(ticket, cliente):
        return None

    # Antes da contagem: um chamado que já tem gente não precisa nem saber
    # quantas falas ela ainda teria de crédito.
    if await _humano_ja_esta_na_conversa(db, ticket):
        return None

    falas = await _quantas_vezes_ela_falou(db, ticket.id)
    # Zero: ela nunca abriu a triagem neste chamado — foi criado antes dela
    # existir, ou com ela desligada. Entrar agora seria se apresentar no meio
    # de uma conversa que já começou sem ela.
    if falas == 0 or falas >= FALAS_MAXIMAS:
        return None

    conteudo, motivo = await _o_que_ela_diz(db, ticket, cliente, texto_do_cliente, falas)

    fala = ChatMessage(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        sender_id=None,
        content=conteudo,
        is_system=False,
        is_ai=True,
        created_at=datetime.now(UTC),
    )
    db.add(fala)

    if motivo is not None:
        _ela_sai_de_cena(db, ticket, motivo)

    return FalaDaHelo(mensagem=fala, motivo=motivo)


def _ela_sai_de_cena(db: AsyncSession, ticket: Ticket, motivo: str) -> None:
    """
    Escalou: a conversa dela acabou naquele chamado, e o histórico registra.

    `helo_saiu` é o campo dela. Sai `True` nos QUATRO motivos, porque em todos
    a conversa acabou do mesmo jeito — o chamado é do humano, e o prompt dela
    promete que depois de escalar ela não fala mais nada ali.

    **`ai_enabled` só cai no pedido explícito de humano, e isso é decisão, não
    esquecimento.** Aquele campo é o botão de gente: desligá-lo fecha também a
    sugestão de resposta e o resumo do TÉCNICO. Quando o cliente pede uma
    pessoa, a vontade dele vale para as ferramentas todas e desligar é o certo.
    Nos outros três — o modelo desistiu, o teto estourou, a IA não respondeu —
    ninguém pediu para sair da IA, e tirar a ferramenta do técnico justamente
    nos chamados em que a IA já falhou seria castigá-lo pelo defeito dela.

    O histórico não é enfeite: sem ele o técnico abre o chamado, vê a IA
    calada, e não tem onde ler por quê. O motivo que o modelo escreveu na linha
    `ESCALAR:` é o melhor texto que existe para essa linha — quem o redigiu
    tinha lido a conversa.
    """
    ticket.helo_saiu = True
    registra_historico(db, ticket.id, None, "helo_saiu", str(False), str(True), motivo)

    if motivo == MOTIVO_PEDIU_HUMANO:
        ticket.ai_enabled = False
        registra_historico(db, ticket.id, None, "ai_enabled", str(True), str(False), motivo)


async def _busca_sem_derrubar(
    db: AsyncSession, ticket: Ticket, vetor: Sequence[float]
) -> list[TrechoRecuperado]:
    """
    A busca vetorial dentro de um SAVEPOINT, e o SAVEPOINT é o ponto.

    O que está em jogo é a mensagem DO CLIENTE. Ela ainda não foi commitada
    quando isto roda — nasce no mesmo commit da resposta da Helô —, e uma falha
    de infraestrutura da IA que apagasse o que o cliente acabou de escrever
    seria o pior defeito que este módulo pode ter.

    Só `except` não resolve isso em PostgreSQL. O erro aborta a transação
    INTEIRA: o `db.add(fala)` seguinte ainda parece funcionar e o commit morre
    com "current transaction is aborted", levando junto a mensagem do cliente.
    O SAVEPOINT é o que devolve a sessão utilizável.

    Vale para extensão `vector` ausente, tabela ainda não migrada e índice
    corrompido — todos indistinguíveis daqui, e todos com o mesmo destino: base
    vazia, e a Helô escala.
    """
    try:
        async with db.begin_nested():
            return await busca_trechos(db, ticket, vetor)
    except SQLAlchemyError as exc:
        logger.warning(f"busca vetorial da Helô falhou; seguindo sem base técnica: {exc}")
        return []


async def _o_que_ela_diz(
    db: AsyncSession,
    ticket: Ticket,
    cliente: User,
    texto_do_cliente: str,
    falas: int,
) -> tuple[str, str | None]:
    """
    O texto da vez e o motivo da escalada, ou `None` se ela segue na conversa.

    Devolve SEMPRE alguma coisa.

    Nenhuma falha de infraestrutura daqui sobe, e nenhum caminho devolve vazio:
    o chamador já decidiu que ela vai falar, e "ela ia falar mas o serviço
    caiu" não é uma resposta que o cliente possa ver. Embedding fora, busca
    quebrada e modelo mudo têm todos o mesmo destino — escalada.

    Defeito de programação continua subindo, de propósito: engolir `TypeError`
    aqui transformaria bug em silêncio, e a Helô escalaria para sempre sem
    ninguém descobrir por quê.
    """
    # O pedido de humano vem ANTES do modelo, e por dois motivos que se somam:
    # ele funciona com o LLM fora do ar, e não se gasta uma chamada para
    # descobrir o que uma lista de substrings já disse.
    if quer_humano(texto_do_cliente):
        return monta_escalada(), MOTIVO_PEDIU_HUMANO

    # Teto de trocas: a última fala dela é uma despedida, não uma tentativa.
    if falas >= TROCAS_MAXIMAS:
        return monta_escalada(), MOTIVO_TETO_DE_TROCAS

    vetor = await embute_um(texto_do_cliente)
    trechos = await _busca_sem_derrubar(db, ticket, vetor) if vetor else []
    base = monta_base_tecnica(trechos)

    contexto = monta_prompt(
        await monta_cadastro(db, ticket, cliente),
        base,
        await monta_conversa(db, ticket, texto_do_cliente),
    )

    bruto = await responde_como_helo(SISTEMA, contexto)
    if not bruto or not bruto.strip():
        # Falha do LLM escala com mensagem neutra. O cliente não precisa saber
        # que uma IA caiu; ele precisa de um humano, e é isso que a escalada
        # entrega. Vale para timeout, chave inválida, serviço fora e resposta
        # vazia — todos indistinguíveis daqui, e todos com o mesmo destino.
        return monta_escalada(), MOTIVO_IA_MUDA

    resposta = le_resposta(bruto)
    if resposta.escalou:
        # O modelo pediu para escalar. O texto DELE vai para o cliente — ele
        # sabe por que está escalando e a frase já está no contexto da
        # conversa; trocar por `monta_escalada()` genérica soaria como se
        # ninguém tivesse lido o que o cliente escreveu.
        return resposta.texto or monta_escalada(), resposta.motivo or MOTIVO_SEM_MOTIVO

    return resposta.texto, None
