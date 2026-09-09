import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/productService", () => ({ getProducts: vi.fn() }));
vi.mock("../../services/equipmentService", () => ({ getMyEquipment: vi.fn() }));
vi.mock("../../services/attachmentService", () => ({ uploadAttachments: vi.fn() }));
vi.mock("../../services/ticketService", () => ({
  createTicket: vi.fn(),
  getTicket: vi.fn(),
  updateTicket: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { MemoryRouter } from "react-router-dom";
import TicketFormPage from "../../pages/tickets/TicketFormPage";
import { getProducts } from "../../services/productService";
import { getMyEquipment } from "../../services/equipmentService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * A categoria e a prioridade eram **pilhas de `<button>`**: doze botões cujo
 * nome era só o rótulo, sem "escolhido", sem grupo e sem relação com as
 * palavras "Categoria" e "Prioridade" escritas acima deles. A escolha existia
 * apenas na cor.
 *
 * A prioridade ainda trazia o **sexto** mapa divergente do mesmo dado, com
 * rótulos no masculino ("Crítico") contra o feminino que a emenda E17 fixou no
 * pacote — no mesmo sistema, a mesma prioridade tinha dois nomes.
 *
 * E a trilha era um `<button>` com a linha inteira dentro, então o nome
 * acessível do controle era "Tickets / Novo chamado": a página de onde se vem
 * e a página onde se está, num controle só.
 */
async function montar() {
  vi.mocked(getProducts).mockResolvedValue({ items: [], total: 0 } as never);
  vi.mocked(getMyEquipment).mockResolvedValue([] as never);

  render(
    <MemoryRouter initialEntries={["/tickets/new"]}>
      <TicketFormPage />
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument(),
  );
}

describe("TicketFormPage", () => {
  it("categoria e prioridade são grupos de rádio, com nome", async () => {
    await montar();
    expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Prioridade" })).toBeInTheDocument();
    // Oito categorias e quatro prioridades, e nenhuma delas é botão.
    expect(screen.getAllByRole("radio")).toHaveLength(12);
  });

  it("a prioridade fala a mesma língua do resto do sistema", async () => {
    // Feminino, concordando com "prioridade" — emenda E17. O mapa que existia
    // aqui dizia "Crítico", "Alto", "Médio", "Baixo".
    await montar();
    for (const rotulo of ["Crítica", "Alta", "Média", "Baixa"]) {
      expect(screen.getByRole("radio", { name: rotulo })).toBeInTheDocument();
    }
  });

  it("a prioridade nasce em Média, e a árvore diz isso", async () => {
    // `defaultValues` já era `medium`; o que faltava era alguém CONSEGUIR saber.
    await montar();
    expect(screen.getByRole("radio", { name: "Média" })).toBeChecked();
  });

  it("escolher categoria muda o que a árvore diz, não só a cor", async () => {
    await montar();
    const rede = screen.getByRole("radio", { name: "Rede" });
    expect(rede).not.toBeChecked();
    await userEvent.click(rede);
    expect(rede).toBeChecked();
  });

  it("a trilha é um link para a lista, e não um botão", async () => {
    await montar();
    const link = screen.getByRole("link", { name: "Tickets" });
    expect(link).toHaveAttribute("href", "/tickets");
    // E a página atual não finge ser clicável.
    expect(screen.queryByRole("link", { name: /Novo chamado/ })).not.toBeInTheDocument();
  });

  it("a etapa atual é dita, e não apenas pintada", async () => {
    await montar();
    const atual = screen.getByText("Formulário");
    expect(atual).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Revisão")).not.toHaveAttribute("aria-current");
  });

  it("o grupo de equipamentos tem nome", async () => {
    // Era um `<label>` sem `htmlFor`: rótulo pendurado no vazio.
    await montar();
    expect(screen.getByRole("group", { name: "Equipamentos" })).toBeInTheDocument();
  });
});
