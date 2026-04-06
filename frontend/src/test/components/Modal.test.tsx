import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Modal, ModalFooter } from "../../components/ui/Modal";

describe("Modal", () => {
  it("renders children when open", () => {
    render(
      <Modal open onClose={vi.fn()}>
        <p>Conteúdo do modal</p>
      </Modal>,
    );
    expect(screen.getByText("Conteúdo do modal")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <Modal open={false} onClose={vi.fn()}>
        <p>Conteúdo oculto</p>
      </Modal>,
    );
    expect(screen.queryByText("Conteúdo oculto")).not.toBeInTheDocument();
  });

  it("renders title when provided", () => {
    render(
      <Modal open onClose={vi.fn()} title="Novo chamado">
        <p>body</p>
      </Modal>,
    );
    expect(screen.getByText("Novo chamado")).toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Modal">
        <p>body</p>
      </Modal>,
    );
    await userEvent.click(screen.getByLabelText("Fechar"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when backdrop is clicked", async () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal open onClose={onClose} title="Modal">
        <p>body</p>
      </Modal>,
    );
    // Backdrop is the absolute div inside the fixed container
    const backdrop = container.querySelector(".absolute.inset-0");
    expect(backdrop).not.toBeNull();
    await userEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Modal">
        <p>body</p>
      </Modal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("ModalFooter", () => {
  it("renders children", () => {
    render(
      <ModalFooter>
        <button>Cancelar</button>
        <button>Salvar</button>
      </ModalFooter>,
    );
    expect(screen.getByText("Cancelar")).toBeInTheDocument();
    expect(screen.getByText("Salvar")).toBeInTheDocument();
  });
});
