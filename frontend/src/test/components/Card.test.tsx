import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card, CardHeader, CardTitle } from "../../components/ui/Card";
import { AA, contraste } from "../helpers/contraste";

describe("Card", () => {
  it("a superfície e a borda saem dos tokens do pacote, não dos alias do D2", () => {
    // `bg-background-surface` e `border-border` são os nomes antigos do HelpHS.
    // Apontam para os mesmos tokens, mas o D2 os marca para sair na Fase 20:
    // quem nasce agora nasce com o nome do pacote.
    const { container } = render(<Card>conteudo</Card>);
    const classe = container.firstElementChild?.className ?? "";
    expect(classe).toContain("bg-surface");
    expect(classe).toContain("border-borda");
    expect(classe).not.toContain("bg-background-surface");
  });

  it("o título não traz cor cravada fora do pacote", () => {
    // Era `text-slate-100`: a cor do tema ESCURO escrita no componente, que só
    // não aparece errada no claro porque o bloco de inversão do `index.css`
    // (D5) a reescreve. O pacote manda `--text-heading`, que inverte sozinho.
    render(<CardTitle>Título</CardTitle>);
    const classe = screen.getByText("Título").className;
    expect(classe).toContain("text-conteudo-heading");
    expect(classe).not.toMatch(/slate-/);
  });

  it("o cabeçalho separa com a borda do pacote", () => {
    const { container } = render(<CardHeader>cabecalho</CardHeader>);
    expect(container.firstElementChild?.className ?? "").toContain(
      "border-borda",
    );
  });

  it.each(["claro", "escuro"] as const)(
    "o título sobre a superfície aprova em AA no tema %s",
    (tema) => {
      expect(contraste("--surface", "--text-heading", tema)).toBeGreaterThanOrEqual(
        AA,
      );
    },
  );
});
