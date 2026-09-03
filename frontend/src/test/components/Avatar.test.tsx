import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Avatar } from "../../components/ui/Avatar";
import { AA, contraste } from "../helpers/contraste";

describe("Avatar", () => {
  it("tira as iniciais das duas primeiras palavras", () => {
    render(<Avatar name="Ana Ferreira Souza" />);
    expect(screen.getByText("AF")).toBeInTheDocument();
  });

  it("a mesma pessoa recebe a mesma cor em qualquer tela", () => {
    const { container: a } = render(<Avatar name="Ana Ferreira" />);
    const { container: b } = render(<Avatar name="Ana Ferreira" />);
    expect(a.firstElementChild?.className).toBe(b.firstElementChild?.className);
  });

  it("com foto, ignora as iniciais e descreve a imagem com o nome", () => {
    render(<Avatar name="Ana Ferreira" src="/foto.png" />);
    expect(screen.getByRole("img")).toHaveAccessibleName("Ana Ferreira");
    expect(screen.queryByText("AF")).not.toBeInTheDocument();
  });

  it.each([
    ["xs", "w-6"],
    ["sm", "w-8"],
    ["md", "w-10"],
    ["lg", "w-12"],
  ] as const)("tamanho %s = o diametro do pacote", (size, classe) => {
    render(<Avatar name="Ana Ferreira" size={size} />);
    expect(screen.getByText("AF")).toHaveClass(classe);
  });

  // ── Fase 7 ────────────────────────────────────────────────────────────

  it("nenhuma cor do disco vem de fora do pacote", () => {
    // `purple` e `pink` sao da paleta padrao do Tailwind: nao existe
    // --color-purple-* nem --color-pink-* em tokens/colors.css, e o config
    // nao os declara. Eram as duas unicas cores do componente fora do sistema.
    const nomes = [
      "Ana Ferreira", "Bruno Lima", "Carla Dias", "Diego Nunes",
      "Elisa Prado", "Fabio Rocha", "Gisele Alves", "Hugo Martins",
      "Iara Campos", "Joao Beltrao", "Karina Melo", "Lucas Vieira",
    ];
    for (const nome of nomes) {
      const { container, unmount } = render(<Avatar name={nome} />);
      const classe = container.firstElementChild?.className ?? "";
      expect(classe).not.toMatch(/purple|pink/);
      unmount();
    }
  });

  it("usa os seis pares solidos do pacote, e so eles", () => {
    // Avatar.jsx, COLORS: fundo claro da rampa + texto no degrau 700, mais o
    // par neutro. Os `/30` translucidos de antes reprovavam AA nos dois temas
    // (6/6 no claro, 5/6 no escuro); estes passam em 5/6 e 6/6.
    const PARES = [
      ["bg-primary-100", "text-primary-700"],
      ["bg-info-50", "text-info-700"],
      ["bg-warning-50", "text-warning-700"],
      ["bg-danger-50", "text-danger-700"],
      ["bg-success-50", "text-success-700"],
      ["bg-surface-elevated", "text-on-tint-neutral"],
    ];
    const vistos = new Set<string>();
    // A cor sai da soma dos char codes % 6, entao seis nomes de uma letra
    // consecutiva cobrem os seis pares.
    for (const c of ["a", "b", "c", "d", "e", "f"]) {
      const { container, unmount } = render(<Avatar name={c} />);
      const classe = container.firstElementChild?.className ?? "";
      const par = PARES.find(([bg]) => classe.includes(bg));
      expect(par, `nenhum par do pacote em "${classe}"`).toBeDefined();
      expect(classe).toContain(par![1]);
      vistos.add(par![0]);
      unmount();
    }
    expect(vistos.size).toBe(6);
  });

  it("as iniciais tem o peso que o pacote pede", () => {
    // --weight-semibold (600), nao --weight-medium (500).
    render(<Avatar name="Ana Ferreira" />);
    expect(screen.getByText("AF")).toHaveClass("font-semibold");
  });

  it("repassa o que o pacote repassa por ...rest", () => {
    render(<Avatar name="Ana Ferreira" data-testid="disco" />);
    expect(screen.getByTestId("disco")).toBeInTheDocument();
  });

  // ── Emendas E4 e E5 ───────────────────────────────────────────────────

  describe("contraste do par neutro", () => {
    // O teste de cima prende **qual** token o sexto par consome; estes prendem
    // **quanto** ele vale. Sem isto, trocar o valor do token no pacote passaria
    // verde — que foi a lacuna do Checkpoint 1.
    //
    // A **E5** mudou a premissa destes testes. A E4 trocou o par por
    // `--on-tint-neutral` porque `--text-muted` dava 4,34:1 sobre
    // `--surface-elevated`; a E5 corrigiu o `--text-muted` na raiz (slate-500 →
    // slate-600) e devolveu `--on-tint-neutral` à condição de alias. Hoje os
    // dois são o mesmo token, e o par estaria correto por qualquer um dos dois
    // caminhos. O que se prende aqui deixou de ser "o alias salva o par" e
    // passou a ser "os dois valem, nas três superfícies".

    const SUPERFICIES = ["--surface", "--bg-base", "--surface-elevated"] as const;
    const TEMAS = ["claro", "escuro"] as const;

    // Regra escrita no `EMENDAS.md` depois da E5, e comprada com duas emendas:
    // contraste de token de texto se mede contra **as três** superfícies onde
    // ele pode assentar, e nos **dois** temas — não contra a mais clara. Medir
    // só o `--surface` foi o que deixou o `--on-tint-warning` passar por "caso
    // de fronteira" na E2 e o `ghost` do Button passar por conforme aqui.
    for (const tema of TEMAS) {
      for (const superficie of SUPERFICIES) {
        it(`o par neutro aprova em AA sobre ${superficie}, tema ${tema}`, () => {
          expect(
            contraste(superficie, "--on-tint-neutral", tema),
          ).toBeGreaterThanOrEqual(AA);
        });
      }
    }

    it("o alias e o token valem a mesma coisa, nos dois temas", () => {
      // Depois da E5, `--on-tint-neutral` é `var(--text-muted)` em `:root` e no
      // `.dark`. Se algum dia divergirem de novo, é sinal de que alguém cravou
      // um degrau em vez de corrigir a origem — foi o que a E2 precisou fazer,
      // e o que a E5 desfez.
      for (const tema of TEMAS) {
        for (const superficie of SUPERFICIES) {
          expect(contraste(superficie, "--on-tint-neutral", tema)).toBe(
            contraste(superficie, "--text-muted", tema),
          );
        }
      }
    });

    it("o --text-faint segue reprovando, e é por isso que não serve de par", () => {
      // Não é regressão: `--text-faint` é reservado a placeholder e ícone
      // decorativo. O teste existe para que ninguém o promova a par de tinta
      // achando que a E5 o consertou junto — ela não o tocou.
      expect(contraste("--surface-elevated", "--text-faint", "claro")).toBeLessThan(AA);
    });
  });
});
