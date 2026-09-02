import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, PriorityBadge, StatusBadge } from "../../components/ui/Badge";
import { AA, contraste } from "../helpers/contraste";

describe("Badge", () => {
  it("renders text", () => {
    render(<Badge>Aberto</Badge>);
    expect(screen.getByText("Aberto")).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("renders label for open status", () => {
    render(<StatusBadge status="open" />);
    expect(screen.getByText("Aberto")).toBeInTheDocument();
  });

  it("renders label for in_progress status", () => {
    render(<StatusBadge status="in_progress" />);
    expect(screen.getByText("Em andamento")).toBeInTheDocument();
  });

  it("renders label for resolved status", () => {
    render(<StatusBadge status="resolved" />);
    expect(screen.getByText("Resolvido")).toBeInTheDocument();
  });

  it("renders label for closed status", () => {
    render(<StatusBadge status="closed" />);
    expect(screen.getByText("Fechado")).toBeInTheDocument();
  });

  it("renders label for cancelled status", () => {
    render(<StatusBadge status="cancelled" />);
    expect(screen.getByText("Cancelado")).toBeInTheDocument();
  });
});

describe("PriorityBadge", () => {
  it("renders label for critical priority", () => {
    render(<PriorityBadge priority="critical" />);
    expect(screen.getByText("Crítico")).toBeInTheDocument();
  });

  it("renders label for high priority", () => {
    render(<PriorityBadge priority="high" />);
    expect(screen.getByText("Alto")).toBeInTheDocument();
  });

  it("renders label for medium priority", () => {
    render(<PriorityBadge priority="medium" />);
    expect(screen.getByText("Médio")).toBeInTheDocument();
  });

  it("renders label for low priority", () => {
    render(<PriorityBadge priority="low" />);
    expect(screen.getByText("Baixo")).toBeInTheDocument();
  });

  // ── Tintas e seus pares ───────────────────────────────────────────────

  describe("as tintas e seus pares", () => {
    it("secondary e muted falam o par da tinta neutra, sem slate cravado", () => {
      for (const v of ["secondary", "muted"] as const) {
        const { container, unmount } = render(<Badge variant={v}>selo</Badge>);
        const classe = container.firstElementChild?.className ?? "";
        expect(classe, v).toContain("text-on-tint-neutral");
        expect(classe, v).not.toMatch(/slate-/);
        unmount();
      }
    });

    it("warning sai do degrau da rampa e vai para o token do par", () => {
      const { container } = render(<Badge variant="warning">selo</Badge>);
      const classe = container.firstElementChild?.className ?? "";
      expect(classe).toContain("text-on-tint-warning");
      // O token já inverte por tema: o `dark:` deixa de ser necessário.
      expect(classe).not.toContain("dark:text-warning-400");
    });

    it.each(["claro", "escuro"] as const)(
      "o par da tinta neutra aprova em AA no tema %s",
      (tema) => {
        expect(
          contraste("--tint-neutral", "--on-tint-neutral", tema),
        ).toBeGreaterThanOrEqual(AA);
      },
    );

    it.each(["claro", "escuro"] as const)(
      "o par da tinta âmbar aprova em AA no tema %s",
      (tema) => {
        // O selo do HelpHS pinta a tinta a 20%, e não os 15% do pacote; medido
        // à parte, o claro dá 6,10:1. Aqui o que se prende é o par de tokens.
        expect(
          contraste("--tint-warning", "--on-tint-warning", tema),
        ).toBeGreaterThanOrEqual(AA);
      },
    );

    it("o --text-faint do pacote reprovaria no muted, e por isso o HelpHS diverge", () => {
      // O pacote pinta `muted` com --text-faint sobre --tint-neutral: 2,34:1 no
      // claro. O desvio é deliberado, e está registrado no relatório da fase.
      expect(contraste("--tint-neutral", "--text-faint", "claro")).toBeLessThan(AA);
    });
  });
});
