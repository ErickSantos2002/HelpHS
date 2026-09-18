import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

/**
 * O `ResponsiveContainer` mede o pai com `ResizeObserver`, e num DOM sem
 * layout o pai tem largura zero — o Recharts então não desenha **nada**, e um
 * caso que só olhasse a tela passaria por vazio.
 *
 * Trocá-lo por um clone do filho com largura e altura cravadas faz o gráfico de
 * verdade renderizar: os `fill` das barras, as marcas do eixo e a legenda saem
 * no SVG, que é onde as decisões desta migração são observáveis. O resto do
 * Recharts é o de produção — o que se mede aqui é o gráfico, não um duplo.
 */
vi.mock("recharts", async (importOriginal) => {
  const real = await importOriginal<typeof import("recharts")>();
  const { cloneElement } = await import("react");
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      cloneElement(children, { width: 640, height: 260 } as never),
  };
});

/*
 * A tela desenha doze gráficos de verdade em cada montagem, e a árvore é
 * compartilhada com outras sessões — o padrão de 5s do Vitest estoura por
 * carga da máquina, não por defeito. O limite maior é do arquivo, e não de um
 * caso escolhido a dedo, para o motivo ficar num lugar só.
 */
vi.setConfig({ testTimeout: 20000 });

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", role: "admin", name: "Admin" } }),
}));
vi.mock("../../services/reportService", () => ({
  getReports: vi.fn(),
  getTechnicianListReport: vi.fn(),
  getTechnicianDetailReport: vi.fn(),
  exportReportsUrl: () => "/api/v1/reports/export",
}));

import ReportsPage from "../../pages/reports/ReportsPage";
import * as reportService from "../../services/reportService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Uma rampa de dez hexadecimais cravados** para a satisfação (`#dc2626` …
 * `#22c55e`), que falhava a separação por construção — degraus vizinhos são
 * próximos de propósito, e o eixo vermelho-verde é o que colapsa em protanopia
 * e deuteranopia. **Duas séries de status pintadas com a §16** (verde de
 * sucesso, âmbar de aviso), que a E18 mediu não caber. **Três séries temporais
 * da mesma natureza em três cores.** E o cromo — eixo, grade e dica — escolhido
 * por `theme === "dark" ? … : …` em JavaScript, com o `gridColor` copiado do
 * fundo da dica.
 *
 * Os casos daqui são sobre **as decisões**, não sobre o desenho: as bordas das
 * três faixas, o número existir no rótulo, a legenda existir. São essas que
 * quebram numa reescrita distraída, e é por elas que a tela responde.
 */
/*
 * As contagens são múltiplos de 11 de propósito: o eixo vertical do Recharts
 * então marca 0, 30, 60, 90, 120 — nenhum deles igual a uma nota de 1 a 10. Se
 * fossem contagens de um dígito, a marca "3" do eixo vertical seria
 * indistinguível da nota 3, e o caso do número no rótulo passaria mesmo com o
 * rótulo apagado.
 */
const DIST_CSAT = Array.from({ length: 10 }, (_, i) => ({
  rating: i + 1,
  count: (10 - i) * 11,
}));

const RELATORIO: reportService.ReportData = {
  period_days: 30,
  total_tickets: 42,
  tickets_by_day: [
    { date: "2026-09-01", count: 3 },
    { date: "2026-09-02", count: 5 },
  ],
  tickets_by_category: [
    { category: "hardware", count: 7 },
    { category: "network", count: 4 },
  ],
  sla_compliance: [
    { priority: "critical", total: 4, breached: 1, compliance_rate: 75 },
    { priority: "high", total: 6, breached: 0, compliance_rate: 100 },
  ],
  csat_distribution: DIST_CSAT,
  csat_average: 8.1,
  recommend_average: 9,
  avg_resolution_by_priority: [{ priority: "critical", avg_hours: 3 }],
  avg_first_response_by_priority: [{ priority: "high", avg_hours: 1.5 }],
  csat_by_day: [
    { date: "2026-09-01", avg_rating: 7.5, count: 2 },
    { date: "2026-09-02", avg_rating: 9, count: 3 },
  ],
  tickets_by_product: [{ product_name: "Notebook Dell", count: 6 }],
  tickets_by_weekday: [
    { weekday: 1, count: 5 },
    { weekday: 6, count: 2 },
  ],
  tickets_by_hour: [
    { hour: 3, count: 1 },
    { hour: 9, count: 4 },
    { hour: 14, count: 6 },
    { hour: 20, count: 2 },
  ],
  oldest_open_tickets: [
    {
      ticket_id: "t1",
      protocol: "HS-2026-0001",
      title: "Impressora não imprime",
      priority: "high",
      category: "hardware",
      status: "awaiting_client",
      age_hours: 50,
      sla_breached: true,
      assignee_name: "Ana",
    },
  ],
  technicians_dist: [
    { technician_name: "Ana", total: 9, resolved: 6, open_count: 3 },
  ],
  reopened_count: 1,
  reopen_rate: 2,
  sla_justifications: [],
  comparison: null,
};

