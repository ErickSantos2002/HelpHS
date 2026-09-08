/**
 * Captura as quatro telas da Fase 11 para o Checkpoint 3.
 *
 * ARTEFATO DE DESENVOLVIMENTO — sai na Fase 20, junto com as rotas de galeria.
 *
 * ── A regra que este script existe para cumprir ──────────────────────────
 *
 * **Nenhuma requisição sai para a rede.** O `backend/.env` deste ambiente
 * aponta para o banco de PRODUÇÃO; um screenshot não vale o risco de tocar
 * nele. O script não "evita" chamadas: ele as impede, por lista de permissão.
 *
 * E ele não contorna a autenticação: **semeia** uma sessão falsa e responde ao
 * `/users/me` com um usuário de mentira. As telas são as de verdade, com as
 * rotas de verdade e o `AuthGuard` de verdade — só os dados é que não existem.
 * Uma galeria que renderizasse cópias das telas provaria coisa nenhuma sobre
 * as telas.
 *
 * ── As travas, antes de cada disparo ─────────────────────────────────────
 *
 *   produto   `data-app="helphs"` no `<html>`, falha fechada
 *   pixel     a cor do viewport contra o `--bg-base` lido do `colors.css`
 *   conteúdo  um seletor que só existe na tela pedida
 *
 * As três bloqueiam sozinhas. Ver `sonda-captura.mjs` e o
 * `e2e/sonda-captura.spec.ts`, onde a do pixel é provada isolada.
 *
 * ── Uso ──────────────────────────────────────────────────────────────────
 *
 *   npm run dev                          (noutro terminal, na 5190)
 *   node scripts/capturar-fase11.mjs
 *
 * Saída: docs/design-system-migration/fase-11/screenshots/
 */
