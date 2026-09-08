import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

/**
 * Quantos blocos a galeria DESTE código declara, lido do repositório.
 *
 * Lido do texto da fonte, e não importado: importar o componente arrastaria
 * React e a árvore inteira para dentro do processo do Playwright, sem ganho —
 * o que se quer aqui é um número, e ele tem de vir do disco, não do navegador.
 * É essa origem que faz a comparação valer: o navegador diz o que está
 * servindo, o disco diz o que deveria estar.
 */
const AMOSTRAS = (() => {
  const fonte = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), "../src/galeria/Galeria.tsx"),
    "utf-8",
  );
  const m = fonte.match(/export const AMOSTRAS = (\d+);/);
  if (!m) {
    throw new Error(
      "AMOSTRAS não encontrada em src/galeria/Galeria.tsx — o marcador da " +
        "galeria saiu ou mudou de forma. Sem ele não há como distinguir a " +
        "galeria de uma 404, e a medição não pode rodar.",
    );
  }
  return Number(m[1]);
})();

/**
 * A trava de PRODUTO, antes da trava de página.
 *
 * São coisas diferentes e nenhuma substitui a outra: esta responde "estou no
 * HelpHS?", e a de `data-galeria` responde "esta página é a galeria deste
 * código?". O incidente que as comprou mostrou por quê — a suíte inteira do
 * HelpHS rodou contra o **ChamadosHS**, que respondia 404 nas rotas dela.
 *
 * A porta exclusiva protege por **acordo**; a identidade protege quando o
 * acordo falha — um checkout antigo ainda de pé, uma porta reaproveitada num
 * túnel, um endereço colado de outro contexto. Combinação se quebra sem avisar.
 *
 * O critério é o marcador de estrutura, **nunca o título**. Título muda por
 * rota, então uma trava baseada nele reprovaria telas legítimas. O título entra
 * no relatório como contexto, para quem lê entender o que foi abraçado.
 *
 * **Falha fechada:** marcador ausente BLOQUEIA. Liberar por omissão é
 * exatamente o modo de falhar que ela existe para não ter. O par disso é o caso
 * que confere que os `.html` declaram o marcador — um garante que a ausência
 * bloqueia, o outro que a presença existe onde precisa.
 *
 * Decisão registrada no `DECISOES.md`, escopo "vale para os dois":
 * HelpHS na 5190, ChamadosHS na 5191, ambas com `strictPort`.
 */
const PRODUTO = "helphs";

async function conferirProduto(page: import("@playwright/test").Page) {
  const marcador = await page.evaluate(() =>
    document.documentElement.getAttribute("data-app"),
  );
  if (marcador === PRODUTO) return;

  const titulo = await page.title();
  const onde = page.url();
  throw new Error(
    marcador === null
      ? `sem marcador de produto em ${onde} (título "${titulo}"). Falha fechada: ` +
        `sem data-app no <html> não há como saber de quem é a página, e liberar ` +
        `por omissão é o modo de falhar que esta trava existe para não ter.`
      : `a página em ${onde} é do produto "${marcador}", e não do "${PRODUTO}" ` +
        `(título "${titulo}"). Servidor do outro produto: confira quem está na ` +
        `porta 5190 — o HelpHS mora nela com strictPort.`,
  );
}

/**
 * A galeria, medida no navegador de verdade.
 *
 * Por que este arquivo existe, com o caso que o comprou: na Fase 7 a medição de
 * TOKENS do `Badge` mostrou **zero** reprovações, e o componente renderizado
 * tinha **sete em quarenta e duas**. Medir o token responde "esta cor sobre
 * aquela passa?". Só isto aqui responde "o que o componente PINTA passa?".
 *
 * Um teste em jsdom não serve: lá `getComputedStyle` não resolve classe do
 * Tailwind nenhuma, e todo elemento volta com `rgba(0, 0, 0, 0)`. É preciso o
 * CSS real — tokens do pacote mais Tailwind compilado — e um motor que o
 * aplique.
 *
 * Não depende do backend: a galeria é entrada própria do Vite, sem roteador e
 * sem sessão.
 */

/** O que a medição devolve por elemento reprovado. */
interface Medicao {
  medidos: number;
  reprovados: Reprovacao[];
}

interface Reprovacao {
  bloco: string;
  piso: number;
  texto: string;
  cor: string;
  fundo: string;
  razao: number;
}

