import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sessao = vi.hoisted(() => ({
  // Um objeto por papel, criado uma vez: a identidade do `user` não pode
  // mudar a cada render.
  admin: { id: "u1", role: "admin", name: "Admin" },
  tecnico: { id: "tech1", role: "technician", name: "Ana Silva" },
  atual: "admin" as "admin" | "tecnico",
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: sessao[sessao.atual] }),
}));
vi.mock("../../services/reportService", async (importOriginal) => {
  const real = await importOriginal<typeof import("../../services/reportService")>();
  return {
    ...real,
    getReports: vi.fn(),
    getTechnicianListReport: vi.fn(),
    getTechnicianDetailReport: vi.fn(),
  };
});

import ReportsPage from "../../pages/reports/ReportsPage";
import * as reportService from "../../services/reportService";
import { escolherNoMenu } from "../helpers/menu";

/**
 * Os Relatórios com os períodos de calendário e os blocos independentes
 * (F1-B-03b). Relógio fixo: 30/10/2026 12:00 em Recife.
 */
vi.setConfig({ testTimeout: 20000 });
const AGORA = new Date("2026-10-30T15:00:00Z");

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(AGORA);
  vi.clearAllMocks();
  sessao.atual = "admin";
});
afterEach(() => {
  vi.useRealTimers();
});

function relatorio(ajuste: Partial<reportService.ReportData> = {}): reportService.ReportData {
  return {
    period_days: 30,
    start_date: "2026-10-01",
    end_date: "2026-10-30",
    timezone: "America/Recife",
    total_tickets: 12,
    tickets_by_day: [{ date: "2026-10-30", count: 12 }],
    tickets_by_category: [{ category: "hardware", count: 12 }],
    sla_compliance: [
      { priority: "critical", total: 0, breached: 0, compliance_rate: 100 },
      { priority: "high", total: 4, breached: 1, compliance_rate: 75 },
    ],
    csat_distribution: [], csat_average: null, recommend_average: null,
    avg_resolution_by_priority: [], avg_first_response_by_priority: [], csat_by_day: [],
    tickets_by_product: [], tickets_by_weekday: [], tickets_by_hour: [],
    oldest_open_tickets: [], technicians_dist: [], reopened_count: 0, reopen_rate: 0,
    sla_justifications: [],
    comparison: {
      start_date: "2026-09-01", end_date: "2026-09-30",
      total_tickets: 10, csat_average: null,
      sla_compliance: [{ priority: "high", total: 2, breached: 0, compliance_rate: 100 }],
    },
    ...ajuste,
  };
}

const LISTA = {
  period_days: 30,
  technicians: [{
    technician_id: "tech1", technician_name: "Ana Silva", total_assigned: 0, resolved: 0,
    open_count: 0, sla_breached: 0, sla_compliance_rate: 100, avg_resolution_hours: null,
    csat_average: null, csat_count: 0,
  }],
};

const DETALHE = {
  period_days: 30, start_date: "2026-10-01", end_date: "2026-10-30",
  technician_id: "tech1", technician_name: "Ana Silva", total_assigned: 3, resolved: 1,
  in_progress: 1, open_count: 1, sla_breached: 0, sla_compliance_rate: 100,
  avg_resolution_hours: 2, csat_average: null, csat_count: 0,
  tickets_by_day: [{ date: "2026-10-30", count: 3 }],
};

function erroDaApi(status: number, detail: string) {
  return Object.assign(new Error("falhou"), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });
}

function padrao() {
  vi.mocked(reportService.getReports).mockResolvedValue(relatorio());
  vi.mocked(reportService.getTechnicianListReport).mockResolvedValue(LISTA);
  vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue(DETALHE);
}

const periodo = () => screen.getByRole("combobox", { name: "Período" });
const ultimo = <T,>(fn: { mock: { calls: T[][] } }) => fn.mock.calls[fn.mock.calls.length - 1];

/** O cartão de indicador pelo rótulo. */
function cartao(rotulo: string): HTMLElement {
  return screen.getByText(rotulo).parentElement as HTMLElement;
}

