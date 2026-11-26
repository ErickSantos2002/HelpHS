import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthShell } from "../../pages/auth/AuthShell";
import { AA, contraste, cor, type Tema } from "../helpers/contraste";

/**
 * AUTH-UI-01 — contraste das telas de autenticação nos dois temas.
 *
 * Os painéis dessas telas têm fundo escuro FIXO (`#0D1623`, `#080F1A`), mas o
 * texto seguia o tema da aplicação por dois caminhos: os tokens (`text-conteudo`,
 * as tintas do `Alert`), que sem a classe `dark` valem as cores do tema claro,
 * e as classes `text-slate-*`, que o `index.css` inverte no tema claro. Medido
 * em navegador em 23/11/2026: título 1,02:1, rótulo 1,24:1, aviso de erro
 * 2,45:1.
 *
 * A regra agora: **bloco de fundo escuro fixo carrega a classe `dark`** (os
 * tokens do escuro estão em `.dark { }`, então valem dali para dentro, seja
 * qual for o tema do `<html>`), e **nenhuma dessas telas escreve
 * `text-slate-*`**, que é a classe que o `index.css` inverte pelo `<html>` e
 * que o escopo não alcança.
 */

const PASTA = resolve(process.cwd(), "src/pages/auth");
const TELAS = [
  "AuthShell.tsx",
  "LoginPage.tsx",
  "RegisterPage.tsx",
  "ResetPasswordPage.tsx",
  "VerifyEmailPage.tsx",
];
const fonte = (arquivo: string) => readFileSync(resolve(PASTA, arquivo), "utf-8");

/** Os dois fundos fixos, como estão escritos nas telas. */
const FUNDO_FORMULARIO = "#0D1623";
const FUNDO_APRESENTACAO = "#080F1A";

type RGB = { r: number; g: number; b: number };