const MEDIR = `(() => {
  // Duas formas, e a segunda quase custou a galeria inteira.
  //
  // O Chromium devolve \`rgb(...)\` para cor literal e **\`color(srgb r g b)\`**
  // para cor que passou por \`color-mix()\` — que é exatamente como o D1 mapeia
  // os tokens deste projeto. A primeira versão deste parser só entendia
  // \`rgb()\` e PULAVA EM SILÊNCIO quase toda a paleta do sistema: media 28 de
  // 85 elementos e passava verde.
  //
  // Quem pegou foi o piso de cobertura, não a leitura do código.
  function parse(c) {
    const rgb = c.match(/rgba?\\(([^)]+)\\)/);
    if (rgb) {
      const p = rgb[1].split(",").map((x) => parseFloat(x.trim()));
      return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }
    // \`color(srgb 0.27 0.33 0.41)\` ou \`color(srgb 0.27 0.33 0.41 / 0.5)\`,
    // com componentes de 0 a 1.
    const srgb = c.match(/color\\(srgb([^)]+)\\)/);
    if (srgb) {
      const partes = srgb[1].split("/");
      const p = partes[0].trim().split(/\\s+/).map(parseFloat);
      if (p.length < 3 || p.some(Number.isNaN)) return null;
      const a = partes.length > 1 ? parseFloat(partes[1]) : 1;
      return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: Number.isNaN(a) ? 1 : a };
    }
    return null;
  }

  function sobre(frente, atras) {
    const a = frente.a;
    return {
      r: frente.r * a + atras.r * (1 - a),
      g: frente.g * a + atras.g * (1 - a),
      b: frente.b * a + atras.b * (1 - a),
      a: 1,
    };
  }

  function luminancia(c) {
    const f = [c.r, c.g, c.b].map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  }

  function razao(a, b) {
    const [maior, menor] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
    return (maior + 0.05) / (menor + 0.05);
  }

  // O fundo EFETIVO: empilha as camadas ate achar uma opaca e compoe de baixo
  // para cima. Parar na primeira camada com alfa daria um numero de fantasia —
  // e as tintas do pacote sao translucidas de proposito.
  function fundoEfetivo(el) {
    const camadas = [];
    let n = el;
    while (n) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) {
        camadas.push(c);
        if (c.a === 1) break;
      }
      n = n.parentElement;
    }
    if (camadas.length === 0) return { r: 255, g: 255, b: 255, a: 1 };
    let base = camadas[camadas.length - 1];
    if (base.a < 1) base = sobre(base, { r: 255, g: 255, b: 255, a: 1 });
    for (let i = camadas.length - 2; i >= 0; i--) base = sobre(camadas[i], base);
    return base;
  }

  const reprovados = [];
  let medidos = 0;
  for (const bloco of document.querySelectorAll("[data-bloco]")) {
    const nome = bloco.getAttribute("data-bloco");
    const piso = bloco.getAttribute("data-piso") === "grafico" ? 3 : 4.5;

    for (const el of bloco.querySelectorAll("*")) {
      // So elementos com texto PROPRIO: um contêiner herda a cor do filho e
      // seria contado duas vezes, com o fundo do lugar errado.
      const proprio = Array.from(el.childNodes)
        .filter((n) => n.nodeType === 3)
        .map((n) => n.textContent.trim())
        .join(" ")
        .trim();
      if (!proprio) continue;

      const estilo = getComputedStyle(el);
      if (estilo.visibility === "hidden" || estilo.display === "none") continue;
      if (parseFloat(estilo.opacity) === 0) continue;

      let cor = parse(estilo.color);
      if (!cor) continue;
      const fundo = fundoEfetivo(el);
      if (cor.a < 1) cor = sobre(cor, fundo);

      medidos++;
      const r = razao(cor, fundo);
      if (r < piso) {
        reprovados.push({
          bloco: nome,
          piso,
          texto: proprio.slice(0, 40),
          cor: estilo.color,
          fundo: "rgb(" + Math.round(fundo.r) + ", " + Math.round(fundo.g) + ", " + Math.round(fundo.b) + ")",
          razao: Math.round(r * 100) / 100,
        });
      }
    }
  }
  return { medidos, reprovados };
})()`;


/**
 * Canario de CSS velho.
 *
 * O servidor de desenvolvimento e REUSADO entre execucoes
 * (`reuseExistingServer: true`). Um servidor subido antes de uma mudanca no
 * `tailwind.config.js` serve CSS sem as classes novas — e a galeria mediu
 * exatamente isso uma vez, acusando quatro reprovacoes que nao existiam. Se eu
 * tivesse "consertado" aquilo, teria quebrado codigo que funciona.
 *
 * Uma classe de token que nao gerou regra faz o elemento HERDAR a cor do pai,
 * o que produz numero plausivel e errado. Este canario reprova alto em vez de
 * medir baixo.
 */
