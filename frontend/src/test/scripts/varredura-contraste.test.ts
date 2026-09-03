import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Os casos de prova da varredura de contraste, amarrados à suíte.
 *
 * O script sabe se provar sozinho (`--provar`), mas prova que ninguém roda não
 * guarda nada. As oito armadilhas que ele trata foram todas achadas por
 * acidente, uma de cada vez, e três delas **transformavam reprovação em
 * aprovação** — o modo de falhar que passa por acerto. Voltar em silêncio é
 * exatamente o que se espera delas.
 *
 * O caso de controle é o que dá valor aos outros: sem ele, "a varredura
 * corretamente não conta este par" e "a varredura não vê nada" são
 * indistinguíveis, e uma exclusão larga demais passaria por conserto.
 */
const SCRIPT = resolve(process.cwd(), "scripts/varredura-contraste.mjs");

describe("varredura de contraste", () => {
  it("os casos de prova passam", () => {
    // `--provar` sai com 1 se algum falhar, e `execFileSync` levanta erro nesse
    // caso — com a saída anexada, para o relatório dizer qual caiu.
    let saida: string;
    try {
      saida = execFileSync("node", [SCRIPT, "--provar"], { encoding: "utf-8" });
    } catch (erro) {
      const e = erro as { stdout?: string };
      throw new Error(`casos de prova falharam:\n${e.stdout ?? erro}`);
    }
    expect(saida).toMatch(/✔ os \d+ casos passam\./);
  });

  it("a varredura roda sobre o src/ sem estourar", () => {
    // Guarda contra o modo de falhar mais silencioso de todos: o script quebrar
    // e devolver lista vazia, que se lê como "nenhuma reprovação".
    const saida = execFileSync("node", [SCRIPT, "--json"], {
      encoding: "utf-8",
      maxBuffer: 8 * 1024 * 1024,
    });
    const achados = JSON.parse(saida);
    expect(Array.isArray(achados)).toBe(true);
    for (const a of achados) {
      expect(a).toHaveProperty("arquivo");
      expect(a.razao).toBeLessThan(4.5);
      expect(a.razao).toBeGreaterThan(1);
    }
  });
});
