import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RadioCards } from "../../components/ui/RadioCards";

/**
 * O que este primitivo tem de provar não é aparência, é **o que a árvore de
 * acessibilidade diz** — porque é exatamente onde a pilha de `<button>` que ele
 * substitui falhava: oito botões chamados "Hardware", "Software"…, sem
 * "escolhido", sem "1 de 8" e sem relação nenhuma com a palavra "Categoria".
 */
const OPCOES = [
  { value: "hardware", label: "Hardware" },
  { value: "software", label: "Software" },
  { value: "network", label: "Rede" },
];

function montar(props: Partial<Parameters<typeof RadioCards>[0]> = {}) {
  const onChange = vi.fn();
  render(
    <RadioCards
      name="categoria"
      label="Categoria"
      value=""
      onChange={onChange}
      options={OPCOES}
      {...props}
    />,
  );
  return { onChange };
}

describe("RadioCards", () => {
  it("cada opção é um rádio, e não um botão", () => {
    montar();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("o nome de cada opção é o rótulo dela", () => {
    montar();
    expect(screen.getByRole("radio", { name: "Hardware" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Rede" })).toBeInTheDocument();
  });

  it("o grupo tem nome, e ele vem do legend", () => {
    montar();
    expect(screen.getByRole("group", { name: /Categoria/ })).toBeInTheDocument();
  });

  it("a árvore diz QUAL está escolhido", () => {
    // O defeito que ele conserta: com `<button>`, a escolha existia só na cor.
    montar({ value: "software" });
    expect(screen.getByRole("radio", { name: "Software" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Hardware" })).not.toBeChecked();
  });

  it("escolher avisa quem chama, com o valor", async () => {
    const { onChange } = montar();
    await userEvent.click(screen.getByRole("radio", { name: "Rede" }));
    expect(onChange).toHaveBeenCalledWith("network");
  });

  it("o grupo inteiro é UMA parada de tabulação", async () => {
    // É o que se ganha usando rádio de verdade: com oito botões, eram oito
    // paradas, e atravessar a grade custava oito Tab.
    montar({ value: "hardware" });
    await userEvent.tab();
    expect(screen.getByRole("radio", { name: "Hardware" })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("radio", { name: "Hardware" })).not.toHaveFocus();
    expect(screen.getByRole("radio", { name: "Software" })).not.toHaveFocus();
  });

  it("a seta anda dentro do grupo e escolhe, sem código nosso", async () => {
    const { onChange } = montar({ value: "hardware" });
    await userEvent.tab();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("software");
  });

  it("o erro é anunciado junto com o grupo, não solto ao lado", async () => {
    montar({ error: "Selecione uma categoria" });
    const grupo = screen.getByRole("group", { name: /Categoria/ });
    const erro = screen.getByText("Selecione uma categoria");
    expect(grupo).toHaveAttribute("aria-describedby", erro.id);
    expect(erro.id).toBeTruthy();
  });

  it("o erro marca os rádios como inválidos", () => {
    montar({ error: "Selecione uma categoria" });
    for (const r of screen.getAllByRole("radio")) {
      expect(r).toHaveAttribute("aria-invalid", "true");
    }
  });

  it("dica e erro nunca descrevem o grupo ao mesmo tempo", () => {
    // Mesma regra da emenda E11 nos campos do pacote: um `aria-describedby`
    // com os dois faz o leitor ler a dica DEPOIS do erro, e a dica costuma
    // contradizer o erro.
    montar({ hint: "Escolha a que mais se aproxima", error: "Selecione uma categoria" });
    const grupo = screen.getByRole("group", { name: /Categoria/ });
    expect(screen.queryByText("Escolha a que mais se aproxima")).not.toBeInTheDocument();
    expect(grupo.getAttribute("aria-describedby")?.split(" ")).toHaveLength(1);
  });

  it("obrigatório chega a cada rádio, que é o nativo", () => {
    montar({ required: true });
    for (const r of screen.getAllByRole("radio")) {
      expect(r).toBeRequired();
    }
  });

  it("o asterisco é desenho, e não entra no nome do grupo", () => {
    // "Categoria *" lido como "Categoria asterisco" é ruído; a obrigatoriedade
    // já viaja no `required` de cada rádio.
    montar({ required: true });
    expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument();
  });

  it("o ícone não vira nome nem ruído", () => {
    montar({ options: [{ value: "hardware", label: "Hardware", icon: "server" }] });
    expect(screen.getByRole("radio", { name: "Hardware" })).toBeInTheDocument();
  });
});
