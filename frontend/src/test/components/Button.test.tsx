import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../../components/ui/Button";

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
    expect(screen.getByRole("button")).toHaveClass("bg-danger");
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

    it("danger fica como estava: fundo --color-danger-500 com texto branco", () => {
      // Nao e endosso — e 3,76:1, reprova a §21. Esta linha existe para que a
      // troca do par danger/success seja uma decisao registrada, e nao uma
      // mudanca que passa despercebida junto de outra coisa. A variante
      // `success` do pacote esta fora do tipo pelo mesmo motivo (2,54:1).
      render(<Button variant="danger">Excluir</Button>);
      const btn = screen.getByRole("button");
      expect(btn).toHaveClass("bg-danger");
      expect(btn).toHaveClass("text-white");
    });

    it("toda variante tem borda de 1px, inclusive a ghost", () => {
      // O pacote pinta borda em todas — na ghost ela e transparente. Sem isso,
      // ghost e secondary lado a lado nao tem a mesma altura.
      for (const variant of ["primary", "secondary", "danger", "ghost"] as const) {
        const { unmount } = render(<Button variant={variant}>x</Button>);
        expect(screen.getByRole("button")).toHaveClass("border");
        unmount();
      }
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
