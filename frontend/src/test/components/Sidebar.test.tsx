import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: PAPEL.atual }),
}));
vi.mock("./../../components/layout/ChangelogModal", () => ({
  ChangelogModal: () => null,
}));

import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../../components/layout/Sidebar";
import { ICON_PATHS } from "../../components/ui";
import { AA, contraste } from "../helpers/contraste";

/**
 * A barra lateral, e por que ela tem teste próprio.
 *
 * É o único componente que aparece em **todas** as 33 telas: um defeito aqui
 * não é de uma página, é do sistema. E ela carregava treze `<svg>` escritos à
 * mão — a segunda maior concentração do inventário — que eram, caractere a
 * caractere, os mesmos traçados que o pacote publica. O `Icon.jsx` do design
 * system diz no cabeçalho que os desenhos dele saíram daqui; estes casos
 * prendem a volta, para que a cópia não renasça.
 *
 * O que estes casos medem é o que a barra **promete**, não como ela está
 * escrita: que quem navega por teclado ou leitor de tela alcança cada destino,
 * que a página atual se declara por mais do que cor, e que o menu de um
 * cliente não expõe rota de administrador. Os únicos casos que leem o arquivo
 * são os de cor — classe de Tailwind não existe no jsdom, e medir cor
 * renderizada ali seria medir nada.
 */

/**
 * O papel do usuário da montagem corrente.
 *
 * Precisa ser mutável porque o `vi.mock` é içado para antes dos `import`, e a
 * fábrica dele não pode fechar sobre uma variável declarada depois. O objeto
 * existe desde o topo do módulo; só o campo muda.
 */
const PAPEL: { atual: { id: string; role: string; name: string } } = {
  atual: { id: "u1", role: "admin", name: "Admin" },
};

const FONTE = readFileSync(
  resolve(process.cwd(), "src/components/layout/Sidebar.tsx"),
  "utf-8",
);

function montar(opcoes: {
  papel?: "admin" | "technician" | "client";
  recolhida?: boolean;
  rota?: string;
} = {}) {
  const { papel = "admin", recolhida = false, rota = "/" } = opcoes;
  PAPEL.atual = { id: "u1", role: papel, name: "Fulano" };

  return render(
    <MemoryRouter initialEntries={[rota]}>
      <Sidebar collapsed={recolhida} mobileOpen={false} onMobileClose={() => {}} />
    </MemoryRouter>,
  );
}

describe("Sidebar — o marco de navegação", () => {
  it("expõe um `nav` com nome próprio", () => {
    montar();
    // Sem nome, o leitor de tela anuncia "navegação" e pronto — e este é o
    // único `nav` do sistema, então o nome é o que o distingue do nada.
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeTruthy();
  });

  it("agrupa os destinos em grupos nomeados, e o nome sobrevive ao recolhimento", () => {
    // O rótulo visível da seção só é desenhado no modo expandido; no recolhido
    // sobra um traço decorativo. O nome do grupo é o que resta para quem não vê.
    for (const recolhida of [false, true]) {
      const { unmount } = montar({ recolhida });
      for (const nome of ["Principal", "Gestão", "Administração"]) {
        expect(
          screen.getByRole("group", { name: nome }),
          `grupo "${nome}", recolhida=${recolhida}`,
        ).toBeTruthy();
      }
      unmount();
    }
  });

  it("não lê o rótulo da seção duas vezes no modo expandido", () => {
    montar();
    // O `<p>` visível repete o nome que o grupo já declara. Se ele voltar à
    // árvore de acessibilidade, "Principal" passa a ser anunciado duas vezes.
    //
    // A consulta é por PAPEL de propósito: `getByText` varre o DOM e não
    // consulta a árvore de acessibilidade, então ele acharia o parágrafo
    // escondido e o caso não mediria nada. `queryAllByRole` respeita
    // `aria-hidden` — some o atributo, o parágrafo reaparece aqui.
    const grupo = screen.getByRole("group", { name: "Principal" });
    expect(within(grupo).queryAllByRole("paragraph")).toHaveLength(0);
  });
});

