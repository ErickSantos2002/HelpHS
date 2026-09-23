"""
Pydantic v2 schemas for Ticket endpoints.
"""

import enum
import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.models import TicketCategory, TicketPriority, TicketStatus
from app.schemas.base import AppBaseModel
from app.schemas.tag import TagResponse

# Um chamado sobre a frota inteira de um cliente ainda é um chamado só; o teto
# existe para o campo não virar depósito de equipamento sem relação com o caso.
MAX_EQUIPMENTS_PER_TICKET = 20


class TicketCreate(AppBaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    # Sem `priority`: o chamado nasce sem prioridade e quem a define é a
    # triagem. O campo não é apenas ignorado por política — ele não existe
    # aqui, então o cliente que monta o POST à mão não tem onde escrever.
    category: TicketCategory = TicketCategory.general
    product_id: uuid.UUID | None = None
    equipment_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=MAX_EQUIPMENTS_PER_TICKET
    )
    client_observation: str | None = Field(default=None, max_length=2000)


class TicketUpdate(AppBaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    # Sem `priority`: prioridade tem um caminho só, o
    # `PATCH /tickets/{id}/priority`. Por aqui ela seria gravada sem recalcular
    # o SLA, e o chamado ficaria crítico com o prazo de quando era baixo.
    category: TicketCategory | None = None
    product_id: uuid.UUID | None = None
    # None = não mexe nos equipamentos; lista vazia = desvincula todos
    equipment_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=MAX_EQUIPMENTS_PER_TICKET
    )
    technician_notes: str | None = None


class InterruptorDaIA(AppBaseModel):
    """Liga ou desliga a IA — num chamado ou num cliente.

    Corpo com um campo só, e um endpoint próprio, em vez de mais um campo no
    `TicketUpdate`: aquele PATCH deixa o técnico mexer apenas em
    `technician_notes`, e o interruptor é justamente dele — é quem entra na
    conversa que quer a Helô calada dali em diante.
    """

    enabled: bool


class TicketStatusUpdate(AppBaseModel):
    status: TicketStatus
    comment: str | None = Field(default=None, max_length=1000)
    # Obrigatória quando o chamado é resolvido FORA do prazo — a regra vive
    # na API, não aqui: só ela conhece o prazo do chamado, e um schema não
    # tem como saber se este chamado específico estourou. Aqui o campo é
    # opcional porque resolver dentro do prazo não exige nada.
    sla_breach_justification: str | None = Field(default=None, max_length=2000)


class TicketPriorityUpdate(AppBaseModel):
    """A triagem. Só a prioridade, e ela é obrigatória.

    Não aceita nulo de propósito: "sem prioridade" é o estado de quem nunca
    foi triado, não uma escolha que alguém faz. Devolver um chamado para a
    fila de triagem seria outra decisão, e ela não foi tomada.
    """

    priority: TicketPriority


class DiasDeExtensao(int, enum.Enum):
    """Os cinco prazos que se pode conceder. A lista e fechada AQUI.

    Enum de inteiros, e nao `Literal[1, 3, ...]`, por um motivo medido: o
    `Literal` de int NAO converte a string que chega numa query string, entao o
    mesmo tipo recusaria `?days=3` no preview e aceitaria `{"days": 3}` no
    corpo. Com o enum, uma definicao so serve aos dois -- e quem montar a
    requisicao na unha recebe 422 antes de qualquer codigo do router rodar,
    sem um `if dias not in (...)` para alguem esquecer de atualizar.
    """

    um = 1
    tres = 3
    cinco = 5
    quinze = 15
    trinta = 30


class SlaExtensionRequest(AppBaseModel):
    """Uma concessao de prazo de resolucao.

    A justificativa e PUBLICA -- foi escrita para o cliente ler, e aparece na
    Atividade dele e na notificacao. Mesmo teto das outras justificativas do
    projeto.
    """

    days: DiasDeExtensao
    justification: str = Field(..., min_length=1, max_length=2000)


class SlaExtensionPreview(AppBaseModel):
    """O que o modal mostra antes de confirmar.

    Existe para a tela nao recalcular prazo: dia util, jornada e feriado sao do
    motor, e um `add_business_days` em TypeScript seria a segunda verdade que
    a entrega do relogio acabou de eliminar.
    """

    days: int
    business_minutes: int
    prazo_atual: datetime | None
    novo_prazo: datetime | None


class TicketAssign(AppBaseModel):
    assignee_id: uuid.UUID | None = None


class TicketObservationUpdate(AppBaseModel):
    client_observation: str | None = Field(default=None, max_length=2000)


class TicketResolve(AppBaseModel):
    resolution_note: str = Field(..., min_length=1, max_length=5000)
    # Obrigatória quando o chamado é resolvido FORA do prazo — a regra vive
    # na API, não aqui: só ela conhece o prazo do chamado, e um schema não
    # tem como saber se este chamado específico estourou. Aqui o campo é
    # opcional porque resolver dentro do prazo não exige nada.
    sla_breach_justification: str | None = Field(default=None, max_length=2000)


class TicketReopen(AppBaseModel):
    # O motivo é obrigatório: quem for atender de novo precisa saber o que
    # continuou errado, e a nota de resolução original fica no chamado.
    reason: str = Field(..., min_length=5, max_length=2000)


