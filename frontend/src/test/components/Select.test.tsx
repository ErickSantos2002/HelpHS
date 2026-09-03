import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Select } from "../../components/ui/Select";
import { AA, contraste } from "../helpers/contraste";

const OPTIONS = [
  { value: "admin", label: "Administrador" },
  { value: "technician", label: "Técnico" },
  { value: "client", label: "Cliente" },
];

describe("Select", () => {
  it("renders all options", () => {
    render(<Select options={OPTIONS} />);
    expect(screen.getByText("Administrador")).toBeInTheDocument();
    expect(screen.getByText("Técnico")).toBeInTheDocument();
    expect(screen.getByText("Cliente")).toBeInTheDocument();
  });

  it("renders placeholder option", () => {
    render(<Select options={OPTIONS} placeholder="Selecione um perfil" />);
    expect(screen.getByText("Selecione um perfil")).toBeInTheDocument();
  });

  it("renders label", () => {
    render(<Select options={OPTIONS} label="Perfil" />);
    expect(screen.getByLabelText("Perfil")).toBeInTheDocument();
  });

  it("renders error message", () => {
    render(<Select options={OPTIONS} error="Campo obrigatório" />);
    expect(screen.getByText("Campo obrigatório")).toBeInTheDocument();
  });

  it("calls onChange on selection", async () => {
    const onChange = vi.fn();
    render(<Select options={OPTIONS} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "Técnico");
    expect(onChange).toHaveBeenCalled();
  });

  it("is disabled when disabled prop is set", () => {
    render(<Select options={OPTIONS} disabled />);
    expect(screen.getByRole("combobox")).toBeDisabled();
  });
});

// ── Fase 8: tokens, e a seta que não seguia o tema ────────────────────

/** Piso da WCAG 1.4.11 para gráfico e indicador não textual. */
const NAO_TEXTO = 3;

describe("Select — tokens", () => {
  const OPCOES = [{ value: "a", label: "Aberto" }];

  it("a seta é um ícone que herda a cor, e não um data URI cravado", () => {
    // Era `background-image` com um SVG em data URI e `stroke='%2394a3b8'` —
    // slate-400 fixo. **Data URI não aceita `var()`**, então a seta nunca
    // seguiu o tema: sobre o campo branco dava 2,56:1, abaixo do piso de 3:1.
    // O `Select.jsx` do pacote tem o mesmo data URI, com o mesmo hexadecimal.
    const { container } = render(<Select options={OPCOES} />);
    expect(container.innerHTML).not.toMatch(/data:image/);
    const seta = container.querySelector("svg");
    expect(seta).not.toBeNull();
    expect(seta!.getAttribute("stroke")).toBe("currentColor");
    expect(seta!.getAttribute("class")).toContain("text-conteudo-muted");
  });

  it("a seta não intercepta o clique do campo", () => {
    // Ela fica por cima do `<select>`; sem `pointer-events-none`, clicar na
    // seta não abriria a lista.
    const { container } = render(<Select options={OPCOES} />);
    expect(container.querySelector("svg")!.getAttribute("class")).toContain(
      "pointer-events-none",
    );
  });

  it("o campo reserva espaço para a seta", () => {
    // Sem o `pr-9`, um rótulo longo passa por baixo dela.
    const { container } = render(<Select options={OPCOES} />);
    expect(container.querySelector("select")!.className).toContain("pr-9");
  });

  it("a borda de repouso é contorno de controle", () => {
    const { container } = render(<Select options={OPCOES} />);
    expect(container.querySelector("select")!.className).toContain(
      "border-borda-control",
    );
  });

  it("o anel de foco sai do degrau de AÇÃO", () => {
    const { container } = render(<Select options={OPCOES} />);
    const c = container.querySelector("select")!.className;
    expect(c).toContain("focus:ring-action");
    expect(c).not.toContain("focus:ring-primary");
  });

  it("as opções não têm cor cravada", () => {
    // `<option>` é pintado pelo sistema em vários navegadores, mas onde o
    // estilo pega ele precisa ser o token — e o placeholder precisa se
    // distinguir das opções reais.
    const { container } = render(
      <Select options={OPCOES} placeholder="Selecione" />,
    );
    const opcoes = [...container.querySelectorAll("option")];
    expect(opcoes[0].className).toContain("text-conteudo-muted");
    expect(opcoes[1].className).toContain("text-conteudo");
    expect(container.innerHTML).not.toMatch(/slate-\d/);
  });

  describe("contraste", () => {
    it.each(["claro", "escuro"] as const)(
      "a seta se distingue do campo, tema %s",
      (tema) => {
        expect(
          contraste("--surface", "--text-muted", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
      },
    );

    it("o slate-400 cravado reprovaria no claro — é o que o pacote ainda tem", () => {
      expect(contraste("--surface", "--text-faint", "claro")).toBeLessThan(
        NAO_TEXTO,
      );
    });

    it.each(["claro", "escuro"] as const)(
      "borda, foco, texto e placeholder, tema %s",
      (tema) => {
        expect(
          contraste("--surface", "--border-control", tema),
        ).toBeGreaterThanOrEqual(NAO_TEXTO);
        expect(contraste("--surface", "--action", tema)).toBeGreaterThanOrEqual(NAO_TEXTO);
        expect(contraste("--surface", "--text-body", tema)).toBeGreaterThanOrEqual(AA);
        expect(contraste("--surface", "--text-muted", tema)).toBeGreaterThanOrEqual(AA);
      },
    );
  });
});