/**
 * `montar()` continua sem argumento para os casos que já existiam; o override
 * serve às seções que só aparecem com dado — a de justificativas de SLA é
 * desenhada só quando houve violação no período, então o fixture padrão a
 * mantém fora da tela de propósito.
 */
async function montar(ajuste: Partial<reportService.ReportData> = {}) {
  vi.mocked(reportService.getReports).mockResolvedValue({ ...RELATORIO, ...ajuste });
  vi.mocked(reportService.getTechnicianListReport).mockResolvedValue({
    period_days: 30,
    technicians: [],
  });
  vi.mocked(reportService.getTechnicianDetailReport).mockResolvedValue(
    null as never,
  );

  const { container } = render(<ReportsPage />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Distribuição CSAT (1–10)" }),
    ).toBeInTheDocument(),
  );
  return container;
}

/** A linha da tabela de chamados antigos, pelo protocolo. */
function linhaDoChamado(): HTMLElement {
  const linha = screen.getByText("HS-2026-0001").closest("tr");
  if (!linha) throw new Error("o protocolo não está numa linha de tabela");
  return linha as HTMLElement;
}

/** O cartão de um gráfico, pelo título que a pessoa lê. */
function cartao(titulo: string): HTMLElement {
  const h2 = screen.getByRole("heading", { name: titulo });
  const card = h2.parentElement?.parentElement;
  if (!card) throw new Error(`o cartão de "${titulo}" não tem envoltório`);
  return card as HTMLElement;
}

/**
 * Os preenchimentos das barras de um cartão, na ordem em que saem no SVG.
 *
 * A espera não é cerimônia: a barra entra animada, e no primeiro quadro ela tem
 * altura zero — o `Rectangle` do Recharts devolve `null` nesse estado. Sem
 * esperar, a lista vem vazia e **um caso sobre cor passaria por não haver cor
 * nenhuma**, que é a pior forma de um caso passar.
 */
async function preenchimentosDas(card: HTMLElement): Promise<string[]> {
  await waitFor(() =>
    expect(
      card.querySelectorAll("path.recharts-rectangle").length,
    ).toBeGreaterThan(0),
  );
  return [...card.querySelectorAll("path.recharts-rectangle")].map(
    (p) => p.getAttribute("fill") ?? "",
  );
}

/**
 * O texto de TODAS as marcas de eixo de um cartão, os dois eixos juntos.
 *
 * Juntos porque separar não é possível aqui: o motor de seletores do happy-dom
 * casa `.recharts-xAxis` e casa `.recharts-cartesian-axis-tick-value`, mas
 * devolve zero para os dois juntos e zero a partir de uma raiz SVG. Um seletor
 * que devolve lista vazia faria um caso sobre "o número está no rótulo" afirmar
 * que nenhum rótulo é o esperado, em silêncio — daí a contagem do eixo vertical
 * ser escolhida, no dado de prova, para não colidir com as notas 1–10.
 */
async function marcasDeEixo(card: HTMLElement): Promise<string[]> {
  // O eixo só sai depois de o gráfico ter medido, junto com as barras.
  await preenchimentosDas(card);
  return [...card.querySelectorAll(".recharts-cartesian-axis-tick-value")].map(
    (t) => t.textContent?.trim() ?? "",
  );
}

