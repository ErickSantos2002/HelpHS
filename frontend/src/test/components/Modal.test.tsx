import { useState } from "react";
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
    render(
      <Modal open onClose={onClose} title="Modal">
        <p>body</p>
      </Modal>,
    );
    // O Modal renderiza via createPortal, então o backdrop fica no body — não no
    // container devolvido pelo render.
    const backdrop = document.body.querySelector(".absolute.inset-0");
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

describe("Modal — Fase 10: o foco volta, e os tokens entram", () => {
  it("devolve o foco a quem abriu", async () => {
    // Sem isso o foco fica no `body` ao fechar: quem navega por teclado volta
    // ao topo da página e percorre tudo de novo até onde estava. É o par do
    // que a armadilha de foco já fazia na entrada — prender sem devolver é
    // meio caminho.
    function Tela() {
      const [aberto, setAberto] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setAberto(true)}>
            Abrir
          </button>
          <Modal open={aberto} onClose={() => setAberto(false)} title="Confirmar">
            <p>corpo</p>
          </Modal>
        </>
      );
    }
    render(<Tela />);

    const abrir = screen.getByRole("button", { name: "Abrir" });
    abrir.focus();
    await userEvent.click(abrir);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));

    expect(abrir).toHaveFocus();
  });

  it("devolve o foco também quando fecha pelo Escape", async () => {
    // A devolução mora na limpeza do efeito, e não num `onClose`, justamente
    // porque o modal fecha por três caminhos: botão, Escape e clique no fundo.
    function Tela() {
      const [aberto, setAberto] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setAberto(true)}>
            Abrir
          </button>
          <Modal open={aberto} onClose={() => setAberto(false)} title="Confirmar">
            <p>corpo</p>
          </Modal>
        </>
      );
    }
    render(<Tela />);

    const abrir = screen.getByRole("button", { name: "Abrir" });
    abrir.focus();
    await userEvent.click(abrir);
    await userEvent.keyboard("{Escape}");

    expect(abrir).toHaveFocus();
  });

  it("o botão de fechar declara type=button", () => {
    // A primeira versão deste teste afirmava que o botão "não submete o
    // formulário que o contém" — e passava com o atributo REMOVIDO. A mutação
    // mostrou por quê: o modal vai para um portal em `document.body`, então o
    // botão nunca é descendente do `<form>` no DOM e não teria como submeter.
    //
    // Quem garante isso hoje é o portal, não o atributo. O atributo fica para o
    // dia em que o portal sair, e o teste prende o atributo — que é a única
    // coisa que ele de fato pode prender.
    render(
      <Modal open onClose={vi.fn()} title="Editar">
        <p>corpo</p>
      </Modal>,
    );

    expect(screen.getByRole("button", { name: "Fechar" })).toHaveAttribute(
      "type",
      "button",
    );
  });

  it("o botão de fechar tem anel de foco no degrau de ação", () => {
    render(
      <Modal open onClose={vi.fn()} title="Editar">
        <p>corpo</p>
      </Modal>,
    );

    expect(screen.getByRole("button", { name: "Fechar" }).className).toContain(
      "focus-visible:ring-action",
    );
  });

  it("não sobra cor cravada nem alias de fundo", () => {
    render(
      <Modal open onClose={vi.fn()} title="Editar">
        <p>corpo</p>
      </Modal>,
    );

    const html = screen.getByRole("dialog").outerHTML;
    expect(html).not.toMatch(/slate-\d/);
    expect(html).not.toMatch(/background-surface|background-elevated/);
  });
});
