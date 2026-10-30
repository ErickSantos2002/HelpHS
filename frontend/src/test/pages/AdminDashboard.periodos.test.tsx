import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
import { escolherNoMenu } from "../helpers/menu";

/**
 * O dashboard do admin com os períodos de calendário e os blocos
 * independentes (F1-B-03b).
 *
 * O relógio é fixo e o fuso é o de Recife, escrito no instante: 30/10/2026
 * 12:00 em Recife. Só o `Date` é falso — as promessas e o `waitFor` andam no
 * tempo de verdade.
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

const STATS = {
  tickets: {
    total: 16, open: 3, in_progress: 2, awaiting: 1, resolved: 4, closed: 5, cancelled: 1,
    by_priority_critical: 2, by_priority_high: 3, by_priority_medium: 4, by_priority_low: 7,
  },
  surveys: { total: 5, average_rating: 8.4 },
  sla: { response_breached: 1, resolve_breached: 2 },
};

function relatorio(total: number) {
  return {
    period_days: 30,
    start_date: "2026-10-01",
    end_date: "2026-10-30",
    timezone: "America/Recife",
    total_tickets: total,
    tickets_by_day: [{ date: "2026-10-30", count: total }],
    tickets_by_category: [{ category: "Hardware", count: total }],
    sla_compliance: [
      { priority: "critical", total: 2, breached: 1, compliance_rate: 50 },
      { priority: "high", total: 0, breached: 0, compliance_rate: 100 },
    ],
    csat_distribution: [], csat_average: null, recommend_average: null,
    avg_resolution_by_priority: [], avg_first_response_by_priority: [], csat_by_day: [],
    tickets_by_product: [], tickets_by_weekday: [], tickets_by_hour: [],
    oldest_open_tickets: [], technicians_dist: [], reopened_count: 0, reopen_rate: 0,
    sla_justifications: [], comparison: null,
  };
}

const TECH_LIST = {
  period_days: 30,
  technicians: [
    {
      technician_id: "tech1", technician_name: "Ana Silva", total_assigned: 5, resolved: 3,
      open_count: 2, sla_breached: 1, sla_compliance_rate: 80, avg_resolution_hours: 4,
      csat_average: 9, csat_count: 2,
    },
    {
      technician_id: "tech2", technician_name: "Bruno Lima", total_assigned: 0, resolved: 0,
      open_count: 0, sla_breached: 0, sla_compliance_rate: 100, avg_resolution_hours: null,
      csat_average: null, csat_count: 0,
    },
  ],
};

/** Um erro no formato do axios, com o `detail` da API. */
function erroDaApi(status: number, detail: string) {
  return Object.assign(new Error("falhou"), {
    isAxiosError: true,
    response: { status, data: { detail } },
  });
}

function padrao() {
  vi.mocked(dashboardService.getDashboardStats).mockResolvedValue(STATS as never);
  vi.mocked(reportService.getReports).mockResolvedValue(relatorio(16) as never);
  vi.mocked(reportService.getTechnicianListReport).mockResolvedValue(TECH_LIST as never);
  vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue({
    ...TECH_LIST.technicians[0], period_days: 30, in_progress: 1,
    tickets_by_day: [{ date: "2026-10-30", count: 2 }],
  } as never);
}

function montar() {
  return render(
    <MemoryRouter>
      <AdminDashboard />
    </MemoryRouter>,
  );
}

const periodo = () => screen.getByRole("combobox", { name: "Período" });
const AVISO = "Aguardando um período válido — corrija as datas acima.";

/** O filtro de técnico: botão cujo nome soma o rótulo "Técnico" e o valor. */
const filtroDeTecnico = () => screen.getByRole("button", { name: /^Técnico / });

/** Inverte o intervalo personalizado: início depois do fim. */
function inverterIntervalo() {
  escolherNoMenu(periodo(), "Personalizado");
  fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-10-20" } });
  fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-10" } });
}

/** O intervalo pedido na última chamada de `getReports`. */
function ultimoIntervaloDoRelatorio() {
  const chamadas = vi.mocked(reportService.getReports).mock.calls;
  return chamadas[chamadas.length - 1][0];
}
function ultimoIntervaloDosTecnicos() {
  const chamadas = vi.mocked(reportService.getTechnicianListReport).mock.calls;
  return chamadas[chamadas.length - 1][0];
}

