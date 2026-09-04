import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getDashboardStats,
  type DashboardStats,
} from "../../services/dashboardService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);

const stats: DashboardStats = {
  tickets: {
    total: 42,
    open: 10,
    in_progress: 7,
    awaiting: 3,
    resolved: 15,
    closed: 6,
    cancelled: 1,
    by_priority_critical: 2,
    by_priority_high: 5,
    by_priority_medium: 20,
    by_priority_low: 15,
  },
  surveys: {
    total: 12,
    average_rating: 4.5,
  },
  sla: {
    response_breached: 2,
    resolve_breached: 1,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getDashboardStats", () => {
  it("busca em GET /dashboard/stats", async () => {
    mockGet.mockResolvedValue({ data: stats });

    await getDashboardStats();

    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith("/dashboard/stats");
  });

  it("não envia filtro nem config: a URL vai sozinha", async () => {
    mockGet.mockResolvedValue({ data: stats });

    await getDashboardStats();

    // Um único argumento — nada de { params } ou headers embutidos aqui.
    expect(mockGet.mock.calls[0]).toHaveLength(1);
  });

  it("devolve o corpo da resposta, não o envelope do axios", async () => {
    mockGet.mockResolvedValue({
      data: stats,
      status: 200,
      statusText: "OK",
      headers: {},
      config: {},
    });

    const result = await getDashboardStats();

    expect(result).toEqual(stats);
    expect(result).not.toHaveProperty("data");
    expect(result).not.toHaveProperty("status");
    expect(result.tickets.total).toBe(42);
    expect(result.sla.response_breached).toBe(2);
  });

  it("preserva average_rating nula em vez de trocar por zero", async () => {
    // Sem pesquisa respondida o backend manda null; virar 0 mentiria uma nota
    // péssima na tela.
    mockGet.mockResolvedValue({
      data: {
        ...stats,
        surveys: { total: 0, average_rating: null },
      },
    });

    const result = await getDashboardStats();

    expect(result.surveys.average_rating).toBeNull();
    expect(result.surveys.total).toBe(0);
  });

  it("propaga o erro da API em vez de devolver números zerados", async () => {
    mockGet.mockRejectedValue(new Error("500 Internal Server Error"));

    await expect(getDashboardStats()).rejects.toThrow(
      "500 Internal Server Error",
    );
  });

  it("consulta o servidor a cada chamada, sem cache entre elas", async () => {
    mockGet.mockResolvedValueOnce({ data: stats });
    mockGet.mockResolvedValueOnce({
      data: { ...stats, tickets: { ...stats.tickets, open: 11 } },
    });

    const primeira = await getDashboardStats();
    const segunda = await getDashboardStats();

    expect(mockGet).toHaveBeenCalledTimes(2);
    expect(primeira.tickets.open).toBe(10);
    expect(segunda.tickets.open).toBe(11);
  });
});