const CLASSES_EXIGIDAS = [
  "text-on-primary",
  "bg-tint-primary",
  "text-on-tint-danger",
  "bg-surface",
  "text-conteudo-muted",
  "border-borda-control",
];

const CANARIO = `(() => {
  const alvo = new Set(CLASSES_EXIGIDAS);
  const achadas = new Set();
  function anda(regras) {
    for (const regra of Array.from(regras)) {
      if (regra.cssRules) anda(regra.cssRules);
      const sel = regra.selectorText;
      if (!sel) continue;
      for (const c of alvo) if (sel.includes("." + c)) achadas.add(c);
    }
  }
  for (const folha of Array.from(document.styleSheets)) {
    try { anda(folha.cssRules); } catch (e) { /* outra origem */ }
  }
  return Array.from(alvo).filter((c) => !achadas.has(c));
})()`;

/**
 * Controle negativo do marcador.
 *
 * Sem ele, "o marcador identifica a galeria" e "o marcador aparece em qualquer
 * página" são indistinguíveis, e um seletor largo demais passaria por conserto.
 * A rota inexistente cai na SPA — que é literalmente o que foi servido em
 * `/galeria.html` no dia em que a medição rodou contra outro produto.
 */
/**
 * A opção escolhida do `RadioCards` PINTA diferente da livre.
 *
 * O estado escolhido sai de `peer-checked:` e da variante descendente
 * `[&_[data-ponto]]`, e as duas só existem se o Tailwind as tiver gerado. Se
 * não gerar — porque alguém montou a classe por concatenação, que é invisível
 * para a varredura dele —, o cartão escolhido fica **idêntico** ao livre: sem
 * erro de compilação, sem aviso, e a medição de contraste continua passando,
 * porque medir duas vezes a mesma cor legítima não reprova nada.
 *
 * Só a comparação entre os dois estados distingue "aplicou" de "não gerou".
 */
test("no RadioCards, a opção escolhida pinta diferente da livre", async ({ page }) => {
  await page.goto("/galeria.html");
  await conferirProduto(page);
  await page.waitForSelector("[data-galeria]");

  const bloco = page.locator('[data-bloco="RadioCards"]');
  await expect(bloco).toBeVisible();

  const escolhido = bloco.getByText("Escolhido").first();
  const livre = bloco.getByText("Livre").first();

  const cor = (l: typeof escolhido) =>
    l.evaluate((el) => {
      const s = getComputedStyle(el as HTMLElement);
      return s.backgroundColor + " | " + s.color + " | " + s.borderColor;
    });

  expect(await cor(escolhido)).not.toBe(await cor(livre));
});

/**
 * As 36 células da E16-b, medidas por estilo COMPUTADO.
 *
 * Seis séries × três superfícies × dois temas. O piso é 3:1 — WCAG 1.4.11,
 * elemento não textual: barra e ponto são forma, não texto.
 *
 * Por que aqui e não numa conta sobre os hexadecimais da emenda: a conta
 * responde "estes doze valores passam?", e a pergunta que importa é "o que o
 * TOKEN entrega na tela passa?". São perguntas diferentes sempre que a recópia
 * do `colors.css` não chega — e foi assim que a E16 anterior entrou com quatro
 * valores reprovando um piso que ela mesma declarava.
 *
 * As amostras não têm texto, então a medição comum da galeria as ignora: ela
 * só olha elemento com texto próprio. Este caso existe para elas.
 */
