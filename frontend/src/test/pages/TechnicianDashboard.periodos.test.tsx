import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => {
  // Um objeto só, criado uma vez: a identidade do `user` é dependência das
  // cargas, e um literal novo a cada chamada as faria pedir sem parar.
  const user = { id: "tech1", name: "Ana Silva", role: "technician" };
  return { useAuth: () => ({ user }) };
});
vi.mock("../../services/dashboardService", () => ({
  getDashboardStats: vi.fn(),
}));
vi.mock("../../services/reportService", () => ({
  getTechnicianDetailReport: vi.fn(),
}));
vi.mock("../../services/ticketService", () => ({
  getTickets: vi.fn(),
}));

import { MemoryRouter } from "react-router-dom";
import TechnicianDashboard from "../../pages/dashboard/TechnicianDashboard";
import * as dashboardService from "../../services/dashboardService";
import * as reportService from "../../services/reportService";
import * as ticketService from "../../services/ticketService";
import type { Ticket, TicketFilters, TicketListResponse } from "../../services/ticketService";
import { escolherNoMenu } from "../helpers/menu";

/**
 * O dashboard do técnico com os períodos de calendário e os blocos
 * independentes (F1-B-03b). Relógio fixo: 30/10/2026 12:00 em Recife.
 */
const AGORA = new Date("2026-10-30T15:00:00Z");

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(AGORA);
  vi.clearAllMocks();
});
afterEach(() => {
  vi.useRealTimers();
});

const MINE = {
  id: "t1", protocol: "HS-1", title: "Impressora sem tinta", status: "open",
  priority: "critical", assignee_id: "tech1", assignee_name: "Ana Silva",
  sla_response_breach: true, sla_resolve_breach: false,
} as unknown as Ticket;

const STATS = {
  tickets: {
    total: 10, open: 4, in_progress: 3, awaiting: 0, resolved: 2, closed: 1, cancelled: 0,
    by_priority_critical: 1, by_priority_high: 1, by_priority_medium: 1, by_priority_low: 1,
  },
  surveys: { total: 0, average_rating: null },
  sla: { response_breached: 0, resolve_breached: 0 },
};

const DETAIL = {
  period_days: 30, technician_id: "tech1", technician_name: "Ana Silva",
  total_assigned: 5, resolved: 2, in_progress: 2, open_count: 1,
  sla_breached: 1, sla_compliance_rate: 80, avg_resolution_hours: 4,
  csat_average: 9, csat_count: 3, tickets_by_day: [{ date: "2026-10-30", count: 2 }],
};

function resposta(items: Ticket[]): TicketListResponse {
  return { items, total: items.length, limit: 200, offset: 0, expediente: null };
}

function erroDaApi(status: number, detail: string) {
  return Object.assign(new Error("falhou"), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });
}

function padrao() {
  vi.mocked(dashboardService.getDashboardStats).mockResolvedValue(STATS as never);
  vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue(DETAIL as never);
  vi.mocked(ticketService.getTickets).mockImplementation(
    async (filters: TicketFilters = {}) => {
      if (filters.assignee_id) return resposta([MINE]);
      if (filters.status === "open") return resposta([MINE]);
      return resposta([]);
    },
  );
}

function montar() {
  return render(
    <MemoryRouter>
      <TechnicianDashboard />
    </MemoryRouter>,
  );
}

/** O cartão "Meu desempenho", pelo título. */
async function desempenho(): Promise<HTMLElement> {
  const titulo = await screen.findByText(/^Meu desempenho —/);
  return titulo.closest(".rounded-xl") as HTMLElement;
}

describe("TechnicianDashboard — períodos", () => {
  it("pede o próprio relatório com as datas do calendário, sem technician_id", async () => {
    padrao();
    montar();
    await waitFor(() =>
      expect(reportService.getTechnicianDetailReport).toHaveBeenCalledWith({
        start_date: "2026-10-01",
        end_date: "2026-10-30",
      }),
    );
    // Sem segundo argumento: o servidor decide de quem é o relatório.
    expect(vi.mocked(reportService.getTechnicianDetailReport).mock.calls[0]).toHaveLength(1);
  });

  it("Hoje deixa de pedir period=1 e passa a pedir o dia de Recife", async () => {
    padrao();
    montar();
    escolherNoMenu(screen.getByRole("combobox", { name: "Período" }), "Hoje");
    await waitFor(() =>
      expect(reportService.getTechnicianDetailReport).toHaveBeenLastCalledWith({
        start_date: "2026-10-30",
        end_date: "2026-10-30",
      }),
    );
  });

  it("trocar de período não pede de novo as listas nem a fila geral", async () => {
    padrao();
    montar();
    // Meus (1) + fila (1) + os quatro status da equipe (4).
    await waitFor(() => expect(ticketService.getTickets).toHaveBeenCalledTimes(6));
    await waitFor(() => expect(dashboardService.getDashboardStats).toHaveBeenCalledTimes(1));
    const listas = vi.mocked(ticketService.getTickets).mock.calls.length;

    escolherNoMenu(screen.getByRole("combobox", { name: "Período" }), "Ontem");
    await waitFor(() => expect(reportService.getTechnicianDetailReport).toHaveBeenCalledTimes(2));
    expect(ticketService.getTickets).toHaveBeenCalledTimes(listas);
    expect(dashboardService.getDashboardStats).toHaveBeenCalledTimes(1);
  });
});

