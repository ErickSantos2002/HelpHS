import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  getChatMessages,
  sendMessageWithLibraryFile,
  suggestReply,
  summarizeConversation,
  improveMessage,
  buildWsUrl,
  type ChatMessage,
} from "../../services/chatService";
import { api, tokenStorage } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  tokenStorage: {
    getAccess: vi.fn(),
    getRefresh: vi.fn(),
    set: vi.fn(),
    setAccess: vi.fn(),
    clear: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockGetAccess = vi.mocked(tokenStorage.getAccess);

const mensagem: ChatMessage = {
  id: "m1",
  ticket_id: "t1",
  sender_id: "u1",
  sender_name: "Rickelme David",
  sender_role: "admin",
  content: "Bom dia, já estou olhando o chamado.",
  is_system: false,
  // Sem anexo por padrão: é o caso comum, e a fixture o diz por escrito em
  // vez de omitir. O tipo passou a declarar os quatro campos quando o front
  // finalmente foi desenhar o anexo da biblioteca, e o `tsc -b` apontou esta
  // fixture na hora -- ela descrevia uma resposta que o servidor não manda
  // mais desde o PR #6.
  library_file_id: null,
  library_file_name: null,
  library_file_mime: null,
  library_file_size: null,
  is_ai: false,
  read_at: null,
  created_at: "2026-09-01T12:00:00Z",
};

/** Resposta padrão da listagem, no formato que o backend devolve. */
const pagina = { items: [mensagem], total: 1, limit: 50, offset: 0 };

beforeEach(() => {
  vi.clearAllMocks();
});

// ── getChatMessages ───────────────────────────────────────────

describe("getChatMessages", () => {
  it("busca as mensagens do chamado sem query quando não há parâmetro", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    const result = await getChatMessages("t1");

    expect(mockGet).toHaveBeenCalledWith("/tickets/t1/messages?");
    expect(result).toEqual(pagina);
  });

  it("devolve a página inteira, e não só os itens", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 137, limit: 20, offset: 40 },
    });

    const result = await getChatMessages("t1", { limit: 20, offset: 40 });

    expect(result.total).toBe(137);
    expect(result.limit).toBe(20);
    expect(result.offset).toBe(40);
    expect(result.items).toEqual([]);
  });

  it("monta a query com limit e offset na ordem em que são escritos", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getChatMessages("t1", { limit: 50, offset: 100 });

    expect(mockGet).toHaveBeenCalledWith("/tickets/t1/messages?limit=50&offset=100");
  });

  it("omite o parâmetro ausente em vez de mandar 'undefined'", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getChatMessages("t1", { offset: 20 });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toBe("/tickets/t1/messages?offset=20");
    expect(url).not.toContain("limit");
  });

  it("manda o zero, que é valor legítimo e não ausência", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getChatMessages("t1", { limit: 0, offset: 0 });

    expect(mockGet).toHaveBeenCalledWith("/tickets/t1/messages?limit=0&offset=0");
  });

  it("usa o id recebido para montar o caminho", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getChatMessages("9f2c-outro-chamado");

    expect(mockGet).toHaveBeenCalledWith("/tickets/9f2c-outro-chamado/messages?");
  });

  it("propaga o erro da API sem engolir", async () => {
    mockGet.mockRejectedValue(new Error("403 Forbidden"));

    await expect(getChatMessages("t1")).rejects.toThrow("403 Forbidden");
  });
});

// ── suggestReply ──────────────────────────────────────────────

describe("suggestReply", () => {
  it("chama POST em suggest-reply e devolve só o texto da sugestão", async () => {
    mockPost.mockResolvedValue({ data: { suggestion: "Sugiro reiniciar o serviço." } });

    const result = await suggestReply("t1");

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/suggest-reply");
    expect(result).toBe("Sugiro reiniciar o serviço.");
  });

  it("não manda corpo na requisição", async () => {
    mockPost.mockResolvedValue({ data: { suggestion: "ok" } });

    await suggestReply("t1");

    expect(mockPost.mock.calls[0]).toHaveLength(1);
  });

  it("propaga o erro quando a IA falha", async () => {
    mockPost.mockRejectedValue(new Error("503 IA indisponível"));

    await expect(suggestReply("t1")).rejects.toThrow("503 IA indisponível");
  });
});

// ── summarizeConversation ─────────────────────────────────────

describe("summarizeConversation", () => {
  it("chama POST em summarize e devolve só o resumo", async () => {
    mockPost.mockResolvedValue({ data: { summary: "Cliente sem acesso ao portal." } });

    const result = await summarizeConversation("t7");

    expect(mockPost).toHaveBeenCalledWith("/tickets/t7/summarize");
    expect(result).toBe("Cliente sem acesso ao portal.");
  });

  it("propaga o erro da API", async () => {
    mockPost.mockRejectedValue(new Error("500 Internal Server Error"));

    await expect(summarizeConversation("t7")).rejects.toThrow("500 Internal Server Error");
  });
});

// ── improveMessage ────────────────────────────────────────────

describe("improveMessage", () => {
  it("envia o rascunho no corpo e devolve o texto melhorado", async () => {
    mockPost.mockResolvedValue({ data: { improved: "Bom dia! Poderia confirmar o ramal?" } });

    const result = await improveMessage("t1", "confirma o ramal ai");

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/improve-message", {
      draft: "confirma o ramal ai",
    });
    expect(result).toBe("Bom dia! Poderia confirmar o ramal?");
  });

  it("envia o rascunho vazio como está, sem trocar por outra coisa", async () => {
    mockPost.mockResolvedValue({ data: { improved: "" } });

    const result = await improveMessage("t1", "");

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/improve-message", { draft: "" });
    expect(result).toBe("");
  });

  it("propaga o erro da API", async () => {
    mockPost.mockRejectedValue(new Error("422 Unprocessable Entity"));

    await expect(improveMessage("t1", "texto")).rejects.toThrow("422 Unprocessable Entity");
  });
});

