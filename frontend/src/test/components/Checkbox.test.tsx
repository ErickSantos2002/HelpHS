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

  it("o foco é visível — o input escondido não pode ser o único indicador", () => {
    // **Defeito do pacote que este componente não tem.** No `Checkbox.jsx` de
    // referência o input é `position:absolute; width:1; height:1; opacity:0` e
    // **nada** reage ao foco dele: quem navega por teclado chega no controle e
    // não vê onde está. Não é anel fraco, é anel nenhum.
    //
    // Aqui o input é `peer` e a caixa desenha o anel. O jsdom não aplica
    // CSS, então o que se prende é a estrutura: as duas metades precisam
    // existir, e perder qualquer uma apaga o foco sem quebrar nada visível.
    const { container } = render(<Checkbox checked={false} label="X" onChange={() => {}} />);
    const input = container.querySelector("input")!;
    expect(input.className).toContain("peer");

    const alvo = container.querySelector('[class*="peer-focus-visible"]');
    expect(alvo).not.toBeNull();
    expect(alvo!.className).toContain("peer-focus-visible:ring-2");
    // E o anel sai do degrau de AÇÃO, como o do Button e o dos campos.
    expect(alvo!.className).toContain("peer-focus-visible:ring-action");
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
        // O visto e o traço usam `--text-on-primary`. O `Checkbox.jsx` do
        // pacote pintava os dois com `--color-white` cravado — 2,69:1 sobre o
        // `--action` do escuro —, e a emenda **E7-b** o corrigiu na origem no
        // mesmo dia. O desvio local durou de uma tarde: hoje este arquivo e a
        // referência dizem a mesma coisa.
        expect(
          contraste("--action", "--text-on-primary", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it("o branco cravado reprovaria no escuro, e é por isso que a E7-b existe", () => {
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
