import { api } from "./api";
import type { TicketPriority } from "../lib/prioridade";
import type { Expediente } from "../lib/tempoUtil";
import type { Tag } from "./tagService";

/** Equipamento como ele aparece dentro do chamado — não é a ficha completa. */
export interface TicketEquipment {
  id: string;
  name: string;
  serial_number: string | null;
  product_id: string | null;
}

export interface Ticket {
  id: string;
  protocol: string;
  title: string;
  description: string;
  status:
    | "open"
    | "in_progress"
    | "awaiting_client"
    | "awaiting_technical"
    | "resolved"
    | "closed"
    | "cancelled";
  /** Nulo ate a triagem: o chamado nasce sem prioridade e quem a define e a
   *  equipe, pelo `updateTicketPriority`. */
  priority: "critical" | "high" | "medium" | "low" | null;
  category: string;
  creator_id: string;
  assignee_id: string | null;
  created_at: string;
  updated_at: string;
  // A IA pode atuar neste chamado. Vale para a Helô e para a classificação
  // automática — desligado, nenhuma delas olha para ele.
  ai_enabled: boolean;
  /** O prazo CARIMBADO. Para contar tempo, use `sla_*_vence_em`. */
  sla_response_due_at: string | null;
  sla_resolve_due_at: string | null;
  /**
   * O prazo EFETIVO — o carimbado mais a pausa acumulada. E o mesmo instante
   * que o backend compara para decidir violacao, entao a tela que mostra este
   * nao pode discordar da regra.
   */
  sla_response_vence_em: string | null;
  sla_resolve_vence_em: string | null;
  /** Minutos UTEIS que faltavam quando a resposta foi montada. */
  sla_response_restante_min: number | null;
  sla_resolve_restante_min: number | null;
  /** O tamanho do prazo em minutos uteis — denominador da barra de progresso. */
  sla_response_total_min: number | null;
  sla_resolve_total_min: number | null;
  /** Total ja concedido em extensoes, em minutos uteis. Zero = sem extensao. */
  sla_resolve_extension_total_min: number;
  /**
   * So no chamado avulso. Na LISTAGEM ele vem uma vez no topo da resposta, e
   * nao repetido em cada item.
   */
  expediente: Expediente | null;
  sla_response_breach: boolean;
  sla_resolve_breach: boolean;
  sla_first_response: string | null;
  product_id: string | null;
  equipments: TicketEquipment[];
  closed_at: string | null;
  resolved_at: string | null;
  auto_closed: boolean;
  reopened_at: string | null;
  reopen_count: number;
  /** Até quando o chamado ainda aceita reabertura (calculado pelo backend). */
  reopen_deadline: string | null;
  assignee_name: string | null;
  product_name: string | null;
  technician_notes: string | null;
  ai_classification: string | null;
  ai_confidence: number | null;
  ai_summary: string | null;
  ai_conversation_summary: string | null;
  client_observation: string | null;
  resolution_note: string | null;
  tags: Tag[];
}

export interface TicketHistory {
  id: string;
  ticket_id: string;
  /** null quando quem agiu foi o próprio sistema (fechamento automático). */
  user_id: string | null;
  user_name: string | null;
  field: string;
  old_value: string | null;
  new_value: string | null;
  comment: string | null;
  created_at: string;
}

export interface TicketHistoryListResponse {
  items: TicketHistory[];
  total: number;
  limit: number;
  offset: number;
}

export async function getTicketHistory(id: string): Promise<TicketHistoryListResponse> {
  const { data } = await api.get<TicketHistoryListResponse>(`/tickets/${id}/history?limit=100`);
  return data;
}

export async function updateTicketStatus(
  id: string,
  status: string,
  comment?: string,
  sla_breach_justification?: string,
): Promise<Ticket> {
  // A justificativa só vai quando existe: o backend a exige para resolver
  // fora do prazo, e sem ela o corpo fica como sempre foi.
  const { data } = await api.patch<Ticket>(`/tickets/${id}/status`, {
    status,
    comment,
    ...(sla_breach_justification ? { sla_breach_justification } : {}),
  });
  return data;
}

export async function toggleTicketAi(id: string, enabled: boolean): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}/ai`, { enabled });
  return data;
}

export async function assignTicket(id: string, assignee_id: string | null): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}/assign`, {
    assignee_id,
  });
  return data;
}

export interface TicketListResponse {
  items: Ticket[];
  total: number;
  limit: number;
  offset: number;
  /** O relogio do servidor, uma vez para a pagina inteira. */
  expediente: Expediente | null;
}

export type SortBy = "created_at" | "updated_at" | "priority" | "sla_resolve_due_at";
export type SortDir = "asc" | "desc";

export interface TicketFilters {
  status?: string;
  priority?: string;
  category?: string;
  assignee_id?: string;
  tag_id?: string;
  creator_id?: string;
  search?: string;
  limit?: number;
  offset?: number;
  sort_by?: SortBy;
  sort_dir?: SortDir;
}

export interface TicketCreatePayload {
  title: string;
  description: string;
  category: string;
  product_id?: string | null;
  equipment_ids?: string[];
  client_observation?: string | null;
}

export interface TicketUpdatePayload {
  title?: string;
  description?: string;
  category?: string;
  product_id?: string | null;
  /** Omitir mantém os equipamentos atuais; lista vazia desvincula todos. */
  equipment_ids?: string[];
  technician_notes?: string | null;
}

export async function createTicket(payload: TicketCreatePayload): Promise<Ticket> {
  const { data } = await api.post<Ticket>("/tickets", payload);
  return data;
}