describe("AdminDashboard — os filtros pedem dias de calendário", () => {
  it("abre em Últimos 30 dias e manda o MESMO intervalo ao relatório e à equipe", async () => {
    padrao();
    montar();
    await waitFor(() => expect(reportService.getReports).toHaveBeenCalled());
    const esperado = { start_date: "2026-10-01", end_date: "2026-10-30" };
    expect(ultimoIntervaloDoRelatorio()).toEqual(esperado);
    expect(ultimoIntervaloDosTecnicos()).toEqual(esperado);
    // Nada de `period`: os dias são os do calendário.
    expect(ultimoIntervaloDoRelatorio()).not.toHaveProperty("period");
  });

  it.each([
    ["Hoje", { start_date: "2026-10-30", end_date: "2026-10-30" }],
    ["Ontem", { start_date: "2026-10-29", end_date: "2026-10-29" }],
    ["Últimos 7 dias", { start_date: "2026-10-24", end_date: "2026-10-30" }],
    ["Este mês", { start_date: "2026-10-01", end_date: "2026-10-30" }],
    ["Mês passado", { start_date: "2026-09-01", end_date: "2026-09-30" }],
  ])("%s pede %o aos dois relatórios", async (rotulo, esperado) => {
    padrao();
    montar();
    await waitFor(() => expect(reportService.getReports).toHaveBeenCalled());

    escolherNoMenu(periodo(), rotulo);
    await waitFor(() => expect(ultimoIntervaloDoRelatorio()).toEqual(esperado));
    expect(ultimoIntervaloDosTecnicos()).toEqual(esperado);
  });

  it("Hoje às 22:30 de Recife ainda é o dia de Recife, não o de UTC", async () => {
    vi.setSystemTime(new Date("2026-10-31T01:30:00Z"));
    padrao();
    montar();
    escolherNoMenu(periodo(), "Hoje");
    await waitFor(() =>
      expect(ultimoIntervaloDoRelatorio()).toEqual({
        start_date: "2026-10-30",
        end_date: "2026-10-30",
      }),
    );
  });

  it("Personalizado manda as datas escolhidas, também para o detalhe do técnico", async () => {
    padrao();
    montar();
    escolherNoMenu(periodo(), "Personalizado");
    fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-08-03" } });
    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-08-17" } });

    const esperado = { start_date: "2026-08-03", end_date: "2026-08-17" };
    await waitFor(() => expect(ultimoIntervaloDoRelatorio()).toEqual(esperado));
    expect(ultimoIntervaloDosTecnicos()).toEqual(esperado);

    fireEvent.click(await screen.findByRole("row", { name: /Ana Silva — clique para filtrar/ }));
    await waitFor(() =>
      expect(reportService.getTechnicianDetailReport).toHaveBeenLastCalledWith(esperado, "tech1"),
    );
  });

  it("datas invertidas: aviso no seletor, nenhum pedido e nenhum número antigo", async () => {
    padrao();
    montar();
    await screen.findByText("Conformidade SLA — Últimos 30 dias");
    escolherNoMenu(periodo(), "Personalizado");
    // A primeira ponta sozinha ainda forma um intervalo válido (20/10 a
    // 30/10), e ele é pedido — é o comportamento certo. O que se mede é o
    // passo seguinte, que inverte o intervalo.
    fireEvent.change(screen.getByLabelText("Data inicial"), { target: { value: "2026-10-20" } });
    await waitFor(() =>
      expect(ultimoIntervaloDoRelatorio()).toEqual({ start_date: "2026-10-20", end_date: "2026-10-30" }),
    );
    expect(await screen.findByRole("img", { name: /Hardware: 16/ })).toBeInTheDocument();
    const pedidos = vi.mocked(reportService.getReports).mock.calls.length;

    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-10" } });

    expect(await screen.findByText("A data inicial não pode ser posterior à data final."))
      .toBeInTheDocument();
    expect(reportService.getReports).toHaveBeenCalledTimes(pedidos);
    // O relatório dos 30 dias saiu da tela: nada de categoria "Hardware 16".
    expect(screen.queryByRole("img", { name: /Hardware: 16/ })).not.toBeInTheDocument();
  });
});