class ExpedienteInfo(AppBaseModel):
    """O estado do relogio de SLA no SERVIDOR, para a tela nao ter calendario.

    A tela precisa saber tres coisas para contar prazo sem saber o que e
    feriado: que horas sao no servidor, se o relogio corre agora, e quando esse
    estado muda. Com isso ela desconta um minuto por minuto enquanto `aberto` e
    CONGELA na `proxima_virada` -- sem jornada, sem fim de semana e sem a
    tabela de feriados do `feriados.py` duplicada em TypeScript.

    O `agora` tambem tira o relogio da maquina de quem olha da conta: era
    `Date.now()` do navegador contra um prazo do servidor, e qualquer desvio de
    relogio aparecia como minutos a mais ou a menos no contador.

    O `fuso` viaja junto porque "Vence em 24/09/2026 as 12:11" so faz sentido
    no fuso em que a jornada e definida. Vem do motor (`FUSO_DA_JORNADA`), e
    nao de um literal do frontend: a regra mora num lugar so.
    """

    agora: datetime
    aberto: bool
    proxima_virada: datetime
    fuso: str


class TicketEquipmentBrief(AppBaseModel):
    """O necessário para exibir o equipamento no chamado, sem a ficha inteira."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    serial_number: str | None = None
    product_id: uuid.UUID | None = None


class TicketResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    protocol: str
    title: str
    description: str
    status: TicketStatus
    # A tela precisa saber o estado para desenhar o botão certo.
    ai_enabled: bool = True
    # Nulo enquanto ninguém triou. A tela mostra "Sem prioridade", e não um
    # valor de mentira.
    priority: TicketPriority | None
    category: TicketCategory
    creator_id: uuid.UUID
    assignee_id: uuid.UUID | None
    product_id: uuid.UUID | None
    equipments: list[TicketEquipmentBrief] = []
    sla_response_due_at: datetime | None
    sla_resolve_due_at: datetime | None
    sla_response_breach: bool
    sla_resolve_breach: bool
    # Quando alguém da equipe falou com o cliente pela primeira vez. É o que
    # deixa o front parar o relógio de resposta em vez de adivinhar pela flag
    # de violação, que só é recalculada em escrita e por isso é velha.
    sla_first_response: datetime | None = None
    # ── O que a tela precisa para contar prazo em horas ÚTEIS ──────────
    #
    # `*_due_at` acima continua sendo o prazo CARIMBADO, intocado. Os dois
    # campos abaixo sao o prazo EFETIVO -- com a pausa acumulada somada --, que
    # e o instante que o `check_breaches` de fato compara. A tela mostra este,
    # e por isso nao pode mais discordar da regra de violacao.
    sla_response_vence_em: datetime | None = None
    sla_resolve_vence_em: datetime | None = None
    # Minutos UTEIS que faltam no instante em que a resposta foi montada. Nao e
    # `vence_em - agora`: essa subtracao corrida foi o defeito que motivou tudo
    # isto, porque contava a noite e o fim de semana como prazo correndo.
    sla_response_restante_min: int | None = None
    sla_resolve_restante_min: int | None = None
    # O tamanho do prazo em minutos UTEIS, da abertura ate o vencimento
    # efetivo. E o denominador da barra de progresso da lista, que hoje calcula
    # `(agora - abertura) / (vence - abertura)` em tempo corrido e por isso
    # enche sozinha durante a noite e o fim de semana.
    sla_response_total_min: int | None = None
    sla_resolve_total_min: int | None = None
    # Total ja concedido em extensoes, em minutos uteis. A lateral mostra
    # "SLA estendido - +N dias uteis"; o cliente ve tambem.
    sla_resolve_extension_total_min: int = 0
    # So no chamado avulso. Na LISTAGEM ele vem uma vez no topo, e nao repetido
    # em cada item: e estado do servidor, nao do chamado.
    expediente: ExpedienteInfo | None = None
    closed_at: datetime | None
    resolved_at: datetime | None = None
    auto_closed: bool = False
    reopened_at: datetime | None = None
    reopen_count: int = 0
    # Até quando este chamado ainda aceita reabertura. Vem calculado do backend
    # para que o frontend não precise repetir a conta de dias úteis.
    reopen_deadline: datetime | None = None
    created_at: datetime
    updated_at: datetime
    assignee_name: str | None = None
    product_name: str | None = None
    technician_notes: str | None = None
    ai_classification: str | None = None
    ai_confidence: float | None = None
    ai_summary: str | None = None
    ai_conversation_summary: str | None = None
    client_observation: str | None = None
    resolution_note: str | None = None
    tags: list[TagResponse] = []


class TicketListResponse(AppBaseModel):
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int
    # Uma vez so, aqui: os itens vem com `expediente = None`. O relogio e o
    # mesmo para os cinquenta chamados da pagina, e repeti-lo em cada um seria
    # carregar cinquenta copias do mesmo instante.
    expediente: ExpedienteInfo | None = None


class TicketHistoryResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    user_id: uuid.UUID | None = None  # NULL = ação do sistema
    user_name: str | None = None
    field: str
    old_value: str | None
    new_value: str | None
    comment: str | None
    created_at: datetime


class TicketHistoryListResponse(AppBaseModel):
    items: list[TicketHistoryResponse]
    total: int
    limit: int
    offset: int


class TicketNoteCreate(AppBaseModel):
    content: str = Field(..., min_length=1)


class TicketNoteResponse(AppBaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    content: str
    created_at: datetime
