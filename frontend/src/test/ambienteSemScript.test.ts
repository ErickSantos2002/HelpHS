import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * O ambiente dos testes (happy-dom) NÃO executa `<script>`.
 *
 * É a condição que deixa o GHSA-834v-8h66-3h79 do happy-dom fora de alcance
 * (ver .github/dependencias-conhecidas.toml): a injeção pelo compilador de
 * ESM só existe com `enableJavaScriptEvaluation: true`.
 *
 * Os dois primeiros casos leem o ambiente EFETIVO deste arquivo — pegam a
 * avaliação ligada no `vite.config.ts`. O terceiro varre o código-fonte, para
 * pegar também quem ligar a opção em OUTRO arquivo de teste (docblock
 * `@vitest-environment-options`), que o ambiente deste não enxerga. Se algum
 * cair, aquela entrada da baseline deixa de valer.
 */
const ESTE_ARQUIVO = "src/test/ambienteSemScript.test.ts";

function arquivosDe(pasta: string): string[] {
  return readdirSync(pasta, { withFileTypes: true }).flatMap((e) => {
    const caminho = join(pasta, e.name);
    if (e.isDirectory()) return e.name === "node_modules" ? [] : arquivosDe(caminho);
    return /\.(ts|tsx|js|jsx|mjs|cjs)$/.test(e.name) ? [caminho] : [];
  });
}

describe("ambiente de teste sem execução de script", () => {
  it("a avaliação de JavaScript do happy-dom está desligada", () => {
    const happyDOM = (window as unknown as { happyDOM?: { settings: Record<string, unknown> } })
      .happyDOM;
    expect(happyDOM).toBeDefined();
    expect(happyDOM?.settings.enableJavaScriptEvaluation).toBe(false);
  });

  it("um <script> inserido no documento não roda", async () => {
    const marcas: string[] = [];
    (window as unknown as { __marcas: string[] }).__marcas = marcas;

    const classico = document.createElement("script");
    classico.textContent = "window.__marcas.push('classico')";
    document.body.appendChild(classico);

    const modulo = document.createElement("script");
    modulo.type = "module";
    modulo.textContent = "window.__marcas.push('modulo')";
    document.body.appendChild(modulo);

    document.body.insertAdjacentHTML("beforeend", "<script>window.__marcas.push('html')</script>");

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(marcas).toEqual([]);
  });

  it("nenhum arquivo nem config liga a avaliação de JavaScript", () => {
    const candidatos = [
      ...arquivosDe("src"),
      ...arquivosDe("e2e"),
      "vite.config.ts",
    ];
    const ligam = candidatos
      .map((c) => relative(".", c).split("\\").join("/"))
      .filter((c) => c !== ESTE_ARQUIVO)
      .filter((c) =>
        /enableJavaScriptEvaluation|vitest-environment-options|environmentOptions/.test(
          readFileSync(c, "utf8"),
        ),
      );
    expect(ligam).toEqual([]);
  });
});
