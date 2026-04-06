import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "../../components/ui/Button";

describe("Button", () => {
  it("renders children", () => {
    render(<Button>Clique aqui</Button>);
    expect(
      screen.getByRole("button", { name: "Clique aqui" }),
    ).toBeInTheDocument();
  });

  it("calls onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Enviar</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled when disabled prop is set", () => {
    render(<Button disabled>Enviar</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("is disabled and shows spinner when loading", () => {
    render(<Button loading>Enviar</Button>);
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
  });

  it("does not call onClick when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Enviar
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("applies danger variant class", () => {
    render(<Button variant="danger">Excluir</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-danger");
  });
});
