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

  it("NÃO fecha quando se clica no fundo, fora do painel", async () => {
    // Pedido do usuário em 15/09/2026: clicar fora de uma modal não a fecha
    // mais; só o X (e os botões dela, e o Escape). Um clique fora por engano
    // descartava o que já estava digitado no formulário.
    //
    // Este caso AFIRMAVA o contrário até aqui ("calls onClose when backdrop is
    // clicked"), e foi invertido, não apagado: sem ele, alguém devolveria o
    // `onClick` ao fundo e nada cairia.
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
    expect(onClose).not.toHaveBeenCalled();
  });

  it("clicar no próprio contêiner do diálogo, fora do painel, também não fecha", async () => {
    // O fundo não é o único alvo possível de um clique "fora": o contêiner
    // `role="dialog"` ocupa a tela inteira (fixed inset-0, com padding). Se o
    // fechamento migrasse para ele um dia, o caso de cima continuaria verde.
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Modal">
        <p>body</p>
      </Modal>,
    );
    await userEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("sem título, o X existe assim mesmo — e fecha", async () => {
    // O X só era desenhado com `title`. Enquanto o fundo fechava, uma modal
    // sem título tinha saída por clique; sem o fundo, ficaria PRESA para quem
    // só tem clique (o Escape seguiria valendo — e celular não tem Escape).
    //
    // Não é hipótese: o detalhe da empresa (GroupsPage) usa `title={company.name}`,
    // e o nome vazio é alcançável — o POST /groups/{group_id}/companies grava
    // "   " aparado para
    // "". Carregando ou com erro de carga, aquela modal não tem botão nenhum.
    // Se só o X fecha por clique, toda modal precisa ter um X.
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose}>
        <p>body</p>
      </Modal>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("título vazio também não apaga o X", async () => {
    // O caso real é string VAZIA, não ausência de prop: `title={company.name}`
    // com `name === ""`. `{title && ...}` trata os dois do mesmo jeito, e o
    // conserto tem de tratar os dois também.
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="">
        <p>body</p>
      </Modal>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("título longo não pode empurrar o X para fora — o título encolhe, o X não", () => {
    // Com o fundo sem fechar, o X é a única saída por clique, e celular não
    // tem Escape. Item flex não encolhe abaixo da maior palavra: um nome de
    // empresa sem espaço levava o X para além da borda.
    //
    // ⚠️ Este caso afirma CLASSE, e jsdom não calcula layout: ele não prova
    // que o X fica dentro, só impede que alguém tire as classes que fazem
    // isso. A prova de layout foi medida em Chromium, a 390px, com controle
    // negativo: classes antigas + 47 letras → X em x=484–512 (fora da tela) e
    // o clique não o acerta; classes novas → X em 333–361, dentro e clicável,
    // com 47 e com 255 letras. Números no commit. Aquela medição usou fonte de
    // fallback: o veredito vale para qualquer fonte, os pixels não.
    render(
      <Modal open onClose={vi.fn()} title={"INDUSTRIAECOMERCIODEEQUIPAMENTOSDESEGURANCALTDA"}>
        <p>body</p>
      </Modal>,
    );
    const titulo = screen.getByRole("heading", { level: 2 });
    expect(titulo).toHaveClass("min-w-0", "break-words");
    expect(screen.getByRole("button", { name: "Fechar" })).toHaveClass("shrink-0");
  });

  it("clicar dentro do painel não fecha", async () => {
    // Controle: sem ele, uma modal que nunca chamasse onClose por clique
    // nenhum passaria nos dois casos acima.
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Modal">
        <p>body</p>
      </Modal>,
    );
    await userEvent.click(screen.getByText("body"));
    expect(onClose).not.toHaveBeenCalled();
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
    // porque o modal fecha por mais de um caminho: o X, os botões da tela que o
    // chamou, o Escape e a desmontagem. (Clique no fundo deixou de fechar em
    // 15/09/2026.)
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
