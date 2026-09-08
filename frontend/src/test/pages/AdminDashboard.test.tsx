import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/dashboardService", () => ({
  getDashboardStats: vi.fn(),
}));
vi.mock("../../services/reportService", () => ({
  getReports: vi.fn(),
  getTechnicianListReport: vi.fn(),
  getTechnicianDetailReport: vi.fn(),
}));

import { MemoryRouter } from "react-router-dom";
import AdminDashboard from "../../pages/dashboard/AdminDashboard";
import * as dashboardService from "../../services/dashboardService";
import * as reportService from "../../services/reportService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * `STATUS_COLORS` e `PRIORITY_COLORS` eram o mapa local que a E18 e o
 * `lib/prioridade.ts` existem para substituir — hexadecimais cravados,
 * rótulo próprio ("Abertos", "Crítico" no masculino) e nenhuma legenda
 * garantida. A rosca e a barra empilhada ficaram TRAVADAS até a E18 gravar
 * `SLOT_DE_STATUS`: uma tentativa anterior de migrá-las com tokens de
 * interface (`color-mix()`) quebrou o gráfico, porque o Recharts escreve a
 * cor em atributo de SVG. O cromo (eixo, grade, dica) e a cor da série
 * temporal única eram `theme === "dark" ? A : B` escrito à mão, a mesma
 * causa-raiz que `TechnicianDashboard` tinha.
 */

const STATS = {
  tickets: {
    total: 16,
    open: 3,
    in_progress: 2,
    awaiting: 1,
    resolved: 4,
    closed: 5,
    cancelled: 1,
    by_priority_critical: 2,
    by_priority_high: 3,
    by_priority_medium: 4,
    by_priority_low: 7,
  },
  surveys: { total: 5, average_rating: 8.4 },
  sla: { response_breached: 1, resolve_breached: 2 },
};

const REPORT = {
  period_days: 30,
  total_tickets: 16,
  tickets_by_day: [
    { date: "2026-09-01", count: 3 },
    { date: "2026-09-02", count: 5 },
  ],
  tickets_by_category: [{ category: "Hardware", count: 6 }],
  sla_compliance: [
    { priority: "critical", total: 2, breached: 1, compliance_rate: 60 },
    { priority: "low", total: 7, breached: 0, compliance_rate: 95 },
  ],
  csat_distribution: [],
  csat_average: 8.4,
  recommend_average: null,
  avg_resolution_by_priority: [],
  avg_first_response_by_priority: [],
  csat_by_day: [],
  tickets_by_product: [],
  tickets_by_weekday: [],
  tickets_by_hour: [],
  oldest_open_tickets: [],
  technicians_dist: [],
  reopened_count: 0,
  reopen_rate: 0,
  comparison: null,
};

const TECH_LIST = {
  period_days: 30,
  technicians: [
    {
      technician_id: "tech1",
      technician_name: "Ana Silva",
      total_assigned: 5,
      resolved: 3,
      open_count: 2,
      sla_breached: 1,
      sla_compliance_rate: 80,
      avg_resolution_hours: 4,
      csat_average: 9,
      csat_count: 2,
    },
  ],
};

