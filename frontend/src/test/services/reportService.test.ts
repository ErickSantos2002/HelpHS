import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getReports,
  getTechnicianListReport,
  getTechnicianDetailReport,
  exportReportsUrl,
  type ReportData,
  type TechnicianListReport,
  type TechnicianDetailReport,
} from "../../services/reportService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockGet = vi.mocked(api.get);

const relatorio: ReportData = {
  period_days: 30,
  total_tickets: 42,
  tickets_by_day: [{ date: "2026-09-01", count: 3 }],
  tickets_by_category: [{ category: "software", count: 12 }],
  sla_compliance: [
    { priority: "high", total: 10, breached: 1, compliance_rate: 90 },
  ],
  csat_distribution: [{ rating: 5, count: 7 }],
  csat_average: 4.5,
  recommend_average: null,
  avg_resolution_by_priority: [{ priority: "high", avg_hours: 3.2 }],
  avg_first_response_by_priority: [{ priority: "high", avg_hours: null }],
  csat_by_day: [{ date: "2026-09-01", avg_rating: null, count: 0 }],
  tickets_by_product: [{ product_name: "Balança", count: 4 }],
  tickets_by_weekday: [{ weekday: 1, count: 9 }],
  tickets_by_hour: [{ hour: 14, count: 5 }],
  oldest_open_tickets: [],
  technicians_dist: [],
  reopened_count: 2,
  reopen_rate: 4.76,
  comparison: null,
};

const listaTecnicos: TechnicianListReport = {
  period_days: 30,
  technicians: [
    {
      technician_id: "u1",
      technician_name: "Gabriel Moura",
      total_assigned: 20,
      resolved: 18,
      open_count: 2,
      sla_breached: 1,
      sla_compliance_rate: 95,
      avg_resolution_hours: 5.5,
      csat_average: 4.8,
      csat_count: 10,
    },
  ],
};

const detalheTecnico: TechnicianDetailReport = {
  period_days: 30,
  technician_id: "u1",
  technician_name: "Gabriel Moura",
  total_assigned: 20,
  resolved: 18,
  in_progress: 1,
  open_count: 2,
  sla_breached: 1,
  sla_compliance_rate: 95,
  avg_resolution_hours: 5.5,
  csat_average: null,
  csat_count: 0,
  tickets_by_day: [{ date: "2026-09-01", count: 2 }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getReports", () => {
  it("busca /dashboard/reports sem nenhum parâmetro quando não há filtro", async () => {
    mockGet.mockResolvedValue({ data: relatorio });

    const result = await getReports();

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports", { params: {} });
    expect(result.total_tickets).toBe(42);
    expect(result.csat_average).toBe(4.5);
  });

  it("repassa todos os filtros preenchidos como params", async () => {
    mockGet.mockResolvedValue({ data: relatorio });

    await getReports({
      period: 7,
      category: "hardware",
      priority: "high",
      start_date: "2026-08-01",
      end_date: "2026-08-31",
    });

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports", {
      params: {
        period: 7,
        category: "hardware",
        priority: "high",
        start_date: "2026-08-01",
        end_date: "2026-08-31",
      },
    });
  });

  it("omite os filtros ausentes em vez de mandar undefined", async () => {
    mockGet.mockResolvedValue({ data: relatorio });

    await getReports({ category: "software" });

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports", {
      params: { category: "software" },
    });
    // Nenhuma chave a mais: o servidor não pode receber priority=undefined.
    const { params } = mockGet.mock.calls[0][1] as {
      params: Record<string, unknown>;
    };
    expect(Object.keys(params)).toEqual(["category"]);
  });

  it("envia period igual a zero, que é filtro válido e não ausência", async () => {
    mockGet.mockResolvedValue({ data: { ...relatorio, period_days: 0 } });

    await getReports({ period: 0 });

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports", {
      params: { period: 0 },
    });
  });

  it("descarta data vazia, mas mantém categoria vazia", async () => {
    mockGet.mockResolvedValue({ data: relatorio });

    await getReports({ start_date: "", end_date: "", category: "" });

    // start_date/end_date usam checagem de valor "cheio"; category usa
    // apenas !== undefined — a assimetria está no código e é intencional.
    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports", {
      params: { category: "" },
    });
  });

  it("devolve o corpo da resposta, não o envelope do axios", async () => {
    mockGet.mockResolvedValue({ data: relatorio, status: 200 });

    const result = await getReports({ period: 30 });

    expect(result).toBe(relatorio);
    expect(result).not.toHaveProperty("status");
  });

  it("propaga o erro quando o servidor recusa o período", async () => {
    mockGet.mockRejectedValue({
      response: { status: 422, data: { detail: "Período inválido" } },
    });

    await expect(getReports({ period: 999 })).rejects.toMatchObject({
      response: { status: 422 },
    });
  });
});