// ── buildWsUrl ────────────────────────────────────────────────

describe("buildWsUrl", () => {
  const locationOriginal = Object.getOwnPropertyDescriptor(window, "location");

  /** Finge a origem da página, que é o que decide entre ws: e wss:. */
  function fingePagina(protocol: string, host: string) {
    Object.defineProperty(window, "location", {
      value: { protocol, host },
      writable: true,
      configurable: true,
    });
  }

  beforeEach(() => {
    mockGetAccess.mockReturnValue("tok-acesso");
    fingePagina("http:", "localhost:5173");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    if (locationOriginal) {
      Object.defineProperty(window, "location", locationOriginal);
    }
  });

  it("usa a origem da página quando a base da API é relativa", () => {
    expect(buildWsUrl("t1")).toBe(
      "ws://localhost:5173/api/v1/ws/tickets/t1?token=tok-acesso"
    );
  });

  it("sobe para wss quando a página está em https", () => {
    fingePagina("https:", "helphs.com.br");

    expect(buildWsUrl("t1")).toBe(
      "wss://helphs.com.br/api/v1/ws/tickets/t1?token=tok-acesso"
    );
  });

  it("ignora a origem da página quando VITE_API_URL é absoluta", () => {
    vi.stubEnv("VITE_API_URL", "http://api.interno:8001/api/v1");
    fingePagina("https:", "helphs.com.br");

    expect(buildWsUrl("t1")).toBe(
      "ws://api.interno:8001/api/v1/ws/tickets/t1?token=tok-acesso"
    );
  });

  it("traduz https da base absoluta para wss", () => {
    vi.stubEnv("VITE_API_URL", "https://api.helphs.com.br/api/v1");

    expect(buildWsUrl("t1")).toBe(
      "wss://api.helphs.com.br/api/v1/ws/tickets/t1?token=tok-acesso"
    );
  });

  it("troca só o começo da URL, não um 'http' no meio dela", () => {
    vi.stubEnv("VITE_API_URL", "https://api.helphs.com.br/http/v1");

    expect(buildWsUrl("t1")).toBe(
      "wss://api.helphs.com.br/http/v1/ws/tickets/t1?token=tok-acesso"
    );
  });

  it("manda token vazio quando não há sessão, em vez de 'null'", () => {
    mockGetAccess.mockReturnValue(null);

    expect(buildWsUrl("t1")).toBe("ws://localhost:5173/api/v1/ws/tickets/t1?token=");
  });

  it("escapa o token para não quebrar a query string", () => {
    mockGetAccess.mockReturnValue("a+b/c=d&e");

    expect(buildWsUrl("t1")).toBe(
      "ws://localhost:5173/api/v1/ws/tickets/t1?token=a%2Bb%2Fc%3Dd%26e"
    );
  });

  it("aponta para o chamado informado", () => {
    expect(buildWsUrl("9f2c-outro-chamado")).toContain("/ws/tickets/9f2c-outro-chamado?");
  });
});

describe("sendMessageWithLibraryFile", () => {
  /**
   * Por que este caminho existe ao lado do WebSocket, e o que estes casos
   * prendem: o manipulador do WS lê **só** `content` e descarta o resto do
   * payload. Um `library_file_id` mandado por lá sumiria em silêncio -- a
   * mensagem chegaria sem o anexo e ninguém veria erro nenhum.
   */
  it("manda o id do arquivo no corpo, junto do texto", async () => {
    mockPost.mockResolvedValue({ data: mensagem });

    await sendMessageWithLibraryFile("t1", "Segue o manual.", "lib-7");

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/messages", {
      content: "Segue o manual.",
      library_file_id: "lib-7",
    });
  });

  it("usa o chamado informado no caminho, e não um fixo", async () => {
    mockPost.mockResolvedValue({ data: mensagem });

    await sendMessageWithLibraryFile("outro-chamado", "oi", "lib-7");

    expect(mockPost.mock.calls[0][0]).toBe("/tickets/outro-chamado/messages");
  });

  it("devolve a mensagem que o servidor gravou, e não a que foi enviada", async () => {
    // O servidor preenche `library_file_name`, `_mime` e `_size` a partir do
    // item. Devolver o que foi mandado deixaria a bolha sem nome de arquivo.
    mockPost.mockResolvedValue({
      data: { ...mensagem, library_file_id: "lib-7", library_file_name: "manual.pdf" },
    });

    const gravada = await sendMessageWithLibraryFile("t1", "Segue.", "lib-7");

    expect(gravada.library_file_name).toBe("manual.pdf");
  });

  it("propaga o 422 do item interno sem engolir", async () => {
    // A recusa é da API, e a razão dela precisa chegar a quem anexou: o
    // técnico tem de entender por que aquele arquivo não pode ir.
    const recusa = Object.assign(new Error("422"), {
      response: { status: 422, data: { detail: "Este arquivo da biblioteca é de uso interno" } },
    });
    mockPost.mockRejectedValue(recusa);

    await expect(sendMessageWithLibraryFile("t1", "Segue.", "lib-7")).rejects.toBe(recusa);
  });
});