describe("ReportsPage — o mesmo intervalo em todos os relatórios", () => {
  it("visão geral, lista de técnicos e detalhe recebem as MESMAS datas", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    const esperado = { start_date: "2026-10-01", end_date: "2026-10-30" };
    expect(ultimo(vi.mocked(reportService.getReports))[0]).toEqual(esperado);

    fireEvent.click(screen.getByRole("button", { name: /Por técnico/ }));
    await waitFor(() =>
      expect(reportService.getTechnicianListReport).toHaveBeenLastCalledWith(esperado),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Detalhes de Ana Silva" }));
    await waitFor(() =>
      expect(reportService.getTechnicianDetailReport).toHaveBeenLastCalledWith(esperado, "tech1"),
    );
  });

  it("Personalizado manda as datas reais a todos, e não uma quantidade de dias", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    escolherNoMenu(periodo(), "Personalizado");
    fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-08-03" } });
    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-08-17" } });

    const esperado = { start_date: "2026-08-03", end_date: "2026-08-17" };
    await waitFor(() => expect(ultimo(vi.mocked(reportService.getReports))[0]).toEqual(esperado));

    fireEvent.click(screen.getByRole("button", { name: /Por técnico/ }));
    await waitFor(() =>
      expect(reportService.getTechnicianListReport).toHaveBeenLastCalledWith(esperado),
    );
  });

  it("a exportação leva as datas do período escolhido", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    escolherNoMenu(periodo(), "Mês passado");
    await waitFor(() => expect(reportService.getReports).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole("button", { name: /Exportar/ }));
    const csv = screen.getByRole("link", { name: /Exportar CSV/ });
    expect(csv.getAttribute("href")).toContain("start_date=2026-09-01");
    expect(csv.getAttribute("href")).toContain("end_date=2026-09-30");
  });
});

describe("ReportsPage — validação e falhas", () => {
  it("intervalo invertido: aviso, nenhum pedido e o relatório anterior sai da tela", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    escolherNoMenu(periodo(), "Personalizado");
    fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-10-20" } });
    await waitFor(() =>
      expect(ultimo(vi.mocked(reportService.getReports))[0]).toMatchObject({ start_date: "2026-10-20" }),
    );
    await screen.findByText("Tickets no período");
    const pedidos = vi.mocked(reportService.getReports).mock.calls.length;

    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-10" } });

    expect(await screen.findByText("A data inicial não pode ser posterior à data final."))
      .toBeInTheDocument();
    expect(reportService.getReports).toHaveBeenCalledTimes(pedidos);
    expect(screen.queryByText("Tickets no período")).not.toBeInTheDocument();
    // Sem intervalo, sem exportação de um período que não existe.
    expect(screen.queryByRole("button", { name: /Exportar/ })).not.toBeInTheDocument();
  });

  it("a falha aparece com o motivo da API, e o seletor continua à vista", async () => {
    padrao();
    vi.mocked(reportService.getReports).mockRejectedValue(
      erroDaApi(422, "O intervalo pode ter no máximo 366 dias."),
    );
    render(<ReportsPage />);

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Visão geral")).toBeInTheDocument();
    expect(within(aviso).getByText("O intervalo pode ter no máximo 366 dias.")).toBeInTheDocument();
    expect(periodo()).toBeInTheDocument();
  });

  it("Tentar de novo recupera a visão geral", async () => {
    padrao();
    vi.mocked(reportService.getReports)
      .mockRejectedValueOnce(erroDaApi(500, "Erro interno"))
      .mockResolvedValue(relatorio());
    render(<ReportsPage />);

    const aviso = await screen.findByRole("alert");
    fireEvent.click(within(aviso).getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByText("Tickets no período")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("a lista de técnicos falha sozinha, com o seu aviso", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianListReport).mockRejectedValue(erroDaApi(500, "Erro"));
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    fireEvent.click(screen.getByRole("button", { name: /Por técnico/ }));

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Desempenho por técnico")).toBeInTheDocument();
  });

  it("resposta atrasada do período anterior não toma o lugar do atual", async () => {
    padrao();
    let soltarAntigo!: (v: reportService.ReportData) => void;
    vi.mocked(reportService.getReports)
      .mockImplementationOnce(() => new Promise((res) => { soltarAntigo = res; }))
      .mockResolvedValueOnce(relatorio({ total_tickets: 7 }));
    render(<ReportsPage />);
    await waitFor(() => expect(reportService.getReports).toHaveBeenCalledTimes(1));

    escolherNoMenu(periodo(), "Últimos 7 dias");
    const total = await screen.findByText("Tickets no período");
    expect(within(total.parentElement as HTMLElement).getByText("7")).toBeInTheDocument();

    await act(async () => soltarAntigo(relatorio({ total_tickets: 99 })));
    expect(screen.queryByText("99")).not.toBeInTheDocument();
  });
});

