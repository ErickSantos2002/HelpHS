import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { AA, contraste } from "../helpers/contraste";

/**
 * O botão "Sair" do menu do usuário.
 *
 * Lê o arquivo em vez de montar a `Topbar`, que arrastaria roteador, sessão e o
 * contador de notificações para prender uma linha de classe — mesma escolha do
 * teste do link de pular.
 *
 * Por que este botão tem teste próprio: ele pintava `text-danger`, o degrau 500
 * cru, e reprovava em **todas as quatro** combinações de tema e estado. A
 * varredura de contraste só via uma delas — a do hover no escuro —, porque no
 * repouso o fundo vem do painel do menu, um nível acima, e "fundo declarado no
 * ancestral" é uma limitação que ela declara. As outras três só apareceram
 * medindo à mão depois que a primeira apontou o elemento.
 */
const FONTE = readFileSync(
  resolve(process.cwd(), "src/components/layout/Topbar.tsx"),
  "utf-8",
);

describe("botão de sair", () => {
  it("não pinta o texto com o degrau 500 cru", () => {
    // `text-danger` é `--color-danger-500`. Sobre o painel do menu
    // (`--surface`) dá 3,76:1 no claro e 4,25:1 no escuro; sobre os dois
    // fundos de hover, 3,60:1 nos dois temas.
    expect(FONTE).toContain("text-on-tint-danger");
    expect(FONTE).not.toMatch(/\btext-danger\b/);
  });

  it.each([
    ["--surface", "repouso"],
    ["--bg-base", "hover no claro"],
    ["--surface-elevated", "hover no escuro"],
  ] as const)(
    "aprova em AA sobre %s (%s), nos dois temas",
    (superficie, situacao) => {
      // As três superfícies que o botão alcança: o painel em repouso, o
      // `bg-slate-50` do hover claro (que é o `--bg-base`) e o
      // `--surface-elevated` do hover escuro.
      for (const tema of ["claro", "escuro"] as const) {
        expect(
          contraste(superficie, "--on-tint-danger", tema),
          `${situacao}, tema ${tema}`,
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );

  it("o degrau 500 reprovaria nas três, e é por isso que o token existe", () => {
    for (const superficie of ["--surface", "--bg-base", "--surface-elevated"]) {
      expect(contraste(superficie, "--color-danger-500", "claro")).toBeLessThan(AA);
    }
  });
});
