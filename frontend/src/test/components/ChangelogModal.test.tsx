import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChangelogModal } from "../../components/layout/ChangelogModal";
import { APP_VERSION, CHANGELOG } from "../../data/changelog";
import { AA, contraste } from "../helpers/contraste";

/**
 * O "O que há de novo?", e por que ele ganhou teste próprio na Fase 16.
 *
 * Ele tinha **21** classes de paleta crua e **3** `<svg>` soltos — e as cores
 * não eram decoração: o tipo de cada entrada (novidade, corrigido, melhoria)
 * era dito em azul, laranja e verde. Se a migração tivesse trocado a cor e
 * perdido o rótulo, ninguém veria o defeito num diff — a tela continuaria
 * bonita e deixaria de informar quem não distingue as três cores.
 *
 * Por isso os casos de conteúdo perguntam pelo TEXTO, e não pela classe: o
 * happy-dom não aplica CSS nenhum, e um caso que afirmasse
 * `toHaveClass("bg-tint-info")` passaria com a regra morta e falharia com a
 * regra certa escrita de outro jeito. Os únicos casos que leem o arquivo são
 * os de cor, e eles medem os TOKENS, não os hexadecimais.
 */
const FONTE = readFileSync(
  resolve(process.cwd(), "src/components/layout/ChangelogModal.tsx"),
  "utf-8",
);

/** Sem comentário: a oitava armadilha da varredura, que já pegou um caso irmão. */
const CODIGO = FONTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

function abrir() {
  return render(<ChangelogModal open onClose={() => {}} />);
}

