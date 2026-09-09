import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
import { ICON_PATHS } from "../../components/ui";
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

  const r = render(
    <MemoryRouter>
      <AdminDashboard />
    </MemoryRouter>,
  );
  await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
  return r;
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

/**
 * ── Segunda passada: os 12 `<svg>` soltos, e o nome do que a linha faz ──
 *
 * A primeira passada migrou a COR dos gráficos e parou aí. O que ficou de
 * fora tem prova própria aqui, e nenhum destes casos lê classe: o jsdom não
 * aplica CSS nenhum, então uma afirmação sobre classe passa com o elemento
 * invisível e reprova com ele visível — mede o texto do atributo, não a tela.
 * O que estes casos leem é o que sobrevive sem CSS: o traçado do desenho, a
 * escala em que ele é desenhado, o papel declarado e o nome acessível.
 */
describe("AdminDashboard — ícones e nome acessível", () => {
  it("a estrela do CSAT é o CONTORNO do pacote, não um desenho preenchido próprio", async () => {
    // Decisão D9.1. Aqui vivia `viewBox="0 0 20 20" fill="currentColor"` com
    // um traçado que só existia nesta tela — outra família de ícone. A E21
    // barrou a troca automática justamente porque nada acusa o erro: trocar
    // por `Icon` às cegas renderiza em escala errada e sem preenchimento, e
    // `ICON_PATHS` é mapa de texto onde todo texto cabe. Este caso fecha o
    // buraco pelo lado do DOM: o `d` desenhado tem de ser o do pacote.
    await montar();
    const linhaCsat = screen.getByText("9.0").parentElement!;
    const estrela = linhaCsat.querySelector("svg")!;
    expect(estrela.querySelector("path")!.getAttribute("d")).toBe(ICON_PATHS.star);
    expect(estrela.getAttribute("fill")).toBe("none");
    expect(estrela.getAttribute("viewBox")).toBe("0 0 24 24");
  });

  it("todo ícone da tela desenha na escala do pacote — nenhum sobrou de outra família", async () => {
    // A prova de que os 12 saíram, e a rede que pega o próximo: qualquer
    // `<svg>` de `viewBox` diferente ou com preenchimento reprova aqui,
    // inclusive um que alguém acrescente amanhã.
    const { container } = await montar();
    const svgs = [...container.querySelectorAll("svg")];
    expect(svgs.length).toBeGreaterThanOrEqual(11);
    for (const svg of svgs) {
      expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
      expect(svg.getAttribute("fill")).toBe("none");
      // Ícone é decoração: o rótulo ao lado é que carrega o significado. Um
      // `<svg>` que entra no nome acessível anuncia "imagem" sem nome nenhum.
      expect(svg.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("o calendário do intervalo personalizado também é do pacote", async () => {
    // Ele só existe no ramo `periodKey === "custom"`, que nenhum caso
    // alcançava — um `<svg>` fora de qualquer rede é um `<svg>` que volta.
    const { container } = await montar();
    const antes = container.querySelectorAll("svg").length;

    fireEvent.change(screen.getByRole("combobox", { name: "Período" }), {
      target: { value: "custom" },
    });
    await waitFor(() =>
      expect(container.querySelectorAll("svg").length).toBeGreaterThan(antes),
    );

    const tracados = [...container.querySelectorAll("svg path")].map((p) =>
      p.getAttribute("d"),
    );
    expect(tracados).toContain(ICON_PATHS.calendar);
  });

  it("os dois filtros do cabeçalho têm nome, e cada um o do SEU tipo de lista", async () => {
    // O defeito que a D9.2 fecha: o `FilterSelect` não repassava `label`, e os
    // dois filtros deste cabeçalho se anunciavam pelo VALOR — "Todos os
    // técnicos" e "Este Mês" — sem dizer de que filtro eram.
    //
    // Os dois controles são diferentes de propósito. O período tem oito
    // opções fixas no código: `<select>` nativo, que se lê por `combobox`. Os
    // técnicos vêm da rede e crescem com a equipe: `Selector variant="filter"`,
    // cujo nome soma o rótulo ao valor visível — daí "Técnico Todos os
    // técnicos", e daí ele NÃO ser um `combobox`.
    await montar();

    expect(screen.getByRole("combobox", { name: "Período" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Técnico Todos os técnicos" }),
    ).toBeInTheDocument();
  });

  it("o período não oferece linha vazia — e isso é o que impede a queda", async () => {
    // A linha de limpar do `FilterSelect` devolvia `""`, e
    // `PERIOD_OPTIONS.find((p) => p.key === "")!.days` lia `days` de
    // `undefined`: a tela caía. O `<select>` nativo não tem essa linha, e as
    // oito opções são exatamente as oito do código.
    await montar();

    const rotulos = within(screen.getByRole("combobox", { name: "Período" }))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(rotulos).toEqual([
      "Hoje",
      "Ontem",
      "Esta Semana",
      "Este Mês",
      "Mês Passado",
      "Este Trimestre",
      "Este Ano",
      "Personalizado",
    ]);
  });

  it("a linha do técnico diz, no nome acessível, o que o clique faz", async () => {
    // O `<tr onClick>` sem teclado é defeito de PRODUTO e continua lá — este
    // caso não o esconde. O que ele prende é o que dava para consertar sem
    // redesenhar: antes a linha se anunciava pela colagem das sete células
    // ("Ana Silva 5 3 2 80% 4.0h 9.0 (2)") e não dizia que era clicável nem o
    // que o clique faria. Agora diz, e o texto acompanha o estado.
    // O clique dispara o detalhe do técnico; sem este retorno o efeito quebra
    // no `.then` de `undefined` e o caso reprovaria por outro motivo.
    vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue({
      technician_id: "tech1",
      technician_name: "Ana Silva",
      tickets_by_day: [{ date: "2026-09-01", count: 3 }],
    } as never);

    await montar();
    const linha = screen.getByRole("row", {
      name: "Ana Silva — clique para filtrar o painel por este técnico",
    });

    fireEvent.click(linha);

    await waitFor(() =>
      expect(
        screen.getByRole("row", {
          name: "Ana Silva — filtro ativo, clique para remover",
        }),
      ).toBeInTheDocument(),
    );
  });

  /*
   * NÃO existe aqui um caso de `role="progressbar"`, e a ausência é
   * deliberada — havia um, e ele saiu.
   *
   * O agente que fez a segunda passada desta tela declarou papel nas três
   * barras desenhadas, citando a §29, e escreveu o caso que o prendia. Isso
   * atropelou uma regra já fixada em `barra-de-sla.test.ts`, que proíbe
   * `role="progressbar"` neste arquivo com o motivo escrito: **as barras de
   * categoria vão de zero ao MAIOR VALOR DA LISTA**, e uma barra cujo máximo
   * é “o maior que aparecer hoje” não mede progresso — mede tamanho relativo.
   *
   * Os outros dois casos (conformidade de SLA, 0 a 100) são discutíveis: uma
   * porcentagem dentro de faixa conhecida é medição, e o papel de medição é
   * `meter`, não `progressbar`. A distinção foi levada ao operador; até ela
   * voltar, vale a regra antiga, que é a mais restritiva.
   *
   * Dois testes em conflito: ganha o que registra uma decisão, não o que
   * registra uma melhoria.
   */
});
