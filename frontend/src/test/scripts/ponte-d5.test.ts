import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// @ts-expect-error — script de build em .mjs, sem tipos.
import { conferirPonte, linhasDoEspelho } from "../../../scripts/ponte-d5.mjs";

/**
 * A catraca da ponte do desvio D5, amarrada à suíte.
 *
 * O `index.css` espelha a rampa `slate` no tema claro com os valores
 * **cravados** em canais. É uma segunda fonte de verdade para a paleta, e
 * nenhuma recópia de token a alcança: se o pacote mudar um degrau, estas linhas
 * seguem dizendo o valor antigo e a tela pinta o valor antigo — sem erro, sem
 * aviso, sem diferença de hash.
 *
 * O modo de falhar não é hipotético. Veio da sessão do ChamadosHS, cuja ponte
 * equivalente ficou **dois valores atrás por uma tarde**, com os arquivos
 * batendo e a tela pintando o de antes.
 */
const CSS = resolve(process.cwd(), "src/index.css");
const TOKENS = resolve(process.cwd(), "src/design-system/tokens/colors.css");

describe("ponte do desvio D5", () => {
  it("o espelho reflete o pacote", () => {
    const { problemas } = conferirPonte();
    expect(problemas).toEqual([]);
  });

  it("a conferência alcança as seis linhas do espelho", () => {
    // Piso de cobertura. Sem ele, "nenhuma divergência" e "o padrão parou de
    // casar e o laço não roda" produzem exatamente a mesma saída verde — foi
    // assim que a galeria mediu 28 de 85 elementos e passou.
    expect(linhasDoEspelho(readFileSync(CSS, "utf-8"))).toHaveLength(6);
  });

  it("acusa quando a PONTE fica atrás do pacote", () => {
    const css = readFileSync(CSS, "utf-8").replace(
      ".text-slate-100 { color: rgb(15 23 42);",
      ".text-slate-100 { color: rgb(15 23 43);",
    );
    const { problemas } = conferirPonte({ textoCss: css });
    expect(problemas).toHaveLength(1);
    expect(problemas[0]).toContain("text-slate-100");
  });

  it("acusa quando o PACOTE muda um degrau", () => {
    // O outro lado da mesma divergência, e o que de fato vai acontecer: quem
    // mexe é o pacote, e o espelho é que fica para trás sem ninguém tocar nele.
    const tokens = readFileSync(TOKENS, "utf-8").replace(
      "--color-slate-900: #0f172a;",
      "--color-slate-900: #0f172b;",
    );
    const { problemas } = conferirPonte({ textoTokens: tokens });
    expect(problemas).toHaveLength(1);
    expect(problemas[0]).toContain("slate-900");
  });

  it("o valor esperado vem do SELETOR, não do comentário", () => {
    // O comentário ao lado de cada linha nomeia o degrau, e é tentador conferir
    // por ele. Não se pode: bastaria errar os dois lados juntos para a checagem
    // passar, e uma ferramenta cujo trabalho é detectar divergência não aceita
    // a própria anotação como prova.
    //
    // Aqui o comentário mente e a linha continua certa — se a conferência
    // olhasse para ele, este caso acusaria.
    const css = readFileSync(CSS, "utf-8").replace(
      "rgb(15 23 42);   }   /* slate-900 */",
      "rgb(15 23 42);   }   /* slate-50 */",
    );
    expect(css).not.toBe(readFileSync(CSS, "utf-8")); // a troca pegou
    expect(conferirPonte({ textoCss: css }).problemas).toEqual([]);
  });
});
