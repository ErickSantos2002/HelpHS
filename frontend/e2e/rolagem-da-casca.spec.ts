import { expect, test, type Page } from "@playwright/test";

/**
 * A casca não rola por causa de texto que ninguém vê.
 *
 * O defeito, visto em produção na v1.15.0: no quadro de chamados a página
 * inteira rolava — sidebar e topbar junto — e embaixo sobrava uma faixa vazia
 * do tamanho de uma tela. Quem esticava o documento eram os `sr-only`.
 *
 * O `sr-only` é `position: absolute`. O bloco de contenção de um elemento
 * absoluto é o ancestral POSICIONADO mais próximo, e um contêiner com
 * `overflow` só corta os descendentes cujo bloco de contenção está dentro dele.
 * Sem ninguém posicionado no caminho, o bloco de contenção é o documento:
 * nenhum `overflow-y-auto` corta aquele texto, e ele estica a rolagem do
 * documento até onde estaria no fluxo — o fim de uma coluna cheia, numa coluna
 * fora da tela.
 *
 * A regra que conserta é "quem rola, contém": todo contêiner que rola e tem
 * `absolute` sem pai posicionado dentro precisa ser `relative`. As três telas
 * daqui são as três em que isso foi MEDIDO — com os dados do
 * `scripts/capturar-telas.mjs`, o quadro e o painel do técnico já quebravam; a
 * lista da KB quebra quando passa de uma tela.
 *
 * As rotas, o `AuthGuard` e a `AppLayout` são os de produção; só os dados são
 * de mentira. A sessão é semeada no `localStorage` e toda chamada `/api/` é
 * respondida aqui — o que não é local é abortado. O `backend/.env` da árvore
 * principal aponta para o banco de PRODUÇÃO, e um teste de leiaute não vale
 * esse risco. Mesmo desenho do `scripts/capturar-telas.mjs`.
 */

const AGORA = Date.parse("2026-06-17T12:00:00Z");
const emHoras = (h: number) => new Date(AGORA + h * 3_600_000).toISOString();

const usuario = (role: "admin" | "technician") => ({
  id: "u-demo",
  name: "Rickelme David",
  email: "demo@exemplo.invalid",
  role,
  is_active: true,
  onboarding_completed: true,
  company_id: "c-demo",
  avatar_url: null,
  phone: "(11) 90000-0000",
  created_at: emHoras(-9600),
  mfa_enabled: false,
});

/**
 * Seis colunas povoadas, e a de "Fechado" com mais cartões do que cabe.
 *
 * As duas coisas são o cenário do defeito, e não enfeite: as seis colunas
 * passam da largura da tela (o quadro rola na horizontal) e a coluna cheia
 * passa da altura (a lista dela rola na vertical). Os cartões são SEM
 * responsável porque é esse ramo que carrega o `sr-only` "Sem responsável".
 */
const CHAMADOS = [
  "open",
  "in_progress",
  "awaiting_technical",
  "awaiting_client",
  "resolved",
  ...Array.from({ length: 12 }, () => "closed"),
].map((status, i) => ({
  id: `t-${i + 1}`,
  protocol: `HS-2026-${String(i + 1).padStart(4, "0")}`,
  title: `Chamado de demonstração ${i + 1}`,
  description: "Nenhum dado real.",
  status,
  priority: "medium",
  category: "software",
  creator_id: "u-cliente",
  creator_name: "Ana Paula",
  assignee_id: null,
  assignee_name: null,
  created_at: emHoras(-30 - i),
  updated_at: emHoras(-2),
  closed_at: status === "closed" ? emHoras(-1) : null,
  sla_response_due_at: emHoras(4),
  sla_resolve_due_at: emHoras(30),
  sla_response_breach: false,
  sla_resolve_breach: false,
  sla_first_response: null,
  equipments: [],
  tags: [],
  product_id: null,
  product_name: null,
  client_observation: null,
}));

/** Quarenta artigos: a lista passa de uma tela, e cada um tem dois `sr-only`. */
const ARTIGOS = Array.from({ length: 40 }, (_, i) => ({
  id: `kb-${i + 1}`,
  title: `Artigo de demonstração ${i + 1}`,
  content: "Nenhum dado real.",
  slug: `artigo-${i + 1}`,
  category: "software",
  tags: [],
  status: "published",
  author_id: "u-demo",
  author_name: "Rickelme David",
  view_count: 10,
  helpful: 2,
  not_helpful: 0,
  created_at: emHoras(-400),
  updated_at: emHoras(-40),
  products: [],
}));

type Respostas = [RegExp, unknown][];

async function abrir(
  page: Page,
  rota: string,
  papel: "admin" | "technician",
  respostas: Respostas,
) {
  // Específico antes de genérico: a primeira que casa responde.
  const tabela: Respostas = [[/\/users\/me$/, usuario(papel)], ...respostas];
  const contexto = page.context();
  await contexto.route("**/*", (r) => {
    const url = new URL(r.request().url());
    if (url.pathname.startsWith("/api/")) {
      const achada = tabela.find(([padrao]) => padrao.test(url.pathname));
      return r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(achada ? achada[1] : { items: [], total: 0 }),
      });
    }
    if (url.host === "localhost:5190") return r.continue();
    return r.abort();
  });
  // O `route` não pega WebSocket. Sem isto, o das notificações sairia pelo
  // proxy do Vite para a 8001.
  await contexto.routeWebSocket(/.*/, (ws) => ws.close());
  await contexto.addInitScript(() => {
    localStorage.setItem("helphs_access_token", "token-de-mentira");
    localStorage.setItem("helphs_refresh_token", "refresh-de-mentira");
    localStorage.setItem("helphs-theme", "dark");
  });

  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto(rota);
}

