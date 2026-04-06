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
  sla_response_breach: boolean;
  sla_resolve_breach: boolean;
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
