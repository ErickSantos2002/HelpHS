import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { QuickReplyPicker } from "./QuickReplyPicker";
import {
  listQuickReplies,
  matchQuickReplies,
  type QuickReply,
} from "../../services/quickReplyService";
import { cn } from "../../lib/utils";
import { Avatar, Button, Icon } from "../ui";
import { rotuloDePapel, varianteDePapel } from "../../lib/papel";
import { TOM_STATUS, type VarianteStatus } from "../../lib/status";
import {
  buildWsUrl,
  getChatMessages,
  improveMessage,
  suggestReply,
  summarizeConversation,
  type ChatMessage,
} from "../../services/chatService";

// ── ChatBubble ────────────────────────────────────────────────

/**
 * O papel de quem fala saiu daqui.
 *
 * Havia um `ROLE_LABEL` e um `ROLE_COLOR` locais — a sétima e a oitava cópia da
 * mesma tabela. O rótulo divergia ("Admin" contra "Administrador", que é o que
 * as outras seis escrevem) e a cor era a cor CHEIA da rampa como texto:
 * `text-info` sobre a superfície branca dá 3,68:1, abaixo do piso de 4,5:1.
 * Agora vem de `lib/papel.ts`, e o tom vem do `TOM_STATUS` — o mesmo
 * vocabulário de variante em que o `varianteDePapel` fala.
 *
 * ── Como as três bolhas se distinguem ─────────────────────────────────
 *
 * Por LADO, por COR e por AUTOR ESCRITO. A cor sozinha não satisfaz a 1.4.1, e
 * é por isso que a bolha da IA mantém "Assistente IA" acima do texto e a de
 * outra pessoa mantém o nome.
 *
 * ⚠️ A bolha de quem está escrevendo (`isOwn`) **não tem autor escrito**, e
 * nunca teve: ela se distingue por ficar à direita e pintar a tinta primária —
 * cor e posição, exatamente o que a 1.4.1 não aceita sozinho. O conserto ("Você"
 * no texto, ou em `sr-only`) muda o que a árvore de acessibilidade fala, e essa
 * decisão não é desta migração. Relatado, não consertado aqui.
 */
function ChatBubble({ msg, isOwn }: { msg: ChatMessage; isOwn: boolean }) {
  const time = new Date(msg.created_at).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });

  if (msg.is_system) {
    return (
      <div className="flex justify-center my-2">
        {/* `conteudo-muted` e não `conteudo-faint`: faint sobre a superfície
            elevada é o par de 2,34:1, e este aviso é texto que se lê. */}
        <span className="text-xs text-conteudo-muted bg-surface-elevated px-3 py-1 rounded-full italic">
          {msg.content}
        </span>
      </div>
    );
  }

  if (msg.is_ai) {
    return (
      <div className="flex gap-2 mb-3">
        {/* Não é `Avatar`: o primitivo deriva a cor do NOME de quem fala, e a
            IA não é uma pessoa entre outras — a marca dela é fixa, e "AI" não
            são iniciais de nome nenhum. */}
        <div className="w-8 h-8 rounded-full bg-tint-info border border-info/30 flex items-center justify-center shrink-0 text-xs font-bold text-on-tint-info">
          AI
        </div>
        <div className="max-w-[75%]">
          <p className="text-xs text-on-tint-info mb-0.5">Assistente IA</p>
          <div className="rounded-xl rounded-tl-none bg-tint-info border border-info/30 px-3 py-2 text-sm text-conteudo leading-relaxed break-words whitespace-pre-wrap">
            {msg.content}
          </div>
          <p className="text-xs text-conteudo-muted mt-0.5">{time}</p>
        </div>
      </div>
    );
  }

  if (isOwn) {
    return (
      <div className="flex flex-col items-end mb-3">
        <div className="max-w-[75%]">
          {/* `bg-tint-primary` e não `bg-primary/20`: a tinta já carrega os 15%
              no próprio token, e é o mesmo fundo que o `Badge` primário pinta.
              A borda continua com o modificador porque ela é a cor cheia da
              rampa a 30% — não é token com alfa (regra (a) do D8-a). */}
          <div className="rounded-xl rounded-tr-none bg-tint-primary border border-primary/30 px-3 py-2 text-sm text-conteudo leading-relaxed break-words whitespace-pre-wrap">
            {msg.content}
          </div>
          <p className="text-xs text-conteudo-muted mt-0.5 text-right">
            {time}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2 mb-3">
      <Avatar name={msg.sender_name} size="sm" />
      <div className="max-w-[75%]">
        <p className="text-xs mb-0.5">
          <span className="text-conteudo font-medium">{msg.sender_name}</span>
          {msg.sender_role && (
            <span
              className={cn(
                "ml-1.5",
                TOM_STATUS[varianteDePapel(msg.sender_role)].texto,
              )}
            >
              {rotuloDePapel(msg.sender_role)}
            </span>
          )}
        </p>
        <div className="rounded-xl rounded-tl-none bg-surface-elevated border border-borda px-3 py-2 text-sm text-conteudo leading-relaxed break-words whitespace-pre-wrap">
          {msg.content}
        </div>
        <p className="text-xs text-conteudo-muted mt-0.5">{time}</p>
      </div>
    </div>
  );
}

