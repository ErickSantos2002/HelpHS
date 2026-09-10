import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/chatService", () => ({
  buildWsUrl: (id: string) => `ws://teste/${id}`,
  getChatMessages: vi.fn(),
  improveMessage: vi.fn(),
  suggestReply: vi.fn(),
  summarizeConversation: vi.fn(),
}));

vi.mock("../../services/quickReplyService", () => ({
  listQuickReplies: vi.fn(),
  matchQuickReplies: () => [],
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { ChatPanel } from "../../components/chat/ChatPanel";
import type { ChatMessage } from "../../services/chatService";
import {
  getChatMessages,
  summarizeConversation,
} from "../../services/chatService";
import { listQuickReplies } from "../../services/quickReplyService";

/**
 * O aviso do ESLint em ChatPanel pede `onStatusChange` nas deps do useCallback
 * que cria `connect`. Atender ao pedido derruba o chat: o pai passa uma arrow
 * INLINE, então a prop muda de identidade a cada render dele; `connect` mudaria
 * junto, o efeito reexecutaria, o cleanup fecharia o socket e ele reconectaria.
 *
 * Estes testes existem para que a próxima pessoa que "consertar" o aviso veja o
 * estrago na hora, e não em produção. São duas metades:
 *
 *   1. o socket é construído UMA vez, por mais que o pai re-renderize;
 *   2. a mudança de status ainda chega ao pai depois desses re-renders — que é
 *      o que torna a closure velha inofensiva e justifica deixar a dep de fora.
 *
 * Sem a segunda, o teste 1 sozinho seria satisfeito por um componente que
 * simplesmente ignora o callback.
 */

const socketsConstruidos: SocketFalso[] = [];

/**
 * O `readyState` fica em CONNECTING e o `onopen` NUNCA dispara sozinho, de
 * propósito. O `connect` real começa com
 * `if (wsRef.current?.readyState === WebSocket.OPEN) return;` — se este falso
 * se declarasse aberto, esse atalho engoliria uma reexecução do efeito e o
 * teste ficaria verde mesmo com a dependência adicionada. Em CONNECTING, toda
 * reexecução vira um socket a mais e aparece na contagem.
 */
class SocketFalso {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readyState: number = SocketFalso.CONNECTING;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    socketsConstruidos.push(this);
  }

  close(code = 1000) {
    this.readyState = SocketFalso.CLOSED;
    this.onclose?.({ code });
  }

  send() {}
}

/** Cada render devolve uma arrow NOVA, igual ao TicketDetailPage:1437. */
const callbacksCriados: Array<(status: string) => void> = [];

function Pai({ marca }: { marca: number }) {
  const [ticket, setTicket] = useState<{ status: string } | null>({ status: "open" });

  const onStatusChange = (s: string) =>
    setTicket((prev) => (prev ? { ...prev, status: s } : prev));
  callbacksCriados.push(onStatusChange);

  return (
    <>
      <span data-testid="marca">{marca}</span>
      <span data-testid="status">{ticket?.status}</span>
      <ChatPanel ticketId="t-1" currentUserId="u-1" onStatusChange={onStatusChange} />
    </>
  );
}

async function rerenderizaOPai(vezes: number) {
  const { rerender } = render(<Pai marca={0} />);
  await act(async () => {});
  for (let i = 1; i <= vezes; i++) {
    rerender(<Pai marca={i} />);
    await act(async () => {});
  }
}

describe("ChatPanel — o pai re-renderiza, o WebSocket não reconecta", () => {
  beforeEach(() => {
    socketsConstruidos.length = 0;
    callbacksCriados.length = 0;
    vi.mocked(getChatMessages).mockResolvedValue({
      items: [],
    } as unknown as Awaited<ReturnType<typeof getChatMessages>>);
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal("WebSocket", SocketFalso);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("constrói o socket uma vez só, com o pai re-renderizando 5 vezes", async () => {
    await rerenderizaOPai(5);

    // A premissa do teste: o pai é mesmo hostil. Se alguém "consertar" o aviso
    // envolvendo o callback do pai num useCallback, esta linha avisa que o
    // cenário deixou de ser o que este teste queria exercitar.
    expect(callbacksCriados.length).toBeGreaterThanOrEqual(6);
    expect(new Set(callbacksCriados).size).toBe(callbacksCriados.length);

    expect(socketsConstruidos).toHaveLength(1);
  });

  it("a mudança de status ainda chega ao pai depois dos re-renders", async () => {
    await rerenderizaOPai(5);

    expect(screen.getByTestId("status")).toHaveTextContent("open");

    await act(async () => {
      socketsConstruidos[0].onmessage?.({
        data: JSON.stringify({ type: "status_update", data: { status: "resolved" } }),
      });
    });

    expect(screen.getByTestId("status")).toHaveTextContent("resolved");
  });
});

/**
 * ── O que o painel PROMETE ────────────────────────────────────────────
 *
 * Estes casos são da Fase 16, e nenhum deles olha classe. O happy-dom **não
 * aplica CSS**: um caso que afirmasse `toHaveClass("bg-tint-info")` passaria
 * com a classe presente e a bolha invisível, e um mutante que trocasse a classe
 * sobreviveria por um motivo que não tem nada a ver com o que o caso mede. O
 * que se mede aqui é o que a pessoa alcança — o texto que ela lê e o nome pelo
 * qual o controle se anuncia.
 *
 * Quatro deles existem por causa da **1.4.1**: quem não separa as cores precisa
 * que o autor da mensagem e o estado da conexão estejam ESCRITOS. A migração
 * trocou as tintas das três bolhas, e sem estes casos ela poderia ter trocado
 * junto o que sobra de informação quando a cor não chega.
 */

let sequencia = 0;

function mensagem(over: Partial<ChatMessage> = {}): ChatMessage {
  sequencia += 1;
  return {
    id: `m-${sequencia}`,
    ticket_id: "t-1",
    sender_id: "outra-pessoa",
    sender_name: "Bruno Lima",
    sender_role: "technician",
    content: "conteúdo",
    is_system: false,
    is_ai: false,
    read_at: null,
    created_at: "2026-09-08T12:00:00.000Z",
    ...over,
  };
}

async function montar({
  papel = "admin",
  historico = [],
  travado = false,
  falhaNoHistorico = false,
}: {
  papel?: string;
  historico?: ChatMessage[];
  travado?: boolean;
  falhaNoHistorico?: boolean;
} = {}) {
  if (falhaNoHistorico) {
    vi.mocked(getChatMessages).mockRejectedValue(new Error("500"));
  } else {
    vi.mocked(getChatMessages).mockResolvedValue({
      items: historico,
    } as unknown as Awaited<ReturnType<typeof getChatMessages>>);
  }

  render(
    <ChatPanel
      ticketId="t-1"
      currentUserId="eu"
      currentUserRole={papel}
      locked={travado}
    />,
  );
  await act(async () => {});
  return socketsConstruidos[0];
}

/** O falso fica em CONNECTING de propósito; abrir é passo explícito. */
async function abre(ws: SocketFalso) {
  await act(async () => {
    ws.readyState = SocketFalso.OPEN;
    ws.onopen?.();
  });
}

describe("ChatPanel — o que o painel promete", () => {
  beforeEach(() => {
    sequencia = 0;
    socketsConstruidos.length = 0;
    vi.mocked(listQuickReplies).mockResolvedValue([]);
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal("WebSocket", SocketFalso);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("o nome e o papel de quem escreveu ficam ESCRITOS", async () => {
    await montar({
      historico: [
        mensagem({ sender_name: "Bruno Lima", sender_role: "technician" }),
        mensagem({
          sender_id: "chefe",
          sender_name: "Ana Souza",
          sender_role: "admin",
        }),
      ],
    });

    expect(screen.getByText("Bruno Lima")).toBeInTheDocument();
    expect(screen.getByText("Ana Souza")).toBeInTheDocument();
    expect(screen.getByText("Técnico")).toBeInTheDocument();

    // "Administrador", e não "Admin". O rótulo vem do `lib/papel.ts`, e a
    // divergência era DESTA tela — as outras seis cópias já escreviam por
    // extenso. Muda texto na tela, e é o que o módulo existe para fazer.
    expect(screen.getByText("Administrador")).toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  });

  it("a bolha da IA diz quem falou, e não só de que cor é", async () => {
    await montar({
      historico: [
        mensagem({
          is_ai: true,
          sender_id: null,
          sender_name: "Helô",
          content: "Tente reiniciar o roteador.",
        }),
      ],
    });

    expect(screen.getByText("Assistente IA")).toBeInTheDocument();
    expect(screen.getByText("Tente reiniciar o roteador.")).toBeInTheDocument();
  });

  it("a mensagem do sistema não ganha autor — ela não é de ninguém", async () => {
    await montar({
      historico: [
        mensagem({
          is_system: true,
          sender_id: null,
          sender_name: "Sistema",
          sender_role: "",
          content: "Status alterado para Em andamento.",
        }),
      ],
    });

    expect(
      screen.getByText("Status alterado para Em andamento."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Sistema")).not.toBeInTheDocument();
  });

  it("o estado da conexão está em TEXTO, e não só no ponto colorido", async () => {
    const ws = await montar();

    expect(screen.getByText("conectando…")).toBeInTheDocument();
    await abre(ws);
    expect(screen.getByText("ao vivo")).toBeInTheDocument();
  });

  it("o botão de enviar tem nome acessível", async () => {
    // Ele era um `<svg>` dentro de um `<button>`, sem título nem rótulo: o
    // nome acessível era vazio e o leitor de tela anunciava só "botão".
    await montar();
    expect(
      screen.getByRole("button", { name: "Enviar mensagem" }),
    ).toBeInTheDocument();
  });

  it("enviar só libera com o socket aberto E com texto digitado", async () => {
    const ws = await montar();
    const botao = screen.getByRole("button", { name: "Enviar mensagem" });
    const campo = screen.getByRole("textbox");

    expect(botao).toBeDisabled();

    fireEvent.change(campo, { target: { value: "oi" } });
    expect(botao).toBeDisabled();

    await abre(ws);
    expect(botao).toBeEnabled();

    fireEvent.change(campo, { target: { value: "   " } });
    expect(botao).toBeDisabled();
  });

  it("quem não é da equipe não vê nenhuma ação de IA", async () => {
    await montar({ papel: "client" });

    expect(
      screen.queryByRole("button", { name: /Sugerir resposta/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Melhorar texto/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resumir" }),
    ).not.toBeInTheDocument();
  });

  it("a equipe vê as três ações de IA, cada uma com o próprio rótulo", async () => {
    await montar({ papel: "technician" });

    expect(
      screen.getByRole("button", { name: /Sugerir resposta \(IA\)/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Melhorar texto \(IA\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resumir" })).toBeInTheDocument();
  });

  it("chamado encerrado tira o campo, e diz por quê", async () => {
    await montar({ travado: true });

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Enviar mensagem" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/o chat está bloqueado/)).toBeInTheDocument();
  });

  it("histórico que não carrega vira aviso escrito", async () => {
    await montar({ falhaNoHistorico: true });

    expect(
      await screen.findByText("Não foi possível carregar o histórico."),
    ).toBeInTheDocument();
  });

  it("o resumo aparece, e os dois controles dele têm nome próprio", async () => {
    vi.mocked(summarizeConversation).mockResolvedValue(
      "Cliente sem internet desde ontem.",
    );
    await montar();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Resumir" }));
    });

    expect(
      screen.getByText("Cliente sem internet desde ontem."),
    ).toBeInTheDocument();
    // Gerado o resumo, o botão passa a oferecer o que já existe.
    expect(screen.getByRole("button", { name: "Resumo" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Regenerar resumo" }),
    ).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Fechar resumo" }));
    });

    await waitFor(() =>
      expect(
        screen.queryByText("Cliente sem internet desde ontem."),
      ).not.toBeInTheDocument(),
    );
  });
});
