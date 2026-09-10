import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";
import { Textarea } from "../../components/ui/Textarea";
import { AA, contraste } from "../helpers/contraste";

/** Piso da WCAG 1.4.11 para indicador não textual: borda, anel de foco. */
const NAO_TEXTO = 3;

function classesDo(props = {}) {
  const { container } = render(<Textarea {...props} />);
  return container.querySelector("textarea")!.className;
}

describe("Textarea", () => {
  it("liga o rótulo ao campo", () => {
    render(<Textarea label="Descrição" />);
    expect(screen.getByLabelText("Descrição")).toBeInTheDocument();
  });

  it("o erro substitui o hint, e não empilha os dois", () => {
    render(<Textarea hint="mínimo 20 caracteres" error="muito curto" />);
    expect(screen.getByText("muito curto")).toBeInTheDocument();
    expect(screen.queryByText("mínimo 20 caracteres")).not.toBeInTheDocument();
  });

  it("repassa a ref, que é melhoria local sobre a referência", () => {
    const ref = createRef<HTMLTextAreaElement>();
    render(<Textarea ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLTextAreaElement);
  });

  // ── Fase 8: os tokens ─────────────────────────────────────────────────

  it("a borda de repouso é contorno de controle, não separador", () => {
    // `--border-control`, da E7. Antes era `border-border` (slate-200), que dá
    // 1,23:1 — a linha de cabelo entre card e fundo, usada para delimitar campo.
    expect(classesDo()).toContain("border-borda-control");
  });

  it("o hover da borda saiu, porque a E7 o tornou no-op", () => {
    // Era `hover:border-slate-500`: a borda ia de 1,23:1 a 4,76:1 só com o
    // mouse em cima. Hoje o repouso JÁ é slate-500, então o hover não teria
    // para onde ir. O `Textarea.jsx` do pacote também não tem hover.
    expect(classesDo()).not.toContain("hover:border");
  });

  it("o anel de foco sai do degrau de AÇÃO", () => {
    const c = classesDo();
    expect(c).toContain("focus:ring-action");
    expect(c).not.toContain("focus:ring-primary");
  });

  it("o erro NÃO troca para action-danger, e isso é deliberado", () => {
    expect(classesDo({ error: "x" })).toContain("border-danger");
  });

  it("o texto do erro usa o par da tinta", () => {
    render(<Textarea error="muito curto" />);
    expect(screen.getByText("muito curto").className).toContain(
      "text-on-tint-danger",
    );
  });

  it("não sobra cor cravada", () => {
    const { container } = render(
      <Textarea label="Descrição" hint="opcional" placeholder="Detalhe o problema" />,
    );
    expect(container.innerHTML).not.toMatch(/slate-\d/);
  });

  it("o placeholder não depende do bloco D5, e por isso precisava do token", () => {
    // Detalhe que muda o diagnóstico: o espelho do `index.css` é
    // `html:not(.dark) .text-slate-500`, e a classe aqui era
    // `placeholder:text-slate-500` — token de classe DIFERENTE, o seletor não
    // casa. Ao contrário do rótulo e do valor, o placeholder não era reescrito
    // no tema claro: era #64748b nos dois, e reprovava no escuro.
    expect(classesDo()).toContain("placeholder:text-conteudo-muted");
  });

  describe("contraste", () => {
    it.each(["claro", "escuro"] as const)(
      "borda de repouso e anel de foco, tema %s",
      (tema) => {
        expect(
          contraste("--surface", "--border-control", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
        expect(contraste("--surface", "--action", tema)).toBeGreaterThanOrEqual(
          NAO_TEXTO,
        );
      },
    );

    it.each(["claro", "escuro"] as const)(
      "rótulo, valor, placeholder, hint e erro são texto, tema %s",
      (tema) => {
        expect(contraste("--surface", "--text-body", tema)).toBeGreaterThanOrEqual(AA);
        expect(contraste("--surface", "--text-muted", tema)).toBeGreaterThanOrEqual(AA);
        expect(
          contraste("--surface", "--on-tint-danger", tema),
        ).toBeGreaterThanOrEqual(AA);
      },
    );
  });
});
