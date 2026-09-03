import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Switch } from "../../components/ui/Switch";
import { AA, contraste } from "../helpers/contraste";

/** Piso da WCAG 1.4.11 para componente de interface e limite gráfico. */
const NAO_TEXTO = 3;

describe("Switch", () => {
  it("é um interruptor de verdade, não um botão com desenho de interruptor", () => {
    // O alternador de tema era um `<button>` com um trilho desenhado dentro.
    // Quem usa leitor de tela ouvia "Modo escuro, botão" — sem estado, sem
    // saber se está ligado. `role="switch"` num input de caixa dá o estado, o
    // teclado e o anúncio de graça.
    render(<Switch checked label="Modo escuro" onChange={() => {}} />);
    const s = screen.getByRole("switch", { name: "Modo escuro" });
    expect(s).toBeChecked();
  });

  it("avisa o estado desligado, e não só o ligado", () => {
    render(<Switch checked={false} label="Modo escuro" onChange={() => {}} />);
    expect(screen.getByRole("switch", { name: "Modo escuro" })).not.toBeChecked();
  });

  it("funciona pelo teclado, porque é um input e não uma div", () => {
    const aoTrocar = vi.fn();
    render(<Switch checked={false} label="Modo escuro" onChange={aoTrocar} />);
    screen.getByRole("switch").focus();
    expect(screen.getByRole("switch")).toHaveFocus();
  });

  it("chama onChange com o valor novo, não com o evento", async () => {
    const aoTrocar = vi.fn();
    render(<Switch checked={false} label="Modo escuro" onChange={aoTrocar} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(aoTrocar).toHaveBeenCalledWith(true);
  });

  it("desabilitado não dispara", async () => {
    const aoTrocar = vi.fn();
    render(<Switch checked={false} disabled label="X" onChange={aoTrocar} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(aoTrocar).not.toHaveBeenCalled();
  });

  it("não usa cor cravada", () => {
    const { container } = render(<Switch checked label="X" onChange={() => {}} />);
    expect(container.innerHTML).not.toMatch(/slate-\d/);
    expect(container.innerHTML).not.toMatch(/\btext-white\b|\bbg-white\b/);
  });

  // ── Contraste: aqui o piso é 3:1, não 4,5:1 ───────────────────────────
  //
  // O interruptor é componente de interface, não texto: quem manda é a WCAG
  // 1.4.11. O rótulo ao lado é texto e segue em 4,5:1.

  describe("contraste, com o piso de componente", () => {
    it.each(["claro", "escuro"] as const)(
      "o trilho ligado se distingue do painel, tema %s",
      (tema) => {
        expect(contraste("--surface", "--action", tema)).toBeGreaterThanOrEqual(
          NAO_TEXTO,
        );
      },
    );

    it.each(["claro", "escuro"] as const)(
      "a bolinha se distingue do trilho ligado, tema %s",
      (tema) => {
        // **Desvio medido do pacote.** Ele pinta a bolinha com `--color-white`
        // cravado, que sobre o `--action` do escuro dá 2,69:1 — o mesmo número
        // que a emenda E1 corrigiu no botão primário e que o link de pular
        // carregava. `--text-on-primary` é o token que a E1 criou para isso.
        expect(
          contraste("--action", "--text-on-primary", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it.each(["claro", "escuro"] as const)(
      "o trilho desligado tem limite perceptível, tema %s",
      (tema) => {
        // **Segundo desvio medido.** O pacote delimita o trilho desligado com
        // `--border-color`: 1,23:1 no claro e 1,39:1 no escuro. Nenhum token de
        // borda do pacote alcança 3:1 contra `--surface` — o mais forte,
        // `--border-strong`, para em 1,48:1. Eles são separadores de superfície,
        // não limites de controle.
        expect(
          contraste("--surface", "--text-muted", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it("o branco cravado reprovaria no escuro, e é por isso que o desvio existe", () => {
      expect(contraste("--action", "--color-white", "escuro")).toBeLessThan(
        NAO_TEXTO,
      );
    });

    it("nenhum token de borda do pacote serviria de limite", () => {
      for (const borda of ["--border-color", "--border-muted", "--border-strong"]) {
        for (const tema of ["claro", "escuro"] as const) {
          expect(contraste("--surface", borda, tema)).toBeLessThan(NAO_TEXTO);
        }
      }
    });

    it("o rótulo ao lado é texto, e segue no piso de texto", () => {
      expect(contraste("--surface", "--text-body", "claro")).toBeGreaterThanOrEqual(AA);
      expect(contraste("--surface", "--text-body", "escuro")).toBeGreaterThanOrEqual(AA);
    });
  });
});
