import { api } from "./api";

export interface Ticket {
  id: string;
  protocol: string;
  title: string;
  status:
    | "open"
    | "in_progress"
    | "awaiting_client"
    | "awaiting_technical"
    | "resolved"
    | "closed"
    | "cancelled";
  priority: "critical" | "high" | "medium" | "low";
  category: string;
  creator_id: string;
  assignee_id: string | null;
  created_at: string;
  updated_at: string;
  sla_response_due_at: string | null;
  sla_resolve_due_at: string | null;
  sla_response_breach: boolean;
  sla_resolve_breach: boolean;
  product_id: string | null;
  equipment_id: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TicketHistory {
  id: string;
  ticket_id: string;
  user_id: string;
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

export async function getTicketHistory(
  id: string,
): Promise<TicketHistoryListResponse> {
  const { data } = await api.get<TicketHistoryListResponse>(
    `/tickets/${id}/history?limit=100`,
  );
  return data;
}

export async function updateTicketStatus(
  id: string,
  status: string,
  comment?: string,
): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}/status`, {
    status,
    comment,
  });
  return data;
}

export async function assignTicket(
  id: string,
  assignee_id: string | null,
): Promise<Ticket> {
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
}

export interface TicketFilters {
  status?: string;
  priority?: string;
  category?: string;
  assignee_id?: string;
  creator_id?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface TicketCreatePayload {
  title: string;
  description: string;
  priority: "critical" | "high" | "medium" | "low";
  category: string;
  product_id?: string | null;
  equipment_id?: string | null;
}

export interface TicketUpdatePayload {
  title?: string;
  description?: string;
  priority?: "critical" | "high" | "medium" | "low";
  category?: string;
  product_id?: string | null;
  equipment_id?: string | null;
}

export async function createTicket(
  payload: TicketCreatePayload,
): Promise<Ticket> {
  const { data } = await api.post<Ticket>("/tickets", payload);
  return data;
}

export async function updateTicket(
  id: string,
  payload: TicketUpdatePayload,
): Promise<Ticket> {
  const { data } = await api.patch<Ticket>(`/tickets/${id}`, payload);
  return data;
}

export async function getTicket(id: string): Promise<Ticket> {
  const { data } = await api.get<Ticket>(`/tickets/${id}`);
  return data;
}

export async function getTickets(
  filters: TicketFilters = {},
): Promise<TicketListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.category) params.set("category", filters.category);
  if (filters.assignee_id) params.set("assignee_id", filters.assignee_id);
  if (filters.creator_id) params.set("creator_id", filters.creator_id);
  if (filters.search) params.set("search", filters.search);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined)
    params.set("offset", String(filters.offset));

  const { data } = await api.get<TicketListResponse>(
    `/tickets?${params.toString()}`,
  );
  return data;
}