describe("AdminDashboard — cada bloco falha sozinho", () => {
  it("relatório do período falha: aviso com o motivo, e o resto continua", async () => {
    padrao();
    vi.mocked(reportService.getReports).mockRejectedValue(
      erroDaApi(500, "Erro interno no relatório"),
    );
    montar();

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Relatório do período")).toBeInTheDocument();
    expect(within(aviso).getByText("Erro interno no relatório")).toBeInTheDocument();
    // Seletor à vista, indicadores acumulados e equipe desenhados.
    expect(periodo()).toBeInTheDocument();
    expect(await screen.findByText("Total de tickets")).toBeInTheDocument();
    expect(await screen.findByText("Performance da equipe — Últimos 30 dias")).toBeInTheDocument();
    // Nenhum "0" fabricado no lugar do relatório.
    expect(screen.queryByText("Sem categorias no período")).not.toBeInTheDocument();
  });

  it("indicadores gerais falham: o relatório do período continua", async () => {
    padrao();
    vi.mocked(dashboardService.getDashboardStats).mockRejectedValue(erroDaApi(503, ""));
    montar();

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Indicadores gerais")).toBeInTheDocument();
    expect(await screen.findByText("Conformidade SLA — Últimos 30 dias")).toBeInTheDocument();
    expect(screen.queryByText("Total de tickets")).not.toBeInTheDocument();
  });

  it("equipe falha: relatório e indicadores continuam", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianListReport).mockRejectedValue(
      erroDaApi(422, "Deve ser maior ou igual a 7"),
    );
    montar();

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Desempenho da equipe")).toBeInTheDocument();
    expect(within(aviso).getByText("Deve ser maior ou igual a 7")).toBeInTheDocument();
    expect(await screen.findByText("Total de tickets")).toBeInTheDocument();
    expect(screen.queryByText(/Performance da equipe/)).not.toBeInTheDocument();
  });

  it("detalhe do técnico falha: aviso próprio, e a tabela da equipe fica", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianDetailReport).mockRejectedValue(erroDaApi(500, "x"));
    montar();
    fireEvent.click(await screen.findByRole("row", { name: /Ana Silva — clique para filtrar/ }));

    const aviso = await screen.findByRole("alert");
    expect(within(aviso).getByText("Atendimentos do técnico")).toBeInTheDocument();
    expect(screen.getByText("Performance da equipe — Últimos 30 dias")).toBeInTheDocument();
  });

  it("Tentar de novo recupera o bloco e limpa o aviso", async () => {
    padrao();
    vi.mocked(reportService.getReports)
      .mockRejectedValueOnce(erroDaApi(500, "Erro interno"))
      .mockResolvedValue(relatorio(16) as never);
    montar();

    const aviso = await screen.findByRole("alert");
    fireEvent.click(within(aviso).getByRole("button", { name: "Tentar de novo" }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(await screen.findByRole("img", { name: /Hardware: 16/ })).toBeInTheDocument();
  });

  it("trocar de período depois de uma falha também limpa o aviso", async () => {
    padrao();
    vi.mocked(reportService.getReports)
      .mockRejectedValueOnce(erroDaApi(500, "Erro interno"))
      .mockResolvedValue(relatorio(3) as never);
    montar();
    await screen.findByRole("alert");

    escolherNoMenu(periodo(), "Ontem");
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(await screen.findByRole("img", { name: /Hardware: 3/ })).toBeInTheDocument();
  });
});

describe("AdminDashboard — resposta atrasada", () => {
  it("o relatório do período anterior, chegando depois, não toma o lugar do atual", async () => {
    padrao();
    let soltarAntigo!: (v: unknown) => void;
    vi.mocked(reportService.getReports)
      .mockImplementationOnce(() => new Promise((res) => { soltarAntigo = res; }) as never)
      .mockResolvedValueOnce(relatorio(7) as never);
    montar();

    escolherNoMenu(periodo(), "Últimos 7 dias");
    expect(await screen.findByRole("img", { name: /Hardware: 7/ })).toBeInTheDocument();

    await act(async () => soltarAntigo(relatorio(99)));
    expect(screen.getByRole("img", { name: /Hardware: 7/ })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Hardware: 99/ })).not.toBeInTheDocument();
  });
});

