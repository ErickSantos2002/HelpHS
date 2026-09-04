import { expect, test } from "@playwright/test";

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

for (const tema of ["claro", "escuro"] as const) {
  test("galeria — nenhum componente reprova o contraste, tema " + tema, async ({
    page,
  }) => {
    await page.goto("/galeria.html");
    await page.waitForSelector("[data-bloco]");

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