const MEDIR_GRAFICO = `(() => {
  // Duas formas, e a segunda NAO e opcional: o Chromium devolve
  // \`color(srgb ...)\`, com componentes de 0 a 1, para tudo que sai de um
  // \`color-mix()\` — que e como as superficies do pacote chegam. Um analisador
  // que so entende \`rgb()\` devolve nulo para elas e todas as razoes viram 0.
  // Foi o que aconteceu na primeira execucao deste caso, e e a MESMA
  // armadilha que fez a galeria medir 28 de 85 elementos e passar verde.
  function parse(c) {
    const rgb = c.match(/rgba?\\(([^)]+)\\)/);
    if (rgb) {
      const p = rgb[1].split(",").map((x) => parseFloat(x.trim()));
      return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }
    const srgb = c.match(/color\\(srgb([^)]+)\\)/);
    if (srgb) {
      const partes = srgb[1].split("/");
      const p = partes[0].trim().split(/\\s+/).map(parseFloat);
      if (p.length < 3 || p.some(Number.isNaN)) return null;
      const a = partes.length > 1 ? parseFloat(partes[1]) : 1;
      return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: Number.isNaN(a) ? 1 : a };
    }
    return null;
  }
  function lum(c) {
    const f = [c.r, c.g, c.b].map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
  }
  function razao(a, b) {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  }
  const linhas = [];
  for (const caixa of document.querySelectorAll("[data-superficie]")) {
    const fundo = parse(getComputedStyle(caixa).backgroundColor);
    for (const am of caixa.querySelectorAll("[data-chart]")) {
      const cor = parse(getComputedStyle(am).backgroundColor);
      linhas.push({
        superficie: caixa.getAttribute("data-superficie"),
        serie: am.getAttribute("data-chart"),
        cor: getComputedStyle(am).backgroundColor,
        fundo: getComputedStyle(caixa).backgroundColor,
        lido: Boolean(cor && fundo),
        razao: cor && fundo ? razao(cor, fundo) : 0,
      });
    }
  }
  return linhas;
})()`;

type Celula = {
  superficie: string;
  serie: string;
  cor: string;
  fundo: string;
  lido: boolean;
  razao: number;
};

for (const tema of ["claro", "escuro"] as const) {
  test("preenchimento de gráfico — as 30 células do tema " + tema + " passam 3:1", async ({ page }) => {
    await page.goto("/galeria.html");
    await conferirProduto(page);
    await page.waitForSelector("[data-galeria]");
    if (tema === "escuro") {
      await page.getByTestId("alternar-tema").click();
      await expect(page.locator("html")).toHaveClass(/dark/);
    }

    const celulas = (await page.evaluate(MEDIR_GRAFICO)) as Celula[];

    // Dois pisos de cobertura, separados por família. Um número só não serve:
    // se um dos dois blocos sumisse do DOM, o total ainda poderia bater por
    // acaso — e "mediu tudo" e "mediu metade duas vezes" se leem iguais.
    const daPaleta = celulas.filter((c) => !c.superficie.startsWith("prio-"));
    const daPrioridade = celulas.filter((c) => c.superficie.startsWith("prio-"));
    expect(daPaleta, "6 séries × 3 superfícies").toHaveLength(18);
    expect(daPrioridade, "4 prioridades × 3 superfícies").toHaveLength(12);

    const tabela = celulas
      .map(
        (c) =>
          `  chart-${c.serie}  ${c.superficie.padEnd(9)}  ${c.razao
            .toFixed(2)
            .padStart(6)}   ${c.cor} sobre ${c.fundo}`,
      )
      .join("\n");
    console.log(`\nE16-b — tema ${tema}\n${tabela}`);

    // Separado de propósito da reprovação: cor que o analisador não entendeu
    // devolve razão 0, e 0 se lê como "reprovou" quando na verdade é "não
    // mediu". As duas coisas exigem consertos opostos.
    expect(
      celulas.filter((c) => !c.lido).map((c) => `chart-${c.serie} em ${c.superficie}`),
      "células cuja cor o analisador não entendeu — isto é falha de LEITURA, não de contraste",
    ).toEqual([]);

    const reprovadas = celulas.filter((c) => c.razao < 3);
    expect(
      reprovadas.map((c) => `chart-${c.serie} em ${c.superficie}: ${c.razao.toFixed(2)}`),
      "séries abaixo de 3:1 (WCAG 1.4.11)",
    ).toEqual([]);
  });
}

/**
 * O par da falha fechada.
 *
 * A trava de produto bloqueia quando o marcador falta — e é isso que se quer.
 * Sem este caso, alguém tirando o `data-app` do `index.html` faria **toda**
 * captura parar, e o relatório diria "sem marcador de produto" sem que ninguém
 * soubesse que o conserto é uma linha de HTML.
 *
 * Um garante que a ausência bloqueia; este garante que a presença existe onde
 * precisa existir. Lido do disco, não do navegador: é o arquivo que declara.
 */
test("as entradas HTML declaram o produto", () => {
  const raiz = dirname(fileURLToPath(import.meta.url));
  for (const arquivo of ["index.html", "galeria.html"]) {
    const html = readFileSync(resolve(raiz, "..", arquivo), "utf-8");
    expect(html, `${arquivo} precisa declarar data-app="${PRODUTO}" no <html>`).toContain(
      `data-app="${PRODUTO}"`,
    );
  }
});