describe("ChangelogModal — o que a janela promete", () => {
  it("é um diálogo com nome", () => {
    abrir();
    expect(screen.getByRole("dialog", { name: "O que há de novo?" })).toBeTruthy();
  });

  it("lista todas as versões do changelog", () => {
    abrir();
    for (const v of CHANGELOG) {
      expect(screen.getAllByText(v.version).length, v.version).toBeGreaterThan(0);
    }
  });

  it("marca a versão vigente com TEXTO, não só com a pastilha verde", () => {
    // 1.4.1. A pastilha da versão corrente era `bg-emerald-500`; o selo
    // "Versão atual" é o que sobra para quem não lê a cor.
    abrir();
    expect(screen.getByText("Versão atual")).toBeTruthy();
    expect(APP_VERSION).toBe(CHANGELOG[0].version);
  });

  it("cada entrada diz o tipo por extenso ao lado do texto", () => {
    // O tipo era carregado por três cores. O rótulo é o que o torna legível
    // sem elas — e é ele que os três selos de tinta agora acompanham.
    abrir();
    const rotulos: Record<string, string> = {
      novidade: "Novidade",
      corrigido: "Corrigido",
      melhoria: "Melhoria",
    };
    const esperados = new Set(CHANGELOG.flatMap((v) => v.entries.map((e) => rotulos[e.type])));
    for (const rotulo of esperados) {
      expect(screen.getAllByText(rotulo).length, rotulo).toBeGreaterThan(0);
    }
  });

  it("o texto de cada entrada da versão corrente aparece junto do seu tipo", () => {
    abrir();
    for (const entrada of CHANGELOG[0].entries) {
      const bloco = screen.getByText(entrada.text).closest("div");
      expect(bloco, entrada.text.slice(0, 40)).toBeTruthy();
      expect(
        within(bloco as HTMLElement).getByText(
          { novidade: "Novidade", corrigido: "Corrigido", melhoria: "Melhoria" }[entrada.type],
        ),
      ).toBeTruthy();
    }
  });

  it("não desenha nada quando está fechada", () => {
    render(<ChangelogModal open={false} onClose={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("ChangelogModal — o que a Fase 16 tirou daqui", () => {
  it("não sobrou `<svg>` solto", () => {
    // Eram três: `plus`, `edit` e `trendingUp` — os três já no pacote, com o
    // mesmo `viewBox` 24×24 e o mesmo `fill="none"`.
    expect(CODIGO).not.toContain("<svg");
  });

  it("não sobrou classe da paleta crua", () => {
    expect(CODIGO).not.toMatch(
      /\b(?:[a-z-]+:)*(?:bg|text|border|fill|stroke|divide|ring)-(?:slate|gray|zinc|red|orange|amber|emerald|sky|blue|indigo|violet|rose)-\d/,
    );
    expect(CODIGO).not.toMatch(/\btext-white\b/);
  });

  it("todo modificador de opacidade está na escala do Tailwind", () => {
    // `bg-blue-500/15` gera CSS; `bg-primary/8` **não gera nada** — sem erro,
    // sem aviso, e o elemento fica sem fundo. A escala padrão vai de cinco em
    // cinco, de 0 a 100.
    const fora = [...CODIGO.matchAll(/[a-z][\w-]*\/(\d+)\b/g)]
      .map((m) => Number(m[1]))
      .filter((n) => n > 100 || n % 5 !== 0);
    expect(fora).toEqual([]);
  });
});

/**
 * A variante de cada tipo, que sai do SIGNIFICADO e não da cor que estava lá.
 *
 * Este é o único caso da suíte que lê o arquivo em vez de olhar a tela, e o
 * motivo é o de sempre: o happy-dom não aplica CSS, então a variante escolhida
 * não é observável na árvore. Ler a fonte é o que o teste da `Sidebar` e o do
 * botão de sair da `Topbar` já fazem pelo mesmo motivo.
 *
 * A expressão exige que fundo, texto e borda venham da **mesma** tinta (a
 * retrovisão `\1`): meia troca — fundo novo com texto velho — é o modo de
 * falha que a E8 documentou no `Badge`, e ele passaria por uma verificação
 * que olhasse só o fundo.
 */
function varianteDe(tipo: string): string {
  const inicio = CODIGO.indexOf(`${tipo}: {`);
  if (inicio === -1) return "(tipo ausente)";
  // O recorte TERMINA no `icon:` da própria entrada, e isso não é detalhe.
  // A primeira versão fatiava daqui até o fim do arquivo: com a entrada
  // mutada de propósito para um trio inconsistente, a expressão não casava
  // ali, seguia adiante e devolvia a variante da entrada SEGUINTE — o caso
  // passava lendo o bloco errado. Foi a mutação "meia troca" que mostrou.
  const fim = CODIGO.indexOf("icon:", inicio);
  const bloco = CODIGO.slice(inicio, fim === -1 ? undefined : fim);
  const m = bloco.match(/bg-tint-([a-z]+) text-on-tint-\1 border border-\1\/30/);
  return m ? m[1] : "(nenhuma)";
}

describe("ChangelogModal — a variante sai do significado", () => {
  it("`novidade` é um anúncio, e anúncio é `info`", () => {
    expect(varianteDe("novidade")).toBe("info");
  });

  it("`corrigido` é um defeito resolvido, e resolvido é `success`", () => {
    // Era `warning` — herança do laranja que estava aqui, não decisão de
    // ninguém. Não há nada a que atentar num defeito que já saiu.
    expect(varianteDe("corrigido")).toBe("success");
  });

  it("`melhoria` ficou GÊMEA de `corrigido`, e isso está em aberto", () => {
    // Trava deliberada, não aprovação: nenhuma das seis tintas significa
    // "melhoria", e as duas que sobravam foram descartadas por medida —
    // `primary` é o mesmo azul de `info` (ΔE76 4,5) e `neutral` é alias do
    // fundo do próprio cartão (ΔE76 0,0). Quem der casa própria a `melhoria`
    // troca este número de propósito, e não por acidente.
    expect(varianteDe("melhoria")).toBe("success");
    expect(varianteDe("melhoria")).toBe(varianteDe("corrigido"));
  });

  it("com duas variantes gêmeas, o rótulo é o que distingue — e ele está lá", () => {
    // É o que mantém 1.4.1 de pé apesar da gêmea: a cor deixou de acrescentar
    // a distinção, o texto nunca deixou de carregá-la.
    abrir();
    expect(screen.getAllByText("Corrigido").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Melhoria").length).toBeGreaterThan(0);
  });
});

describe("ChangelogModal — as cores medidas nos tokens", () => {
  it.each([...new Set(["novidade", "corrigido", "melhoria"].map(varianteDe))])(
    "a tinta `%s`, que algum tipo usa, aprova em AA nos dois temas",
    (variante) => {
      // A lista sai do próprio arquivo: se alguém trocar a variante de um
      // tipo, é a tinta NOVA que passa a ser medida — e não a que este teste
      // teria cravado à mão.
      //
      // As tintas carregam alfa de 15% e assentam sobre `--surface-elevated`,
      // que é o fundo do cartão de cada entrada.
      for (const tema of ["claro", "escuro"] as const) {
        expect(
          contraste(`--tint-${variante}`, `--on-tint-${variante}`, tema, "--surface-elevated"),
          `${variante}, ${tema}`,
        ).toBeGreaterThanOrEqual(AA);
      }
    },
  );

  it("a pastilha da versão vigente deixou de ser a cor cheia com branco", () => {
    for (const tema of ["claro", "escuro"] as const) {
      expect(contraste("--action-success", "--text-on-success", tema), tema)
        .toBeGreaterThanOrEqual(AA);
      // O que ela era: `bg-emerald-500` com `text-white`.
      expect(contraste("--color-success-500", "--color-white", tema), tema)
        .toBeLessThan(AA);
    }
  });
});