// ── WS status indicator ───────────────────────────────────────

type WsStatus = "connecting" | "connected" | "disconnected";

/**
 * O ponto do socket, no vocabulário de variante do resto do sistema.
 *
 * `bg-yellow-500` não é token nenhum — amarelo não existe no pacote, e o degrau
 * de aviso que passa 3:1 contra as três superfícies é `--fill-warning`. As três
 * classes saem do `TOM_STATUS`, que é onde elas já estão escritas por extenso.
 *
 * A tabela é **local de propósito**: estado de WebSocket tem um consumidor só e
 * não é vocabulário compartilhado — é a mesma regra pela qual `lib/papel.ts`
 * existe e `lib/auditoria.ts` não. O que ela não faz é repetir as classes:
 * mapeia para a variante e deixa o tom no módulo.
 *
 * O ponto pode ser só cor porque o texto ao lado diz a mesma coisa; sem ele,
 * seria 1.4.1.
 */
const VARIANTE_DO_SOCKET: Record<WsStatus, VarianteStatus> = {
  connecting: "warning",
  connected: "primary",
  disconnected: "muted",
};

const TITULO_DO_SOCKET: Record<WsStatus, string> = {
  connecting: "Conectando…",
  connected: "Conectado",
  disconnected: "Desconectado",
};

function StatusDot({ status }: { status: WsStatus }) {
  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full",
        TOM_STATUS[VARIANTE_DO_SOCKET[status]].ponto,
        status === "connecting" && "animate-pulse",
      )}
      title={TITULO_DO_SOCKET[status]}
    />
  );
}

// ── ChatPanel ─────────────────────────────────────────────────

interface ChatPanelProps {
  ticketId: string;
  currentUserId: string;
  currentUserRole?: string;
  savedSummary?: string | null;
  locked?: boolean;
  onStatusChange?: (status: string) => void;
}

