/**
 * Captura os screenshots da casca para o Checkpoint 1.
 *
 * ARTEFATO DE DESENVOLVIMENTO — sai na Fase 20, junto com a rota de galeria.
 *
 * ── A regra que este script existe para cumprir ──────────────────────────
 *
 * Nenhuma requisição pode sair para a rede. O `backend/.env` deste ambiente
 * aponta para o banco de PRODUÇÃO; um screenshot não vale o risco de tocar
 * nele. Então o script não "evita" chamadas: ele as impede.
 *
 * O bloqueio é por lista de permissão, não por lista de bloqueio:
 *
 *   - `localhost:5173`      → passa (é o Vite servindo o próprio app)
 *   - `data:` e `blob:`     → passam (não saem da máquina)
 *   - fonts.googleapis.com  → NEGADO, com fallback local de fonte
 *   - fonts.gstatic.com     → NEGADO, idem
 *   - qualquer chamada de API (`/api/`) → respondida com dado falso daqui
 *   - QUALQUER outra coisa  → abortada E registrada como fuga
 *
 * Se qualquer fuga for registrada, o script sai com código 1 e não deixa os
 * screenshots passarem por bons. É esse o ponto: o modo de falhar precisa ser
 * barulhento. Um screenshot bonito tirado contra produção seria pior do que
 * nenhum screenshot.
 *
 * A fonte é negada de propósito. Ela vem do token
 * (`design-system/tokens/typography.css`) e o Google é rede externa como
 * qualquer outra. Sem ela o navegador cai na pilha de fallback declarada no
 * próprio token — o que muda a forma das letras, não cor, medida, espaçamento
 * ou contraste, que é o que estes screenshots existem para comparar. O
 * relatório do Checkpoint 1 registra isso.
 *
 * ── Uso ──────────────────────────────────────────────────────────────────
 *
 *   npm run dev                         (noutro terminal)
 *   node scripts/capturar-casca.mjs
 *
 * Saída: docs/design-system-migration/fase-0/screenshots/
 *        helphs-<tela>-<tema>-<largura>.png   (nome da seção 28)
 */
import { chromium } from "@playwright/test";
import { mkdir, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SAIDA = path.resolve(
  RAIZ,
  "../docs/design-system-migration/fase-0/screenshots",
);
const BASE = process.env.GALERIA_URL ?? "http://localhost:5173";

/** Resposta falsa para o contador de não lidas da Topbar. É a única chamada
 *  que a casca faz por conta própria; o 3 é para o badge aparecer no
 *  screenshot em vez de ficar escondido no estado zero. */
const NOTIFICACOES_FALSAS = {
  items: [],
  total: 0,
  unread: 3,
};

/** tela, estado da galeria, largura, altura */
const TELAS = [
  ["sidebar-expandida", "expandida", 1366, 768],
  ["sidebar-recolhida", "recolhida", 1366, 768],
  ["gaveta-mobile", "gaveta", 390, 844],
];

const TEMAS = ["claro", "escuro"];

const fugas = [];
const bloqueadas = [];

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
  // Uma rota só, casando tudo. Nada de rota específica antes desta: a
  // primeira que casa é a que responde, e "tudo" precisa ser o piso.
  await context.route("**/*", async (route) => {
    const req = route.request();
    const url = req.url();

    if (/\/api\//.test(url)) {
      if (/\/notifications/.test(url)) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(NOTIFICACOES_FALSAS),
        });
      }
      // Qualquer outra chamada de API responde vazio. A galeria não deveria
      // fazer nenhuma; se fizer, o corpo vazio mantém a tela de pé e a linha
      // abaixo deixa o rastro no relatório.
      bloqueadas.push(url);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
    }

    if (ehLocal(url)) return route.continue();

    // Fonte do Google: negada de propósito, e isso não é fuga.
    if (/fonts\.(googleapis|gstatic)\.com/.test(url)) {
      bloqueadas.push(url);
      return route.abort();
    }

    // Chegou aqui: alguém tentou sair para a rede sem que este script
    // soubesse. Aborta e denuncia.
    fugas.push(url);
    return route.abort();
  });
}

async function capturar() {
  await mkdir(SAIDA, { recursive: true });

  const browser = await chromium.launch();
  try {
    for (const [tela, estado, largura, altura] of TELAS) {
      for (const tema of TEMAS) {
        const context = await browser.newContext({
          viewport: { width: largura, height: altura },
          deviceScaleFactor: 2,
          // Trava o tema no nível do sistema também, para o caso de o app
          // cair no `prefers-color-scheme` antes de ler o localStorage.
          colorScheme: tema === "escuro" ? "dark" : "light",
        });

        await instalarBloqueio(context);

        // O ThemeContext lê `helphs-theme` do localStorage na montagem. Semear
        // antes de navegar evita o piscar de tema e, mais importante, evita
        // capturar o tema errado por corrida.
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
        const alvo = `${BASE}/galeria-ds?estado=${estado}`;
        await page.goto(alvo, { waitUntil: "networkidle" });

        // Prova de que a casca montou: sem isto, um erro de render viraria um
        // PNG em branco aprovado como evidência.
        await page.waitForSelector(`[data-galeria="${estado}"]`, {
          timeout: 10_000,
        });
        await page.waitForSelector("#sidebar-nav", { timeout: 10_000 });

        const classes = await page.evaluate(
          () => document.documentElement.className,
        );
        const escuroNoDom = classes.includes("dark");
        if (escuroNoDom !== (tema === "escuro")) {
          throw new Error(
            `tema errado em ${tela}/${tema}: <html class="${classes}">`,
          );
        }

        const arquivo = path.join(
          SAIDA,
          `helphs-${tela}-${tema}-${largura}.png`,
        );
        await page.screenshot({ path: arquivo });
        console.log(`  ✔ ${path.basename(arquivo)}`);

        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}

console.log(`Capturando a casca de ${BASE} — toda a rede está interceptada.`);
await capturar();

const unicas = [...new Set(bloqueadas)];
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