describe("ReportsPage — indicadores e comparação", () => {
  it("SLA Crítico sem chamados mostra «—», e não 100%", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    const critico = cartao("SLA Crítico");
    expect(within(critico).getByText("—")).toBeInTheDocument();
    expect(within(critico).getByText("sem chamados críticos")).toBeInTheDocument();
    expect(within(cartao("SLA Alto")).getByText("75%")).toBeInTheDocument();
  });

  it("o técnico sem chamado no período tem SLA «—» na tabela", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    fireEvent.click(screen.getByRole("button", { name: /Por técnico/ }));
    const linha = (await screen.findByRole("button", { name: "Detalhes de Ana Silva" })).closest("tr")!;
    expect(within(linha).queryByText("100%")).not.toBeInTheDocument();
  });

  it("diz com que dias a variação é comparada", async () => {
    padrao();
    render(<ReportsPage />);
    expect(await screen.findByTestId("nota-da-comparacao")).toHaveTextContent(
      "Variações comparadas com 01/09 – 30/09.",
    );
  });

  it("em Hoje, avisa que a comparação é com o dia de ontem inteiro", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    escolherNoMenu(periodo(), "Hoje");
    await waitFor(() => expect(reportService.getReports).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId("nota-da-comparacao")).toHaveTextContent(
      "Hoje, até agora, comparado com o dia de ontem inteiro.",
    );
  });

  it("o subtítulo do total diz os dias que o servidor aplicou", async () => {
    padrao();
    render(<ReportsPage />);
    const rotulo = await screen.findByText("Tickets no período");
    expect(within(rotulo.parentElement as HTMLElement).getByText("01/10 – 30/10")).toBeInTheDocument();
  });
});

describe("ReportsPage — permissões preservadas", () => {
  it("o técnico vê só o próprio relatório: sem abas, sem exportar, sem technician_id", async () => {
    sessao.atual = "tecnico";
    padrao();
    render(<ReportsPage />);

    expect(await screen.findByText("Atribuídos no período")).toBeInTheDocument();
    expect(reportService.getTechnicianDetailReport).toHaveBeenCalledWith({
      start_date: "2026-10-01",
      end_date: "2026-10-30",
    });
    expect(vi.mocked(reportService.getTechnicianDetailReport).mock.calls[0]).toHaveLength(1);
    expect(reportService.getReports).not.toHaveBeenCalled();
    expect(reportService.getTechnicianListReport).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Por técnico/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Exportar/ })).not.toBeInTheDocument();
  });

  it("o admin não pede o detalhe de ninguém até escolher um técnico", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    expect(reportService.getTechnicianDetailReport).not.toHaveBeenCalled();
  });
});

describe("ReportsPage — intervalo inválido não é carregamento (V1)", () => {
  const AVISO = "Aguardando um período válido — corrija as datas acima.";

  function inverter() {
    escolherNoMenu(periodo(), "Personalizado");
    fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-10-20" } });
    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-10" } });
  }

  it("visão geral: aviso no lugar do relatório, sem anel; corrigir volta a carregar", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    inverter();
    await screen.findByText("A data inicial não pode ser posterior à data final.");
    expect(screen.getByText(AVISO)).toBeInTheDocument();
    expect(screen.queryByText("Tickets no período")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("status", { name: "Carregando..." })).toHaveLength(0);

    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-25" } });
    expect(await screen.findByText("Tickets no período")).toBeInTheDocument();
    expect(screen.queryByText(AVISO)).not.toBeInTheDocument();
  });

  it("por técnico com detalhe aberto: aviso, e o painel não diz «Carregando detalhes…»", async () => {
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Tickets no período");
    fireEvent.click(screen.getByRole("button", { name: /Por técnico/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Detalhes de Ana Silva" }));
    await screen.findByText("Detalhes — Ana Silva");
    inverter();
    await screen.findByText("A data inicial não pode ser posterior à data final.");

    expect(screen.queryByText("Carregando detalhes…")).not.toBeInTheDocument();
    expect(screen.getByText("Detalhes do técnico")).toBeInTheDocument();
    expect(screen.getAllByText(AVISO)).toHaveLength(2);
    expect(screen.queryAllByRole("status", { name: "Carregando..." })).toHaveLength(0);
  });

  it("técnico: as próprias métricas esperam um período válido", async () => {
    sessao.atual = "tecnico";
    padrao();
    render(<ReportsPage />);
    await screen.findByText("Atribuídos no período");
    inverter();
    await screen.findByText("A data inicial não pode ser posterior à data final.");
    expect(screen.getByText(AVISO)).toBeInTheDocument();
    expect(screen.queryByText("Atribuídos no período")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("status", { name: "Carregando..." })).toHaveLength(0);
  });
});
