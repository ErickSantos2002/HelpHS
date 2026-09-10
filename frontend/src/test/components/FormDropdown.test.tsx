import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FormDropdown } from "../../components/ui/FormDropdown";

/**
 * Dropdown dos formulários — o irmão de dentro do modal do FilterSelect.
 *
 * A diferença que importa: aqui o painel fica no fluxo do próprio campo (sem
 * portal), porque dentro de um modal o portal escaparia da pilha de foco. Em
 * troca, ele carrega o que um campo de formulário precisa e o filtro não tem:
 * rótulo, mensagem de erro e estado desabilitado.
 *
 * Assim como no filtro, a linha do placeholder devolve `""` — nos formulários
 * isso é "não escolher", o valor que o zod recebe para reclamar de obrigatório.
 *
 * ── Uma mudanca de papel, na unificacao ───────────────────────────────
 *
 * As linhas de opcao eram `<button>` sem papel declarado, e hoje sao
 * `role="option"` dentro de um `role="listbox"` — o papel explicito SUBSTITUI o
 * implicito, entao `getByRole("button")` nao as acha mais. A troca e
 * deliberada: um listbox cujas opcoes se anunciam como "botao" nao entrega o
 * contrato que o widget promete. Nada mudou para o mouse; as assercoes abaixo
 * sao as mesmas, so a consulta acompanhou o papel.
 */

const PRIORIDADES = [
  { value: "low", label: "Baixa", dot: "#22c55e" },
  { value: "high", label: "Alta", dot: "#ef4444" },
];

function renderCampo(props: Partial<React.ComponentProps<typeof FormDropdown>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <FormDropdown value="" onChange={onChange} options={PRIORIDADES} {...props} />,
  );
  return { ...utils, onChange };
}

/** O gatilho é o primeiro botão; as opções só existem depois de abrir. */
function gatilho() {
  return screen.getAllByRole("button")[0];
}

describe("FormDropdown — o que aparece no campo", () => {
  it("sem valor, mostra o placeholder padrão", () => {
    renderCampo();

    expect(gatilho()).toHaveTextContent("Selecione…");
  });

  it("com valor, mostra o rótulo da opção escolhida", () => {
    renderCampo({ value: "high" });

    expect(gatilho()).toHaveTextContent("Alta");
  });

  it("valor fora da lista cai no placeholder", () => {
    renderCampo({ value: "urgent" });

    expect(gatilho()).toHaveTextContent("Selecione…");
  });

  it("mostra o rótulo do campo", () => {
    renderCampo({ label: "Prioridade" });

    expect(screen.getByText("Prioridade")).toBeInTheDocument();
  });

  it("mostra a mensagem de erro da validação", () => {
    renderCampo({ error: "Escolha uma prioridade" });

    expect(screen.getByText("Escolha uma prioridade")).toBeInTheDocument();
  });
});

describe("FormDropdown — abrir e escolher", () => {
  it("as opções só aparecem depois do clique", async () => {
    renderCampo();

    expect(screen.queryByRole("button", { name: "Baixa" })).not.toBeInTheDocument();

    await userEvent.click(gatilho());

    expect(screen.getByRole("option", { name: "Baixa" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Alta" })).toBeInTheDocument();
  });

  it("escolher uma opção devolve o valor e fecha", async () => {
    const { onChange } = renderCampo();

    await userEvent.click(gatilho());
    await userEvent.click(screen.getByRole("option", { name: "Alta" }));

    expect(onChange).toHaveBeenCalledWith("high");
    expect(screen.queryByRole("button", { name: "Baixa" })).not.toBeInTheDocument();
  });

  it("a linha do placeholder devolve vazio — é o 'não escolher'", async () => {
    const { onChange } = renderCampo({ value: "high" });

    await userEvent.click(gatilho());
    await userEvent.click(screen.getByRole("option", { name: "Selecione…" }));

    expect(onChange).toHaveBeenCalledWith("");
  });

  it("clicar no gatilho de novo fecha sem avisar mudança", async () => {
    const { onChange } = renderCampo();

    await userEvent.click(gatilho());
    await userEvent.click(gatilho());

    expect(screen.queryByRole("button", { name: "Baixa" })).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("fecha ao clicar fora", async () => {
    render(
      <div>
        <FormDropdown value="" onChange={vi.fn()} options={PRIORIDADES} />
        <button type="button">Salvar</button>
      </div>,
    );

    await userEvent.click(gatilho());
    expect(screen.getByRole("option", { name: "Baixa" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(screen.queryByRole("button", { name: "Baixa" })).not.toBeInTheDocument();
  });
});

describe("FormDropdown — desabilitado", () => {
  it("não abre e não deixa escolher", async () => {
    // O modal de equipamento desabilita a prioridade enquanto carrega a lista;
    // abrir um painel vazio ali seria pior do que não abrir.
    //
    // Quem garante isso é o atributo `disabled` do <button>: o navegador não
    // dispara clique em controle desabilitado. Havia um `!disabled &&` no
    // onClick que nunca chegava a rodar — linha morta que este teste continua
    // cobrindo depois da remoção.
    const { onChange } = renderCampo({ disabled: true });

    await userEvent.click(gatilho());

    expect(screen.queryByRole("button", { name: "Baixa" })).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("marca o gatilho como desabilitado para o leitor de tela", () => {
    renderCampo({ disabled: true });

    expect(gatilho()).toBeDisabled();
  });
});
