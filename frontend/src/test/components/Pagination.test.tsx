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

describe("Pagination — Fase 9: o que os tokens e o teclado mudaram", () => {
  it("é uma navegação com nome, e não uma div solta no fim da lista", () => {
    // Sem o landmark, quem usa leitor de tela não consegue pular para a
    // paginação: ela é só mais um punhado de botões depois da tabela.
    render(
      <Pagination page={2} pageSize={10} total={42} onPageChange={() => {}} />,
    );

    expect(screen.getByRole("navigation", { name: "Paginação" })).toBeInTheDocument();
  });

  it("a página atual é anunciada por aria-current, e continua alcançável", () => {
    // Antes ela era marcada com `disabled`, o que a tirava da ordem de
    // tabulação: quem navega por teclado não conseguia chegar nela para saber
    // onde estava. `aria-current="page"` diz a mesma coisa sem sumir com o
    // botão — o mesmo erro de "sinal certo, mecanismo errado" da E9.
    render(
      <Pagination page={2} pageSize={10} total={42} onPageChange={() => {}} />,
    );

    // Os dois layouts existem no jsdom, e com page=2 ambos mostram "2" como
    // atual. Os dois têm de dizer a mesma coisa.
    const atuais = screen.getAllByRole("button", { name: "2" });
    expect(atuais).toHaveLength(2);
    for (const b of atuais) {
      expect(b).toHaveAttribute("aria-current", "page");
      expect(b).not.toBeDisabled();
    }
  });

  it("clicar na página atual não dispara mudança", async () => {
    // A guarda substituiu o `disabled`: sem ela, o clique pediria de novo a
    // página em que já se está.
    const onPageChange = vi.fn();
    render(
      <Pagination page={2} pageSize={10} total={42} onPageChange={onPageChange} />,
    );

    await userEvent.click(screen.getAllByRole("button", { name: "2" })[0]);

    expect(onPageChange).not.toHaveBeenCalled();
  });

  it("a página atual usa o par medido, e não branco sobre o degrau de marca", () => {
    // Era `bg-primary text-white` — 3,83:1, medido pela varredura, e página é
    // texto. É a família da E1: branco cravado sobre um fundo que muda de tema.
    render(
      <Pagination page={2} pageSize={10} total={42} onPageChange={() => {}} />,
    );

    const c = screen.getAllByRole("button", { name: "2" })[0].className;
    expect(c).toContain("bg-action");
    expect(c).toContain("text-on-primary");
    expect(c).not.toContain("text-white");
  });

  it("não sobra cor cravada nem alias de fundo", () => {
    const { container } = render(
      <Pagination page={2} pageSize={10} total={42} onPageChange={() => {}} />,
    );

    expect(container.innerHTML).not.toMatch(/slate-\d/);
    expect(container.innerHTML).not.toMatch(/background-surface|background-elevated/);
  });
});
