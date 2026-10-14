import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getTickets,
  getTicket,
  createTicket,
  updateTicket,
  updateTicketStatus,
  assignTicket,
  getTicketHistory,
  reopenTicket,
  resolveTicket,
  updateTicketPriority,
  createTicketCall,
} from "../../services/ticketService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);

const ticket = {
  id: "t1",
  protocol: "HS-2026-0001",
  title: "Problema no sistema",
  description: "Detalhes",
  status: "open",
  priority: "medium",
  category: "software",
  creator_id: "u1",
  assignee_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  sla_response_due_at: null,
  sla_resolve_due_at: null,
  sla_response_breach: false,
  sla_resolve_breach: false,
  product_id: null,
  equipment_id: null,
  closed_at: null,
  ai_classification: null,
  ai_confidence: null,
  ai_summary: null,
  ai_conversation_summary: null,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getTickets", () => {
  it("calls GET /tickets with no filters", async () => {
    mockGet.mockResolvedValue({
      data: { items: [ticket], total: 1, limit: 20, offset: 0 },
    });

    const result = await getTickets();

    expect(mockGet).toHaveBeenCalledWith("/tickets?");
    expect(result.items).toHaveLength(1);
    expect(result.total).toBe(1);
  });

  it("appends status and priority filters to the URL", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getTickets({ status: "open", priority: "high" });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("status=open");
    expect(url).toContain("priority=high");
  });

  it("appends search, sort and pagination params", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 10, offset: 10 },
    });

    await getTickets({
      search: "erro",
      limit: 10,
      offset: 10,
      sort_by: "created_at",
      sort_dir: "desc",
    });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("search=erro");
    expect(url).toContain("limit=10");
    expect(url).toContain("offset=10");
    expect(url).toContain("sort_by=created_at");
    expect(url).toContain("sort_dir=desc");
  });
});

describe("getTicket", () => {
  it("calls GET /tickets/:id", async () => {
    mockGet.mockResolvedValue({ data: ticket });

    const result = await getTicket("t1");

    expect(mockGet).toHaveBeenCalledWith("/tickets/t1");
    expect(result.id).toBe("t1");
  });
});

describe("createTicket", () => {
  it("posts to /tickets and returns the created ticket", async () => {
    mockPost.mockResolvedValue({ data: ticket });

    const result = await createTicket({
      title: "Problema no sistema",
      description: "Detalhes",
      category: "software",
    });

    expect(mockPost).toHaveBeenCalledWith("/tickets", {
      title: "Problema no sistema",
      description: "Detalhes",
      category: "software",
    });
    expect(result.protocol).toBe("HS-2026-0001");
  });

  it("a abertura não leva prioridade no corpo", async () => {
    // `toHaveBeenCalledWith` acima já é exato, mas ele cai por "objeto
    // diferente" se qualquer campo mudar. Este diz POR QUE cairia — e é o que
    // alguém lê quando pensa em pôr o campo de volta.
    mockPost.mockResolvedValue({ data: ticket });

    await createTicket({
      title: "Problema no sistema",
      description: "Detalhes",
      category: "software",
    });

    const [, corpo] = mockPost.mock.calls[0];
    expect(corpo).not.toHaveProperty("priority");
  });
});

describe("updateTicketPriority", () => {
  it("patches /tickets/:id/priority — e não o PATCH genérico", async () => {
    mockPatch.mockResolvedValue({ data: { ...ticket, priority: "critical" } });

    const result = await updateTicketPriority("t1", "critical");

    expect(mockPatch).toHaveBeenCalledWith("/tickets/t1/priority", {
      priority: "critical",
    });
    expect(result.priority).toBe("critical");
  });
});

describe("updateTicket", () => {
  it("patches /tickets/:id with the payload", async () => {
    mockPatch.mockResolvedValue({ data: { ...ticket, title: "Novo título" } });

    const result = await updateTicket("t1", { title: "Novo título" });

    expect(mockPatch).toHaveBeenCalledWith("/tickets/t1", {
      title: "Novo título",
    });
    expect(result.title).toBe("Novo título");
  });
});

describe("updateTicketStatus", () => {
  it("patches /tickets/:id/status with status and optional comment", async () => {
    mockPatch.mockResolvedValue({ data: { ...ticket, status: "in_progress" } });

    await updateTicketStatus("t1", "in_progress", "Iniciando atendimento");

    expect(mockPatch).toHaveBeenCalledWith("/tickets/t1/status", {
      status: "in_progress",
      comment: "Iniciando atendimento",
    });
  });

  it("sends undefined comment when not provided", async () => {
    mockPatch.mockResolvedValue({ data: ticket });

    await updateTicketStatus("t1", "resolved");

    expect(mockPatch).toHaveBeenCalledWith("/tickets/t1/status", {
      status: "resolved",
      comment: undefined,
    });
  });
});

