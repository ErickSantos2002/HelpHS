import { api } from "./api";
import { tokenStorage } from "./api";

export interface ChatMessage {
  id: string;
  ticket_id: string;
  // Nulo quando quem falou nao foi gente: a Helo (is_ai) e as mensagens
  // automaticas do sistema. Comparar com o id do usuario logado continua
  // valendo — null nunca e igual a um id, entao a bolha nao vira "minha".
  sender_id: string | null;
  sender_name: string;
  sender_role: string;
  content: string;
  is_system: boolean;
  is_ai: boolean;
  read_at: string | null;
  created_at: string;

  // ── Anexo da biblioteca (PR #6) ────────────────────────────────
  //
  // O backend já mandava os quatro desde o merge, e este tipo não os declarava.
  // Omitir campo que chega é a mesma família do `nullh` da /sla-config, no
  // sentido contrário: lá o tipo afirmava um valor que podia faltar, aqui ele
  // esconde um que existe — e o que o tipo esconde a tela não desenha.
  //
  // ⚠️ O LINK NÃO VEM AQUI, de propósito: ele tem validade e sai do
  // `GET /library/{id}/download`, que confere a visibilidade na hora de
  // emitir. Guardar um link na mensagem entregaria um item interno a quem
  // abrisse a conversa depois de o item ter sido fechado.
  library_file_id: string | null;
  library_file_name: string | null;
  library_file_mime: string | null;
  library_file_size: number | null;
}

export interface ChatMessageListResponse {
  items: ChatMessage[];
  total: number;
  limit: number;
  offset: number;
}

export async function getChatMessages(
  ticketId: string,
  params: { limit?: number; offset?: number } = {}
): Promise<ChatMessageListResponse> {
  const p = new URLSearchParams();
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  const { data } = await api.get<ChatMessageListResponse>(`/tickets/${ticketId}/messages?${p}`);
  return data;
}

/**
 * Envia mensagem COM anexo da biblioteca, pelo REST.
 *
 * O texto puro continua saindo pelo WebSocket, e esta função não o substitui.
 * A separação não é gosto: o manipulador do WS lê **só** `content` e descarta o
 * resto do payload (`app/routers/chat.py`), então um `library_file_id` mandado
 * por lá sumiria em silêncio — a mensagem chegaria sem o anexo e ninguém veria
 * erro. Conferido na fonte antes de escolher o caminho.
 *
 * E o REST é onde mora a guarda: `ensure_pode_anexar_no_chat` recusa item
 * INTERNO com 422 e razão escrita, antes de gravar. A recusa é da API porque
 * ela é chamada por outros clientes além desta tela.
 *
 * Não é preciso reinserir a mensagem na lista: o próprio `POST` transmite pelo
 * WebSocket (`manager.broadcast`), então ela volta pelo mesmo caminho das
 * outras — inclusive para quem a enviou.
 *
 * ⚠️ `content` é obrigatório no schema (`min_length=1`). Não existe mensagem só
 * com arquivo, e quem chamar daqui com texto vazio recebe 422 de validação.
 */
export async function sendMessageWithLibraryFile(
  ticketId: string,
  content: string,
  libraryFileId: string,
): Promise<ChatMessage> {
  const { data } = await api.post<ChatMessage>(`/tickets/${ticketId}/messages`, {
    content,
    library_file_id: libraryFileId,
  });
  return data;
}

export async function suggestReply(ticketId: string): Promise<string> {
  const { data } = await api.post<{ suggestion: string }>(`/tickets/${ticketId}/suggest-reply`);
  return data.suggestion;
}

export async function summarizeConversation(ticketId: string): Promise<string> {
  const { data } = await api.post<{ summary: string }>(`/tickets/${ticketId}/summarize`);
  return data.summary;
}

export async function improveMessage(ticketId: string, draft: string): Promise<string> {
  const { data } = await api.post<{ improved: string }>(`/tickets/${ticketId}/improve-message`, {
    draft,
  });
  return data.improved;
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
