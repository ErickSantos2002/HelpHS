import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "tech1", name: "Ana Silva", role: "technician" } }),
}));
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

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * `PRIORITY_DOT` era um SEXTO mapa de prioridade — "médio" apontava para
 * `bg-primary`, e o canônico (`lib/prioridade.ts`) diz `bg-info`. O ponto
 * também não tinha nome acessível: era a única fonte da prioridade na linha,
 * sem rótulo visível nem `sr-only`, contra a regra que o próprio módulo
 * documenta. O gráfico usava `#0ea5e9` cravado — a quarta cor diferente entre
 * cinco gráficos da mesma natureza (chamados por dia) — e o cromo do tooltip
 * e do eixo era `theme === "dark" ? A : B` escrito à mão, igual nas outras
 * duas telas do mesmo formato.
 */

const MINE = {
  id: "t1",
  protocol: "HS-1",
  title: "Impressora sem tinta",
  status: "open",
  priority: "critical",
  assignee_id: "tech1",
  assignee_name: "Ana Silva",
  sla_response_breach: true,
  sla_resolve_breach: false,
} as unknown as Ticket;

const QUEUE_ONLY = {
  id: "t2",
  protocol: "HS-2",
  title: "Rede lenta no 2º andar",
  status: "open",
  priority: "low",
  assignee_id: null,
  assignee_name: null,
  sla_response_breach: false,
  sla_resolve_breach: false,
} as unknown as Ticket;

const TEAMMATE = {
  id: "t3",
  protocol: "HS-3",
  title: "Notebook não liga",
  status: "in_progress",
  priority: "medium",
  assignee_id: "tech2",
  assignee_name: "Bruno Souza",
  sla_response_breach: false,
  sla_resolve_breach: false,
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
  period_days: 30,
  technician_id: "tech1",
  technician_name: "Ana Silva",
  total_assigned: 5,
  resolved: 2,
  in_progress: 2,
  open_count: 1,
  sla_breached: 1,
  sla_compliance_rate: 80,
  avg_resolution_hours: 4,
  csat_average: 9,
  csat_count: 3,
  tickets_by_day: [{ date: "2026-09-01", count: 2 }],
};

function resposta(items: Ticket[]): TicketListResponse {
  return { items, total: items.length, limit: 200, offset: 0 };
}

/**
 * Cada chamada de `getTickets` na tela pede um filtro diferente — "meus",
 * "fila aberta", e os quatro status ativos para montar a equipe. O dublê
 * responde pelo filtro, não por ordem de chamada, porque o `Promise.all` não
 * garante ordem de execução.
 */
function configurarTickets() {
  vi.mocked(ticketService.getTickets).mockImplementation(
    async (filters: TicketFilters = {}) => {
      if (filters.assignee_id) return resposta([MINE]);
      // MINE também é "open" — um chamado meu e aberto aparece nos dois
      // lugares de verdade. É o que dá ao teste de agrupamento um caso onde
      // as DUAS metades do filtro da equipe (sem responsável, e sou eu)
      // precisam disparar para o resultado bater.
      if (filters.status === "open") return resposta([QUEUE_ONLY, MINE]);
      if (filters.status === "in_progress") return resposta([TEAMMATE]);
      return resposta([]);
    },
  );
}

/** O card inteiro de uma `TicketListCard`, a partir do título dela. */
function cardDe(titulo: string): HTMLElement {
  const el = screen.getByText(titulo);
  const card = el.closest(".rounded-xl");
  if (!card) throw new Error(`card de "${titulo}" não encontrado`);
  return card as HTMLElement;
}

async function montar() {
  vi.mocked(dashboardService.getDashboardStats).mockResolvedValue(STATS as never);
  vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue(DETAIL as never);
  configurarTickets();

  render(
    <MemoryRouter>
      <TechnicianDashboard />
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
}

describe("TechnicianDashboard", () => {
  it("o cumprimento usa só o primeiro nome, não o nome completo", async () => {
    await montar();
    expect(screen.getByText("Ana")).toBeInTheDocument();
    expect(screen.queryByText("Ana Silva")).not.toBeInTheDocument();
  });

  it("cada lista mostra só os tickets que lhe cabem, com a contagem certa", async () => {
    await montar();

    const meus = cardDe("Meus tickets");
    expect(within(meus).getByText("1")).toBeInTheDocument();
    expect(within(meus).getByText("Impressora sem tinta")).toBeInTheDocument();

    const fila = cardDe("Fila — Tickets abertos");
    expect(within(fila).getByText("2")).toBeInTheDocument();
    expect(within(fila).getByText("Rede lenta no 2º andar")).toBeInTheDocument();
    expect(within(fila).getByText("Impressora sem tinta")).toBeInTheDocument();

    const equipe = cardDe("Tickets da equipe");
    expect(within(equipe).getByText("1")).toBeInTheDocument();
    expect(within(equipe).getByText("Notebook não liga")).toBeInTheDocument();
    expect(within(equipe).getByText("Bruno Souza")).toBeInTheDocument();
    // O agrupamento da equipe pula quem não tem responsável (Rede lenta) e
    // quem sou eu (Impressora sem tinta) — as duas metades do `if` de
    // `TechnicianDashboard`, e as duas têm de disparar para isto bater.
    expect(within(equipe).queryByText("Rede lenta no 2º andar")).not.toBeInTheDocument();
    expect(within(equipe).queryByText("Impressora sem tinta")).not.toBeInTheDocument();
  });

  it("o selo SLA aparece só no chamado com prazo vencido", async () => {
    await montar();
    // A fila tem os dois lado a lado: o meu (vencido) e o da rede (no prazo).
    // Prende QUAL dos dois leva o selo, não só a contagem.
    const fila = cardDe("Fila — Tickets abertos");
    const vencido = within(fila).getByText("Impressora sem tinta").closest("button")!;
    const noPrazo = within(fila).getByText("Rede lenta no 2º andar").closest("button")!;
    expect(within(vencido).getByText("SLA")).toBeInTheDocument();
    expect(within(noPrazo).queryByText("SLA")).not.toBeInTheDocument();
  });

  it("o ponto de prioridade tem nome acessível — não é só cor", async () => {
    // Antes, `PRIORITY_DOT` pintava o ponto e nada mais: quem não distinguisse
    // a cor não tinha a prioridade de jeito nenhum. Regra do
    // `lib/prioridade.ts`: o ponto nunca é a única fonte, o rótulo vai junto.
    await montar();
    expect(within(cardDe("Meus tickets")).getByText("Prioridade Crítica.")).toBeInTheDocument();
  });

  it("listas vazias mostram a mensagem combinada, não uma tela quebrada", async () => {
    vi.mocked(dashboardService.getDashboardStats).mockResolvedValue(STATS as never);
    vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue(DETAIL as never);
    vi.mocked(ticketService.getTickets).mockResolvedValue(resposta([]));

    render(
      <MemoryRouter>
        <TechnicianDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());

    expect(screen.getByText("Nenhum ticket atribuído")).toBeInTheDocument();
    expect(screen.getByText("Nenhum ticket ativo na equipe")).toBeInTheDocument();
    expect(screen.getByText("Fila limpa")).toBeInTheDocument();
  });

  it("sem dados no período, o gráfico vira mensagem — não fica em branco", async () => {
    vi.mocked(dashboardService.getDashboardStats).mockResolvedValue(STATS as never);
    vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue({
      ...DETAIL,
      tickets_by_day: [],
    } as never);
    configurarTickets();

    render(
      <MemoryRouter>
        <TechnicianDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());

    expect(screen.getByText("Sem dados para o período")).toBeInTheDocument();
  });
});
