import { api } from "./api";

export type AuditAction =
  | "create"
  | "update"
  | "delete"
  | "login"
  | "logout"
  | "export"
  | "assign"
  | "status_change"
  | "password_change"
  | "anonymize";

export interface AuditLog {
  id: string;
  user_id: string | null;
  action: AuditAction;
  entity_type: string;
  entity_id: string | null;
  old_data: Record<string, unknown> | null;
  new_data: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditFilters {
  action?: string;
  entity_type?: string;
  user_id?: string;
  date_from?: string;
  date_to?: string;
  offset?: number;
  limit?: number;
}

export async function getAuditLogs(
  filters: AuditFilters = {},
): Promise<AuditLogListResponse> {
  const params: Record<string, string | number> = {};
  if (filters.action) params.action = filters.action;
  if (filters.entity_type) params.entity_type = filters.entity_type;
  if (filters.user_id) params.user_id = filters.user_id;
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.offset !== undefined) params.offset = filters.offset;
  if (filters.limit !== undefined) params.limit = filters.limit;

  const { data } = await api.get<AuditLogListResponse>("/audit-logs", {
    params,
  });
  return data;
}
