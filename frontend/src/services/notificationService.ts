import { api } from "./api";

export type NotificationType =
  | "ticket_created"
  | "ticket_assigned"
  | "ticket_updated"
  | "ticket_resolved"
  | "ticket_closed"
  | "sla_warning"
  | "sla_breached"
  | "chat_message"
  | "satisfaction_survey"
  | "system";

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  message: string;
  data: Record<string, unknown> | null;
  read: boolean;
  read_at: string | null;
  email_sent: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  unread: number;
  limit: number;
  offset: number;
}

export async function getNotifications(
  params: { limit?: number; offset?: number; unread_only?: boolean } = {},
): Promise<NotificationListResponse> {
  const p = new URLSearchParams();
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  if (params.unread_only) p.set("unread_only", "true");
  const { data } = await api.get<NotificationListResponse>(
    `/notifications?${p}`,
  );
  return data;
}

export async function markRead(id: string): Promise<Notification> {
  const { data } = await api.patch<Notification>(`/notifications/${id}/read`);
  return data;
}

export async function markAllRead(): Promise<void> {
  await api.patch("/notifications/read-all");
}

export async function deleteNotification(id: string): Promise<void> {
  await api.delete(`/notifications/${id}`);
}
