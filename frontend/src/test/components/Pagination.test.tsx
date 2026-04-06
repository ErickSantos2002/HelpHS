import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "../../components/ui/Pagination";

describe("Pagination", () => {
  it("shows result count", () => {
    render(
      <Pagination page={1} pageSize={10} total={42} onPageChange={() => {}} />,
    );
    expect(screen.getByText("1–10 de 42")).toBeInTheDocument();
  });

  it("shows 'Nenhum resultado' when total is 0", () => {
    render(
      <Pagination page={1} pageSize={10} total={0} onPageChange={() => {}} />,
    );
    expect(screen.getByText("Nenhum resultado")).toBeInTheDocument();
  });

  it("disables prev button on first page", () => {
    render(
      <Pagination page={1} pageSize={10} total={30} onPageChange={() => {}} />,
    );
    expect(screen.getByLabelText("Página anterior")).toBeDisabled();
  });

  it("disables next button on last page", () => {
    render(
      <Pagination page={3} pageSize={10} total={30} onPageChange={() => {}} />,
    );
    expect(screen.getByLabelText("Próxima página")).toBeDisabled();
  });

  it("calls onPageChange with next page when clicking next", async () => {
    const onPageChange = vi.fn();
    render(
      <Pagination
        page={2}
        pageSize={10}
        total={50}
        onPageChange={onPageChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Próxima página"));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it("calls onPageChange with prev page when clicking prev", async () => {
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

  it("calls onPageChange when clicking a page number", async () => {
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
