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
