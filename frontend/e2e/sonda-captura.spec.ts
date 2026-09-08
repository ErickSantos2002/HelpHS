import { expect, test } from "@playwright/test";

import {
  conferirPixel,
  corDeFundoEsperada,
  lerCorEfetiva,
  // @ts-expect-error — módulo de build em .mjs, sem tipos.
} from "../scripts/sonda-captura.mjs";

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
    // o vermelho não casa a faixa, o escuro não casa, o transparente não casa.
    // A faixa e o token davam a mesma resposta na bateria inteira, e a bateria
    // não provava nada sobre qual dos dois estava sendo usado.
    //
    // `rgb(240, 240, 240)` separa os dois: é claro, casa a faixa, e **não é**
    // `--bg-base`. Só a comparação com o token acusa.
    await page.goto("/galeria.html");
    await page.addStyleTag({
      content: ".min-h-screen { background: rgb(240, 240, 240) !important; }",
    });
    const erro = await conferirPixel(page, "claro").catch((e: Error) => e);
    expect(
      erro,
      "uma faixa aproximada de cor clara liberaria isto",
    ).toBeInstanceOf(Error);
    expect((erro as Error).message).toContain("rgb(240, 240, 240)");
    expect((erro as Error).message).toContain("rgb(248, 250, 252)");
  });

  test("BLOQUEIA com o BODY certo e o elemento de cima errado", async ({
    page,
  }) => {
    // O caso que a sessão do ChamadosHS pediu, e que refuta a primeira versão
    // desta trava.
    //
    // Ela seguia a cascata do canvas — html, e se transparente o body. Lá o
    // `body` fica claro enquanto uma div do app pinta o viewport de escuro, e a
    // cascata leria o body: valor opaco, legítimo, e do tema errado.
    //
    // Aqui o `body` continua com `--bg-base` e só a div que cobre é trocada.
    // Uma sonda que lê o body libera; esta tem de bloquear.
    await page.goto("/galeria.html");
    await page.addStyleTag({
      content: ".min-h-screen { background: rgb(13, 27, 42) !important; }",
    });
    const corpo = await page.evaluate(
      () => getComputedStyle(document.body).backgroundColor,
    );
    expect(corpo, "o body continua com a cor certa do tema claro").toBe(
      "rgb(248, 250, 252)",
    );
    const erro = await conferirPixel(page, "claro").catch((e: Error) => e);
    expect(
      erro,
      "uma sonda que lê o body veria a cor certa e liberaria",
    ).toBeInstanceOf(Error);
    expect((erro as Error).message).toContain("rgb(13, 27, 42)");
  });

  test("BLOQUEIA quando nada pinta o viewport", async ({ page }) => {
    // O modo de falhar que medir às cegas esconde: sem nada opaco cobrindo e
    // com os dois fundos transparentes, a foto sai com o branco do navegador.
    await page.goto("/galeria.html");
    await page.addStyleTag({
      content:
        "html, body, .min-h-screen { background: transparent !important; }",
    });
    const erro = await conferirPixel(page, "claro").catch((e: Error) => e);
    expect(erro).toBeInstanceOf(Error);
    expect((erro as Error).message).toContain("nada pinta o viewport");
  });

  test("normaliza `color(srgb …)`, que é como o token chega", async ({
    page,
  }) => {
    // A div que cobre o viewport usa classe de token, e o Chromium devolve
    // `color(srgb …)` para tudo que sai de `color-mix()`. Comparar strings
    // faria a sonda NUNCA casar — e a versão anterior, que lia o body, escapava
    // disso por acidente, porque o `base.css` pinta com valor literal.
    //
    // A primeira versão deste caso só checava que `conferirPixel` resolvia — e
    // resolvia mesmo SEM a normalização, porque o elemento em `color(srgb …)`
    // era descartado, a sonda caía no recuo do `body`, e o `body` está certo.
    // O RECUO MASCARAVA A PERDA. A mutação pegou.
    //
    // Agora o caso prova de ONDE veio a medição.
    await page.goto("/galeria.html");
    const cobre = await page.evaluate(
      () =>
        getComputedStyle(document.querySelector(".min-h-screen")!)
          .backgroundColor,
    );
    expect(cobre, "o elemento que cobre chega no formato color(srgb …)").toContain(
      "color(srgb",
    );

    const lido = await lerCorEfetiva(page);
    expect(
      lido.cobrindo.length,
      "sem normalizar, o elemento em color(srgb) seria descartado e a lista ficaria vazia",
    ).toBeGreaterThan(0);
    expect(lido.cobrindo[lido.cobrindo.length - 1].quem).toContain("min-h-screen");
    expect(lido.canvas).toBe(lido.cobrindo[lido.cobrindo.length - 1].cor);

    await expect(conferirPixel(page, "claro")).resolves.toBeUndefined();
  });
});