import { chromium } from "@playwright/test";
import { mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { BASE, conferirPixel, conferirProduto } from "./sonda-captura.mjs";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SAIDA = path.resolve(
  RAIZ,
  "../docs/design-system-migration/fase-11/screenshots",
);

const AGORA = Date.now();
const emHoras = (h) => new Date(AGORA + h * 3_600_000).toISOString();

/**
 * O usuário de mentira. O PAPEL varia por tela, e não é detalhe:
 * a rota `/` escolhe o painel pelo papel, e o painel da Fase 11 é o do
 * CLIENTE. Capturar como admin fotografaria o `AdminDashboard`, que tem a
 * rosca e a barra empilhada — travadas até a E18 chegar ao código.
 */
const usuario = (role) => ({
  id: "u-demo",
  name: "Rickelme David",
  email: "demo@exemplo.invalid",
  role,
  is_active: true,
  onboarding_completed: true,
  company_id: "c-demo",
});

/** Um chamado por status, para o quadro ter as seis colunas povoadas. */
const CHAMADOS = [
  ["open", "critical", "Sem acesso à plataforma do Phoebus", "hardware"],
  ["open", "medium", "Impressora do 2º andar sem conexão", "network"],
  ["in_progress", "high", "Lentidão no sistema de chamados", "software"],
  ["awaiting_technical", "high", "Troca de HD do notebook da recepção", "hardware"],
  ["awaiting_client", "low", "Confirmação de horário para manutenção", "general"],
  ["resolved", "medium", "E-mail corporativo não sincroniza", "email"],
  ["closed", "low", "Solicitação de acesso ao drive", "access"],
].map(([status, priority, title, category], i) => ({
  id: `t-${i + 1}`,
  protocol: `HS-2026-${String(i + 1).padStart(4, "0")}`,
  title,
  description:
    "Descrição de demonstração. Nenhum dado real foi usado nesta captura.",
  status,
  priority,
  category,
  creator_id: "u-demo",
  creator_name: "Ana Paula",
  assignee_id: i % 3 === 0 ? "u-tec" : null,
  assignee_name: i % 3 === 0 ? "Erick Dantas" : null,
  created_at: emHoras(-30 - i * 6),
  updated_at: emHoras(-2),
  closed_at: status === "closed" ? emHoras(-1) : null,
  sla_response_due_at: emHoras(i % 2 === 0 ? 4 : -3),
  sla_resolve_due_at: emHoras(i % 2 === 0 ? 30 : -6),
  sla_response_breach: i === 3,
  sla_resolve_breach: false,
  sla_first_response: i > 4 ? emHoras(-20) : null,
  equipments: [],
  tags: [],
  product_id: null,
  product_name: null,
  client_observation: null,
}));

const lista = { items: CHAMADOS, total: CHAMADOS.length };

/**
 * Resposta por rota. A chave é testada contra o caminho da API, e **a ordem
 * importa**: a primeira que casa responde.
 *
 * Os sufixos de `/tickets/<id>/...` vêm TODOS antes do `/tickets` solto, que
 * não tem âncora e casa com qualquer coisa abaixo dele. Foi assim que o
 * `/tickets/t-1/messages` recebeu a LISTA DE CHAMADOS como se fossem mensagens
 * — e a tela de detalhe caiu inteira, com o erro apontando para o seletor que
 * faltou em vez de para a resposta errada.
 */
const respostas = (role) => [
  [/\/users\/me$/, usuario(role)],
  // `{ items: [...] }`, e nao o array: os dois servicos devolvem
  // `data.items`. Dar array faz `.items` vir indefinido e o `.map` seguinte
  // derruba a arvore inteira — foi assim que a tela de detalhe saiu vazia,
  // com a sonda dizendo "nao montou" e nada dizendo por que.
  [/\/users\/technicians/, { items: [{ id: "u-tec", name: "Erick Dantas" }] }],
  [/\/tickets\/[^/]+\/history/, { items: [] }],
  [/\/tickets\/[^/]+\/attachments/, { items: [] }],
  [/\/tickets\/[^/]+\/notes/, []],  // este devolve array mesmo
  [/\/tickets\/[^/]+\/survey/, null],
  [/\/tickets\/[^/]+\/messages/, { items: [] }],
  [/\/tickets\/[^/]+$/, CHAMADOS[0]],
  [/\/tickets/, lista],
  [/\/quick-replies/, { items: [] }],
  [/\/notifications/, { items: [], total: 0, unread: 2 }],
  [/\/tags/, { items: [] }],
  [/\/products/, { items: [], total: 0 }],
  [/\/equipment/, { items: [] }],
];

/** tela, caminho, papel, seletor que SÓ existe nela, largura, altura */
const TELAS = [
  ["painel", "/", "client", "table", 1366, 900],
  ["lista", "/tickets", "admin", "[aria-labelledby^='coluna-']", 1366, 900],
  ["formulario", "/tickets/new", "client", "fieldset", 1366, 1200],
  ["detalhe", "/tickets/t-1", "admin", "nav[aria-label='Trilha']", 1366, 1200],
  // O quadro rola na horizontal, e a 1366 so cabem quatro das seis colunas —
  // que e o que um usuario nessa largura de fato ve, e por isso a captura de
  // 1366 fica. Esta segunda existe para a EVIDENCIA: as seis colunas juntas,
  // com os dois "Aguardando" no mesmo ambar.
  ["lista-larga", "/tickets", "admin", "[aria-labelledby^='coluna-']", 2100, 900],
];

const fugas = [];
const barradas = [];

function ehLocal(url) {
  try {
    const u = new URL(url);
    if (u.protocol === "data:" || u.protocol === "blob:") return true;
    return u.host === new URL(BASE).host;
  } catch {
    return false;
  }
}

async function instalarBloqueio(context, role) {
  const RESPOSTAS = respostas(role);
  await context.route("**/*", async (route) => {
    const url = route.request().url();

    if (/\/api\//.test(url)) {
      const caminho = new URL(url).pathname;
      for (const [padrao, corpo] of RESPOSTAS) {
        if (padrao.test(caminho)) {
          return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(corpo),
          });
        }
      }
      // Chamada de API que este script não previu. Denuncia, e responde na
      // forma que a maioria dos serviços espera — `{ items: [] }`, e não `{}`.
      //
      // Não é conveniência: `{}` fazia `data.items` vir indefinido, e a tela
      // caía inteira. O `ChatPanel` do detalhe morreu assim, e a captura
      // parou com "a tela não montou" enquanto a causa estava DUAS LINHAS
      // ACIMA, na lista de barradas que ninguém tinha lido ainda.
      barradas.push(caminho);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0 }),
      });
    }

    if (ehLocal(url)) return route.continue();

    if (/fonts\.(googleapis|gstatic)\.com/.test(url)) {
      barradas.push(url);
      return route.abort();
    }

    fugas.push(url);
    return route.abort();
  });
}

