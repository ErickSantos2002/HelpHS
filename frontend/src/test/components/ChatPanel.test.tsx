import { act, render, screen } from "@testing-library/react";
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
import { getChatMessages } from "../../services/chatService";

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
