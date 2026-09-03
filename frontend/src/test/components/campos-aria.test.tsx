import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Input } from "../../components/ui/Input";
import { Selector } from "../../components/ui/Selector";
import { Textarea } from "../../components/ui/Textarea";

/**
 * O erro do formulário chegando a quem não o vê.
 *
 * Os três campos renderizavam o erro e a dica como `<p>` soltos ao lado do
 * controle. Visualmente ficam juntos; na árvore de acessibilidade **não havia
 * relação nenhuma**. A pessoa ouvia o nome do campo, digitava, o formulário
 * recusava — e ela nunca ouvia por quê.
 *
 * O projeto inteiro tinha **zero ocorrências** de `aria-invalid`,
 * `aria-describedby` e `aria-required` quando este arquivo nasceu. O achado veio
 * da sessão do ChamadosHS, que encontrou o mesmo em treze formulários e resolveu
 * com um componente `Campo`; aqui os primitivos já são donos do rótulo, do erro
 * e da dica, então a ligação mora dentro deles e nenhuma tela muda.
 *
 * ── Por que `aria-required` não aparece aqui ──────────────────────────
 *
 * O `Input` e o `Textarea` recebem `required` nativo pelo espalhamento das
 * props, e o atributo nativo já informa a árvore de acessibilidade. Repetir com
 * `aria-required` declararia duas vezes a mesma coisa — e as duas podem
 * divergir. O `Selector` não tem controle nativo, e por isso é o único que
 * precisaria; hoje ele não tem prop de obrigatoriedade, então não finge ter.
 */

const CAMPOS = [
  ["Input", (p: Record<string, unknown>) => <Input label="Título" {...p} />],
  ["Textarea", (p: Record<string, unknown>) => <Textarea label="Título" {...p} />],
] as const;

describe("campos — o erro é ligado ao controle", () => {
  it.each(CAMPOS)("%s: o erro é apontado por aria-describedby", (_nome, montar) => {
    render(montar({ error: "Informe o título" }));

    const campo = screen.getByLabelText("Título");
    const alvo = campo.getAttribute("aria-describedby");

    expect(alvo).toBeTruthy();
    expect(document.getElementById(alvo!)).toHaveTextContent("Informe o título");
  });

  it.each(CAMPOS)("%s: o campo recusado é marcado como inválido", (_nome, montar) => {
    render(montar({ error: "Informe o título" }));

    expect(screen.getByLabelText("Título")).toHaveAttribute("aria-invalid", "true");
  });

  it.each(CAMPOS)("%s: campo sem erro não se declara inválido", (_nome, montar) => {
    render(montar({}));

    expect(screen.getByLabelText("Título")).not.toHaveAttribute("aria-invalid");
  });

  it.each(CAMPOS)("%s: a dica também é apontada, quando não há erro", (_nome, montar) => {
    render(montar({ hint: "Máximo de 80 caracteres" }));

    const alvo = screen.getByLabelText("Título").getAttribute("aria-describedby");
    expect(document.getElementById(alvo!)).toHaveTextContent("Máximo de 80 caracteres");
  });

  it.each(CAMPOS)("%s: com erro, quem é apontado é o erro e não a dica", (_nome, montar) => {
    // A dica nem é renderizada quando há erro — o apontamento tem de seguir o
    // que está na tela, ou aponta para um id que não existe.
    render(montar({ error: "Informe o título", hint: "Máximo de 80 caracteres" }));

    const alvo = screen.getByLabelText("Título").getAttribute("aria-describedby");
    expect(document.getElementById(alvo!)).toHaveTextContent("Informe o título");
  });

  it.each(CAMPOS)("%s: o required nativo passa, sem aria-required duplicado", (_nome, montar) => {
    render(montar({ required: true }));

    const campo = screen.getByLabelText("Título");
    expect(campo).toBeRequired();
    expect(campo).not.toHaveAttribute("aria-required");
  });
});

describe("campos — o id deixa de sair do rótulo", () => {
  it("dois campos com o mesmo rótulo não compartilham id", () => {
    // O id vinha de `label.toLowerCase()`. Dois "Telefone" na mesma tela — e há
    // seis no projeto — geravam o MESMO id, o que faz o segundo `htmlFor`
    // apontar para o primeiro campo: clicar no rótulo de baixo foca o de cima.
    render(
      <>
        <Input label="Telefone" />
        <Input label="Telefone" />
      </>,
    );

    const [a, b] = screen.getAllByLabelText("Telefone");
    expect(a.id).toBeTruthy();
    expect(a.id).not.toBe(b.id);
  });

  it("campo sem rótulo ainda recebe id", () => {
    // Antes o id ficava `undefined`, e com ele o `htmlFor`.
    const { container } = render(<Input placeholder="Buscar" />);

    expect(container.querySelector("input")!.id).toBeTruthy();
  });

  it("o id passado por quem chama continua ganhando", () => {
    render(<Input label="Título" id="titulo-do-chamado" />);

    expect(screen.getByLabelText("Título").id).toBe("titulo-do-chamado");
  });
});

describe("Selector — o erro do seletor", () => {
  function montarSelector(error?: string) {
    render(
      <Selector
        value={null}
        onChange={vi.fn()}
        options={[{ value: "a", label: "Aberto" }]}
        label="Situação"
        error={error}
      />,
    );
    return screen.getAllByRole("button")[0];
  }

  it("o erro é apontado pelo gatilho", () => {
    const gatilho = montarSelector("Escolha uma situação");
    const alvo = gatilho.getAttribute("aria-describedby");

    expect(document.getElementById(alvo!)).toHaveTextContent("Escolha uma situação");
  });

  it("o gatilho recusado é marcado como inválido", () => {
    expect(montarSelector("Escolha uma situação")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("sem erro, não aponta para nada", () => {
    expect(montarSelector()).not.toHaveAttribute("aria-describedby");
  });
});
