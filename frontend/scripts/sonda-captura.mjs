import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * As travas que toda captura atravessa antes de disparar.
 *
 * ── O que havia antes, e por que não servia ───────────────────────────
 *
 * O `capturar-casca.mjs` **não tinha checagem de pixel nenhuma**. Conferia
 * `document.documentElement.className.includes("dark")` — a CLASSE, que é
 * promessa. Uma página com `class="dark"` e o CSS do tema claro (folha antiga,
 * token não carregado, build velho) passava e virava evidência.
 *
 * O `capturar-primitivos.mjs` tinha checagem, com dois defeitos:
 *
 *   1. media `document.body` direto. Funciona **hoje**, porque o `base.css` do
 *      pacote pinta o `body` e o `html` não tem fundo — então o fundo do canvas
 *      se propaga do `body`. No dia em que alguém pintar o `html`, a regra do
 *      CSS inverte: o canvas passa a vir do `html`, e a sonda continuaria
 *      medindo o `body`, que já não é o que a foto mostra.
 *
 *   2. comparava com a expressão `rgb(2xx, 2xx, 2xx)`. Isso aprova **qualquer
 *      cor clara**, não a cor certa. Trocar `--bg-base` por outro cinza claro
 *      qualquer passaria; um tema claro errado passaria.
 *
 * ── O que estas travas fazem ──────────────────────────────────────────
 *
 * O valor esperado vem do `tokens/colors.css` **em disco**, resolvido pela
 * cadeia de `var()`. É a mesma forma da catraca da ponte D5 e do marcador da
 * galeria: **o disco diz o que deveria ser, o navegador diz o que é.** Ler o
 * valor esperado do próprio navegador (`getPropertyValue('--bg-base')`) seria
 * circular — se o token não carregasse, os dois lados ficariam vazios e
 * concordariam.
 *
 * E o que se mede é a **cor do canvas**, pela regra do CSS: o fundo do `html`
 * se não for transparente; senão, o do `body`. Se os dois forem transparentes,
 * bloqueia — nada pinta, e a foto sairia com o branco do navegador.
 */

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TOKENS = path.join(RAIZ, "src", "design-system", "tokens", "colors.css");

/** O HelpHS mora aqui. Ver a decisão de porta exclusiva no `DECISOES.md`. */
export const BASE = process.env.GALERIA_URL ?? "http://localhost:5190";

export const PRODUTO = "helphs";

