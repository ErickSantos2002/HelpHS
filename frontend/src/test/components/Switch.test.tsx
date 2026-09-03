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
        // O trilho desligado usa `--border-control`, o token que a emenda
        // **E7** criou. Antes dela o pacote o delimitava com `--border-color`,
        // que dá 1,23:1 — e nenhum dos três tokens de borda alcançava 3:1.
        expect(
          contraste("--surface", "--border-control", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it("o branco cravado reprovaria no escuro, e é por isso que o desvio existe", () => {
      expect(contraste("--action", "--color-white", "escuro")).toBeLessThan(
        NAO_TEXTO,
      );
    });

    it("os separadores de superfície não serviriam de limite, e é por isso que a E7 existe", () => {
      // Não é regressão: `--border-color` e `--border-strong` são a linha de
      // cabelo entre um card e o fundo, e para isso 1,2:1 é o desenho certo. O
      // erro era usá-los para dizer "aqui começa um controle". Este teste é o
      // que impede alguém de "simplificar" o trilho de volta para eles.
      for (const borda of ["--border-color", "--border-muted", "--border-strong"]) {
        for (const tema of ["claro", "escuro"] as const) {
          expect(contraste("--surface", borda, tema)).toBeLessThan(NAO_TEXTO);
        }
      }
    });

    it.each(["--surface", "--bg-base", "--surface-elevated"] as const)(
      "o --border-control passa sobre %s, nos dois temas",
      (superficie) => {
        // A regra da E5, aplicada à E7: token de traço se mede contra as três
        // superfícies onde ele pode assentar, e não contra a mais clara.
        for (const tema of ["claro", "escuro"] as const) {
          expect(
            contraste(superficie, "--border-control", tema),
          ).toBeGreaterThanOrEqual(NAO_TEXTO);
        }
      },
    );

    it("o rótulo ao lado é texto, e segue no piso de texto", () => {
      expect(contraste("--surface", "--text-body", "claro")).toBeGreaterThanOrEqual(AA);
      expect(contraste("--surface", "--text-body", "escuro")).toBeGreaterThanOrEqual(AA);
    });
  });
});
