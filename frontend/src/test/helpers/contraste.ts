/**
 * Contraste WCAG 2.x lido dos tokens **de verdade**.
 *
 * O arquivo de origem é `src/design-system/tokens/colors.css`, a cópia byte a
 * byte do pacote. Um teste que cravasse os hexadecimais aqui passaria feliz
 * depois de alguém trocar o valor no token — que é exatamente o acidente que
 * estes testes existem para impedir.
 *
 * Não é um motor de CSS: resolve `var()` encadeado, hexadecimal de 6 dígitos e
 * `rgb(r g b / a)`, que é tudo o que o `colors.css` usa hoje. Qualquer forma
 * fora dessas levanta erro em vez de devolver um número errado.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export type Tema = "claro" | "escuro";
type RGBA = { r: number; g: number; b: number; a: number };

// A partir da raiz do projeto, que é onde o Vitest roda. `import.meta.url` não
// serve: sob a transformação do Vitest ele não é uma URL `file:`.
const CAMINHO = resolve(process.cwd(), "src/design-system/tokens/colors.css");

/** Tira comentários (inclusive os de várias linhas) antes de qualquer parse. */
function semComentarios(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

function bloco(css: string, seletor: string): Record<string, string> {
  const i = css.indexOf(seletor + " {");
  if (i === -1) throw new Error(`bloco "${seletor}" não encontrado em colors.css`);
  const fim = css.indexOf("}", i);
  const corpo = css.slice(i + seletor.length + 2, fim);

  const mapa: Record<string, string> = {};
  for (const linha of corpo.split(";")) {
    const m = linha.match(/^\s*(--[\w-]+)\s*:\s*(.+?)\s*$/s);
    if (m) mapa[m[1]] = m[2];
  }
  return mapa;
}

const CSS = semComentarios(readFileSync(CAMINHO, "utf-8"));
const RAIZ = bloco(CSS, ":root");
const ESCURO = bloco(CSS, ".dark");

/** Resolve `var(--x)` até chegar num literal. O `.dark` cai no `:root`. */
function resolver(valor: string, tema: Tema, saltos = 0): string {
  if (saltos > 20) throw new Error(`ciclo de var() ao resolver "${valor}"`);
  const m = valor.match(/^var\((--[\w-]+)\)$/);
  if (!m) return valor;

  const nome = m[1];
  const bruto = tema === "escuro" ? (ESCURO[nome] ?? RAIZ[nome]) : RAIZ[nome];
  if (bruto === undefined) throw new Error(`token ${nome} não existe no tema ${tema}`);
  return resolver(bruto, tema, saltos + 1);
}

function paraRGBA(literal: string): RGBA {
  const hex = literal.match(/^#([0-9a-fA-F]{6})$/);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: 1 };
  }

  const rgb = literal.match(
    /^rgb\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+)\s*)?\)$/,
  );
  if (rgb) {
    return {
      r: Number(rgb[1]),
      g: Number(rgb[2]),
      b: Number(rgb[3]),
      a: rgb[4] === undefined ? 1 : Number(rgb[4]),
    };
  }

  throw new Error(`formato de cor não suportado: "${literal}"`);
}

/** Valor final de um token, já resolvido, no tema pedido. */
export function cor(token: string, tema: Tema): RGBA {
  return paraRGBA(resolver(`var(${token})`, tema));
}

/** Compõe uma cor translúcida sobre um fundo opaco. */
function sobre(frente: RGBA, fundo: RGBA): RGBA {
  if (frente.a === 1) return frente;
  if (fundo.a !== 1) throw new Error("o fundo da composição precisa ser opaco");
  return {
    r: frente.a * frente.r + (1 - frente.a) * fundo.r,
    g: frente.a * frente.g + (1 - frente.a) * fundo.g,
    b: frente.a * frente.b + (1 - frente.a) * fundo.b,
    a: 1,
  };
}

function luminancia({ r, g, b }: RGBA): number {
  const [R, G, B] = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

/**
 * Razão de contraste entre dois tokens, no mesmo tema.
 *
 * `base` é o que estiver por baixo quando o fundo for translúcido — as tintas
 * de 15% do pacote pegam o tom da superfície, e sem isso o número é fantasia.
 */
export function contraste(
  tokenFundo: string,
  tokenTexto: string,
  tema: Tema,
  tokenBase = "--surface",
): number {
  const base = cor(tokenBase, tema);
  const fundo = sobre(cor(tokenFundo, tema), base);
  const texto = sobre(cor(tokenTexto, tema), fundo);

  const [maior, menor] = [luminancia(fundo), luminancia(texto)].sort((a, b) => b - a);
  return (maior + 0.05) / (menor + 0.05);
}

/** Piso da §21 para texto normal. */
export const AA = 4.5;
