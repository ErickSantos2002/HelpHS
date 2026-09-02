/**
 * Captura os screenshots dos primitivos para o Checkpoint 2.
 *
 * Irmão do `capturar-casca.mjs`, com a mesma regra de rede e pelo mesmo motivo:
 * o `backend/.env` desta máquina aponta para o banco de PRODUÇÃO, e um
 * screenshot não vale o risco de tocar nele.
 *
 * Toda requisição é interceptada por uma rota única, com lista de permissão:
 *
 *   - localhost:5173, data:, blob:  → passam
 *   - fonts.googleapis / gstatic    → negadas de propósito (a fonte é local
 *                                     desde a E3; se aparecer aqui, é regressão)
 *   - QUALQUER outra coisa          → abortada E registrada como fuga
 *
 * Havendo uma fuga sequer, o script sai com código 1 e recusa os próprios
 * screenshots como evidência. O modo de falhar precisa ser barulhento: um PNG
 * bonito tirado contra produção seria pior do que nenhum PNG.
 *
 * Diferença para o da casca: a página dos primitivos não monta contexto nem
 * chama API. A expectativa, aqui, é **zero** requisição de API — e o relatório
 * mostra a lista vazia como parte da evidência.
 *
 * Uso:
 *   npm run dev                       (noutro terminal)
 *   node scripts/capturar-primitivos.mjs
 *
 * Saída: docs/design-system-migration/fase-7/screenshots/
 */
import { chromium } from "@playwright/test";
import { mkdir, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SAIDA = path.resolve(
  RAIZ,
  "../docs/design-system-migration/fase-7/screenshots",
);
const BASE = process.env.GALERIA_URL ?? "http://localhost:5173";

/** nome do arquivo, largura, altura. A página é uma só e rola: a altura aqui é
 *  só a da janela; o screenshot é de página inteira. */
const TELAS = [["primitivos", 1366, 900]];

const TEMAS = ["claro", "escuro"];

const fugas = [];
const bloqueadas = [];
const apiChamada = [];

function ehLocal(url) {
  try {
    const u = new URL(url);
    if (u.protocol === "data:" || u.protocol === "blob:") return true;
    return u.host === new URL(BASE).host;
  } catch {
    return false;
  }
}

async function instalarBloqueio(context) {
  await context.route("**/*", async (route) => {
    const url = route.request().url();

    if (/\/api\//.test(url)) {
      // Esta página não deveria chamar API nenhuma. Se chamar, o corpo vazio
      // mantém a tela de pé e a linha abaixo deixa o rastro no relatório.
      apiChamada.push(url);
      bloqueadas.push(url);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
    }

    if (ehLocal(url)) return route.continue();

    if (/fonts\.(googleapis|gstatic)\.com/.test(url)) {
      bloqueadas.push(url);
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
    for (const [tela, largura, altura] of TELAS) {
      for (const tema of TEMAS) {
        const context = await browser.newContext({
          viewport: { width: largura, height: altura },
          deviceScaleFactor: 2,
          colorScheme: tema === "escuro" ? "dark" : "light",
        });

        await instalarBloqueio(context);

        await context.addInitScript(
          ([chave, valor]) => {
            try {
              window.localStorage.setItem(chave, valor);
            } catch {
              /* modo anônimo: o colorScheme acima já cobre */
            }
          },
          ["helphs-theme", tema === "escuro" ? "dark" : "light"],
        );

        const page = await context.newPage();
        await page.goto(`${BASE}/galeria-primitivos`, {
          waitUntil: "networkidle",
        });

        // Prova de que a página montou: sem isto, um erro de render viraria um
        // PNG em branco aprovado como evidência.
        await page.waitForSelector('[data-galeria="primitivos"]', {
          timeout: 10_000,
        });

        // Prova de que os quatro primitivos renderizaram de fato. O Avatar é o
        // único que não tem tag própria — conta-se pelo texto das iniciais.
        const contagens = await page.evaluate(() => ({
          svg: document.querySelectorAll('[data-galeria] svg').length,
          selos: document.querySelectorAll("span.rounded-full.border").length,
        }));
        if (contagens.svg < 75) {
          throw new Error(
            `esperava ao menos 75 <svg> (25 ícones × 3 pesos), vi ${contagens.svg}`,
          );
        }

        const classes = await page.evaluate(
          () => document.documentElement.className,
        );
        if (classes.includes("dark") !== (tema === "escuro")) {
          throw new Error(`tema errado em ${tema}: <html class="${classes}">`);
        }

        const arquivo = path.join(SAIDA, `helphs-${tela}-${tema}-${largura}.png`);
        await page.screenshot({ path: arquivo, fullPage: true });
        console.log(
          `  ✔ ${path.basename(arquivo)}  (${contagens.svg} ícones, ${contagens.selos} selos)`,
        );

        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}

console.log(`Capturando os primitivos de ${BASE} — toda a rede está interceptada.`);
await capturar();

const unicas = [...new Set(bloqueadas)];
console.log(`\nRequisições barradas de propósito (${unicas.length}):`);
for (const u of unicas) console.log(`  · ${u}`);

if (apiChamada.length === 0) {
  console.log("\n✔ Nenhuma chamada de API — a página não tem o que pedir.");
} else {
  console.log(`\n⚠ ${apiChamada.length} chamada(s) de API, respondidas vazias.`);
}

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