export async function updateTicket(id: string, payload: TicketUpdatePayload): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}`, payload);
  return data;
}

/**
 * A triagem: define ou troca a prioridade do chamado.
 *
 * Endpoint proprio, e nao o `updateTicket` generico, por dois motivos. O
 * primeiro e de permissao: o PATCH generico e a porta de todos os campos do
 * chamado, e dar a chave dela ao tecnico para que ele possa triar entregaria
 * junto o titulo, a categoria e o produto. O segundo e de regra: so este
 * caminho recalcula o SLA do nivel novo -- gravar a prioridade por fora
 * deixaria um chamado critico com o prazo de quando era baixo.
 */
/** Os cinco prazos que se pode conceder. A lista e fechada no backend. */
export type DiasDeExtensao = 1 | 3 | 5 | 15 | 30;

export interface SlaExtensionPreview {
  days: number;
  business_minutes: number;
  prazo_atual: string | null;
  novo_prazo: string | null;
}

/**
 * O prazo que a concessao produziria, SEM conceder.
 *
 * Existe para o modal mostrar "de ... para ..." sem recalcular prazo na tela:
 * dia util, jornada e feriado sao do motor, e um `add_business_days` em
 * TypeScript seria a segunda verdade que a entrega do relogio eliminou.
 */
export async function previewSlaExtension(
  ticketId: string,
  days: DiasDeExtensao
): Promise<SlaExtensionPreview> {
  const { data } = await api.get<SlaExtensionPreview>(
    `/tickets/${ticketId}/sla/extend/preview`,
    { params: { days } }
  );
  return data;
}

/**
 * Concede a extensao. POST porque cada concessao e um EVENTO auditavel, e
 * pode acontecer mais de uma vez.
 */
export async function extendSla(
  ticketId: string,
  days: DiasDeExtensao,
  justification: string
): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/tickets/${ticketId}/sla/extend`, {
    days,
    justification,
  });
  return data;
}

export async function updateTicketPriority(
  ticketId: string,
  priority: TicketPriority
): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(
    `/tickets/${ticketId}/priority`,
    { priority }
  );
  return data;
}

export async function updateClientObservation(
  id: string,
  client_observation: string | null
): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}/observation`, {
    client_observation,
  });
  return data;
}

export async function resolveTicket(
  id: string,
  resolution_note: string,
  sla_breach_justification?: string,
): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/tickets/${id}/resolve`, {
    resolution_note,
    ...(sla_breach_justification ? { sla_breach_justification } : {}),
  });
  return data;
}

export async function reopenTicket(id: string, reason: string): Promise<Ticket> {
  const { data } = await api.post<Ticket>(`/tickets/${id}/reopen`, { reason });
  return data;
}

export async function getTicket(id: string): Promise<Ticket> {
  const { data } = await api.get<Ticket>(`/tickets/${id}`);
  return data;
}

export interface TicketNote {
  id: string;
  ticket_id: string;
  author_id: string;
  author_name: string;
  content: string;
  created_at: string;
}

export async function listTicketNotes(ticketId: string): Promise<TicketNote[]> {
  const { data } = await api.get<TicketNote[]>(`/tickets/${ticketId}/notes`);
  return data;
}

export async function createTicketNote(ticketId: string, content: string): Promise<TicketNote> {
  const { data } = await api.post<TicketNote>(`/tickets/${ticketId}/notes`, { content });
  return data;
}

export async function deleteTicketNote(ticketId: string, noteId: string): Promise<void> {
  await api.delete(`/tickets/${ticketId}/notes/${noteId}`);
}

export async function getTickets(filters: TicketFilters = {}): Promise<TicketListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.category) params.set("category", filters.category);
  if (filters.assignee_id) params.set("assignee_id", filters.assignee_id);
  if (filters.tag_id) params.set("tag_id", filters.tag_id);
  if (filters.creator_id) params.set("creator_id", filters.creator_id);
  if (filters.search) params.set("search", filters.search);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.sort_dir) params.set("sort_dir", filters.sort_dir);

  const { data } = await api.get<TicketListResponse>(`/tickets?${params.toString()}`);
  return data;
}

// ── Telefonia ─────────────────────────────────────────────────

/**
 * Desfecho da TENTATIVA de ligação, como o backend o conta.
 *
 * Não é "o telefone tocou": é o que sabemos sobre o efeito externo. Os dois
 * primeiros são estados de passagem e não deveriam chegar ao navegador — a
 * rota só responde depois que a tentativa alcançou um desfecho —, mas estão
 * declarados porque o backend pode persisti-los e um dia devolvê-los.
 */
export type TicketCallCreationStatus =
  | "pending"
  | "dispatching"
  | "confirmed"
  | "rejected"
  | "unavailable"
  | "indeterminate";

/**
 * A resposta pública da tentativa — três campos, e nada mais.
 *
 * Não existe aqui `provider_call_id`, telefone, `caller`, `called`,
 * `extension`, metadata nem corpo do fornecedor: o backend não os devolve, e
 * declarar campo que não chega convidaria alguém a lê-lo.
 */
export interface TicketCall {
  id: string;
  creation_status: TicketCallCreationStatus;
  created_at: string;
}

/**
 * Registra uma tentativa de ligação para o cliente do chamado.
 *
 * O corpo é `{}` de propósito, e o backend recusa qualquer campo extra com
 * 422. Quem liga, para quem, de qual ramal e em que grafia é decidido lá
 * dentro, no instante da ação — o navegador não escolhe nada disso.
 */
export async function createTicketCall(id: string): Promise<TicketCall> {
  const { data } = await api.post<TicketCall>(`/tickets/${id}/calls`, {});
  return data;
}