describe("Sidebar — o item ativo", () => {
  it("se declara por `aria-current`, não só pela cor", () => {
    montar({ rota: "/tickets" });
    const ativo = screen.getByRole("link", { name: "Tickets" });
    // 1.4.1: cor não pode ser o único portador da informação "você está aqui".
    expect(ativo.getAttribute("aria-current")).toBe("page");
  });

  it("marca um destino só", () => {
    montar({ rota: "/tickets" });
    const marcados = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("aria-current") === "page");
    expect(marcados.map((a) => a.textContent)).toEqual(["Tickets"]);
  });

  it("o Dashboard não fica ativo em toda rota que começa com barra", () => {
    montar({ rota: "/tickets" });
    expect(
      screen.getByRole("link", { name: "Dashboard" }).getAttribute("aria-current"),
    ).toBeNull();
  });

  it("na tela de um chamado, quem continua marcado é Tickets", () => {
    // O detalhe de um chamado é uma sub-rota de `/tickets`, e é aí que `end`
    // ganha o seu sentido: se todo item fechasse a rota, a barra ficaria sem
    // nenhuma página atual justamente na tela mais visitada do sistema.
    montar({ rota: "/tickets/t1" });
    const marcados = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("aria-current") === "page");
    expect(marcados.map((a) => a.textContent)).toEqual(["Tickets"]);
  });
});