/** `#rrggbb` no formato que o `getComputedStyle` devolve. */
function hexParaRgb(hex) {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Lê `--bg-base` do `colors.css` e resolve a cadeia de `var()`.
 *
 * No `:root` ele é `var(--color-slate-50)`; no `.dark`, um literal. A busca
 * volta para o `:root` quando o bloco do tema não declara o token — que é o
 * que o CSS faz por herança.
 */
export function corDeFundoEsperada(tema, texto = readFileSync(TOKENS, "utf-8")) {
  const bloco = (nome) => {
    const i = texto.indexOf(nome);
    if (i < 0) return "";
    const fim = texto.indexOf("\n}", i);
    return texto.slice(i, fim < 0 ? undefined : fim);
  };
  const raiz = bloco(":root {");
  const escuro = bloco(".dark {");
  const onde = tema === "escuro" ? [escuro, raiz] : [raiz];

  function valor(token, profundidade = 0) {
    if (profundidade > 8) {
      throw new Error(`cadeia de var() sem fim a partir de ${token}`);
    }
    for (const b of onde) {
      const m = b.match(new RegExp("\\" + token + "\\s*:\\s*([^;]+);"));
      if (!m) continue;
      const bruto = m[1].trim();
      const ref = bruto.match(/^var\(\s*(--[\w-]+)\s*\)$/);
      if (ref) return valor(ref[1], profundidade + 1);
      const hex = bruto.match(/^#[0-9a-fA-F]{6}$/);
      if (hex) return hexParaRgb(bruto);
      throw new Error(`valor de ${token} não é hex nem var(): ${bruto}`);
    }
    throw new Error(
      `${token} não existe no colors.css para o tema ${tema} — ` +
        `os tokens saíram do lugar, e sem eles a captura não pode valer.`,
    );
  }

  return valor("--bg-base");
}

/** Lido no navegador: a cor que de fato pinta o viewport. */
const COR_DO_CANVAS = `(() => {
  const html = getComputedStyle(document.documentElement).backgroundColor;
  const corpo = getComputedStyle(document.body).backgroundColor;
  const transparente = (c) =>
    !c || c === "transparent" || /rgba\\(\\s*0,\\s*0,\\s*0,\\s*0\\s*\\)/.test(c);
  return {
    html,
    corpo,
    // Regra do CSS: o fundo do canvas vem do html; se ele for transparente,
    // propaga-se o do body.
    canvas: transparente(html) ? (transparente(corpo) ? null : corpo) : html,
  };
})()`;

/**
 * A trava de PIXEL. Bloqueia sozinha, sem depender de marcador nem de classe.
 *
 * ── Por que ela espera a cor ASSENTAR ─────────────────────────────────
 *
 * O `base.css` do pacote põe `transition: var(--transition-colors)` no `body`,
 * com `--duration-fast` de **150ms**. Durante a troca de tema o
 * `getComputedStyle` devolve a cor **no meio do caminho** — nem a de origem nem
 * a de destino.
 *
 * Isso apareceu na primeira execução da prova desta própria trava: forçar o
 * fundo transparente devolveu `rgba(248, 250, 252, 0.03)`, um valor que não é
 * de tema nenhum. Uma captura disparada logo depois de aplicar o tema
 * fotografaria a cor misturada, e uma checagem de leitura única aprovaria —
 * porque o valor lido seria o mesmo que a foto mostra, e os dois estariam
 * errados juntos.
 *
 * Então: lê, espera mais que a transição, lê de novo, e só vale quando as duas
 * leituras concordam.
 */
export async function conferirPixel(page, tema, onde = "") {
  const esperado = corDeFundoEsperada(tema);

  let lido = await page.evaluate(COR_DO_CANVAS);
  let assentou = false;
  for (let i = 0; i < 5 && !assentou; i++) {
    await page.waitForTimeout(200); // > --duration-fast (150ms)
    const denovo = await page.evaluate(COR_DO_CANVAS);
    assentou = denovo.canvas === lido.canvas;
    lido = denovo;
  }
  if (!assentou) {
    throw new Error(
      `${onde}a cor do viewport não parou de mudar depois de 1s: última ` +
        `leitura ${lido.canvas}. A transição de tema do \`base.css\` dura ` +
        `150ms; algo mais longo está em curso, e a foto sairia no meio dele.`,
    );
  }

  if (lido.canvas === null) {
    throw new Error(
      `${onde}nada pinta o viewport: html e body têm fundo transparente ` +
        `(html=${lido.html}, body=${lido.corpo}). A foto sairia com o branco ` +
        `do navegador, e não com o tema.`,
    );
  }

  if (lido.canvas !== esperado) {
    throw new Error(
      `${onde}o PIXEL não é o do tema ${tema}: o canvas pinta ${lido.canvas} e ` +
        `o token --bg-base do colors.css vale ${esperado}.\n` +
        `  html=${lido.html}  body=${lido.corpo}\n` +
        `  Classe e atributo são promessa; isto é o que a foto vai mostrar.`,
    );
  }
}

/** A trava de PRODUTO. Falha fechada: marcador ausente bloqueia. */
export async function conferirProduto(page, onde = "") {
  const marcador = await page.evaluate(() =>
    document.documentElement.getAttribute("data-app"),
  );
  if (marcador === PRODUTO) return;
  const titulo = await page.title();
  throw new Error(
    marcador === null
      ? `${onde}sem marcador de produto (título "${titulo}"). Falha fechada.`
      : `${onde}a página é do produto "${marcador}", e não do "${PRODUTO}" ` +
        `(título "${titulo}"). Confira quem está na porta de ${BASE}.`,
  );
}
