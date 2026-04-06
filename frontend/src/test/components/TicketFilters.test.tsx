import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  EMPTY_FILTERS,
  TicketFilters,
} from "../../components/ui/TicketFilters";

describe("TicketFilters", () => {
  it("renders search input and filter selects", () => {
    render(<TicketFilters value={EMPTY_FILTERS} onChange={vi.fn()} />);
    expect(
      screen.getByPlaceholderText("Buscar por título ou protocolo…"),
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

  it("calls onChange when status filter changes", async () => {
    const onChange = vi.fn();
    render(<TicketFilters value={EMPTY_FILTERS} onChange={onChange} />);
    const selects = screen.getAllByRole("combobox");
    // status is the first select
    await userEvent.selectOptions(selects[0], "Aberto");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "open" }),
    );
  });

  it("calls onChange when priority filter changes", async () => {
    const onChange = vi.fn();
    render(<TicketFilters value={EMPTY_FILTERS} onChange={onChange} />);
    const selects = screen.getAllByRole("combobox");
    // priority is the second select
    await userEvent.selectOptions(selects[1], "Crítico");
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ priority: "critical" }),
    );
  });
});