describe("assignTicket", () => {
  it("patches /tickets/:id/assign with assignee_id", async () => {
    mockPatch.mockResolvedValue({ data: { ...ticket, assignee_id: "u2" } });

    await assignTicket("t1", "u2");

    expect(mockPatch).toHaveBeenCalledWith("/tickets/t1/assign", {
      assignee_id: "u2",
    });
  });

  it("accepts null to unassign", async () => {
    mockPatch.mockResolvedValue({ data: ticket });

    await assignTicket("t1", null);

    expect(mockPatch).toHaveBeenCalledWith("/tickets/t1/assign", {
      assignee_id: null,
    });
  });
});

describe("getTicketHistory", () => {
  /**
   * Um backend falso com `total` linhas em ordem crescente, que responde às
   * páginas como o real (`offset`/`limit`, teto de 200 por página).
   */
  function historicoCom(total: number) {
    const todas = Array.from({ length: total }, (_, i) => ({
      id: `h${i}`,
      created_at: new Date(Date.UTC(2026, 9, 1) + i * 60_000).toISOString(),
    }));
    mockGet.mockImplementation(async (url: string) => {
      const q = new URLSearchParams(url.split("?")[1]);
      const limit = Number(q.get("limit"));
      const offset = Number(q.get("offset") ?? 0);
      expect(limit).toBeLessThanOrEqual(200);
      return { data: { items: todas.slice(offset, offset + limit), total, limit, offset } };
    });
    return todas;
  }

  it("um chamado comum é uma requisição só", async () => {
    historicoCom(30);

    const res = await getTicketHistory("t1");

    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith("/tickets/t1/history?limit=200&offset=0");
    expect(res.items).toHaveLength(30);
  });

  it("com mais de 100 eventos, os mais novos continuam presentes e em ordem", async () => {
    // Era `limit=100` numa lista crescente: do 101º em diante, sumiam — e são
    // justamente os mais novos, como o evento do anexo que acabou de entrar.
    const todas = historicoCom(450);

    const res = await getTicketHistory("t1");

    expect(res.items).toHaveLength(450);
    expect(res.items[res.items.length - 1].id).toBe(todas[449].id);
    expect(res.items.map((h) => h.id)).toEqual(todas.map((h) => h.id));
    expect(res.total).toBe(450);
  });

  it("acima do teto, fica com os mais recentes, ainda em ordem crescente", async () => {
    const todas = historicoCom(1500);

    const res = await getTicketHistory("t1");

    expect(res.items).toHaveLength(1000);
    expect(res.items[0].id).toBe(todas[500].id);
    expect(res.items[res.items.length - 1].id).toBe(todas[1499].id);
    const datas = res.items.map((h) => h.created_at);
    expect([...datas].sort()).toEqual(datas);
  });

  function offsetsPedidos(): number[] {
    return mockGet.mock.calls.map(([url]) =>
      Number(new URLSearchParams(String(url).split("?")[1]).get("offset")),
    );
  }

  it("pede exatamente as páginas necessárias — nenhuma vazia além do total", async () => {
    historicoCom(450);
    await getTicketHistory("t1");
    expect(offsetsPedidos()).toEqual([0, 200, 400]);

    mockGet.mockClear();
    historicoCom(400); // múltiplo exato da página: não há terceira página
    await getTicketHistory("t1");
    expect(offsetsPedidos()).toEqual([0, 200]);

    mockGet.mockClear();
    historicoCom(1500); // acima do teto: a 1ª página e a janela dos 1000 recentes
    await getTicketHistory("t1");
    expect(offsetsPedidos()).toEqual([0, 500, 700, 900, 1100, 1300]);
  });

  it("falha numa página adicional faz a leitura inteira falhar, como antes", async () => {
    // A política de erro é a de sempre: a tela recebe a rejeição e trata como
    // tratava a requisição única. Devolver só um pedaço esconderia o buraco.
    historicoCom(450);
    const real = mockGet.getMockImplementation()!;
    mockGet.mockImplementation(async (url: string) => {
      if (url.includes("offset=200")) throw new Error("falha na página 2");
      return real(url);
    });

    await expect(getTicketHistory("t1")).rejects.toThrow("falha na página 2");
  });

  it("linha repetida entre páginas não aparece duas vezes", async () => {
    // Paginação por offset: se uma linha entrar entre duas requisições, a
    // última da página anterior volta no começo da seguinte.
    const todas = historicoCom(250);
    const real = mockGet.getMockImplementation()!;
    mockGet.mockImplementation(async (url: string) => {
      const r = (await real(url)) as { data: { items: unknown[] } };
      if (url.includes("offset=200")) r.data.items = [todas[199], ...r.data.items];
      return r;
    });

    const res = await getTicketHistory("t1");

    expect(res.items).toHaveLength(250);
    expect(new Set(res.items.map((h) => h.id)).size).toBe(250);
  });
});

