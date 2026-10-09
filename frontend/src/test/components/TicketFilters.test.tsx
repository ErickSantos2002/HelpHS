import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  EMPTY_FILTERS,
  TicketFilters,
} from "../../components/ui/TicketFilters";
import { escolherNoMenu } from "../helpers/menu";

describe("TicketFilters", () => {
  it("renders search input and filter menus", () => {
    render(<TicketFilters value={EMPTY_FILTERS} onChange={vi.fn()} />);
    expect(
      screen.getByPlaceholderText("Buscar por título, protocolo ou nº de série…"),
    ).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
    expect(screen.getByText("Prioridade")).toBeInTheDocument();
    expect(screen.getByText("Categoria")).toBeInTheDocument();
  });

  it("does not show Limpar button when no filters active", () => {
    render(<TicketFilters value={EMPTY_FILTERS} onChange={vi.fn()} />);
    expect(screen.queryByText("Limpar")).not.toBeInTheDocument();
  });

  it("shows Limpar button when a filter is active", () => {
    render(
      <TicketFilters
        value={{ ...EMPTY_FILTERS, status: "open" }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText("Limpar")).toBeInTheDocument();
  });

  it("calls onChange with cleared filters on Limpar click", async () => {
    const onChange = vi.fn();
    render(
      <TicketFilters
        value={{ ...EMPTY_FILTERS, priority: "high" }}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByText("Limpar"));
    expect(onChange).toHaveBeenCalledWith(EMPTY_FILTERS);
  });

  it("calls onChange when status filter changes", () => {
    const onChange = vi.fn();
    render(<TicketFilters value={EMPTY_FILTERS} onChange={onChange} />);
    const selects = screen.getAllByRole("combobox");
    // status is the first field; the menu is picked by label, not by value
    escolherNoMenu(selects[0], "Aberto");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "open" }),
    );
  });

  it("calls onChange when priority filter changes", () => {
    const onChange = vi.fn();
    render(<TicketFilters value={EMPTY_FILTERS} onChange={onChange} />);
    const selects = screen.getAllByRole("combobox");
    // priority is the second field
    escolherNoMenu(selects[1], "Crítico");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ priority: "critical" }),
    );
  });

  it("clears the status filter through the placeholder row", () => {
    const onChange = vi.fn();
    render(
      <TicketFilters
        value={{ ...EMPTY_FILTERS, status: "open" }}
        onChange={onChange}
      />,
    );
    const selects = screen.getAllByRole("combobox");
    // The first row of the menu is the placeholder, of value "" — it is what
    // empties the filter, as the placeholder row of the old control did.
    escolherNoMenu(selects[0], "Status");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "" }),
    );
  });
});