export function ChatPanel({
  ticketId,
  currentUserId,
  currentUserRole,
  savedSummary,
  locked = false,
  onStatusChange,
}: ChatPanelProps) {
  const isStaff =
    currentUserRole === "admin" || currentUserRole === "technician";

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [improving, setImproving] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [summary, setSummary] = useState<string | null>(savedSummary ?? null);
  const [showSummary, setShowSummary] = useState(false);
  const [quickReplies, setQuickReplies] = useState<QuickReply[]>([]);
  const [activeReply, setActiveReply] = useState(0);
  const [pickerDismissed, setPickerDismissed] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea as content grows (max ~8 lines)
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [input]);

  // Load initial history via REST
  useEffect(() => {
    getChatMessages(ticketId, { limit: 100 })
      .then((res) => setMessages(res.items))
      .catch(() => setLoadError(true));
  }, [ticketId]);

  // Respostas rápidas — só a equipe usa o menu "/"
  useEffect(() => {
    if (!isStaff) return;
    listQuickReplies()
      .then(setQuickReplies)
      .catch(() => setQuickReplies([]));
  }, [isStaff]);

  // O menu abre quando a mensagem começa com "/" e ainda não foi dispensado
  const quickReplyQuery =
    isStaff && input.startsWith("/") && !pickerDismissed ? input.slice(1) : null;
  const filteredReplies =
    quickReplyQuery === null ? [] : matchQuickReplies(quickReplies, quickReplyQuery);
  const pickerOpen = filteredReplies.length > 0;

  // Volta para o topo da lista a cada tecla digitada
  useEffect(() => {
    setActiveReply(0);
  }, [input]);

  // Digitar "/" de novo reabre o menu depois de um Esc
  useEffect(() => {
    if (!input.startsWith("/")) setPickerDismissed(false);
  }, [input]);

  function applyQuickReply(reply: QuickReply) {
    setInput(reply.content);
    setActiveReply(0);
    setPickerDismissed(true);
    inputRef.current?.focus();
  }

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
          detail?: string;
          data?: ChatMessage & { status?: string };
        };
        if (payload.type === "error" && payload.detail) {
          toast.error(payload.detail);
          return;
        }
        if (payload.type === "status_update" && payload.data?.status) {
          onStatusChange?.(payload.data.status);
        }
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
    // `onStatusChange` fica FORA das deps de propósito, e não por esquecimento.
    //
    // O pai (TicketDetailPage) passa uma arrow inline, então a prop ganha
    // identidade nova a cada render dele. Se ela entrar aqui, `connect` muda de
    // identidade junto, o efeito abaixo reexecuta, o cleanup fecha o socket e
    // ele reconecta: tempestade de reconexão no chat a cada tecla digitada na
    // página do chamado.
    //
    // A closure velha é inofensiva porque o único uso da prop é chamar
    // `setTicket` com atualização funcional: o setter do `useState` tem
    // identidade estável por garantia do React, e o updater recebe `prev`
    // fresco. Não há dado velho a capturar.
    //
    // ⚠️ Esta isenção vale enquanto essa condição valer. Se algum dia o
    // `onStatusChange` do pai passar a LER uma variável do render (props,
    // estado, contexto) em vez de só chamar um setter estável, a closure velha
    // passa a mentir e o certo aí é o padrão de ref para o callback mais
    // recente — não incluir a dep. `ChatPanel.test.tsx` prende as duas metades:
    // que o socket é construído uma vez só, e que a mudança de status ainda
    // chega ao pai depois de vários re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
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
    // Com o menu aberto as teclas pertencem a ele — Enter insere em vez de enviar
    if (pickerOpen) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveReply((i) => (i + 1) % filteredReplies.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveReply((i) => (i - 1 + filteredReplies.length) % filteredReplies.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        applyQuickReply(filteredReplies[activeReply]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setPickerDismissed(true);
        return;
      }
    }

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

  async function handleImprove() {
    const draft = input.trim();
    if (!draft) return;
    setImproving(true);
    try {
      const improved = await improveMessage(ticketId, draft);
      setInput(improved);
      inputRef.current?.focus();
    } catch {
      // silently ignore — user keeps original draft
    } finally {
      setImproving(false);
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
    <div className="rounded-xl bg-surface border border-borda flex flex-col lg:h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-borda shrink-0">
        <h2 className="text-sm font-semibold text-conteudo-heading">Chat</h2>
        <div className="flex items-center gap-3">
          {isStaff && (
            <Button
              variant="secondary"
              size="sm"
              onClick={
                summary ? () => setShowSummary((v) => !v) : handleSummarize
              }
              // O `Button` desabilita junto com o anel de carregando, então
              // `loading` sozinho faz o que o `disabled={summarizing}` fazia.
              loading={summarizing}
              icon={<Icon name="document" size={14} strokeWidth={2} />}
              title={
                summary
                  ? "Ver/ocultar resumo da conversa"
                  : "Gerar resumo da conversa com IA"
              }
            >
              {summarizing ? "Resumindo…" : summary ? "Resumo" : "Resumir"}
            </Button>
          )}
          <div className="flex items-center gap-1.5">
            <StatusDot status={wsStatus} />
            <span className="text-xs text-conteudo-muted">
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
        <div className="border-b border-borda bg-surface-elevated/50 px-4 py-3 shrink-0">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <p className="text-xs font-medium text-conteudo-muted mb-1">
                Resumo da conversa (IA)
              </p>
              <p className="text-xs text-conteudo leading-relaxed">{summary}</p>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {/* Os dois só têm ícone, e o nome acessível vem do `title` — que
                  é o que a árvore de acessibilidade lê quando não há texto
                  dentro do controle. Já era assim antes da migração. */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleSummarize}
                loading={summarizing}
                icon={<Icon name="refresh" size={14} strokeWidth={2} />}
                title="Regenerar resumo"
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowSummary(false)}
                icon={<Icon name="close" size={14} strokeWidth={2} />}
                title="Fechar resumo"
              />
            </div>
          </div>
        </div>
      )}

      {/* Message list */}
      <div className="h-[320px] overflow-y-auto lg:h-auto lg:flex-1 lg:overflow-y-auto px-4 py-3 space-y-0">
        {loadError && (
          // `text-on-tint-danger` e não `text-danger`: o degrau cheio da rampa
          // como cor de TEXTO dá 3,76:1 sobre a superfície. O par da tinta dá
          // 6,5:1 no claro e 7,39:1 no escuro, e inverte sozinho por tema.
          <p className="text-xs text-on-tint-danger text-center py-4">
            Não foi possível carregar o histórico.
          </p>
        )}
        {!loadError && messages.length === 0 && (
          <p className="text-xs text-conteudo-muted text-center py-8">
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
      <div className="border-t border-borda px-3 py-2.5 shrink-0">
        {locked ? (
          <p className="text-xs text-conteudo-muted text-center py-2 italic">
            Este ticket foi encerrado — o chat está bloqueado.
          </p>
        ) : (
          <>
            {isStaff && (
              <div className="mb-2 flex flex-wrap gap-2">
                {/* As duas ações de IA eram ROXAS — `purple-*`, que não é do
                    pacote: não existe `--color-purple-*` nem `--color-pink-*`.
                    Não há tom de "isto é IA" no sistema, e inventar um é
                    emenda. As duas caíram no degrau secundário e, com isso,
                    perderam a cor que as separava do resto da barra. O ícone e
                    o rótulo continuam dizendo que é IA. Relatado ao operador. */}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleSuggest}
                  loading={suggesting}
                  disabled={wsStatus === "disconnected"}
                  icon={<Icon name="lightbulb" size={14} strokeWidth={2} />}
                >
                  {suggesting ? "Gerando…" : "Sugerir resposta (IA)"}
                </Button>

                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleImprove}
                  loading={improving}
                  disabled={!input.trim() || wsStatus === "disconnected"}
                  icon={<Icon name="edit" size={14} strokeWidth={2} />}
                  title="Melhorar gramática e clareza do texto digitado"
                >
                  {improving ? "Melhorando…" : "Melhorar texto (IA)"}
                </Button>
              </div>
            )}
            <div className="relative flex items-center gap-2">
              {pickerOpen && (
                <QuickReplyPicker
                  replies={filteredReplies}
                  activeIndex={activeReply}
                  onSelect={applyQuickReply}
                  onHover={setActiveReply}
                />
              )}
              <textarea
                ref={inputRef}
                rows={1}
                className={cn(
                  "flex-1 resize-none rounded-lg border bg-surface-elevated px-3 py-2 text-sm text-conteudo",
                  "placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent",
                  // O hover da borda SAIU, pelo mesmo motivo pelo qual saiu do
                  // primitivo `Textarea`: a E7 levou a borda de repouso do
                  // controle a `--border-control`, que é slate-500 — exatamente
                  // onde o `hover:border-slate-500` chegava. O campo está sempre
                  // na força que antes dependia do ponteiro, e a 1.4.11 pede 3:1
                  // para o limite do componente, não 3:1 sob o mouse.
                  "border-borda-control transition-colors leading-relaxed",
                  "overflow-hidden",
                )}
                placeholder={
                  isStaff
                    ? "Escreva uma mensagem… (/ para respostas rápidas)"
                    : "Escreva uma mensagem… (Enter para enviar)"
                }
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={wsStatus === "disconnected"}
              />
              {/* Era `bg-primary` com `text-white`: 3,83:1 nos DOIS temas,
                  porque o degrau 500 é absoluto e não inverte. O `Button`
                  primário usa o par `--action` / `--text-on-primary`, que é
                  branco no claro e navy no escuro.

                  O `aria-label` é acréscimo: o botão só tinha um `<svg>`
                  dentro, sem título nem rótulo, então o nome acessível era
                  VAZIO — um leitor de tela anunciava "botão" e mais nada. */}
              <Button
                variant="primary"
                className="shrink-0"
                aria-label="Enviar mensagem"
                onClick={send}
                disabled={!input.trim() || sending || wsStatus !== "connected"}
                icon={<Icon name="send" size={16} strokeWidth={2} />}
              />
            </div>
            <p className="text-xs text-conteudo-muted mt-1 pl-1">
              Enter para enviar · Shift+Enter para nova linha
            </p>
          </>
        )}
      </div>
    </div>
  );
}