describe("ReportsPage — a escala de satisfação", () => {
  it("as dez notas caem nas TRÊS faixas que o operador decidiu", async () => {
    // As bordas são o que quebra numa reescrita distraída: 4 e 5, 7 e 8. Uma
    // rampa de dez cores passaria neste caso só se cada nota tivesse cor
    // própria — e é exatamente isso que a decisão proibiu.
    await montar();
    const cores = await preenchimentosDas(cartao("Distribuição CSAT (1–10)"));

    expect(cores).toHaveLength(10);
    expect(cores.slice(0, 4)).toEqual(Array(4).fill("var(--fill-danger)"));
    expect(cores.slice(4, 7)).toEqual(Array(3).fill("var(--fill-warning)"));
    expect(cores.slice(7, 10)).toEqual(Array(3).fill("var(--fill-success)"));
  });

  it("são TRÊS cores distintas, e nenhuma é hexadecimal cravado", async () => {
    // A rampa antiga tinha dez valores diferentes; se alguém a trouxer de
    // volta, este caso reprova antes de o de cima chegar às bordas.
    await montar();
    const cores = await preenchimentosDas(cartao("Distribuição CSAT (1–10)"));

    expect(new Set(cores).size).toBe(3);
    for (const c of cores) expect(c).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  });

  it("o NÚMERO da nota está escrito no rótulo, nas dez barras", async () => {
    // É este caso que sustenta a decisão inteira. Três faixas de cor não
    // satisfazem 1.4.1 sozinhas — só têm menos passos que dez. O que resolve é
    // a nota estar escrita, e o Recharts esconde marca que se sobreponha a
    // menos que se peça o contrário.
    await montar();
    const marcas = await marcasDeEixo(cartao("Distribuição CSAT (1–10)"));
    const notas = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

    expect(marcas).toEqual(expect.arrayContaining(notas));
  });
});

describe("ReportsPage — o gráfico de status", () => {
  it("tem legenda, e ela NOMEIA cada série", async () => {
    // Regra da E18, e ela deixou de ser conveniência no dia em que a cor deixou
    // de significar: enquanto o verde era o verde, quem conhecia o sistema lia
    // a cor. Com a paleta categórica, quem diz o que a série é são estas
    // palavras — e nada mais na tela as diz.
    await montar();
    const card = cartao("Distribuição de tickets por técnico");
    const legenda = [...card.querySelectorAll(".recharts-legend-item-text")].map(
      (t) => t.textContent?.trim(),
    );

    // Conjunto, e não sequência: a ordem em que o Recharts empilha os itens é
    // detalhe dele. O que a E18 exige é que as duas séries tenham NOME.
    expect(legenda).toHaveLength(2);
    expect(legenda).toEqual(expect.arrayContaining(["Resolvidos", "Em aberto"]));
    // E o nome é o da pessoa, não a chave do backend.
    expect(legenda).not.toContain("open_count");
  });

  it("as séries pegam a tabela fixa da E18, e não a tinta semântica", async () => {
    // `resolved` é o quinto slot e `open` é o primeiro — escrito à mão na E18
    // justamente para que "Resolvidos" não mude de cor entre o painel e o
    // relatório. Verde e âmbar aqui seriam a §16 aplicada a gráfico, que a E18
    // mediu não caber.
    await montar();
    const cores = await preenchimentosDas(
      cartao("Distribuição de tickets por técnico"),
    );

    expect(new Set(cores)).toEqual(new Set(["var(--chart-5)", "var(--chart-1)"]));
  });
});

describe("ReportsPage — as séries temporais", () => {
  it("os gráficos de contagem ao longo do tempo usam UMA cor só", async () => {
    // Eram `#6366f1` aqui, `#f59e0b` na tendência e `#22c55e` no detalhe do
    // técnico — três gráficos da mesma natureza em três cores, e a diferença
    // não afirmava nada. Regra do operador: mesma medida, uma cor.
    const container = await montar();
    await waitFor(() =>
      expect(
        container.querySelectorAll("path.recharts-area-curve").length,
      ).toBeGreaterThan(1),
    );
    const tracos = [
      ...container.querySelectorAll("path.recharts-area-curve"),
    ].map((p) => p.getAttribute("stroke"));

    expect(new Set(tracos).size).toBe(1);
    expect(tracos[0]).toBe("var(--chart-1)");
  });
});

