import { expect, test } from "@playwright/test";

// @ts-expect-error — módulo de build em .mjs, sem tipos.
import { conferirPixel, corDeFundoEsperada } from "../scripts/sonda-captura.mjs";

/**
 * A trava de PIXEL das sondas de captura, provada **sozinha**.
 *
 * Nenhum destes casos usa o marcador `data-app`, nem a classe `dark` do
 * `<html>`, nem o canário de classes, nem a espera por seletor. É de propósito:
 * a pergunta que eles respondem é se a linha do pixel **bloqueia por conta
 * própria**, e não se o conjunto bloqueia.
 *
 * A pergunta veio de um defeito achado na sonda da sessão do ChamadosHS, e aqui
 * a auditoria encontrou dois:
 *
 *   `capturar-casca.mjs` não tinha checagem de pixel NENHUMA — conferia
 *   `className.includes("dark")`, que é promessa. Página com `class="dark"` e
 *   CSS do tema claro passava e virava evidência.
 *
 *   `capturar-primitivos.mjs` tinha, mas media `document.body` direto e
 *   comparava com a expressão `rgb(2xx, 2xx, 2xx)` — que aprova **qualquer**
 *   cor clara, e não a cor certa.
 *
 * O valor esperado agora vem do `tokens/colors.css` em disco, resolvido pela
 * cadeia de `var()`. Ler o esperado do próprio navegador seria circular: sem o
 * token carregado, os dois lados ficariam vazios e concordariam.
 */
test.describe("sonda de captura — a trava de pixel", () => {
  test("o valor esperado sai do token, e não de uma faixa aproximada", () => {
    // `--bg-base` é `var(--color-slate-50)` no claro e um literal no escuro.
    // Se a resolução da cadeia quebrar, isto cai antes de qualquer navegador.
    expect(corDeFundoEsperada("claro")).toBe("rgb(248, 250, 252)");
    expect(corDeFundoEsperada("escuro")).toBe("rgb(13, 27, 42)");
  });

  test("libera quando o pixel é o do tema", async ({ page }) => {
    // Controle positivo. Sem ele, "bloqueia sempre" passaria por
    // "bloqueia certo".
    await page.goto("/galeria.html");
    await expect(conferirPixel(page, "claro")).resolves.toBeUndefined();
  });

  test("BLOQUEIA quando o pixel é de outro tema, sozinha", async ({ page }) => {
    // A página está no claro. Pedir a conferência do escuro é o mesmo que uma
    // captura de tema escuro contra uma página que não trocou de tema — o
    // caso que a checagem por classe deixava passar quando a classe mentia.
    await page.goto("/galeria.html");
    const erro = await conferirPixel(page, "escuro").catch((e: Error) => e);
    expect(erro).toBeInstanceOf(Error);
    expect((erro as Error).message).toContain("o PIXEL não é o do tema escuro");
    expect((erro as Error).message).toContain("rgb(248, 250, 252)");
  });

  test("BLOQUEIA um cinza claro que NÃO é o do token", async ({ page }) => {
    // O caso decisivo, e ele existe porque a prova sem ele estava furada.
    //
    // A checagem antiga comparava com a expressão `rgb(2xx, 2xx, 2xx)`. Uma
    // mutação que a trouxesse de volta passava em TODOS os outros casos daqui:
    // o vermelho `rgb(255, 0, 0)` não casa a faixa, o escuro não casa, o
    // transparente não casa. A faixa e o token davam a mesma resposta em toda
    // a bateria, e a bateria não provava nada sobre qual dos dois estava
    // sendo usado.
    //
    // `rgb(240, 240, 240)` separa os dois: é claro, casa a faixa, e **não é**
    // `--bg-base`. Só a comparação com o token acusa.
    await page.goto("/galeria.html");
    await page.addStyleTag({
      content: "html { background: rgb(240, 240, 240) !important; }",
    });
    const erro = await conferirPixel(page, "claro").catch((e: Error) => e);
    expect(
      erro,
      "uma faixa aproximada de cor clara liberaria isto",
    ).toBeInstanceOf(Error);
    expect((erro as Error).message).toContain("rgb(240, 240, 240)");
    expect((erro as Error).message).toContain("rgb(248, 250, 252)");
  });

  test("BLOQUEIA quando nada pinta o viewport", async ({ page }) => {
    // O modo de falhar que medir `body` às cegas esconde: com os dois fundos
    // transparentes, a foto sai com o branco do navegador. Uma checagem que
    // lesse só o `body` veria `rgba(0, 0, 0, 0)` e teria de adivinhar o que
    // fazer com isso.
    await page.goto("/galeria.html");
    await page.addStyleTag({
      content: "html, body { background: transparent !important; }",
    });
    const erro = await conferirPixel(page, "claro").catch((e: Error) => e);
    expect(erro).toBeInstanceOf(Error);
    expect((erro as Error).message).toContain("nada pinta o viewport");
  });

  test("mede o CANVAS, e não o body — o html ganha quando pinta", async ({
    page,
  }) => {
    // Regra do CSS: o fundo do canvas vem do `html`; só se ele for
    // transparente é que se propaga o do `body`. Hoje o pacote pinta o `body`
    // e o `html` fica sem fundo, então medir o `body` acerta POR ACIDENTE DE
    // CONFIGURAÇÃO. Aqui o acidente é desfeito: o `html` passa a pintar uma cor
    // errada, o `body` continua com a certa, e a trava tem de acusar.
    await page.goto("/galeria.html");
    await page.addStyleTag({
      content: "html { background: rgb(255, 0, 0) !important; }",
    });
    const erro = await conferirPixel(page, "claro").catch((e: Error) => e);
    expect(
      erro,
      "uma checagem que lesse o body veria a cor certa e liberaria",
    ).toBeInstanceOf(Error);
    expect((erro as Error).message).toContain("rgb(255, 0, 0)");
  });
});
