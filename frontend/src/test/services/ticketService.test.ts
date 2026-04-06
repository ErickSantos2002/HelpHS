import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getTickets,
  getTicket,
  createTicket,
  updateTicket,
  updateTicketStatus,
  assignTicket,
  getTicketHistory,
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
      priority: "medium",
      category: "software",
    });

    expect(mockPost).toHaveBeenCalledWith("/tickets", {
      title: "Problema no sistema",
      description: "Detalhes",
      priority: "medium",
      category: "software",
    });
    expect(result.protocol).toBe("HS-2026-0001");
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
  it("calls GET /tickets/:id/history with limit=100", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 100, offset: 0 },
    });

    await getTicketHistory("t1");

    expect(mockGet).toHaveBeenCalledWith("/tickets/t1/history?limit=100");
  });
});
