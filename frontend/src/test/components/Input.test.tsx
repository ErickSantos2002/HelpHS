import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Input } from "../../components/ui/Input";

describe("Input", () => {
  it("renders without label", () => {
    render(<Input placeholder="Digite aqui" />);
    expect(screen.getByPlaceholderText("Digite aqui")).toBeInTheDocument();
  });

  it("renders with label", () => {
    render(<Input label="Nome" />);
    expect(screen.getByLabelText("Nome")).toBeInTheDocument();
  });

  it("renders error message", () => {
    render(<Input label="E-mail" error="E-mail inválido" />);
    expect(screen.getByText("E-mail inválido")).toBeInTheDocument();
  });

  it("renders hint when no error", () => {
    render(<Input hint="Use letras e números" />);
    expect(screen.getByText("Use letras e números")).toBeInTheDocument();
  });

  it("does not render hint when error is present", () => {
    render(<Input hint="Dica" error="Erro" />);
    expect(screen.queryByText("Dica")).not.toBeInTheDocument();
    expect(screen.getByText("Erro")).toBeInTheDocument();
  });

  it("calls onChange when typing", async () => {
    const onChange = vi.fn();
    render(<Input onChange={onChange} />);
    await userEvent.type(screen.getByRole("textbox"), "abc");
    expect(onChange).toHaveBeenCalled();
  });

  it("is disabled when disabled prop is set", () => {
    render(<Input disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
});