describe("TechnicianDashboard — falhas", () => {
  it("relatório falha: nada de zeros nem 100%, aviso com o motivo e o resto da tela", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianDetailReport).mockRejectedValue(
      erroDaApi(422, "Deve ser maior ou igual a 7"),
    );
    montar();

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Meu desempenho")).toBeInTheDocument();
    expect(within(aviso).getByText("Deve ser maior ou igual a 7")).toBeInTheDocument();

    const cartao = await desempenho();
    expect(within(cartao).queryByText("100%")).not.toBeInTheDocument();
    expect(within(cartao).queryByText("Atribuídos")).not.toBeInTheDocument();
    expect(within(cartao).getByText("Indisponível — veja o aviso acima.")).toBeInTheDocument();

    // As listas e o seletor continuam.
    expect(screen.getByRole("combobox", { name: "Período" })).toBeInTheDocument();
    expect(await screen.findAllByText("Impressora sem tinta")).not.toHaveLength(0);
  });

  it("Tentar de novo recupera o relatório e limpa o aviso", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianDetailReport)
      .mockRejectedValueOnce(erroDaApi(500, "Erro interno"))
      .mockResolvedValue(DETAIL as never);
    montar();

    const aviso = await screen.findByRole("alert");
    fireEvent.click(within(aviso).getByRole("button", { name: "Tentar de novo" }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    const cartao = await desempenho();
    expect(await within(cartao).findByText("80%")).toBeInTheDocument();
  });

  it("a fila falha sozinha: «Indisponível», e não «Fila limpa»", async () => {
    padrao();
    vi.mocked(ticketService.getTickets).mockImplementation(
      async (filters: TicketFilters = {}) => {
        if (filters.assignee_id) return resposta([MINE]);
        throw erroDaApi(503, "");
      },
    );
    montar();

    const avisos = await screen.findAllByRole("alert");
    const titulos = avisos.map((a) => a.querySelector("p")?.textContent);
    expect(titulos).toEqual(expect.arrayContaining(["Fila — tickets abertos", "Tickets da equipe"]));
    expect(screen.queryByText("Fila limpa")).not.toBeInTheDocument();
    // Os meus chamados chegaram e estão na tela.
    expect(await screen.findByText("Impressora sem tinta")).toBeInTheDocument();
  });

  it("a fila geral falha: o indicador mostra «—», não zero", async () => {
    padrao();
    vi.mocked(dashboardService.getDashboardStats).mockRejectedValue(erroDaApi(500, ""));
    montar();

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Fila geral")).toBeInTheDocument();
    const rotulo = screen.getByText("Fila geral aberta");
    const card = rotulo.closest("div")!.parentElement as HTMLElement;
    expect(within(card).getByText("Indisponível")).toBeInTheDocument();
  });
});

describe("TechnicianDashboard — SLA sem dados", () => {
  it("sem chamado atribuído no período, a conformidade é «—»", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue({
      ...DETAIL, total_assigned: 0, resolved: 0, in_progress: 0, open_count: 0,
      sla_breached: 0, sla_compliance_rate: 100, avg_resolution_hours: null,
      csat_average: null, csat_count: 0, tickets_by_day: [],
    } as never);
    montar();

    const cartao = await desempenho();
    await within(cartao).findByText("Atribuídos");
    const linha = within(cartao).getByText("Conformidade SLA").parentElement as HTMLElement;
    expect(within(linha).getByText("—")).toBeInTheDocument();
    expect(within(cartao).queryByText("100%")).not.toBeInTheDocument();
  });
});

describe("TechnicianDashboard — intervalo inválido não é carregamento (V1)", () => {
  it("o desempenho espera um período válido, sem anel; corrigir volta a carregar", async () => {
    padrao();
    render(<MemoryRouter><TechnicianDashboard /></MemoryRouter>);
    await screen.findByText("Atribuídos");
    escolherNoMenu(screen.getByRole("combobox", { name: "Período" }), "Personalizado");
    fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-10-20" } });
    await waitFor(() =>
      expect(reportService.getTechnicianDetailReport).toHaveBeenLastCalledWith(
        { start_date: "2026-10-20", end_date: "2026-10-30" },
      ),
    );
    await screen.findByText("Atribuídos");
    const pedidos = vi.mocked(reportService.getTechnicianDetailReport).mock.calls.length;

    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-10" } });

    await screen.findByText("A data inicial não pode ser posterior à data final.");
    const aviso = "Aguardando um período válido — corrija as datas acima.";
    expect(screen.getAllByText(aviso)).toHaveLength(2);
    expect(screen.queryByText("Atribuídos")).not.toBeInTheDocument();
    // As listas de agora continuam prontas; só o período espera.
    expect(screen.queryAllByRole("status", { name: "Carregando..." })).toHaveLength(0);
    expect(screen.getByText("Período inválido")).toBeInTheDocument();
    expect(reportService.getTechnicianDetailReport).toHaveBeenCalledTimes(pedidos);

    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-25" } });
    expect(await screen.findByText("Atribuídos")).toBeInTheDocument();
    expect(screen.queryByText(aviso)).not.toBeInTheDocument();
  });
});
