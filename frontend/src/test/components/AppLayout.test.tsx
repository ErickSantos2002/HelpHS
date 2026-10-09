import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { AA, contraste } from "../helpers/contraste";

/**
 * O link "Pular para o conteúdo principal".
 *
 * Não é renderizado aqui de propósito: montar o `AppLayout` arrasta `Sidebar`,
 * `Topbar`, roteador e sessão, e o que se quer prender é uma linha de classe.
 * O teste lê o arquivo — se alguém trocar o par de cores, ele cai.
 *
 * Por que este link tem teste próprio e as outras 19 reprovações não: ele é
 * casca e não página, é o primeiro foco de toda página do sistema, e existe
 * exclusivamente para quem navega por teclado. A única pessoa que chega a vê-lo
 * era justamente a que não conseguia lê-lo.
 */
const FONTE = readFileSync(
  resolve(process.cwd(), "src/components/layout/AppLayout.tsx"),
  "utf-8",
);

describe("link de pular para o conteúdo", () => {
  it("não pinta o texto com branco cravado sobre --action", () => {
    // `focus:bg-action focus:text-white` dá 2,69:1 no escuro, onde --action
    // inverte para primary-400. É o mesmo defeito que a emenda E1 consertou no
    // Button, e que aqui passou porque o Checkpoint 1 mediu o token, não o JSX.
    expect(FONTE).toContain("focus:bg-action");
    expect(FONTE).not.toContain("focus:text-white");
    expect(FONTE).toContain("focus:text-on-primary");
  });

  it.each(["claro", "escuro"] as const)(
    "o par do link aprova em AA no tema %s",
    (tema) => {
      expect(contraste("--action", "--text-on-primary", tema)).toBeGreaterThanOrEqual(
        AA,
      );
    },
  );

  it("branco cravado reprovaria no escuro — é por isso que o token existe", () => {
    expect(contraste("--action", "--color-white", "escuro")).toBeLessThan(AA);
  });
});