/**
 * Quanto cada contêiner que rola rola, com e sem os `sr-only`.
 *
 * A DIFERENÇA é a medida do defeito, e não um número absoluto: o quadro
 * precisa rolar, a lista da KB precisa rolar, e o que nenhum deles pode é
 * rolar a mais por causa de texto que ninguém vê. Tirar os `sr-only` do leiaute
 * e medir de novo separa uma coisa da outra sem depender de quantos itens cabem
 * na tela. (Eles são absolutos, então sair do leiaute não mexe em mais nada.)
 *
 * Mede TODO contêiner com `overflow` rolável, e não uma lista escolhida: o
 * primeiro conserto que eu desenhei posicionava só o `<main>`, e o texto
 * escondido deixava de esticar o documento para esticar o `<main>` — uma barra
 * de rolagem para nada, num elemento que uma lista fixa não teria olhado.
 */
async function rolagemFantasma(page: Page) {
  const medir = () =>
    page.evaluate(() => {
      const rolaveis = [
        document.scrollingElement!,
        ...Array.from(document.querySelectorAll("body *")).filter((el) => {
          const s = getComputedStyle(el);
          return /auto|scroll/.test(s.overflowX + s.overflowY);
        }),
      ];
      return rolaveis.map((el, i) => ({
        quem:
          el === document.scrollingElement
            ? "documento"
            : `#${i} ${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}.` +
              String(el.className).split(" ").slice(0, 4).join("."),
        y: el.scrollHeight - el.clientHeight,
        x: el.scrollWidth - el.clientWidth,
      }));
    });

  const com = await medir();
  const estilo = await page.addStyleTag({
    content: ".sr-only { display: none !important; }",
  });
  const sem = await medir();
  await estilo.evaluate((el) => (el as Element).remove());

  const fantasmas = com
    .map((c, i) => ({ quem: c.quem, y: c.y - sem[i].y, x: c.x - sem[i].x }))
    .filter((d) => d.y !== 0 || d.x !== 0);
  const extensao = (trecho: string) => com.find((c) => c.quem.includes(trecho));
  return { documento: com[0], fantasmas, extensao };
}

test("quadro de chamados: quem rola é o quadro, e não a casca", async ({
  page,
}) => {
  await abrir(page, "/tickets", "admin", [
    [/\/users\/technicians/, { items: [] }],
    [/\/tickets$/, { items: CHAMADOS, total: CHAMADOS.length }],
  ]);
  // 15s, e não os 5s do padrão: o primeiro teste da execução pega o Vite
  // compilando a rota a frio.
  await expect(page.locator("[aria-labelledby^='coluna-']")).toHaveCount(6, {
    timeout: 15_000,
  });

  const { documento, fantasmas, extensao } = await rolagemFantasma(page);
  expect(documento, "a casca rola").toMatchObject({ y: 0, x: 0 });
  expect(fantasmas, "rolagem que só existe por causa de `sr-only`").toEqual([]);

  // Controle positivo: o quadro continua rolando. Um conserto que cortasse a
  // rolagem dele passaria nas duas checagens acima escondendo as colunas.
  expect(extensao("kanban-scroll")?.x, "o quadro deixou de rolar").toBeGreaterThan(
    0,
  );
});

test("base de conhecimento: a lista longa rola no <main>, e não na casca", async ({
  page,
}) => {
  await abrir(page, "/kb", "admin", [
    [/\/kb\/articles$/, { items: ARTIGOS, total: ARTIGOS.length, limit: 50, offset: 0 }],
  ]);
  await expect(page.getByText("Artigo de demonstração 40")).toBeVisible({
    timeout: 15_000,
  });

  const { documento, fantasmas, extensao } = await rolagemFantasma(page);
  expect(documento, "a casca rola").toMatchObject({ y: 0, x: 0 });
  expect(fantasmas, "rolagem que só existe por causa de `sr-only`").toEqual([]);
  expect(extensao("main#main-content")?.y, "a lista deixou de rolar").toBeGreaterThan(
    0,
  );
});

test("painel do técnico: a lista de chamados rola dentro da caixa", async ({
  page,
}) => {
  await abrir(page, "/", "technician", [
    [
      /\/dashboard\/reports\/technician/,
      {
        period_days: 30,
        technician_id: "u-demo",
        technician_name: "Rickelme David",
        total_assigned: 0,
        resolved: 0,
        in_progress: 0,
        open_count: 0,
        sla_breached: 0,
        sla_compliance_rate: 100,
        avg_resolution_hours: null,
        csat_average: null,
        csat_count: 0,
        tickets_by_day: [],
      },
    ],
    [/\/dashboard\/stats/, { tickets: { open: CHAMADOS.length } }],
    [/\/tickets$/, { items: CHAMADOS, total: CHAMADOS.length }],
  ]);
  await expect(page.getByText("Chamado de demonstração 17").first()).toBeAttached({
    timeout: 15_000,
  });

  const { documento, fantasmas, extensao } = await rolagemFantasma(page);
  expect(documento, "a casca rola").toMatchObject({ y: 0, x: 0 });
  expect(fantasmas, "rolagem que só existe por causa de `sr-only`").toEqual([]);
  expect(extensao("max-h-[168px]")?.y, "a lista deixou de rolar").toBeGreaterThan(
    0,
  );
});
