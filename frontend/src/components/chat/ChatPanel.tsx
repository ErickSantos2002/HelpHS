import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "../../lib/utils";
import {
  buildWsUrl,
  getChatMessages,
  suggestReply,
  summarizeConversation,
  type ChatMessage,
} from "../../services/chatService";

// ── Role label ────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  technician: "Técnico",
  client: "Cliente",
};

const ROLE_COLOR: Record<string, string> = {
  admin: "text-primary",
  technician: "text-info",
  client: "text-slate-400",
};

// ── ChatBubble ────────────────────────────────────────────────

function ChatBubble({ msg, isOwn }: { msg: ChatMessage; isOwn: boolean }) {
  const time = new Date(msg.created_at).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });

  if (msg.is_system) {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-slate-500 bg-background-elevated px-3 py-1 rounded-full italic">
          {msg.content}
        </span>
      </div>
    );
  }

  if (msg.is_ai) {
    return (
      <div className="flex gap-2 mb-3">
        <div className="w-7 h-7 rounded-full bg-purple-900 border border-purple-700 flex items-center justify-center shrink-0 text-xs font-bold text-purple-300">
          AI
        </div>
        <div className="max-w-[75%]">
          <p className="text-xs text-purple-400 mb-0.5">Assistente IA</p>
          <div className="rounded-xl rounded-tl-none bg-purple-950 border border-purple-800 px-3 py-2 text-sm text-slate-200 leading-relaxed">
            {msg.content}
          </div>
          <p className="text-xs text-slate-600 mt-0.5">{time}</p>
        </div>
      </div>
    );
  }

  if (isOwn) {
    return (
      <div className="flex flex-col items-end mb-3">
        <div className="max-w-[75%]">
          <div className="rounded-xl rounded-tr-none bg-primary/20 border border-primary/30 px-3 py-2 text-sm text-slate-100 leading-relaxed">
            {msg.content}
          </div>
          <p className="text-xs text-slate-600 mt-0.5 text-right">{time}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2 mb-3">
      {/* Avatar initial */}
      <div className="w-7 h-7 rounded-full bg-background-elevated border border-border flex items-center justify-center shrink-0 text-xs font-medium text-slate-300">
        {msg.sender_name.charAt(0).toUpperCase()}
      </div>
      <div className="max-w-[75%]">
        <p className="text-xs mb-0.5">
          <span className="text-slate-300 font-medium">{msg.sender_name}</span>
          {msg.sender_role && (
            <span
              className={cn(
                "ml-1.5",
                ROLE_COLOR[msg.sender_role] ?? "text-slate-500",
              )}
            >
              {ROLE_LABEL[msg.sender_role] ?? msg.sender_role}
            </span>
          )}
        </p>
        <div className="rounded-xl rounded-tl-none bg-background-elevated border border-border px-3 py-2 text-sm text-slate-200 leading-relaxed">
          {msg.content}
        </div>
        <p className="text-xs text-slate-600 mt-0.5">{time}</p>
      </div>
    </div>
  );
}

// ── WS status indicator ───────────────────────────────────────

type WsStatus = "connecting" | "connected" | "disconnected";

function StatusDot({ status }: { status: WsStatus }) {
  return (
    <span
      className={cn("inline-block w-2 h-2 rounded-full", {
        "bg-yellow-500 animate-pulse": status === "connecting",
        "bg-primary": status === "connected",
        "bg-slate-600": status === "disconnected",
      })}
      title={
        status === "connected"
          ? "Conectado"
          : status === "connecting"
            ? "Conectando…"
            : "Desconectado"
      }
    />
  );
}

// ── ChatPanel ─────────────────────────────────────────────────

interface ChatPanelProps {
  ticketId: string;
  currentUserId: string;
  currentUserRole?: string;
  savedSummary?: string | null;
}

