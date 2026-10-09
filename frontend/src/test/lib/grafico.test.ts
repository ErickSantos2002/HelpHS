import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  COR_SERIE_TEMPORAL,
  CROMO,
  ENVOLTORIO_DICA,
  ESTILO_DICA,
  FAIXAS_CSAT,
  SLOTS_DE_SERIE,
  preenchimentoCsat,
  slotCategorico,
} from "../../lib/grafico";

/**
 * O caso que existe por causa de um gráfico quebrado.
 *
 * O `colors.css` do pacote registra que a tentativa anterior de migrar a rosca
 * e a barra empilhada com tokens **de interface** quebrou o gráfico. A causa é
 * que as tintas são `color-mix()`, e o Recharts escreve a cor em **atributo de
 * SVG** — onde `color-mix()` não resolve em todo motor.
 *
 * Ler o módulo não prova nada sobre isso: `var(--surface)` e `var(--tint-info)`
 * são indistinguíveis no TypeScript. O que prova é seguir a cadeia no
 * `colors.css` **em disco**, nos dois temas, até o valor final — e é o que este
 * arquivo faz.
 */
const CSS = readFileSync(
  path.join(process.cwd(), "src/design-system/tokens/colors.css"),
  "utf-8",
);

function bloco(seletor: string): Map<string, string> {
  const i = CSS.indexOf(seletor + " {");
  if (i < 0) throw new Error(`bloco ${seletor} não existe no colors.css`);
  const fim = CSS.indexOf("\n}", i);
  const corpo = CSS.slice(i, fim);
  const mapa = new Map<string, string>();
  for (const m of corpo.matchAll(/^\s{2}(--[a-z0-9-]+):\s*([^;]+);/gm)) {
    mapa.set(m[1], m[2].trim());
  }
  return mapa;
}

const CLARO = bloco(":root");
const ESCURO = bloco(".dark");

/** Segue a cadeia de `var()` até um valor que não seja `var()`. */
function resolver(expr: string, tema: "claro" | "escuro", passos = 0): string {
  if (passos > 10) throw new Error(`cadeia sem fim em ${expr}`);
  const m = expr.match(/^var\((--[a-z0-9-]+)\)$/);
  if (!m) return expr;
  const de = tema === "escuro" ? (ESCURO.get(m[1]) ?? CLARO.get(m[1])) : CLARO.get(m[1]);
  if (de === undefined) throw new Error(`${m[1]} não existe no tema ${tema}`);
  return resolver(de, tema, passos + 1);
}

const TOKENS_USADOS = [
  ...Object.values(CROMO),
  ...SLOTS_DE_SERIE,
  ...FAIXAS_CSAT.map((f) => f.preenchimento),
  preenchimentoCsat(0),
];