describe("AdminDashboard — indicadores", () => {
  it("SLA sem chamados no período mostra «—», não 100%", async () => {
    padrao();
    montar();
    const titulo = await screen.findByText("Conformidade SLA — Últimos 30 dias");
    const bloco = titulo.closest(".rounded-xl") as HTMLElement;

    // Alta veio com total 0 e compliance_rate 100 da API.
    expect(within(bloco).getByText("Alta")).toBeInTheDocument();
    expect(within(bloco).getByText("(sem chamados)")).toBeInTheDocument();
    expect(within(bloco).queryByText("100%")).not.toBeInTheDocument();
    // Só a prioridade com chamado tem barra de medição.
    const barras = within(bloco).getAllByRole("meter");
    expect(barras).toHaveLength(1);
    expect(barras[0]).toHaveAccessibleName("Conformidade de SLA — Crítica");
  });

  it("técnico sem chamado atribuído no período: conformidade «—», sem barra", async () => {
    padrao();
    montar();
    const linha = await screen.findByRole("row", { name: /Bruno Lima/ });
    expect(within(linha).getByText("— sem chamados")).toBeInTheDocument();
    expect(within(linha).queryByRole("meter")).not.toBeInTheDocument();
    expect(within(linha).queryByText("100%")).not.toBeInTheDocument();
  });

  it("os indicadores do topo dizem que são acumulados e não recarregam com o período", async () => {
    padrao();
    montar();
    expect(
      await screen.findByText("Acumulado desde o início do sistema — não muda com o período escolhido."),
    ).toBeInTheDocument();
    expect(screen.getByText("Tickets por Prioridade — acumulado")).toBeInTheDocument();
    await waitFor(() => expect(dashboardService.getDashboardStats).toHaveBeenCalledTimes(1));

    escolherNoMenu(periodo(), "Ontem");
    await waitFor(() => expect(reportService.getReports).toHaveBeenCalledTimes(2));
    expect(dashboardService.getDashboardStats).toHaveBeenCalledTimes(1);
  });

  it("o seletor mostra os dias que o período cobre", async () => {
    padrao();
    montar();
    escolherNoMenu(periodo(), "Mês passado");
    expect(await screen.findByText("01/09 – 30/09 · horário de Recife")).toBeInTheDocument();
  });
});

