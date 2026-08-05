import { api } from "./api";

export interface QuickReply {
  id: string;
  shortcut: string;
  title: string;
  content: string;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuickReplyPayload {
  shortcut: string;
  title: string;
  content: string;
  is_active?: boolean;
}

export async function listQuickReplies(): Promise<QuickReply[]> {
  const { data } = await api.get<{ items: QuickReply[]; total: number }>("/quick-replies");
  return data.items;
}

export async function createQuickReply(payload: QuickReplyPayload): Promise<QuickReply> {
  const { data } = await api.post<QuickReply>("/quick-replies", payload);
  return data;
}

export async function updateQuickReply(
  id: string,
  payload: Partial<QuickReplyPayload>,
): Promise<QuickReply> {
  const { data } = await api.patch<QuickReply>(`/quick-replies/${id}`, payload);
  return data;
}

export async function deleteQuickReply(id: string): Promise<void> {
  await api.delete(`/quick-replies/${id}`);
}

/** Remove acentos e caixa para a busca do menu "/" ser tolerante. */
function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/**
 * Filtra as respostas para o menu do chat: só as ativas, casando por atalho ou
 * por título. Query vazia (apenas a "/" digitada) devolve todas as ativas.
 */
export function matchQuickReplies(replies: QuickReply[], query: string): QuickReply[] {
  const active = replies.filter((r) => r.is_active);
  const term = normalize(query.trim());
  if (!term) return active;
  return active.filter(
    (r) => normalize(r.shortcut).includes(term) || normalize(r.title).includes(term),
  );
}
