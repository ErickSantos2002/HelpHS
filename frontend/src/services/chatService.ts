import { api } from "./api";
import { tokenStorage } from "./api";

export interface ChatMessage {
  id: string;
  ticket_id: string;
  sender_id: string;
  sender_name: string;
  sender_role: string;
  content: string;
  is_system: boolean;
  is_ai: boolean;
  read_at: string | null;
  created_at: string;
}

export interface ChatMessageListResponse {
  items: ChatMessage[];
  total: number;
  limit: number;
  offset: number;
}

export async function getChatMessages(
  ticketId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<ChatMessageListResponse> {
  const p = new URLSearchParams();
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  const { data } = await api.get<ChatMessageListResponse>(
    `/tickets/${ticketId}/messages?${p}`,
  );
  return data;
}

export async function suggestReply(ticketId: string): Promise<string> {
  const { data } = await api.post<{ suggestion: string }>(
    `/tickets/${ticketId}/suggest-reply`,
  );
  return data.suggestion;
}

export async function summarizeConversation(ticketId: string): Promise<string> {
  const { data } = await api.post<{ summary: string }>(
    `/tickets/${ticketId}/summarize`,
  );
  return data.summary;
}

export function buildWsUrl(ticketId: string): string {
  const token = tokenStorage.getAccess() ?? "";
  const apiBase = import.meta.env.VITE_API_URL ?? "/api/v1";

  let wsBase: string;
  if (apiBase.startsWith("http")) {
    wsBase = apiBase.replace(/^http/, "ws");
  } else {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    wsBase = `${proto}//${window.location.host}${apiBase}`;
  }

  return `${wsBase}/ws/tickets/${ticketId}?token=${encodeURIComponent(token)}`;
}