describe("ReportsPage — os filtros da barra", () => {
  /**
   * O defeito que a D9.2 fecha: o `FilterSelect` não repassava `label`, e os
   * três filtros desta barra se anunciavam pelo VALOR escolhido — "Últimos 30
   * dias", "Hardware", "Alta" — sem dizer de que filtro cada um era. São três
   * `<select>` nativos porque as três listas são fixas no código (cinco
   * períodos, oito categorias, quatro prioridades) e nenhuma cresce com o
   * banco.
   */
  it("os três filtros têm nome próprio, e não se anunciam pelo valor", async () => {
    await montar();

    expect(screen.getByRole("combobox", { name: "Período" })).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Categoria" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Prioridade" }),
    ).toBeInTheDocument();
  });

  it("o período não oferece linha vazia: escolher um é obrigatório", async () => {
    // A linha de limpar do `FilterSelect` devolvia `""`, que `Number(period)
    // || 30` traduzia de volta para trinta dias enquanto o gatilho anunciava
    // "Período" — a tela mostrava um número e dizia outro.
    await montar();

    const rotulos = within(screen.getByRole("combobox", { name: "Período" }))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(rotulos).toEqual([
      "Últimos 7 dias",
      "Últimos 14 dias",
      "Últimos 30 dias",
      "Últimos 90 dias",
      "Personalizado",
    ]);
  });

  it("o seletor de técnico é o de LISTA LONGA, e leva rótulo mais valor no nome", async () => {
    // Os técnicos vêm da rede e crescem com a equipe: pela D9.2 este é o
    // `Selector variant="filter"`, e não o `<select>` nativo. O nome acessível
    // dele soma o rótulo ao valor visível — "Técnico" mais o que o gatilho
    // mostra —, e é por isso que ele NÃO se lê por `combobox`.
    //
    // O "Ver detalhes de:" ao lado é texto solto e nunca foi `<label>` de
    // nada: sem o `label` do `Selector`, este controle não tinha nome nenhum.
    const user = userEvent.setup();
    await montar();

    // A lista de técnicos só é buscada ao entrar na aba, e `montar` já deixou
    // o dublê devolvendo lista vazia — por isso a troca vem DEPOIS dele.
    vi.mocked(reportService.getTechnicianListReport).mockResolvedValue({
      period_days: 30,
      technicians: [
        {
          technician_id: "t1",
          technician_name: "Ana Silva",
          total_tickets: 3,
          resolved_tickets: 2,
          avg_resolution_hours: 4,
          avg_rating: 4.5,
        },
      ],
    } as never);

    await user.click(screen.getByRole("button", { name: "Por técnico" }));

    expect(
      await screen.findByRole("button", {
        name: "Técnico Selecione um técnico",
      }),
    ).toBeInTheDocument();
  });

  it("categoria e prioridade oferecem, sim, a linha de «todas»", async () => {
    // Aqui o vazio SIGNIFICA algo — "todas" — e é o estado inicial dos dois.
    await montar();

    expect(screen.getByRole("combobox", { name: "Categoria" })).toHaveValue("");
    expect(
      within(screen.getByRole("combobox", { name: "Categoria" })).getByRole(
        "option",
        { name: "Todas as categorias" },
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("combobox", { name: "Prioridade" })).getByRole(
        "option",
        { name: "Todas as prioridades" },
      ),
    ).toBeInTheDocument();
  });
});

