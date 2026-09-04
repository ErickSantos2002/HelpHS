import { describe, expect, it } from "vitest";
import {
  PRIORIDADE,
  PRIORIDADES,
  rotuloDePrioridade,
} from "../../lib/prioridade";
import type { TicketPriority } from "../../lib/prioridade";
import { contraste } from "../helpers/contraste";

/**
 * A fonte única de prioridade.
 *
 * O que este arquivo guarda é a **unicidade**, não o desenho: existiam cinco
 * mapas divergentes nas telas mais o canônico do `Badge`, e a divergência
 * chegava à palavra — "Alto" numa tela, "Alta" noutra, no mesmo sistema.
 */

const TODAS: TicketPriority[] = ["critical", "high", "medium", "low"];
/** Piso da WCAG 1.4.11 para objeto gráfico que carrega informação sozinho. */
const NAO_TEXTO = 3;

describe("prioridade — o rótulo", () => {
  it.each([
    ["critical", "Crítica"],
    ["high", "Alta"],
    ["medium", "Média"],
    ["low", "Baixa"],
  ] as const)("%s é %s, no feminino", (p, esperado) => {
    // Concorda com "prioridade". A emenda E17 fixou isto no pacote; aqui é o
    // lado do HelpHS dela.
    expect(PRIORIDADE[p].rotulo).toBe(esperado);
  });

  it("nenhum rótulo sobrou no masculino", () => {
    const rotulos = TODAS.map((p) => PRIORIDADE[p].rotulo).join(" ");

    expect(rotulos).not.toMatch(/Crítico|Alto|Médio|Baixo/);
  });

  it("valor desconhecido do backend volta cru, sem quebrar", () => {
    expect(rotuloDePrioridade("blocker")).toBe("blocker");
    expect(rotuloDePrioridade("high")).toBe("Alta");
  });
});

describe("prioridade — a ordem", () => {
  it("vai da mais urgente para a menos", () => {
    expect(PRIORIDADES).toEqual(["critical", "high", "medium", "low"]);
  });

  it("a ordem serve para ordenar, e não repete número", () => {
    const ordens = TODAS.map((p) => PRIORIDADE[p].ordem);

    expect(new Set(ordens).size).toBe(4);
  });
});

describe("prioridade — o gráfico não usa a paleta categórica", () => {
  it.each(TODAS)("%s aponta para cor semântica, não para --chart-*", (p) => {
    // `--chart-*` (emenda E16) serve a séries SEM significado próprio. A
    // prioridade tem significado, e ele já está pintado no resto da interface.
    expect(PRIORIDADE[p].grafico).not.toMatch(/--chart-/);
    expect(PRIORIDADE[p].grafico).toMatch(/^var\(--/);
  });
});

describe("prioridade — o ponto", () => {
  it("usa a cor cheia da própria variante", () => {
    expect(PRIORIDADE.critical.ponto).toBe("bg-danger");
    expect(PRIORIDADE.high.ponto).toBe("bg-warning");
    expect(PRIORIDADE.medium.ponto).toBe("bg-info");
  });

  it("o ponto de `low` usa o token que INVERTE por tema", () => {
    // Os degraus fixos falham em um dos dois temas: slate-400 dá 2,34 no claro
    // e slate-500 dá 2,85 no escuro. `--border-control` inverte e passa nos
    // dois, e é o único neutro do pacote que faz isso.
    expect(PRIORIDADE.low.ponto).toBe("bg-borda-control");
  });

  it.each(["claro", "escuro"] as const)(
    "as cores do ponto que PASSAM o piso de 3:1, tema %s",
    (tema) => {
      // `critical` e `medium` passam nos dois temas contra a pior superfície.
      for (const tok of ["--color-danger-500", "--color-info-500", "--border-control"]) {
        expect(contraste("--surface-elevated", tok, tema)).toBeGreaterThanOrEqual(
          NAO_TEXTO,
        );
      }
    },
  );

  it("o ponto de `high` REPROVA o piso, e é por isso que o rótulo é obrigatório", () => {
    // `--color-warning-500` dá 1,96:1 contra a superfície no tema claro.
    // Enquanto a cor for o único portador da informação, isso é reprovação.
    // Com o rótulo em texto ao lado — visível ou `sr-only` — a cor vira
    // REFORÇO, o piso deixa de se aplicar, e a informação existe para quem não
    // a vê. O teste prende o número para que ninguém "aprove" o ponto sozinho.
    expect(contraste("--surface", "--color-warning-500", "claro")).toBeLessThan(
      NAO_TEXTO,
    );
  });
});