test("o marcador da galeria não existe fora dela", async ({ page }) => {
  await page.goto("/uma-rota-que-nao-existe");
  // A 404 da SPA e do HelpHS: o marcador de PRODUTO libera; o de PAGINA, nao.
  await conferirProduto(page);
  await expect(page.locator("[data-galeria]")).toHaveCount(0);
});

for (const tema of ["claro", "escuro"] as const) {
  test("galeria — nenhum componente reprova o contraste, tema " + tema, async ({
    page,
  }) => {
    await page.goto("/galeria.html");
    await conferirProduto(page);

    // ── Canário de página, ANTES de qualquer captura ────────────────────
    //
    // O `galeria.html` sai do mesmo servidor que serve a aplicação, e um
    // servidor subido antes do arquivo existir devolve a 404 da SPA. Ela vem
    // com o MESMO CSS, então o canário de classes lá embaixo passa tranquilo;
    // só a espera pelo seletor caía, por tempo esgotado, e tempo esgotado não
    // diz o que houve. Foi o segundo servidor obsoleto do mesmo dia.
    const marcador = page.locator("[data-galeria]");
    await marcador
      .waitFor({ timeout: 15_000 })
      .catch(async () => {
        const titulo = await page.title();
        const h1 = await page
          .locator("h1")
          .first()
          .textContent()
          .catch(() => null);
        throw new Error(
          `a página em /galeria.html não é a galeria: sem [data-galeria] ` +
            `(título "${titulo}", h1 "${h1 ?? "—"}").\n` +
            `  O título é o que separa as duas causas:\n` +
            `  - diz "HelpHS" → servidor de desenvolvimento anterior ao ` +
            `arquivo; reinicie o 'npm run dev'.\n` +
            `  - diz outra coisa → o servidor NÃO é o do HelpHS. Foi assim que ` +
            `a suíte apontou para o ChamadosHS: o Vite escorregava de porta em ` +
            `silêncio e o Playwright abraçava o servidor do outro projeto. ` +
            `O HelpHS mora na 5190 com 'strictPort'; confira quem está lá.`,
        );
      });

    // A galeria é a galeria — mas é a DESTE código? Servidor servindo pacote
    // velho mostra a galeria de antes, coerente consigo mesma. Só a comparação
    // contra a fonte no disco separa as duas.
    await expect(
      marcador,
      "a galeria servida declara um número de amostras diferente do que a " +
        "fonte declara. O servidor está servindo pacote antigo: reinicie o " +
        "'npm run dev' antes de acreditar em qualquer número desta galeria.",
    ).toHaveAttribute("data-galeria", String(AMOSTRAS));

    // E renderizou inteira? Um bloco que estourou some sem barulho.
    await expect(
      page.locator("[data-bloco]"),
      "a galeria não renderizou todos os blocos que declara",
    ).toHaveCount(AMOSTRAS);

    // A galeria começa no claro; o botão alterna a classe `dark` na raiz.
    if (tema === "escuro") {
      await page.getByTestId("alternar-tema").click();
      await expect(page.locator("html")).toHaveClass(/dark/);
    } else {
      await expect(page.locator("html")).not.toHaveClass(/dark/);
    }

    const faltando = (await page.evaluate(
      CANARIO.replace("CLASSES_EXIGIDAS", JSON.stringify(CLASSES_EXIGIDAS)),
    )) as string[];
    expect(
      faltando,
      "classes de token sem regra CSS. Provável servidor de desenvolvimento " +
        "servindo config antiga: reinicie o 'npm run dev' antes de acreditar " +
        "em qualquer número desta galeria.",
    ).toEqual([]);

    const { medidos, reprovados } = (await page.evaluate(MEDIR)) as Medicao;

    // Piso de COBERTURA. Sem ele, um seletor quebrado faria a medicao passar
    // medindo zero elemento — e um teste verde que nao mede nada e pior que
    // nenhum, porque conta como cobertura.
    expect(medidos).toBeGreaterThan(40);

    if (reprovados.length > 0) {
      const linhas = reprovados
        .map(
          (r) =>
            "  " +
            r.bloco.padEnd(20) +
            String(r.razao).padStart(6) +
            " (piso " +
            r.piso +
            ")  " +
            r.cor +
            " sobre " +
            r.fundo +
            "  «" +
            r.texto +
            "»",
        )
        .join("\n");
      throw new Error(
        "componentes reprovando no tema " +
          tema +
          " (" +
          reprovados.length +
          "):\n" +
          linhas,
      );
    }
  });
}