describe("ReportsPage — as fontes únicas", () => {
  it("o status da tabela fala a língua do módulo, e não a abreviação local", async () => {
    // O mapa daqui dizia "Aguard. cliente"; o módulo diz "Aguardando cliente".
    // A forma curta existe lá, e é para a coluna de 268px do quadro.
    await montar();
    expect(within(linhaDoChamado()).getByText("Aguardando cliente")).toBeInTheDocument();
    expect(screen.queryByText("Aguard. cliente")).not.toBeInTheDocument();
  });

  it("a categoria e a prioridade da linha saem dos módulos", async () => {
    // Dentro da LINHA, e não na tela toda: "Hardware" e "Alta" também são
    // opção dos dois filtros do cabeçalho. Procurar na tela inteira passava
    // mesmo com a célula mostrando o valor cru do backend — foi a mutação que
    // achou, e não a leitura.
    await montar();
    const linha = within(linhaDoChamado());
    expect(linha.getByText("Hardware")).toBeInTheDocument();
    expect(linha.getByText("Alta")).toBeInTheDocument();
  });

  it("nenhuma cor de gráfico é hexadecimal cravado, em nenhum dos doze", async () => {
    // A varredura de contraste lê CLASSE do Tailwind; cor escrita em atributo
    // de SVG não passa por ela. Foi assim que o eixo reprovou nos dois temas
    // sem aparecer em catraca nenhuma.
    const container = await montar();
    // Esperar as barras do ÚLTIMO gráfico da página: sem isso o SVG ainda está
    // meio desenhado, e "não achei hexadecimal" seria "não achei nada".
    await preenchimentosDas(cartao("Distribuição de tickets por técnico"));
    const pintados = container.querySelectorAll("[fill], [stroke], [stop-color]");

    expect(pintados.length).toBeGreaterThan(50);
    for (const el of pintados) {
      for (const attr of ["fill", "stroke", "stop-color"]) {
        const v = el.getAttribute(attr);
        // `none` e `url(#gradiente)` são legítimos; hexadecimal não é.
        if (v) expect(v, `${el.tagName} ${attr}`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      }
    }
  });

  it("a aba ativa usa o degrau de AÇÃO, e não o par de 3,83:1", async () => {
    // `bg-primary text-white` era o único par que a catraca cobrava desta tela.
    await montar();
    const ativa = screen.getByRole("button", { name: /Visão geral/ });

    expect(ativa.className).toContain("bg-action");
    expect(ativa.className).toContain("text-on-primary");
    expect(ativa.className).not.toContain("text-white");
  });
});

/**
 * A seção que responde POR QUÊ.
 *
 * O relatório já dizia quantos chamados estouraram o prazo — cartão de
 * conformidade e gráfico por prioridade. Nenhum dos dois diz a causa, e cinco
 * atrasos por "peça em falta" pedem providência oposta a cinco por "aberto na
 * sexta às 17h", com o mesmo número nos dois casos.
 *
 * O que estes casos prendem é isto: **o motivo escrito chega inteiro à tela**,
 * a tela **não decide** quem violou (a lista vem pronta do servidor), e o corte
 * de 200 do `_build_report` é DITO em vez de silencioso.
 */
describe("ReportsPage — SLA violado, o motivo do atraso", () => {
  const JUSTIFICATIVA = {
    ticket_id: "t9",
    protocol: "HS-2026-0099",
    title: "Balança fora de calibração",
    priority: "high",
    resolved_at: "2026-09-05T18:30:00Z",
    assignee_name: "Carlos",
    justification:
      "Peça de reposição em falta no estoque do fornecedor; o prazo correu enquanto o pedido estava em trânsito.",
  };

  /*
    Período sem violação nenhuma não desenha casca vazia — a guarda fica no
    pai, como nas outras seções desta tela. Uma tabela com "nenhum registro" no
    meio do relatório se lê como coisa quebrada, não como boa notícia.
  */
  it("não aparece quando ninguém estourou prazo no período", async () => {
    await montar({ sla_justifications: [] });

    expect(
      screen.queryByRole("heading", { name: /SLA violado/ }),
    ).not.toBeInTheDocument();
  });

  it("mostra o motivo escrito, inteiro, com protocolo e responsável", async () => {
    await montar({ sla_justifications: [JUSTIFICATIVA] });

    expect(
      screen.getByRole("heading", { name: "SLA violado — motivo do atraso" }),
    ).toBeInTheDocument();
    expect(screen.getByText("HS-2026-0099")).toBeInTheDocument();
    expect(screen.getByText("Carlos")).toBeInTheDocument();
    /*
      O texto INTEIRO, e não um prefixo. O motivo é o conteúdo desta seção: a
      versão cortada em "Peça de reposição em falta no estoq…" não serve a
      ninguém, e um `slice()` na tela passaria despercebido num caso que só
      procurasse o começo da frase.
    */
    expect(screen.getByText(JUSTIFICATIVA.justification)).toBeInTheDocument();

    /*
      A data de resolução sai, e o caso NÃO prende o horário: o
      `toLocaleDateString` usa o fuso da máquina, e prender "15:30" faria a
      suíte verde aqui e vermelha num CI em UTC — um caso que reprova pela
      máquina, não pelo código. O que importa é que a coluna tenha data em vez
      do traço de ausente.
    */
    const linha = screen.getByText("HS-2026-0099").closest("tr") as HTMLElement;
    expect(within(linha).getByText(/\d{2}\/\d{2}\/2026/)).toBeInTheDocument();
  });

  it("a prioridade sai pelo rótulo, e não pelo valor cru do banco", async () => {
    await montar({ sla_justifications: [JUSTIFICATIVA] });

    const linha = screen.getByText("HS-2026-0099").closest("tr") as HTMLElement;
    expect(within(linha).getByText("Alta")).toBeInTheDocument();
    expect(within(linha).queryByText("high")).not.toBeInTheDocument();
  });

  /*
    `_build_report` corta em 200, ordenados do mais recente para o mais antigo.
    Corte silencioso lido como cobertura total é o que faz alguém decidir sobre
    um número que não é o número — então ele é dito, e só quando acontece.
  */
  it("diz que está mostrando as 200 mais recentes quando bate no teto", async () => {
    const duzentos = Array.from({ length: 200 }, (_, i) => ({
      ...JUSTIFICATIVA,
      ticket_id: `t${i}`,
      protocol: `HS-2026-${String(i).padStart(4, "0")}`,
    }));
    await montar({ sla_justifications: duzentos });

    expect(
      screen.getByText("mostrando as 200 mais recentes do período"),
    ).toBeInTheDocument();
  });

  it("não fala em teto quando a lista cabe inteira", async () => {
    await montar({ sla_justifications: [JUSTIFICATIVA] });

    expect(
      screen.queryByText(/200 mais recentes/),
    ).not.toBeInTheDocument();
  });

  /*
    A tela recebe a lista pronta e não recalcula prazo: ela não tem a pausa
    acumulada (`sla_total_paused_ms`), então uma conta local acharia vencido o
    que não está — e um falso positivo aqui põe no relatório um chamado que não
    violou nada. Este caso prende o desenho: o que o servidor mandou é o que
    aparece, sem filtro por data do lado de cá.
  */
  it("desenha o que o servidor mandou, sem filtrar por data na tela", async () => {
    await montar({
      sla_justifications: [
        JUSTIFICATIVA,
        // Resolvido "no futuro" e sem responsável: dado que qualquer conta
        // local de prazo descartaria. A tela não conta — ela mostra.
        {
          ...JUSTIFICATIVA,
          ticket_id: "t10",
          protocol: "HS-2026-0100",
          resolved_at: null,
          assignee_name: null,
          justification: "Cliente não respondeu à solicitação de acesso remoto.",
        },
      ],
    });

    expect(screen.getByText("HS-2026-0099")).toBeInTheDocument();
    expect(screen.getByText("HS-2026-0100")).toBeInTheDocument();
    expect(
      screen.getByText("Cliente não respondeu à solicitação de acesso remoto."),
    ).toBeInTheDocument();

    /*
      Sem responsável e sem data de resolução, as duas células mostram o traço.
      Célula genuinamente vazia e célula com valor ausente são a mesma coisa
      olhando a tela — e a primeira se lê como tabela quebrada.
    */
    const semDono = screen.getByText("HS-2026-0100").closest("tr") as HTMLElement;
    expect(within(semDono).getAllByText("—")).toHaveLength(2);
  });
});