describe("getTechnicianListReport", () => {
  it("usa período de 30 dias quando nada é informado", async () => {
    mockGet.mockResolvedValue({ data: listaTecnicos });

    const result = await getTechnicianListReport();

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports/technicians", {
      params: { period: 30 },
    });
    expect(result.technicians[0].technician_name).toBe("Gabriel Moura");
  });

  it("respeita o período informado no lugar do padrão", async () => {
    mockGet.mockResolvedValue({ data: { ...listaTecnicos, period_days: 7 } });

    const result = await getTechnicianListReport(7);

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports/technicians", {
      params: { period: 7 },
    });
    expect(result.period_days).toBe(7);
  });

  it("aceita lista de técnicos vazia sem quebrar", async () => {
    mockGet.mockResolvedValue({ data: { period_days: 30, technicians: [] } });

    const result = await getTechnicianListReport();

    expect(result.technicians).toEqual([]);
  });

  it("propaga o erro de permissão para a tela tratar", async () => {
    mockGet.mockRejectedValue({ response: { status: 403 } });

    await expect(getTechnicianListReport()).rejects.toMatchObject({
      response: { status: 403 },
    });
  });
});

describe("getTechnicianDetailReport", () => {
  it("sem técnico informado, pede só o período (o próprio usuário logado)", async () => {
    mockGet.mockResolvedValue({ data: detalheTecnico });

    const result = await getTechnicianDetailReport();

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports/technician", {
      params: { period: 30 },
    });
    const { params } = mockGet.mock.calls[0][1] as {
      params: Record<string, unknown>;
    };
    expect(Object.keys(params)).toEqual(["period"]);
    expect(result.technician_id).toBe("u1");
  });

  it("acrescenta technician_id quando um técnico é escolhido", async () => {
    mockGet.mockResolvedValue({ data: detalheTecnico });

    await getTechnicianDetailReport(7, "u9");

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports/technician", {
      params: { period: 7, technician_id: "u9" },
    });
  });

  it("id vazio equivale a não escolher técnico nenhum", async () => {
    mockGet.mockResolvedValue({ data: detalheTecnico });

    await getTechnicianDetailReport(15, "");

    expect(mockGet).toHaveBeenCalledWith("/dashboard/reports/technician", {
      params: { period: 15 },
    });
  });

  it("mantém csat nulo vindo do servidor em vez de virar zero", async () => {
    mockGet.mockResolvedValue({ data: detalheTecnico });

    const result = await getTechnicianDetailReport();

    expect(result.csat_average).toBeNull();
    expect(result.csat_count).toBe(0);
  });
});

describe("exportReportsUrl", () => {
  it("monta a URL de csv com o período", () => {
    expect(exportReportsUrl("csv", { period: 30 })).toBe(
      "/api/v1/dashboard/reports/export/csv?period=30",
    );
  });

  it("troca o formato no caminho, não na query", () => {
    expect(exportReportsUrl("pdf", { period: 30 })).toBe(
      "/api/v1/dashboard/reports/export/pdf?period=30",
    );
  });

  it("usa o intervalo de datas quando as duas pontas vêm preenchidas", () => {
    expect(
      exportReportsUrl("csv", {
        start_date: "2026-08-01",
        end_date: "2026-08-31",
      }),
    ).toBe(
      "/api/v1/dashboard/reports/export/csv?start_date=2026-08-01&end_date=2026-08-31",
    );
  });

  it("o intervalo de datas vence o período quando os dois são informados", () => {
    const url = exportReportsUrl("pdf", {
      period: 90,
      start_date: "2026-08-01",
      end_date: "2026-08-31",
    });

    expect(url).not.toContain("period=");
    expect(url).toContain("start_date=2026-08-01");
    expect(url).toContain("end_date=2026-08-31");
  });

  it("cai para o período quando só uma ponta do intervalo foi preenchida", () => {
    expect(
      exportReportsUrl("csv", { period: 7, start_date: "2026-08-01" }),
    ).toBe("/api/v1/dashboard/reports/export/csv?period=7");

    expect(exportReportsUrl("csv", { period: 7, end_date: "2026-08-31" })).toBe(
      "/api/v1/dashboard/reports/export/csv?period=7",
    );
  });

  it("sem período e com intervalo pela metade, não sobra nenhum parâmetro", () => {
    expect(exportReportsUrl("csv", { start_date: "2026-08-01" })).toBe(
      "/api/v1/dashboard/reports/export/csv?",
    );
  });

  it("sem filtro nenhum, devolve a rota com a query vazia", () => {
    expect(exportReportsUrl("pdf", {})).toBe(
      "/api/v1/dashboard/reports/export/pdf?",
    );
  });

  it("acrescenta categoria e prioridade depois do recorte de tempo", () => {
    expect(
      exportReportsUrl("csv", {
        period: 30,
        category: "hardware",
        priority: "high",
      }),
    ).toBe(
      "/api/v1/dashboard/reports/export/csv?period=30&category=hardware&priority=high",
    );
  });

  it("escapa acento e espaço na categoria", () => {
    const url = exportReportsUrl("csv", {
      period: 30,
      category: "manutenção preventiva",
    });

    expect(url).toBe(
      "/api/v1/dashboard/reports/export/csv?period=30&category=manuten%C3%A7%C3%A3o+preventiva",
    );
  });

  it("categoria e prioridade vazias não entram na query", () => {
    expect(
      exportReportsUrl("csv", { period: 30, category: "", priority: "" }),
    ).toBe("/api/v1/dashboard/reports/export/csv?period=30");
  });

  it("é função pura: não toca no cliente HTTP", () => {
    exportReportsUrl("csv", { period: 30 });

    expect(mockGet).not.toHaveBeenCalled();
  });
});
