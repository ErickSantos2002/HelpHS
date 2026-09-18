import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Spinner } from "../../components/ui/Spinner";

describe("Spinner", () => {
  it("se anuncia como status com nome acessivel", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toHaveAccessibleName("Carregando...");
  });

  it("a cor sai do degrau interativo, nao do degrau de marca", () => {
    // --action = primary-600 no claro e primary-400 no escuro. O `text-primary`
    // de antes resolvia para --color-primary-500 nos dois temas — o degrau que
    // o proprio colors.css marca como "nunca texto" e que nao inverte.
    render(<Spinner />);
    const anel = screen.getByRole("status");
    expect(anel).toHaveClass("text-action");
    expect(anel).not.toHaveClass("text-primary");
  });

  it("gira com o keyframe do pacote, na duracao do pacote", () => {
    // hs-spin 0.7s, de tokens/motion.css — nao o `spin` de 1s do Tailwind.
    render(<Spinner />);
    expect(screen.getByRole("status").className).toContain("hs-spin_0.7s");
  });

  it.each([
    ["sm", "w-4"],
    ["md", "w-6"],
    ["lg", "w-8"],
  ] as const)("tamanho %s tem o diametro do pacote", (size, classe) => {
    render(<Spinner size={size} />);
    expect(screen.getByRole("status")).toHaveClass(classe);
  });

  it("repassa o que o pacote repassa por ...rest", () => {
    render(<Spinner data-testid="anel" id="carregando" />);
    const anel = screen.getByTestId("anel");
    expect(anel).toHaveAttribute("id", "carregando");
  });

  it("ainda aceita className, que o HelpHS usa e o pacote resolve por style", () => {
    render(<Spinner className="mx-auto" />);
    expect(screen.getByRole("status")).toHaveClass("mx-auto");
  });
});
