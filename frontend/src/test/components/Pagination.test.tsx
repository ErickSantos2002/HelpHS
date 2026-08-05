import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "../../components/ui/Pagination";

/**
 * O componente renderiza dois layouts ao mesmo tempo (desktop e mobile),
 * alternados por CSS. No jsdom os dois existem no DOM, então os testes miram
 * um layout de cada vez: o desktop pelos rótulos "Anterior"/"Próxima" e o
 * mobile pelos aria-labels dos chevrons.
 */
describe("Pagination", () => {
  it("mostra a contagem de resultados", () => {
    render(
      <Pagination page={1} pageSize={10} total={42} onPageChange={() => {}} />,
    );
    expect(
      screen.getByText("Mostrando 1 a 10 de 42 registros"),
    ).toBeInTheDocument();
    expect(screen.getByText("1–10 de 42 registros")).toBeInTheDocument();
  });

  it("usa o itemLabel informado", () => {
    render(
      <Pagination
        page={1}
        pageSize={10}
        total={42}
        itemLabel="usuários"
        onPageChange={() => {}}
      />,
    );
    expect(
      screen.getByText("Mostrando 1 a 10 de 42 usuários"),
    ).toBeInTheDocument();
  });

  it("mostra 'Nenhum resultado' quando total é 0", () => {
    render(
      <Pagination page={1} pageSize={10} total={0} onPageChange={() => {}} />,
    );
    expect(screen.getAllByText("Nenhum resultado")).toHaveLength(2);
  });

  it("desabilita o botão de voltar na primeira página", () => {
    render(
      <Pagination page={1} pageSize={10} total={30} onPageChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByLabelText("Página anterior")).toBeDisabled();
  });

  it("desabilita o botão de avançar na última página", () => {
    render(
      <Pagination page={3} pageSize={10} total={30} onPageChange={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Próxima" })).toBeDisabled();
    expect(screen.getByLabelText("Próxima página")).toBeDisabled();
  });

  it("chama onPageChange com a próxima página", async () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={2}
        pageSize={10}
        total={50}
        onPageChange={onPageChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Próxima" }));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it("chama onPageChange com a página anterior", async () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={3}
        pageSize={10}
        total={50}
        onPageChange={onPageChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Página anterior"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("chama onPageChange ao clicar no número da página", async () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={1}
        pageSize={10}
        total={30}
        onPageChange={onPageChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "2" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});