describe("equipamentos do chamado", () => {
  it("envia a lista de equipamentos ao abrir o chamado", async () => {
    mockPost.mockResolvedValue({ data: ticket });

    await createTicket({
      title: "Três aparelhos sem conexão",
      description: "Nenhum deles conecta",
      category: "hardware",
      product_id: "p1",
      equipment_ids: ["e1", "e2", "e3"],
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/tickets",
      expect.objectContaining({ equipment_ids: ["e1", "e2", "e3"] }),
    );
  });

  it("lista vazia desvincula todos os equipamentos na edição", async () => {
    mockPatch.mockResolvedValue({ data: ticket });

    await updateTicket("t1", { equipment_ids: [] });

    expect(mockPatch).toHaveBeenCalledWith("/tickets/t1", { equipment_ids: [] });
  });
});

describe("resolveTicket", () => {
  it("exige a nota de resolução no corpo da requisição", async () => {
    mockPost.mockResolvedValue({ data: { ...ticket, status: "resolved" } });

    await resolveTicket("t1", "Placa substituída.");

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/resolve", {
      resolution_note: "Placa substituída.",
    });
  });
});

describe("justificativa de SLA violado no corpo", () => {
  // O backend exige `sla_breach_justification` para resolver chamado fora do
  // prazo. Quando ela não existe, o corpo tem de ficar como sempre foi: uma
  // chave `undefined` a mais é invisível para o `toHaveBeenCalledWith`, e por
  // isso os casos de ausência olham a chave, e não a igualdade.
  it("resolveTicket leva a justificativa quando ela existe", async () => {
    mockPost.mockResolvedValue({ data: { ...ticket, status: "resolved" } });

    await resolveTicket("t1", "Placa substituída.", "Peça importada atrasou.");

    expect(mockPost).toHaveBeenLastCalledWith("/tickets/t1/resolve", {
      resolution_note: "Placa substituída.",
      sla_breach_justification: "Peça importada atrasou.",
    });
  });

  it("sem justificativa, o corpo do resolve não ganha a chave", async () => {
    mockPost.mockResolvedValue({ data: { ...ticket, status: "resolved" } });

    await resolveTicket("t1", "Placa substituída.");

    expect(mockPost.mock.lastCall?.[1]).not.toHaveProperty("sla_breach_justification");
  });

  it("updateTicketStatus leva a justificativa quando ela existe", async () => {
    mockPatch.mockResolvedValue({ data: ticket });

    await updateTicketStatus("t1", "resolved", undefined, "Peça importada atrasou.");

    expect(mockPatch).toHaveBeenLastCalledWith("/tickets/t1/status", {
      status: "resolved",
      comment: undefined,
      sla_breach_justification: "Peça importada atrasou.",
    });
  });

  it("sem justificativa, o corpo do status não ganha a chave", async () => {
    mockPatch.mockResolvedValue({ data: ticket });

    await updateTicketStatus("t1", "in_progress", "Iniciando atendimento");

    expect(mockPatch.mock.lastCall?.[1]).not.toHaveProperty("sla_breach_justification");
  });
});

describe("reopenTicket", () => {
  it("envia o motivo da reabertura para o endpoint do chamado", async () => {
    mockPost.mockResolvedValue({ data: { ...ticket, status: "in_progress" } });

    const reaberto = await reopenTicket("t1", "O aparelho voltou a travar.");

    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/reopen", {
      reason: "O aparelho voltou a travar.",
    });
    expect(reaberto.status).toBe("in_progress");
  });

  it("propaga o erro quando o prazo já venceu, para a tela mostrar o motivo", async () => {
    mockPost.mockRejectedValue({
      response: { status: 409, data: { detail: "O prazo de 5 dias úteis..." } },
    });

    await expect(reopenTicket("t1", "Voltou o problema")).rejects.toMatchObject({
      response: { status: 409 },
    });
  });
});

describe("createTicketCall", () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  it("manda o corpo VAZIO — o navegador nao escolhe para quem se liga", async () => {
    // O contrato do backend e `extra="forbid"` com zero campos. Qualquer
    // `phone`, `called`, `caller`, `extension` ou `metadata` daqui viraria
    // 422. Este caso e a prova de que nao mandamos nenhum deles.
    mockPost.mockResolvedValue({
      data: { id: "c1", creation_status: "confirmed", created_at: "2026-09-25T10:00:00Z" },
    } as never);

    const r = await createTicketCall("t1");

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost).toHaveBeenCalledWith("/tickets/t1/calls", {});
    const [, corpo] = mockPost.mock.calls[0];
    expect(Object.keys(corpo as object)).toHaveLength(0);
    expect(r.creation_status).toBe("confirmed");
  });

  it("devolve so os tres campos publicos", async () => {
    mockPost.mockResolvedValue({
      data: { id: "c1", creation_status: "indeterminate", created_at: "2026-09-25T10:00:00Z" },
    } as never);
    const r = await createTicketCall("t1");
    expect(Object.keys(r).sort()).toEqual(["created_at", "creation_status", "id"]);
  });
});