export function ChatPanel({
  ticketId,
  currentUserId,
  currentUserRole,
  savedSummary,
}: ChatPanelProps) {
  const isStaff =
    currentUserRole === "admin" || currentUserRole === "technician";

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [summary, setSummary] = useState<string | null>(savedSummary ?? null);
  const [showSummary, setShowSummary] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load initial history via REST
  useEffect(() => {
    getChatMessages(ticketId, { limit: 100 })
      .then((res) => setMessages(res.items))
      .catch(() => setLoadError(true));
  }, [ticketId]);

  // WebSocket lifecycle
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setWsStatus("connecting");
    const ws = new WebSocket(buildWsUrl(ticketId));
    wsRef.current = ws;

    ws.onopen = () => setWsStatus("connected");

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data as string) as {
          type: string;
          data?: ChatMessage;
        };
        if (payload.type === "message" && payload.data) {
          setMessages((prev) => {
            // Deduplicate by id
            if (prev.some((m) => m.id === payload.data!.id)) return prev;
            return [...prev, payload.data!];
          });
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = (ev) => {
      setWsStatus("disconnected");
      // Auto-reconnect unless deliberately closed (code 1000) or auth error
      if (ev.code !== 1000 && ev.code !== 4001 && ev.code !== 4003) {
        reconnectTimer.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = () => {
      setWsStatus("disconnected");
    };
  }, [ticketId]);

  useEffect(() => {
    connect();
    return () => {
      reconnectTimer.current && clearTimeout(reconnectTimer.current);
      wsRef.current?.close(1000);
    };
  }, [connect]);

  function send() {
    const content = input.trim();
    if (!content || wsStatus !== "connected") return;
    setSending(true);
    try {
      wsRef.current?.send(JSON.stringify({ content }));
      setInput("");
      inputRef.current?.focus();
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  async function handleSuggest() {
    setSuggesting(true);
    try {
      const suggestion = await suggestReply(ticketId);
      setInput(suggestion);
      inputRef.current?.focus();
    } catch {
      // silently ignore — user can retry
    } finally {
      setSuggesting(false);
    }
  }

  async function handleSummarize() {
    setSummarizing(true);
    try {
      const result = await summarizeConversation(ticketId);
      setSummary(result);
      setShowSummary(true);
    } catch {
      // silently ignore — user can retry
    } finally {
      setSummarizing(false);
    }
  }

  return (
    <div className="rounded-xl bg-background-surface border border-border flex flex-col h-[480px]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <h2 className="text-sm font-semibold text-slate-300">Chat</h2>
        <div className="flex items-center gap-3">
          {isStaff && (
            <button
              onClick={
                summary ? () => setShowSummary((v) => !v) : handleSummarize
              }
              disabled={summarizing}
              className={cn(
                "flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors",
                "border border-slate-700 text-slate-400 hover:bg-background-elevated hover:text-slate-300",
                "disabled:opacity-40 disabled:cursor-not-allowed",
              )}
              title={
                summary
                  ? "Ver/ocultar resumo da conversa"
                  : "Gerar resumo da conversa com IA"
              }
            >
              {summarizing ? (
                <span className="inline-block w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin" />
              ) : (
                <svg
                  className="w-3 h-3"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              )}
              {summarizing ? "Resumindo…" : summary ? "Resumo" : "Resumir"}
            </button>
          )}
          <div className="flex items-center gap-1.5">
            <StatusDot status={wsStatus} />
            <span className="text-xs text-slate-500">
              {wsStatus === "connected"
                ? "ao vivo"
                : wsStatus === "connecting"
                  ? "conectando…"
                  : "desconectado"}
            </span>
          </div>
        </div>
      </div>

      {/* Summary panel */}
      {isStaff && showSummary && summary && (
        <div className="border-b border-border bg-background-elevated/50 px-4 py-3 shrink-0">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <p className="text-xs font-medium text-slate-400 mb-1">
                Resumo da conversa (IA)
              </p>
              <p className="text-xs text-slate-300 leading-relaxed">
                {summary}
              </p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                onClick={handleSummarize}
                disabled={summarizing}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-40"
                title="Regenerar resumo"
              >
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </button>
              <button
                onClick={() => setShowSummary(false)}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
                title="Fechar resumo"
              >
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-0">
        {loadError && (
          <p className="text-xs text-danger text-center py-4">
            Não foi possível carregar o histórico.
          </p>
        )}
        {!loadError && messages.length === 0 && (
          <p className="text-xs text-slate-500 text-center py-8">
            Nenhuma mensagem ainda. Seja o primeiro a escrever.
          </p>
        )}
        {messages.map((msg) => (
          <ChatBubble
            key={msg.id}
            msg={msg}
            isOwn={msg.sender_id === currentUserId}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border px-3 py-2.5 shrink-0">
        {isStaff && (
          <div className="mb-2">
            <button
              onClick={handleSuggest}
              disabled={suggesting || wsStatus === "disconnected"}
              className={cn(
                "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md transition-colors",
                "border border-purple-700 text-purple-400 hover:bg-purple-900/40",
                "disabled:opacity-40 disabled:cursor-not-allowed",
              )}
            >
              {suggesting ? (
                <>
                  <span className="inline-block w-3 h-3 border border-purple-400 border-t-transparent rounded-full animate-spin" />
                  Gerando…
                </>
              ) : (
                <>
                  <svg
                    className="w-3 h-3"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.347.346a3 3 0 01-1.595.835l-.468.094a2 2 0 01-2.362-1.174l-.101-.302a3 3 0 01.22-2.562l.345-.518"
                    />
                  </svg>
                  Sugerir resposta (IA)
                </>
              )}
            </button>
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            rows={1}
            className={cn(
              "flex-1 resize-none rounded-lg border bg-background-elevated px-3 py-2 text-sm text-slate-100",
              "placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent",
              "border-border hover:border-slate-500 transition-colors leading-relaxed",
              "max-h-28 overflow-y-auto",
            )}
            placeholder="Escreva uma mensagem… (Enter para enviar)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={wsStatus === "disconnected"}
          />
          <button
            onClick={send}
            disabled={!input.trim() || sending || wsStatus !== "connected"}
            className={cn(
              "shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              "bg-primary text-white hover:bg-primary/90",
              "disabled:opacity-40 disabled:cursor-not-allowed",
            )}
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
              />
            </svg>
          </button>
        </div>
        <p className="text-xs text-slate-600 mt-1 pl-1">
          Enter para enviar · Shift+Enter para nova linha
        </p>
      </div>
    </div>
  );
}