async function montar() {
  vi.mocked(dashboardService.getDashboardStats).mockResolvedValue(STATS as never);
  vi.mocked(reportService.getReports).mockResolvedValue(REPORT as never);
  vi.mocked(reportService.getTechnicianListReport).mockResolvedValue(TECH_LIST as never);

  render(
    <MemoryRouter>
      <AdminDashboard />
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
}

/** O bloco do gráfico a partir do título do seu cabeçalho. */
function blocoDe(titulo: string): HTMLElement {
  const el = screen.getByText(titulo);
  const bloco = el.closest(".rounded-xl");
  if (!bloco) throw new Error(`bloco de "${titulo}" não encontrado`);
  return bloco as HTMLElement;
}

describe("AdminDashboard", () => {
  it("a legenda da rosca usa o rótulo canônico de lib/status.ts, não o mapa local", async () => {
    // O mapa local dizia "Abertos", "Resolvidos", "Fechados", "Cancelados" —
    // plural, e divergente do rótulo que o resto do sistema usa (o Badge, a
    // coluna do quadro). `rotuloDeStatus` devolve o singular; achar "Aberto"
    // aqui só é possível depois da troca.
    await montar();
    const rosca = blocoDe("Tickets por Status");
    for (const rotulo of ["Aberto", "Em andamento", "Resolvido", "Fechado", "Cancelado"]) {
      expect(within(rosca).getByText(rotulo)).toBeInTheDocument();
    }
  });

  it("a cor de cada fatia da rosca vem da tabela fixa da E18, não de hexadecimal cravado", async () => {
    // SLOT_DE_STATUS: open -> --chart-1, cancelled -> --chart-7. Trocar os
    // dois de lugar, ou voltar a `STATUS_COLORS`, muda o `backgroundColor`
    // que este teste lê — ele não sabe o valor de cor por leitura de código,
    // só pelo que o DOM afirma.
    await montar();
    const rosca = blocoDe("Tickets por Status");
    const linhaAberto = within(rosca).getByText("Aberto").closest("div")!;
    const swatchAberto = linhaAberto.querySelector("span[style]") as HTMLElement;
    expect(swatchAberto.style.backgroundColor).toBe("var(--chart-1)");

    const linhaCancelado = within(rosca).getByText("Cancelado").closest("div")!;
    const swatchCancelado = linhaCancelado.querySelector("span[style]") as HTMLElement;
    expect(swatchCancelado.style.backgroundColor).toBe("var(--chart-7)");
  });

  it("a distribuição de status (barra) usa o mesmo rótulo e a mesma cor da rosca", async () => {
    // StatusBar e a rosca mostram os MESMOS seis blocos — "Resolvidos"
    // mudaria de cor entre os dois se cada um tivesse o seu próprio mapa.
    await montar();
    const barra = screen.getByText("Distribuição de status").closest(".rounded-xl") as HTMLElement;
    const linhaAberto = within(barra).getByText(/^Aberto:/).closest("div")!;
    const swatch = linhaAberto.querySelector("span[style]") as HTMLElement;
    expect(swatch.style.backgroundColor).toBe("var(--chart-1)");
  });

  // A barra empilhada por prioridade e a área temporal não têm caso aqui: o
  // rótulo do eixo, a cor da barra e o traço da área só existem dentro do SVG
  // que o Recharts desenha, e o `ResponsiveContainer` mede o contêiner em 0×0
  // neste ambiente de teste (happy-dom não faz layout de verdade) — o mesmo
  // limite documentado em `TechnicianDashboard.test.tsx`, que pela mesma razão
  // também nunca lê conteúdo de dentro de um gráfico. `rotuloDePrioridade` e
  // `graficoDePrioridade` já têm caso de prova em `test/lib/prioridade.test.ts`;
  // o que este arquivo não prova é que ESTA tela os chama com a chave certa —
  // ficou de fora, e está registrado na ficha da fase.

  it("sem dados no período, o gráfico temporal vira mensagem — não fica em branco", async () => {
    vi.mocked(dashboardService.getDashboardStats).mockResolvedValue(STATS as never);
    vi.mocked(reportService.getReports).mockResolvedValue({
      ...REPORT,
      tickets_by_day: [],
    } as never);
    vi.mocked(reportService.getTechnicianListReport).mockResolvedValue(TECH_LIST as never);

    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());

    expect(screen.getByText("Sem dados para o período")).toBeInTheDocument();
  });

  it("nenhum ticket: a rosca vira mensagem, e não uma rosca vazia", async () => {
    vi.mocked(dashboardService.getDashboardStats).mockResolvedValue({
      ...STATS,
      tickets: {
        ...STATS.tickets,
        total: 0, open: 0, in_progress: 0, awaiting: 0, resolved: 0, closed: 0, cancelled: 0,
      },
    } as never);
    vi.mocked(reportService.getReports).mockResolvedValue(REPORT as never);
    vi.mocked(reportService.getTechnicianListReport).mockResolvedValue(TECH_LIST as never);

    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());

    const rosca = blocoDe("Tickets por Status");
    expect(within(rosca).getByText("Nenhum ticket")).toBeInTheDocument();
  });
});