async function capturar() {
  await mkdir(SAIDA, { recursive: true });
  const browser = await chromium.launch();
  try {
    for (const [tela, rota, role, seletor, largura, altura] of TELAS) {
      for (const tema of ["claro", "escuro"]) {
        const context = await browser.newContext({
          viewport: { width: largura, height: altura },
          deviceScaleFactor: 2,
          colorScheme: tema === "escuro" ? "dark" : "light",
        });
        await instalarBloqueio(context, role);
        await context.addInitScript(
          ([tk, rf, tema]) => {
            try {
              window.localStorage.setItem("helphs_access_token", tk);
              window.localStorage.setItem("helphs_refresh_token", rf);
              window.localStorage.setItem("helphs-theme", tema);
            } catch {
              /* modo anônimo: o colorScheme do contexto já cobre */
            }
          },
          ["token-de-mentira", "refresh-de-mentira", tema === "escuro" ? "dark" : "light"],
        );

        const page = await context.newPage();
        const onde = `${tela}/${tema}: `;

        // Erro de JavaScript derruba a arvore inteira e deixa o `<body>`
        // VAZIO — e uma sonda que so olha seletor diz "nao montou" sem dizer
        // por que. Guardado aqui para entrar na mensagem.
        const erros = [];
        page.on("pageerror", (e) => erros.push(String(e.message).slice(0, 160)));
        await page.goto(`${BASE}${rota}`, { waitUntil: "networkidle" });

        await conferirProduto(page, onde);
        await page.waitForSelector(seletor, { timeout: 15_000 }).catch(async () => {
          // A mensagem carrega o que a tela MOSTROU e o que o script não
          // previu. Sem isso, "não montou" manda investigar o seletor — e a
          // causa costuma ser uma resposta de API que ninguém escreveu.
          const texto = (await page.locator("body").innerText().catch(() => ""))
            .replace(/\s+/g, " ")
            .slice(0, 240);
          const naoPrevistas = [...new Set(barradas)].filter((u) =>
            u.startsWith("/api"),
          );
          throw new Error(
            `${onde}a tela não montou: nenhum \`${seletor}\` em ${rota}.
` +
              `  a tela mostra: ${texto || "(vazia)"}
` +
              `  chamadas de API sem resposta prevista: ` +
              `${naoPrevistas.join(", ") || "nenhuma"}
` +
              `  erros de JavaScript: ${erros.join(" | ") || "nenhum"}`,
          );
        });
        await conferirPixel(page, tema, onde);

        const arquivo = path.join(SAIDA, `helphs-${tela}-${tema}-${largura}.png`);
        await page.screenshot({ path: arquivo, fullPage: true });
        console.log(`  ✔ ${path.basename(arquivo)}`);
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}

console.log(`Capturando a Fase 11 de ${BASE} — toda a rede está interceptada.`);
await capturar();

const unicas = [...new Set(barradas)];
console.log(`\nRequisições barradas de propósito (${unicas.length}):`);
for (const u of unicas) console.log(`  · ${u}`);

const arquivos = (await readdir(SAIDA)).filter((f) => f.endsWith(".png"));
console.log(`\n${arquivos.length} screenshot(s) em ${SAIDA}`);

if (fugas.length > 0) {
  console.error(`\n✖ ${fugas.length} requisição(ões) escaparam do bloqueio:`);
  for (const u of [...new Set(fugas)]) console.error(`  · ${u}`);
  console.error(
    "\nOs screenshots NÃO valem como evidência: algo tentou sair para a rede.",
  );
  process.exit(1);
}

console.log("\n✔ Nenhuma requisição escapou. Nada saiu para a rede.");
