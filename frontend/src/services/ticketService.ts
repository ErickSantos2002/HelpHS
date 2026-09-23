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
