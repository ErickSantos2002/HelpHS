import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui/Table";

describe("Table", () => {
  it("renders table with header and rows", () => {
    render(
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Nome</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow>
            <TableCell>Ticket 1</TableCell>
            <TableCell>Aberto</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    expect(screen.getByText("Nome")).toBeInTheDocument();
    expect(screen.getByText("Ticket 1")).toBeInTheDocument();
  });

  it("renders TableEmpty with message", () => {
    render(
      <Table>
        <TableBody>
          <TableEmpty colSpan={3} message="Nenhum ticket." />
        </TableBody>
      </Table>,
    );
    expect(screen.getByText("Nenhum ticket.")).toBeInTheDocument();
  });

  it("calls onClick when row is clickable", async () => {
    const onClick = vi.fn();
    render(
      <Table>
        <TableBody>
          <TableRow clickable onClick={onClick}>
            <TableCell>Linha clicável</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    await userEvent.click(screen.getByText("Linha clicável"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("renders sort indicator on sortable header", () => {
    render(
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell sortable sorted="asc">
              Data
            </TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody />
      </Table>,
    );
    expect(screen.getByText("↑")).toBeInTheDocument();
  });

  it("calls onSort when sortable header is clicked", async () => {
    const onSort = vi.fn();
    render(
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell sortable onSort={onSort}>
              Data
            </TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody />
      </Table>,
    );
    await userEvent.click(screen.getByText("Data"));
    expect(onSort).toHaveBeenCalledTimes(1);
  });
});

describe("Table — Fase 9: o que era só de mouse", () => {
  function comOrdenacao(sorted: "asc" | "desc" | null, onSort = vi.fn()) {
    render(
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell sortable sorted={sorted} onSort={onSort}>
              Título
            </TableHeaderCell>
            <TableHeaderCell>Situação</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody />
      </Table>,
    );
    return onSort;
  }

  it("ordenar é um botão, e não um cabeçalho com onClick", async () => {
    // Era `<th onClick>`: fora da ordem de tabulação e sem resposta a tecla.
    // Quem não usa mouse não conseguia ordenar a tabela.
    const onSort = comOrdenacao(null);

    const botao = screen.getByRole("button", { name: /Título/ });
    await userEvent.click(botao);

    expect(onSort).toHaveBeenCalledTimes(1);
  });

  it("o cabeçalho anuncia a ordem, em vez de deixá-la só na seta", () => {
    // A seta é decoração: quem usa leitor de tela não a vê. `aria-sort` no
    // `<th>` é o que diz "ordenado do menor para o maior".
    comOrdenacao("asc");

    expect(screen.getByRole("columnheader", { name: /Título/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
  });

  it("coluna sem ordenação não finge que tem", () => {
    comOrdenacao("asc");

    expect(screen.getByRole("columnheader", { name: "Situação" })).not.toHaveAttribute(
      "aria-sort",
    );
  });

  it("a seta fica escondida do leitor de tela", () => {
    // Sem `aria-hidden`, o nome acessível do botão vira "Título ↑" — o caractere
    // é lido como texto, e cada leitor o pronuncia de um jeito.
    comOrdenacao("desc");

    expect(screen.getByRole("button", { name: "Título" })).toBeInTheDocument();
  });

  it("linha clicável entra na ordem de tabulação e responde ao Enter", async () => {
    // Era `<tr onClick>`: só mouse. O papel de linha é preservado de propósito —
    // `role="button"` num `<tr>` quebraria o "linha 3 de 40" do leitor de tela.
    const onClick = vi.fn();
    render(
      <Table>
        <TableBody>
          <TableRow clickable onClick={onClick}>
            <TableCell>Chamado 42</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );

    const linha = screen.getByRole("row");
    expect(linha).toHaveAttribute("tabindex", "0");

    linha.focus();
    await userEvent.keyboard("{Enter}");

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("linha não clicável fica fora da ordem de tabulação", async () => {
    render(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>Chamado 42</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );

    expect(screen.getByRole("row")).not.toHaveAttribute("tabindex");
  });

  it("não sobra cor cravada nem alias de fundo", () => {
    const { container } = render(
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell sortable sorted="asc" onSort={vi.fn()}>
              Título
            </TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow clickable onClick={vi.fn()}>
            <TableCell muted>vazio</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );

    expect(container.innerHTML).not.toMatch(/slate-\d/);
    expect(container.innerHTML).not.toMatch(/background-surface|background-elevated/);
  });
});