describe("grafico — o cromo sai do token, não do tema em JavaScript", () => {
  it("todo token que o módulo usa RESOLVE para hexadecimal literal, nos dois temas", () => {
    // O caso do gráfico quebrado. Um `color-mix()` aqui não dá erro de tipo,
    // não dá erro em teste de componente e não aparece em revisão — aparece
    // como forma sem cor no navegador de alguém.
    for (const expr of TOKENS_USADOS) {
      for (const tema of ["claro", "escuro"] as const) {
        expect(resolver(expr, tema), `${expr} no ${tema}`).toMatch(
          /^#[0-9a-fA-F]{6}$/,
        );
      }
    }
  });

  it("o eixo passa o piso de TEXTO nas três superfícies dos dois temas", () => {
    // O `stroke` do `XAxis` pinta a linha E o texto das marcas, então o piso é
    // 4,5:1 e não 3:1. O valor anterior (`#94a3b8` claro, `#475569` escuro)
    // reprovava até o de forma: 2,34 e 1,79 no pior caso.
    const SUPERFICIES = {
      claro: ["--bg-base", "--surface", "--surface-elevated"],
      escuro: ["--bg-base", "--surface", "--surface-elevated"],
    };
    for (const tema of ["claro", "escuro"] as const) {
      const eixo = resolver(CROMO.eixo, tema);
      for (const nome of SUPERFICIES[tema]) {
        const fundo = resolver(`var(${nome})`, tema);
        expect(contraste(eixo, fundo), `eixo sobre ${nome} no ${tema}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("a grade NÃO mudou de valor — é higiene, e higiene não muda a tela", () => {
    // A regra do @chamadoshs: cor é higiene ou acessibilidade conforme quem
    // carrega a informação. A linha de grade não carrega — a marca do eixo
    // carrega. Se este caso reprovar, alguém trocou o token por outro degrau, e
    // aí é mudança de aparência disfarçada de migração.
    expect(resolver(CROMO.grade, "claro")).toBe("#f1f5f9");
    expect(resolver(CROMO.grade, "escuro")).toBe("#1e3a5f");
  });

  it("o fundo e o texto da dica são EXATOS nos dois temas", () => {
    expect(resolver(CROMO.dicaFundo, "claro")).toBe("#ffffff");
    expect(resolver(CROMO.dicaFundo, "escuro")).toBe("#132238");
    expect(resolver(CROMO.dicaTexto, "claro")).toBe("#0f172a");
    expect(resolver(CROMO.dicaTexto, "escuro")).toBe("#f1f5f9");
  });

  it("nenhum estilo de dica carrega hexadecimal cravado", () => {
    // O jeito de perder tudo isto é alguém escrever `#132238` de volta num dos
    // dois objetos porque "ficou igual".
    const texto = JSON.stringify([ESTILO_DICA, ENVOLTORIO_DICA]);
    expect(texto).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(ESTILO_DICA.backgroundColor).toBe("var(--surface)");
  });
});

describe("grafico — os slots de série", () => {
  it("são sete, e nenhum repete", () => {
    expect(SLOTS_DE_SERIE).toHaveLength(7);
    expect(new Set(SLOTS_DE_SERIE).size).toBe(7);
  });

  it("o índice cicla no sétimo, e não devolve indefinido", () => {
    // Série sem cor some do gráfico sem erro nenhum.
    expect(slotCategorico(0)).toBe("var(--chart-1)");
    expect(slotCategorico(6)).toBe("var(--chart-7)");
    expect(slotCategorico(7)).toBe("var(--chart-1)");
    expect(slotCategorico(13)).toBe("var(--chart-7)");
  });

  it("índice inválido recua para o primeiro slot", () => {
    expect(slotCategorico(-1)).toBe("var(--chart-1)");
    expect(slotCategorico(1.5)).toBe("var(--chart-1)");
    expect(slotCategorico(Number.NaN)).toBe("var(--chart-1)");
  });

  it("a série temporal única usa um slot da paleta, e sempre o mesmo", () => {
    expect(SLOTS_DE_SERIE).toContain(COR_SERIE_TEMPORAL);
    expect(COR_SERIE_TEMPORAL).toBe("var(--chart-1)");
  });
});

describe("grafico — as três faixas da satisfação", () => {
  it("as bordas das faixas são as que o operador decidiu", () => {
    // 1-4 danger, 5-7 warning, 8-10 success. As bordas são o que quebra numa
    // reescrita distraída: 4 e 5, 7 e 8.
    expect(preenchimentoCsat(1)).toBe("var(--fill-danger)");
    expect(preenchimentoCsat(4)).toBe("var(--fill-danger)");
    expect(preenchimentoCsat(5)).toBe("var(--fill-warning)");
    expect(preenchimentoCsat(7)).toBe("var(--fill-warning)");
    expect(preenchimentoCsat(8)).toBe("var(--fill-success)");
    expect(preenchimentoCsat(10)).toBe("var(--fill-success)");
  });

  it("nota fora da escala recua para o NEUTRO", () => {
    // Se o backend passar a mandar 0-10, o zero não pode virar vermelho: seria
    // afirmar "insatisfeito" sobre um valor que ninguém definiu.
    expect(preenchimentoCsat(0)).toBe("var(--border-control)");
    expect(preenchimentoCsat(11)).toBe("var(--border-control)");
    const faixas = FAIXAS_CSAT.map((f) => f.preenchimento);
    expect(faixas).not.toContain(preenchimentoCsat(0));
  });

  it("as três faixas cobrem 1 a 10 sem buraco e sem sobreposição", () => {
    const cobertas = new Set<number>();
    for (const f of FAIXAS_CSAT) {
      for (let n = f.de; n <= f.ate; n++) {
        expect(cobertas.has(n), `nota ${n} em duas faixas`).toBe(false);
        cobertas.add(n);
      }
    }
    expect([...cobertas].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });
});

/** Contraste WCAG entre dois hexadecimais de seis dígitos. */
function contraste(a: string, b: string): number {
  const lum = (hex: string) => {
    const n = hex.replace("#", "");
    const canais = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255);
    const f = canais.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  };
  const [alto, baixo] = lum(a) > lum(b) ? [lum(a), lum(b)] : [lum(b), lum(a)];
  return (alto + 0.05) / (baixo + 0.05);
}