describe("AdminDashboard — intervalo inválido não é carregamento (V1)", () => {
  it("os blocos do período dizem que esperam um período válido, sem anel de carregando", async () => {
    padrao();
    montar();
    await screen.findByText("Conformidade SLA — Últimos 30 dias");
    await screen.findByRole("row", { name: /Ana Silva/ });
    const relatorios = vi.mocked(reportService.getReports).mock.calls.length;
    const listas = vi.mocked(reportService.getTechnicianListReport).mock.calls.length;

    inverterIntervalo();

    expect(await screen.findByText("A data inicial não pode ser posterior à data final."))
      .toBeInTheDocument();
    // Nenhum bloco do período fica girando: não há pedido a esperar.
    expect(screen.queryAllByRole("status", { name: "Carregando..." })).toHaveLength(0);
    expect(screen.queryByText("Carregando…")).not.toBeInTheDocument();
    expect(screen.getAllByText(AVISO).length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Período inválido")).toBeInTheDocument();
    // E nada foi pedido com o intervalo invertido (a 1ª ponta, 20/10–30/10, é válida).
    const validos = (n: number) => n + 1;
    expect(reportService.getReports).toHaveBeenCalledTimes(validos(relatorios));
    expect(reportService.getTechnicianListReport).toHaveBeenCalledTimes(validos(listas));
    // Nenhum número de antes: a equipe saiu da tela.
    expect(screen.queryByRole("row", { name: /Ana Silva/ })).not.toBeInTheDocument();
  });

  it("corrigir o intervalo volta a carregar e tira o aviso", async () => {
    padrao();
    montar();
    await screen.findByText("Conformidade SLA — Últimos 30 dias");
    inverterIntervalo();
    await screen.findByText("A data inicial não pode ser posterior à data final.");

    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-25" } });

    await waitFor(() =>
      expect(ultimoIntervaloDoRelatorio()).toEqual({ start_date: "2026-10-20", end_date: "2026-10-25" }),
    );
    expect(await screen.findByRole("img", { name: /Hardware: 16/ })).toBeInTheDocument();
    expect(await screen.findByRole("row", { name: /Ana Silva/ })).toBeInTheDocument();
    expect(screen.queryByText(AVISO)).not.toBeInTheDocument();
  });
});

describe("AdminDashboard — o filtro de técnico não some (V2)", () => {
  it("carregando: o filtro aparece, desabilitado", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianListReport).mockImplementation(() => new Promise(() => {}));
    montar();
    const filtro = filtroDeTecnico();
    expect(filtro).toHaveAccessibleName("Técnico Todos os técnicos");
    expect(filtro).toBeDisabled();
  });

  it("falha da API: o filtro aparece, desabilitado", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianListReport).mockRejectedValue(erroDaApi(500, "x"));
    montar();
    await screen.findByRole("alert");
    expect(filtroDeTecnico()).toBeDisabled();
  });

  it("intervalo inválido: o filtro aparece, desabilitado", async () => {
    padrao();
    montar();
    await waitFor(() => expect(filtroDeTecnico()).toBeEnabled());
    inverterIntervalo();
    await screen.findByText("A data inicial não pode ser posterior à data final.");
    expect(filtroDeTecnico()).toBeDisabled();
  });

  it("Tentar de novo: desabilitado enquanto pede, habilitado com a lista", async () => {
    padrao();
    let soltar!: (v: unknown) => void;
    vi.mocked(reportService.getTechnicianListReport)
      .mockRejectedValueOnce(erroDaApi(500, "x"))
      .mockImplementationOnce(() => new Promise((res) => { soltar = res; }) as never);
    montar();
    const aviso = await screen.findByRole("alert");
    fireEvent.click(within(aviso).getByRole("button", { name: "Tentar de novo" }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(filtroDeTecnico()).toBeDisabled();
    await act(async () => soltar(TECH_LIST));
    expect(filtroDeTecnico()).toBeEnabled();
  });

  it("lista vazia: o filtro aparece, só com «Todos os técnicos»", async () => {
    padrao();
    vi.mocked(reportService.getTechnicianListReport).mockResolvedValue(
      { period_days: 30, technicians: [] } as never,
    );
    montar();
    await waitFor(() => expect(reportService.getTechnicianListReport).toHaveBeenCalled());
    await waitFor(() => expect(filtroDeTecnico()).toBeEnabled());
    fireEvent.click(filtroDeTecnico());
    const opcoes = within(screen.getByRole("listbox")).getAllByRole("option");
    // Só "Todos os técnicos": nenhum nome. (O filtro repete a opção como a
    // linha de limpar do `Selector`, e isso já era assim antes desta tela.)
    expect(new Set(opcoes.map((o) => o.textContent))).toEqual(new Set(["Todos os técnicos"]));
  });

  it("a escolha sobrevive ao intervalo inválido e vale para o intervalo corrigido", async () => {
    padrao();
    montar();
    fireEvent.click(await screen.findByRole("row", { name: /Ana Silva — clique para filtrar/ }));
    await waitFor(() => expect(filtroDeTecnico()).toHaveAccessibleName("Técnico Ana Silva"));

    inverterIntervalo();
    await screen.findByText("A data inicial não pode ser posterior à data final.");
    expect(filtroDeTecnico()).toHaveAccessibleName("Técnico Ana Silva");
    expect(filtroDeTecnico()).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Data final"), { target: { value: "2026-10-25" } });
    await waitFor(() =>
      expect(reportService.getTechnicianDetailReport).toHaveBeenLastCalledWith(
        { start_date: "2026-10-20", end_date: "2026-10-25" }, "tech1",
      ),
    );
    await waitFor(() => expect(filtroDeTecnico()).toBeEnabled());
    expect(filtroDeTecnico()).toHaveAccessibleName("Técnico Ana Silva");
  });
});