describe("Sidebar — o nome de cada destino", () => {
  it("cada item tem nome acessível com a barra expandida", () => {
    montar({ recolhida: false });
    for (const nome of ["Dashboard", "Tickets", "Base de Conhecimento", "Usuários"]) {
      expect(screen.getByRole("link", { name: nome }), nome).toBeTruthy();
    }
  });

  it("cada item continua tendo nome acessível com a barra RECOLHIDA", () => {
    // O caso que justifica o arquivo: recolhida, o item é só o desenho. O nome
    // vem da dica, que fica na árvore mesmo com `opacity-0` — se alguém
    // trocar a dica por um `title`, ou a condicionar a hover de verdade, todo
    // link do sistema vira "link" sem nome.
    montar({ recolhida: true });
    for (const nome of ["Dashboard", "Tickets", "Base de Conhecimento", "Usuários"]) {
      expect(screen.getByRole("link", { name: nome }), nome).toBeTruthy();
    }
  });

  it("o ícone não entra no nome acessível", () => {
    montar({ recolhida: true });
    const link = screen.getByRole("link", { name: "Dashboard" });
    const svg = link.querySelector("svg");
    // `aria-hidden` no desenho: sem ele o nome do link ganharia o conteúdo do
    // `<svg>` e deixaria de ser previsível.
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("Sidebar — quem vê o quê", () => {
  it("o cliente não alcança nenhuma rota de gestão ou administração", () => {
    montar({ papel: "client" });
    for (const proibido of [
      "Relatórios",
      "Agenda",
      "Grupos",
      "Respostas Rápidas",
      "Usuários",
      "Produtos",
      "Etiquetas",
      "Configuração SLA",
      "Audit Logs",
    ]) {
      expect(screen.queryByRole("link", { name: proibido }), proibido).toBeNull();
    }
    // E vê o que é dele.
    expect(screen.getByRole("link", { name: "Meus Equipamentos" })).toBeTruthy();
  });

  it("o técnico vê gestão, mas não o que é só do admin", () => {
    montar({ papel: "technician" });
    expect(screen.getByRole("link", { name: "Relatórios" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Usuários" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Configuração SLA" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Audit Logs" })).toBeNull();
    // "Meus Equipamentos" é do cliente.
    expect(screen.queryByRole("link", { name: "Meus Equipamentos" })).toBeNull();
  });

  it("um grupo que ficou sem item não é anunciado", () => {
    // O cliente não tem nenhum item de "Gestão"; o grupo vazio some inteiro,
    // em vez de sobrar como cabeçalho de nada.
    montar({ papel: "client" });
    expect(screen.queryByRole("group", { name: "Gestão" })).toBeNull();
    expect(screen.queryByRole("group", { name: "Administração" })).toBeNull();
    expect(screen.getByRole("group", { name: "Principal" })).toBeTruthy();
  });
});

describe("Sidebar — os treze desenhos vêm do pacote", () => {
  it("nenhum `<svg>` é escrito à mão no arquivo", () => {
    // Fora de comentário: os treze traçados que moravam aqui são a origem
    // declarada do `Icon` do pacote, e uma cópia local os congelaria.
    const semComentarios = FONTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(
      /\/\/.*$/gm,
      "",
    );
    expect(semComentarios).not.toContain("<svg");
  });

  it("desenha um ícone por item, todos do conjunto publicado", () => {
    const { container } = montar({ papel: "admin" });
    const desenhos = [...container.querySelectorAll("nav svg")];
    expect(desenhos.length).toBe(screen.getAllByRole("link").length);

    // `Set<string>` explícito: o mapa do pacote é `as const`, e sem a anotação
    // o `has()` só aceitaria os 68 literais — o que é o contrário do que o
    // caso pergunta, que é justamente se um traçado de fora entrou.
    const doPacote = new Set<string>(
      Object.values(ICON_PATHS).flatMap((d) => (typeof d === "string" ? [d] : [...d])),
    );
    for (const svg of desenhos) {
      for (const path of svg.querySelectorAll("path")) {
        expect(doPacote.has(path.getAttribute("d") ?? ""), path.getAttribute("d") ?? "").toBe(
          true,
        );
      }
    }
  });

  it("o ícone do item mantém a escala e o traço da navegação", () => {
    const { container } = montar();
    const svg = container.querySelector("nav svg")!;
    // 24×24 com traço 1,75 e 20px de lado — o envelope que as treze tags
    // locais tinham. Trocar um ícone de outra família (`viewBox="0 0 20 20"`,
    // `fill="currentColor"`) renderiza na escala errada sem quebrar o `tsc`.
    expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(svg.getAttribute("fill")).toBe("none");
    expect(svg.getAttribute("stroke")).toBe("currentColor");
    expect(svg.getAttribute("stroke-width")).toBe("1.75");
    expect(svg.getAttribute("width")).toBe("20");
  });
});

describe("Sidebar — as cores, medidas nos tokens", () => {
  it("não sobrou paleta crua fora de comentário", () => {
    const semComentarios = FONTE.replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
      .replace(/\/\/.*$/gm, "");
    expect(semComentarios).not.toMatch(
      /\b(?:bg|text|border|fill|stroke|from|to|via)-(?:slate|sky|indigo|amber|emerald|violet|rose|gray|zinc|stone|red|orange|yellow|lime|green|teal|cyan|blue|purple|fuchsia|pink)-\d{2,3}\b/,
    );
    // E nenhum branco cravado: `bg-primary` com `text-white` dá 3,83:1.
    expect(semComentarios).not.toContain("text-white");
  });

  /**
   * Cada linha prende as duas metades do par: a **classe** que o arquivo
   * escreve e o **número** que os tokens dela dão. Medir só o token prova que
   * a paleta é sólida e não prova que esta tela a usa — foi assim que passaram
   * o link de pular e a página ativa da `Pagination`.
   */
  it.each([
    ["item em repouso", "text-conteudo-muted", "--surface", "--text-muted"],
    ["item sob o cursor", "hover:text-conteudo-heading", "--surface-elevated", "--text-heading"],
    ["item ativo", "bg-action-tint text-action", "--action-tint", "--action"],
    ["dica do modo recolhido", "bg-surface-elevated", "--surface-elevated", "--text-heading"],
    ["dica: o texto dela", "text-conteudo-heading", "--surface-elevated", "--text-heading"],
    ["rodapé: versão e crédito", "text-conteudo-muted", "--surface", "--text-muted"],
  ] as const)("%s aprova em AA nos dois temas", (_papel, classe, fundo, texto) => {
    expect(FONTE).toContain(classe);
    for (const tema of ["claro", "escuro"] as const) {
      expect(contraste(fundo, texto, tema), tema).toBeGreaterThanOrEqual(AA);
    }
  });

  it("o crédito do rodapé usa o degrau que aprova, e não o de mesmo nome", () => {
    // `text-slate-400 dark:text-slate-600` dava 2,56:1 no claro e 2,11:1 no
    // escuro sobre `--surface`. O degrau `--text-faint`, que seria o nome
    // óbvio, também reprova: 2,56 e 3,36. Por isso o crédito escureceu.
    expect(contraste("--surface", "--text-faint", "claro")).toBeLessThan(AA);
    expect(contraste("--surface", "--text-faint", "escuro")).toBeLessThan(AA);
    expect(contraste("--surface", "--color-slate-400", "claro")).toBeLessThan(AA);
    expect(contraste("--surface", "--color-slate-600", "escuro")).toBeLessThan(AA);
    expect(FONTE).not.toMatch(/text-conteudo-faint/);
  });
});
