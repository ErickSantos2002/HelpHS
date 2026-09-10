import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Input } from "../../components/ui/Input";
import { AA, contraste } from "../helpers/contraste";

describe("Input", () => {
  it("renders without label", () => {
    render(<Input placeholder="Digite aqui" />);
    expect(screen.getByPlaceholderText("Digite aqui")).toBeInTheDocument();
  });

  it("renders with label", () => {
    render(<Input label="Nome" />);
    expect(screen.getByLabelText("Nome")).toBeInTheDocument();
  });

  it("renders error message", () => {
    render(<Input label="E-mail" error="E-mail inválido" />);
    expect(screen.getByText("E-mail inválido")).toBeInTheDocument();
  });

  it("renders hint when no error", () => {
    render(<Input hint="Use letras e números" />);
    expect(screen.getByText("Use letras e números")).toBeInTheDocument();
  });

  it("does not render hint when error is present", () => {
    render(<Input hint="Dica" error="Erro" />);
    expect(screen.queryByText("Dica")).not.toBeInTheDocument();
    expect(screen.getByText("Erro")).toBeInTheDocument();
  });

  it("calls onChange when typing", async () => {
    const onChange = vi.fn();
    render(<Input onChange={onChange} />);
    await userEvent.type(screen.getByRole("textbox"), "abc");
    expect(onChange).toHaveBeenCalled();
  });

  it("is disabled when disabled prop is set", () => {
    render(<Input disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
});

// ── Fase 8: os tokens que o campo consome ─────────────────────────────

/** Piso da WCAG 1.4.11 para indicador não textual: borda, anel de foco. */
const NAO_TEXTO = 3;

describe("Input — tokens", () => {
  function classesDo(props = {}) {
    const { container } = render(<Input {...props} />);
    return container.querySelector("input")!.className;
  }

  it("a borda de repouso é contorno de controle, não separador", () => {
    // `--border-control`, da emenda E7. Antes dela era `border-border`
    // (slate-200), que dá 1,23:1 contra a superfície — a linha de cabelo entre
    // um card e o fundo, usada para dizer "aqui começa um campo".
    expect(classesDo()).toContain("border-borda-control");
  });

  it("o anel de foco sai do degrau de AÇÃO, não do de marca", () => {
    // `colors.css` é explícito: "botão primário, item ativo, foco e link saem
    // daqui — nunca de --color-primary-500".
    const c = classesDo();
    expect(c).toContain("focus:ring-action");
    expect(c).not.toContain("focus:ring-primary");
  });

  it("o erro NÃO troca para action-danger, e isso é deliberado", () => {
    // O movimento óbvio regride o escuro: `--action-danger` só existe no
    // `:root`, e o `.dark` não o redefine. 4,25:1 viraria 3,31:1.
    const c = classesDo({ error: "obrigatório" });
    expect(c).toContain("border-danger");
    expect(c).not.toContain("border-action-danger");
  });

  it("o texto do erro usa o par da tinta, que inverte por tema", () => {
    render(<Input error="campo obrigatório" />);
    expect(screen.getByText("campo obrigatório").className).toContain(
      "text-on-tint-danger",
    );
  });

  it("não sobra cor cravada", () => {
    const { container } = render(
      <Input label="Nome" hint="como aparece no chamado" placeholder="Ana" />,
    );
    expect(container.innerHTML).not.toMatch(/slate-\d/);
  });

  describe("contraste", () => {
    it.each(["claro", "escuro"] as const)(
      "a borda de repouso se distingue da superfície, tema %s",
      (tema) => {
        expect(
          contraste("--surface", "--border-control", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it.each(["claro", "escuro"] as const)(
      "o anel de foco se distingue da superfície, tema %s",
      (tema) => {
        expect(contraste("--surface", "--action", tema)).toBeGreaterThanOrEqual(
          NAO_TEXTO,
        );
      },
    );

    it.each(["claro", "escuro"] as const)(
      "a borda de erro se distingue da superfície, tema %s",
      (tema) => {
        expect(
          contraste("--surface", "--color-danger-500", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it("action-danger seria PIOR no escuro — a prova da não-mudança", () => {
      // Medido, e o número corrige a intuição: `--action-danger` no escuro dá
      // **3,31:1**, que ainda passa o piso de 3:1 — ele não reprova, ele
      // **piora**. O `--color-danger-500` dá 4,25:1 no mesmo lugar, porque não
      // inverte; o `--action-danger` só é declarado no `:root` e o `.dark` não
      // o redefine, então o degrau claro fica sobre o fundo escuro.
      //
      // Se um dia o `.dark` passar a redefinir `--action-danger`, este teste
      // cai e a troca vira possível. Enquanto ele passar, a borda fica onde está.
      const cru = contraste("--surface", "--color-danger-500", "escuro");
      const acao = contraste("--surface", "--action-danger", "escuro");
      expect(acao).toBeLessThan(cru);
      expect(cru).toBeGreaterThanOrEqual(4);
    });

    it.each(["claro", "escuro"] as const)(
      "o texto de erro, o rótulo e o hint são texto, tema %s",
      (tema) => {
        expect(
          contraste("--surface", "--on-tint-danger", tema),
        ).toBeGreaterThanOrEqual(AA);
        expect(contraste("--surface", "--text-body", tema)).toBeGreaterThanOrEqual(AA);
        expect(contraste("--surface", "--text-muted", tema)).toBeGreaterThanOrEqual(AA);
      },
    );
  });
});
