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

// ── Fase 16: o id que saía do rótulo, e colidia em silêncio ───────────

/**
 * O `Select` era o consumidor que ficou para trás na **E11**.
 *
 * O `id` do campo vinha de `label.toLowerCase()`. Dois seletores com o mesmo
 * rótulo na mesma tela geram o **mesmo id**, e um `id` repetido não é erro de
 * HTML: o `htmlFor` do segundo rótulo resolve para o campo do primeiro, e nada
 * acusa — nem `tsc`, nem `eslint`, nem os casos acima, que só montam um
 * seletor de cada vez. É exatamente o ponto cego que o caso da colisão fecha.
 */
describe("Select — o id não sai mais do rótulo", () => {
  const SITUACAO = [
    { value: "aberto", label: "Aberto" },
    { value: "fechado", label: "Fechado" },
  ];

  function doisIguais() {
    return render(
      <>
        <Select label="Situação" options={SITUACAO} />
        <Select label="Situação" options={SITUACAO} />
      </>,
    );
  }

  it("dois seletores com o MESMO rótulo não compartilham id", () => {
    const { container } = doisIguais();
    const [a, b] = [...container.querySelectorAll("select")];

    expect(a.id).toBeTruthy();
    expect(b.id).toBeTruthy();
    expect(a.id).not.toBe(b.id);
  });

  it("cada rótulo alcança o SEU campo, e não o de cima", async () => {
    // É o que a pessoa faz: clicar no rótulo para cair no campo. Com o id
    // derivado, clicar no segundo rótulo focava o primeiro seletor.
    const { container } = doisIguais();
    const [primeiro, segundo] = [...container.querySelectorAll("select")];
    const [rotuloDeCima, rotuloDeBaixo] = screen.getAllByText("Situação");

    await userEvent.click(rotuloDeBaixo);
    expect(segundo).toHaveFocus();
    expect(primeiro).not.toHaveFocus();

    await userEvent.click(rotuloDeCima);
    expect(primeiro).toHaveFocus();
    expect(segundo).not.toHaveFocus();
  });

  it("cada rótulo aponta para um campo que existe", () => {
    // A outra metade da colisão: os dois `htmlFor` resolviam para o mesmo
    // elemento. Aqui cada um tem de resolver para o seu.
    const { container } = doisIguais();
    const campos = [...container.querySelectorAll("select")];
    const alvos = [...container.querySelectorAll("label")].map((l) =>
      document.getElementById(l.getAttribute("for")!),
    );

    expect(alvos).toEqual(campos);
  });

  it("o id passado por quem chama continua ganhando", () => {
    // As telas que filtram por este primitivo depois da D9.2 mandam o seu.
    render(<Select label="Período" options={SITUACAO} id="filtro-periodo" />);

    expect(screen.getByLabelText("Período").id).toBe("filtro-periodo");
  });

  it("seletor sem rótulo ainda recebe id", () => {
    // Antes ficava `undefined` — o caso dos filtros que só têm placeholder.
    const { container } = render(
      <Select options={SITUACAO} placeholder="Status" />,
    );

    expect(container.querySelector("select")!.id).toBeTruthy();
  });
});