function hex(valor: string): RGB {
  const n = parseInt(valor.slice(1), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function luminancia({ r, g, b }: RGB): number {
  const [R, G, B] = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

function razao(a: RGB, b: RGB): number {
  const [maior, menor] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (maior + 0.05) / (menor + 0.05);
}

/** Token (com a opacidade que tiver) composto sobre um fundo opaco. */
function sobre(token: string, tema: Tema, fundo: RGB): RGB {
  const c = cor(token, tema);
  return {
    r: c.a * c.r + (1 - c.a) * fundo.r,
    g: c.a * c.g + (1 - c.a) * fundo.g,
    b: c.a * c.b + (1 - c.a) * fundo.b,
  };
}

describe("AUTH-UI-01 — as telas não escrevem a classe que o tema claro inverte", () => {
  it.each(TELAS)("%s não usa text-slate-*", (arquivo) => {
    expect(fonte(arquivo)).not.toMatch(/text-slate-\d/);
  });
});

describe("AUTH-UI-01 — todo bloco de fundo escuro fixo carrega o escopo escuro", () => {
  it.each(TELAS)("%s", (arquivo) => {
    const blocos = fonte(arquivo).match(/className="[^"]*bg-\[#0(?:D1623|80F1A)\][^"]*"/g) ?? [];
    for (const bloco of blocos) {
      expect(bloco).toMatch(/className="dark /);
    }
  });

  it("os quatro blocos existem onde se espera", () => {
    const conta = (arquivo: string) =>
      (fonte(arquivo).match(/className="dark [^"]*bg-\[#0(?:D1623|80F1A)\]/g) ?? []).length;
    expect(conta("AuthShell.tsx")).toBe(1);
    expect(conta("LoginPage.tsx")).toBe(2);
    expect(conta("RegisterPage.tsx")).toBe(1);
  });

  /**
   * O painel do formulário do cadastro usa `bg-surface-base`, que acompanha o
   * tema. Marcá-lo como escuro deixaria o tema claro com texto claro sobre
   * fundo claro — o mesmo defeito, do outro lado.
   */
  it("o painel do cadastro que acompanha o tema NÃO recebe o escopo", () => {
    const painel = fonte("RegisterPage.tsx").match(/className="[^"]*bg-surface-base[^"]*"/g) ?? [];
    expect(painel).toHaveLength(1);
    expect(painel[0]).not.toMatch(/\bdark\b/);
  });
});

describe("AUTH-UI-01 — a moldura", () => {
  function renderiza() {
    render(
      <MemoryRouter>
        <AuthShell
          title="Título da tela"
          subtitle="Subtítulo da tela"
          footer={<a href="/login">Voltar para o acesso</a>}
        >
          <p>conteúdo</p>
        </AuthShell>
      </MemoryRouter>,
    );
  }

  it("a raiz é o escopo escuro e contém título, conteúdo e rodapé", () => {
    renderiza();

    const raiz = screen.getByRole("heading", { name: "Título da tela" }).closest(".dark");
    expect(raiz).not.toBeNull();
    expect(raiz).toContainElement(screen.getByText("conteúdo"));
    expect(raiz).toContainElement(screen.getByRole("link", { name: "Voltar para o acesso" }));
    expect(raiz).toContainElement(screen.getByText(/HelpHS — Health/));
  });

  it("título, subtítulo e rodapé usam tokens semânticos", () => {
    renderiza();

    expect(screen.getByRole("heading", { name: "Título da tela" }).className).toContain(
      "text-conteudo-heading",
    );
    expect(screen.getByText("Subtítulo da tela").className).toContain("text-conteudo-muted");
    expect(screen.getByText(/HelpHS — Health/).className).toContain("text-conteudo-muted");
  });

  /** O link do rodapé vem de cada tela; a área de toque é dada pela moldura. */
  it("o link do rodapé ganha 24px de altura pela moldura", () => {
    renderiza();

    const rodape = screen.getByRole("link", { name: "Voltar para o acesso" }).parentElement;
    expect(rodape?.className).toContain("[&_a]:inline-block");
    expect(rodape?.className).toContain("[&_a]:py-1");
  });
});

/**
 * Os números saem do `colors.css` de verdade, no tema ESCURO — que é o que
 * vale dentro do escopo, qualquer que seja o tema da aplicação.
 */
describe("AUTH-UI-01 — contraste dos tokens sobre os fundos fixos", () => {
  const fundos = [
    ["formulário", hex(FUNDO_FORMULARIO)],
    ["apresentação", hex(FUNDO_APRESENTACAO)],
  ] as const;

  const textos = [
    ["título", "--text-heading"],
    ["rótulo e corpo", "--text-body"],
    ["subtítulo, ajuda e rodapé", "--text-muted"],
    ["link", "--text-link"],
  ] as const;

  for (const [nomeFundo, fundo] of fundos) {
    it.each(textos)(`${nomeFundo}: %s passa de 4,5:1`, (_nome, token) => {
      expect(razao(sobre(token, "escuro", fundo), fundo)).toBeGreaterThanOrEqual(AA);
    });
  }

  it.each(["info", "danger", "success"])("aviso %s passa de 4,5:1 no painel do formulário", (v) => {
    const base = hex(FUNDO_FORMULARIO);
    const tinta = sobre(`--tint-${v}`, "escuro", base);
    expect(razao(sobre(`--on-tint-${v}`, "escuro", tinta), tinta)).toBeGreaterThanOrEqual(AA);
  });

  it("a borda do campo passa de 3:1 contra o painel", () => {
    const base = hex(FUNDO_FORMULARIO);
    expect(razao(sobre("--border-control", "escuro", base), base)).toBeGreaterThanOrEqual(3);
  });

  /** O placeholder do `Input` é `--text-muted` sobre `--surface`. */
  it("o placeholder do campo passa de 4,5:1 dentro do escopo", () => {
    expect(contraste("--surface", "--text-muted", "escuro")).toBeGreaterThanOrEqual(AA);
  });

  /**
   * "Reenviar e-mail de confirmação" e o número do passo do cadastro: texto de
   * link sobre 10–12% da cor de marca. Com `text-primary` (o degrau 500) davam
   * 4,24 e 4,41.
   */
  it.each([
    ["botão de reenviar, 10% de marca", FUNDO_FORMULARIO, 0.1],
    ["número do passo, 12% de marca", FUNDO_APRESENTACAO, 0.12],
  ])("%s", (_nome, fundoHex, alfa) => {
    const base = hex(fundoHex);
    const marca = cor("--color-primary-500", "escuro");
    const fundo = {
      r: alfa * marca.r + (1 - alfa) * base.r,
      g: alfa * marca.g + (1 - alfa) * base.g,
      b: alfa * marca.b + (1 - alfa) * base.b,
    };
    expect(razao(sobre("--text-link", "escuro", fundo), fundo)).toBeGreaterThanOrEqual(AA);
  });
});

describe("AUTH-UI-01 — o painel do cadastro que acompanha o tema", () => {
  const temas: Tema[] = ["claro", "escuro"];
  const textos = [
    ["título", "--text-heading"],
    ["subtítulo e rodapé", "--text-muted"],
    ["link Entrar", "--text-link"],
  ] as const;

  for (const tema of temas) {
    it.each(textos)(`${tema}: %s passa de 4,5:1 sobre --bg-base`, (_nome, token) => {
      expect(contraste("--bg-base", token, tema)).toBeGreaterThanOrEqual(AA);
    });
  }
});

describe("AUTH-UI-01 — áreas de toque dos links isolados", () => {
  it("'Esqueci minha senha' e os links de Política e Termos do login têm 24px", () => {
    const login = fonte("LoginPage.tsx");
    expect(login).toMatch(/to="\/esqueci-senha"\s+className="inline-block py-1 /);
    expect(login.match(/className="inline-block py-1 text-conteudo-link/g)).toHaveLength(2);
  });
});
