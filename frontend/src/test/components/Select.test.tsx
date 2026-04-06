import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Select } from "../../components/ui/Select";

const OPTIONS = [
  { value: "admin", label: "Administrador" },
  { value: "technician", label: "Técnico" },
  { value: "client", label: "Cliente" },
];

describe("Select", () => {
  it("renders all options", () => {
    render(<Select options={OPTIONS} />);
    expect(screen.getByText("Administrador")).toBeInTheDocument();
    expect(screen.getByText("Técnico")).toBeInTheDocument();
    expect(screen.getByText("Cliente")).toBeInTheDocument();
  });

  it("renders placeholder option", () => {
    render(<Select options={OPTIONS} placeholder="Selecione um perfil" />);
    expect(screen.getByText("Selecione um perfil")).toBeInTheDocument();
  });

  it("renders label", () => {
    render(<Select options={OPTIONS} label="Perfil" />);
    expect(screen.getByLabelText("Perfil")).toBeInTheDocument();
  });

  it("renders error message", () => {
    render(<Select options={OPTIONS} error="Campo obrigatório" />);
    expect(screen.getByText("Campo obrigatório")).toBeInTheDocument();
  });

  it("calls onChange on selection", async () => {
    const onChange = vi.fn();
    render(<Select options={OPTIONS} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "Técnico");
    expect(onChange).toHaveBeenCalled();
  });

  it("is disabled when disabled prop is set", () => {
    render(<Select options={OPTIONS} disabled />);
    expect(screen.getByRole("combobox")).toBeDisabled();
  });
});
