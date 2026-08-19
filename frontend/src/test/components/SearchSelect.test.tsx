import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SearchSelect } from "../../components/ui/SearchSelect";

/**
 * Picker de busca server-side.
 *
 * Existe porque a lista de origem não cabe num dropdown: `GET /users` tem
 * `limit` máximo de 100 e ordena por data de criação, então pré-carregar tudo
 * quebraria em silêncio ao passar de 100 clientes — e mostraria os 100 mais
 * recentes, ordem que não ajuda ninguém a achar um nome.
 *
 * O componente não conhece a API: recebe `onSearch`, o que mantém `ui/`
 * apresentacional e o teste livre de mock de serviço.
 */

const CLIENTES = [
  { value: "u1", label: "Ana Souza", hint: "ana@empresa.com" },
  { value: "u2", label: "Bruno Lima", hint: "bruno@empresa.com" },
];

function renderPicker(props: Partial<React.ComponentProps<typeof SearchSelect>> = {}) {
  const onChange = vi.fn();
  const onSearch = vi.fn().mockResolvedValue(CLIENTES);
  const utils = render(
    <SearchSelect
      value={null}
      onChange={onChange}
      onSearch={onSearch}
      label="Dono"
      placeholder="Buscar cliente…"
      emptyLabel="— Sem dono —"
      debounceMs={0}
      {...props}
    />,
  );
  return { ...utils, onChange, onSearch };
}

describe("SearchSelect — exibição", () => {
  it("sem valor, mostra o rótulo de vazio", () => {
    renderPicker();

    expect(screen.getByRole("button", { name: /Sem dono/ })).toBeInTheDocument();
  });

  it("com valor, mostra o rótulo recebido — sem precisar buscar", async () => {
    // Ao editar, o nome do dono já vem no equipamento; buscar só para exibir
    // seria uma ida à API por abertura de modal.
    const { onSearch } = renderPicker({ value: "u1", selectedLabel: "Ana Souza" });

    expect(screen.getByRole("button", { name: /Ana Souza/ })).toBeInTheDocument();
    expect(onSearch).not.toHaveBeenCalled();
  });
});

describe("SearchSelect — busca", () => {
  it("busca ao digitar e lista os resultados", async () => {
    const { onSearch } = renderPicker();

    await userEvent.click(screen.getByRole("button", { name: /Sem dono/ }));
    await userEvent.type(screen.getByPlaceholderText("Buscar cliente…"), "ana");

    await waitFor(() => expect(onSearch).toHaveBeenCalledWith("ana"));
    expect(await screen.findByText("Ana Souza")).toBeInTheDocument();
    expect(screen.getByText("bruno@empresa.com")).toBeInTheDocument();
  });

  it("escolher um resultado devolve id e rótulo", async () => {
    const { onChange } = renderPicker();

    await userEvent.click(screen.getByRole("button", { name: /Sem dono/ }));
    await userEvent.type(screen.getByPlaceholderText("Buscar cliente…"), "ana");
    await userEvent.click(await screen.findByText("Ana Souza"));

    expect(onChange).toHaveBeenCalledWith("u1", "Ana Souza");
  });

  it("limpar devolve null — é como se desvincula um equipamento", async () => {
    const { onChange } = renderPicker({ value: "u1", selectedLabel: "Ana Souza" });

    await userEvent.click(screen.getByRole("button", { name: /Ana Souza/ }));
    await userEvent.click(screen.getByRole("option", { name: /Sem dono/ }));

    expect(onChange).toHaveBeenCalledWith(null, null);
  });

  it("busca sem resultado avisa, em vez de mostrar lista vazia", async () => {
    const { onSearch } = renderPicker();
    onSearch.mockResolvedValue([]);

    await userEvent.click(screen.getByRole("button", { name: /Sem dono/ }));
    await userEvent.type(screen.getByPlaceholderText("Buscar cliente…"), "zzz");

    expect(await screen.findByText("Nenhum cliente encontrado.")).toBeInTheDocument();
  });

  it("falha na busca não quebra o formulário", async () => {
    const { onSearch } = renderPicker();
    onSearch.mockRejectedValue(new Error("500"));

    await userEvent.click(screen.getByRole("button", { name: /Sem dono/ }));
    await userEvent.type(screen.getByPlaceholderText("Buscar cliente…"), "ana");

    expect(await screen.findByText("Não foi possível buscar agora.")).toBeInTheDocument();
  });
});

describe("SearchSelect — resposta atrasada", () => {
  it("resultado de uma busca antiga não sobrescreve o da mais recente", async () => {
    // Digitar rápido dispara buscas em sequência; se a primeira voltar depois
    // da segunda, a lista mostraria o resultado do termo errado.
    let resolveAntiga!: (v: typeof CLIENTES) => void;
    const antiga = new Promise<typeof CLIENTES>((r) => {
      resolveAntiga = r;
    });
    const onSearch = vi
      .fn()
      .mockReturnValueOnce(antiga)
      .mockResolvedValueOnce([{ value: "u9", label: "Resultado novo" }]);

    renderPicker({ onSearch });

    await userEvent.click(screen.getByRole("button", { name: /Sem dono/ }));
    const campo = screen.getByPlaceholderText("Buscar cliente…");
    await userEvent.type(campo, "a");
    await waitFor(() => expect(onSearch).toHaveBeenCalledTimes(1));
    await userEvent.type(campo, "b");
    await waitFor(() => expect(onSearch).toHaveBeenCalledTimes(2));

    expect(await screen.findByText("Resultado novo")).toBeInTheDocument();

    resolveAntiga(CLIENTES);

    await waitFor(() => expect(screen.getByText("Resultado novo")).toBeInTheDocument());
    expect(screen.queryByText("Ana Souza")).not.toBeInTheDocument();
  });
});
