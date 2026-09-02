import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../../components/ui/Button";
import { AA, contraste } from "../helpers/contraste";

describe("Button", () => {
  it("renders children", () => {
    render(<Button>Clique aqui</Button>);
    expect(
      screen.getByRole("button", { name: "Clique aqui" }),
    ).toBeInTheDocument();
  });

  it("calls onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Enviar</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled when disabled prop is set", () => {
    render(<Button disabled>Enviar</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("is disabled and shows spinner when loading", () => {
    render(<Button loading>Enviar</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
  });

  it("does not call onClick when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Enviar
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("applies danger variant class", () => {
    render(<Button variant="danger">Excluir</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-action-danger");
  });

  // ── Fase 7 — alinhamento com DS/components/core/Button ────────────────

  describe("variantes", () => {
    it("primary pinta o texto com --text-on-primary, nao com branco fixo", () => {
      // O token vale branco no claro e navy no escuro (emenda E1 do pacote).
      // `text-white` cravado devolveria 2,69:1 no tema escuro.
      render(<Button variant="primary">Salvar</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toHaveClass("bg-action");
      expect(btn).toHaveClass("text-on-primary");
      expect(btn).not.toHaveClass("text-white");
    });

    it("secondary sai da superficie, nao da elevada, e tem borda", () => {
      render(<Button variant="secondary">Cancelar</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toHaveClass("bg-surface");
      expect(btn).toHaveClass("text-conteudo");
      expect(btn).toHaveClass("border-borda");
    });

    it("ghost usa --text-muted e fundo transparente", () => {
      render(<Button variant="ghost">Filtrar</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toHaveClass("bg-transparent");
      expect(btn).toHaveClass("text-conteudo-muted");
    });

    it("danger sai do degrau de acao da E2, nao da cor cheia com branco fixo", () => {
      // Era `bg-danger text-white` — 3,76:1, reprovando a §21. A E2 criou o
      // par `--action-danger` / `--text-on-danger`, como o primario ja tinha.
      render(<Button variant="danger">Excluir</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toHaveClass("bg-action-danger");
      expect(btn).toHaveClass("text-on-danger");
      expect(btn).toHaveClass("hover:bg-action-danger-hover");
      expect(btn).not.toHaveClass("text-white");
      expect(btn).not.toHaveClass("bg-danger");
    });

    it("success entrou com a E2, no par dela", () => {
      // Ficou de fora em a5f43d0 porque o pacote mandava `--color-success-500`
      // com branco: 2,54:1, e a rampa acabava no 700 — o hover nao tinha para
      // onde escurecer. A E2 estendeu a rampa ate o 800.
      render(<Button variant="success">Aprovar</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toHaveClass("bg-action-success");
      expect(btn).toHaveClass("text-on-success");
      expect(btn).toHaveClass("hover:bg-action-success-hover");
      expect(btn).not.toHaveClass("text-white");
    });

    it("toda variante tem borda de 1px, inclusive a ghost", () => {
      // O pacote pinta borda em todas — na ghost ela e transparente. Sem isso,
      // ghost e secondary lado a lado nao tem a mesma altura.
      for (const variant of ["primary", "secondary", "danger", "success", "ghost"] as const) {
        const { unmount } = render(<Button variant={variant}>x</Button>);
        expect(screen.getByRole("button")).toHaveClass("border");
        unmount();
      }
    });
  });

  // ── Contraste, medido nos tokens de verdade ───────────────────────────
  //
  // Estes nao olham classe: leem `src/design-system/tokens/colors.css`,
  // resolvem o `var()` encadeado e calculam a razao da WCAG 2.x. Se alguem
  // trocar o valor no token, o teste cai — que e o acidente que a §21 pede
  // para impedir. Os testes de classe acima e este aqui se seguram: um prende
  // qual token o botao consome, o outro prende quanto aquele token vale.
  describe("contraste dos botoes preenchidos", () => {
    const ESTADOS = [
      ["repouso", "--action-danger"],
      ["hover", "--action-danger-hover"],
    ] as const;
    const TEMAS = ["claro", "escuro"] as const;

    for (const tema of TEMAS) {
      for (const [estado, fundo] of ESTADOS) {
        it(`danger no ${estado}, tema ${tema}, aprova em AA`, () => {
          expect(contraste(fundo, "--text-on-danger", tema)).toBeGreaterThanOrEqual(AA);
        });
      }
    }

    it("danger sai dos 3,76:1 de antes nos quatro casos", () => {
      // O valor antigo era a cor cheia da rampa com branco. Fica aqui para que
      // a melhora seja verificavel, e nao so afirmada no commit.
      for (const tema of TEMAS) {
        expect(contraste("--color-danger-500", "--color-white", tema)).toBeLessThan(AA);
        for (const [, fundo] of ESTADOS) {
          expect(contraste(fundo, "--text-on-danger", tema)).toBeGreaterThan(
            contraste("--color-danger-500", "--color-white", tema),
          );
        }
      }
    });

    it("success aprova em AA nos dois estados e nos dois temas", () => {
      for (const tema of TEMAS) {
        expect(contraste("--action-success", "--text-on-success", tema))
          .toBeGreaterThanOrEqual(AA);
        expect(contraste("--action-success-hover", "--text-on-success", tema))
          .toBeGreaterThanOrEqual(AA);
      }
    });

    it("primary tambem, e e o unico dos tres cujo par inverte por tema", () => {
      for (const tema of TEMAS) {
        expect(contraste("--action", "--text-on-primary", tema)).toBeGreaterThanOrEqual(AA);
        expect(contraste("--action-hover", "--text-on-primary", tema))
          .toBeGreaterThanOrEqual(AA);
      }
      // `danger` e `success` sao degraus absolutos: mesmo numero nos dois
      // temas. O primario nao — e por isso precisou da emenda E1.
      expect(contraste("--action-danger", "--text-on-danger", "claro")).toBeCloseTo(
        contraste("--action-danger", "--text-on-danger", "escuro"),
        10,
      );
      expect(contraste("--action", "--text-on-primary", "claro")).not.toBeCloseTo(
        contraste("--action", "--text-on-primary", "escuro"),
        1,
      );
    });
  });

  describe("icone", () => {
    it("renderiza o icone antes do rotulo", () => {
      render(
        <Button icon={<svg data-testid="icone" />}>Novo chamado</Button>,
      );
      const btn = screen.getByRole("button");
      const icone = screen.getByTestId("icone");
      expect(btn).toContainElement(icone);
      expect(
        icone.compareDocumentPosition(btn.lastChild as Node) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    it("o icone da lugar ao anel enquanto carrega", () => {
      render(
        <Button loading icon={<svg data-testid="icone" />}>
          Salvando
        </Button>,
      );
      expect(screen.queryByTestId("icone")).not.toBeInTheDocument();
    });
  });

  describe("fullWidth", () => {
    it("ocupa a linha inteira quando pedido", () => {
      render(<Button fullWidth>Entrar</Button>);
      expect(screen.getByRole("button")).toHaveClass("w-full");
    });

    it("nao ocupa a linha inteira por padrao", () => {
      render(<Button>Entrar</Button>);
      expect(screen.getByRole("button")).not.toHaveClass("w-full");
    });

    it("nao atropela o className que as paginas ja passam", () => {
      // 14 chamadas passam `w-full` ou `w-full sm:w-auto` por className hoje.
      // A prop e adicao; as paginas migram nas Fases 11-16.
      render(<Button className="w-full sm:w-auto">Novo</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toHaveClass("w-full");
      expect(btn).toHaveClass("sm:w-auto");
    });
  });

  describe("carregando", () => {
    it("o anel e decorativo: nao entra no nome acessivel do botao", () => {
      render(<Button loading>Salvar</Button>);
      expect(
        screen.getByRole("button", { name: "Salvar" }),
      ).toBeInTheDocument();
    });

    it("o anel herda a cor do texto do botao, nao a cor primaria fixa", () => {
      const { container } = render(<Button variant="danger" loading>Excluir</Button>);
      const anel = container.querySelector("[aria-hidden='true']");
      expect(anel).not.toBeNull();
      expect(anel).toHaveClass("border-current");
    });
  });
});
