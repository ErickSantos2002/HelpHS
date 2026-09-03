import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "../../components/ui/Checkbox";
import { AA, contraste } from "../helpers/contraste";

/** Piso da WCAG 1.4.11: componente de interface e limite gráfico. */
const NAO_TEXTO = 3;

describe("Checkbox", () => {
  it("é uma caixa de seleção de verdade, com nome acessível", () => {
    render(<Checkbox checked label="Disponível no chat" onChange={() => {}} />);
    expect(
      screen.getByRole("checkbox", { name: "Disponível no chat" }),
    ).toBeChecked();
  });

  it("chama onChange com o valor novo, não com o evento", async () => {
    const aoTrocar = vi.fn();
    render(<Checkbox checked={false} label="X" onChange={aoTrocar} />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(aoTrocar).toHaveBeenCalledWith(true);
  });

  it("desabilitado não dispara", async () => {
    const aoTrocar = vi.fn();
    render(<Checkbox checked={false} disabled label="X" onChange={aoTrocar} />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(aoTrocar).not.toHaveBeenCalled();
  });

  it("o hint é uma segunda linha, e não some quando existe", () => {
    render(
      <Checkbox
        checked={false}
        label="Todos os produtos"
        hint="Marcar limpa a seleção individual"
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("Marcar limpa a seleção individual")).toBeInTheDocument();
  });

  it("indeterminado é anunciado como MISTO, e não só desenhado", () => {
    // O `Checkbox.jsx` do pacote desenha o traço e **não** marca a propriedade
    // `indeterminate` no input: quem usa leitor de tela ouve "não marcado", que
    // é a informação errada. Aqui a propriedade do DOM é marcada, e o estado
    // vira `mixed` na árvore de acessibilidade.
    render(<Checkbox checked={false} indeterminate label="Parcial" onChange={() => {}} />);
    const caixa = screen.getByRole("checkbox") as HTMLInputElement;
    expect(caixa.indeterminate).toBe(true);
    expect(caixa).toHaveAttribute("aria-checked", "mixed");
  });

  it("não usa cor cravada", () => {
    const { container } = render(<Checkbox checked label="X" onChange={() => {}} />);
    expect(container.innerHTML).not.toMatch(/slate-\d/);
    expect(container.innerHTML).not.toMatch(/accent-primary/);
    expect(container.innerHTML).not.toMatch(/stroke="white"|#fff/i);
  });

  describe("contraste, com o piso de componente", () => {
    it.each(["claro", "escuro"] as const)(
      "o contorno da caixa vazia se distingue da superfície, tema %s",
      (tema) => {
        // `--border-control`, da emenda E7. Antes dela o pacote usava
        // `--border-strong` aqui, que dá 1,48:1 no claro.
        expect(
          contraste("--surface", "--border-control", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it.each(["claro", "escuro"] as const)(
      "a caixa marcada se distingue da superfície, tema %s",
      (tema) => {
        expect(contraste("--surface", "--action", tema)).toBeGreaterThanOrEqual(
          NAO_TEXTO,
        );
      },
    );

    it.each(["claro", "escuro"] as const)(
      "o visto se distingue da caixa marcada, tema %s",
      (tema) => {
        // **Desvio medido do pacote, o mesmo do `Switch`.** O `Checkbox.jsx`
        // pinta o visto e o traço indeterminado com `--color-white` cravado.
        // Sobre o `--action` do escuro isso dá **2,69:1** — abaixo do piso de
        // 3:1. A emenda E7 corrigiu a bolinha do `Switch` e **não** alcançou
        // estes dois, porque o escopo dela nomeou só o interruptor.
        expect(
          contraste("--action", "--text-on-primary", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it("o branco cravado reprovaria no escuro — é o que o pacote ainda tem", () => {
      expect(contraste("--action", "--color-white", "escuro")).toBeLessThan(
        NAO_TEXTO,
      );
    });

    it("o rótulo e o hint são texto, e vão pelo piso de texto", () => {
      for (const tema of ["claro", "escuro"] as const) {
        expect(contraste("--surface", "--text-body", tema)).toBeGreaterThanOrEqual(AA);
        expect(contraste("--surface", "--text-muted", tema)).toBeGreaterThanOrEqual(AA);
      }
    });
  });
});
