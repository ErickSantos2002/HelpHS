import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/productService", () => ({ getProducts: vi.fn() }));
vi.mock("../../services/equipmentService", () => ({ getMyEquipment: vi.fn() }));
vi.mock("../../services/attachmentService", () => ({ uploadAttachments: vi.fn() }));
vi.mock("../../services/ticketService", () => ({
  createTicket: vi.fn(),
  getTicket: vi.fn(),
  updateTicket: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { MemoryRouter, Route, Routes } from "react-router-dom";
import { CATEGORIAS } from "../../lib/categoria";
import TicketFormPage from "../../pages/tickets/TicketFormPage";
import { getMyEquipment } from "../../services/equipmentService";
import { getProducts } from "../../services/productService";
import { createTicket, getTicket, updateTicket } from "../../services/ticketService";

/**
 * Editar um chamado não pode desvincular os equipamentos dele.
 *
 * O que acontecia: o formulário carregava o chamado com os aparelhos marcados
 * e, logo em seguida, um efeito que reagia ao produto ZERAVA a seleção — a
 * carga do chamado é, para o efeito, uma troca de produto. O `PATCH` levava
 * `equipment_ids` sempre, então saía `[]`, e lista vazia é o contrato do
 * backend para "desvincule todos". Bastava corrigir a descrição para o chamado
 * perder os aparelhos, sem aviso.
 *
 * Quem edita é a equipe, e o `/equipment/my` dela não traz os aparelhos do
 * cliente: a tela nem mostrava o que estava prestes a apagar.
 *
 * O que estes casos prendem:
 *
 *   - a edição abre com os aparelhos do chamado na lista e marcados, estejam
 *     ou não entre os de quem edita, e chegue a lista antes ou depois do
 *     chamado;
 *   - o conjunto que não mudou NÃO vai no `PATCH` (omitir é "não mexa");
 *   - o que mudou de propósito vai inteiro — inclusive vazio;
 *   - trocar o produto, que é um gesto de quem edita, limpa a seleção;
 *   - a criação continua mandando o conjunto sempre.
 */

const TITAN = { id: "p1", name: "Titan", description: null, version: null, is_active: true };
const PHOEBUS = { id: "p2", name: "Phoebus", description: null, version: null, is_active: true };

const CHAMADO = {
  id: "t1",
  protocol: "HS-2026-0042",
  title: "Chamado com dois aparelhos",
  category: CATEGORIAS[0].value,
  product_id: "p1",
  equipments: [
    { id: "h1", name: "Titan da portaria", serial_number: "SN-1", product_id: "p1" },
    { id: "h2", name: "Titan do almoxarifado", serial_number: null, product_id: "p1" },
  ],
};

const SEM_APARELHOS = { ...CHAMADO, id: "t2", title: "Chamado sem aparelho", equipments: [] };

/** Um aparelho de quem edita, do mesmo produto, que o chamado não tem. */
const DO_EDITOR = {
  id: "e9",
  product_id: "p1",
  owner_id: "u1",
  name: "Titan da recepção",
  serial_number: "SN-9",
  model: null,
  description: null,
  location: null,
  is_active: true,
  created_at: "2026-11-01T12:00:00Z",
  updated_at: "2026-11-01T12:00:00Z",
};

function montar(rota: string) {
  render(
    <MemoryRouter initialEntries={[rota]}>
      <Routes>
        <Route path="/tickets/new" element={<TicketFormPage />} />
        <Route path="/tickets/:id/edit" element={<TicketFormPage />} />
        <Route path="*" element={<p>fora do formulário</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function abrirEdicao(chamado: { id: string; title: string } = CHAMADO) {
  vi.mocked(getTicket).mockResolvedValue(chamado as never);
  montar(`/tickets/${chamado.id}/edit`);
  await waitFor(() => expect(screen.getByLabelText("Título *")).toHaveValue(chamado.title));
}

function descrever(texto = "Só a descrição mudou.") {
  fireEvent.change(screen.getByLabelText("Descrição *"), { target: { value: texto } });
}

function ficha(nome: string | RegExp): HTMLElement {
  return within(screen.getByRole("group", { name: "Equipamentos" })).getByRole("button", {
    name: nome,
  });
}

function escolherProduto(nome: string) {
  // O seletor de produto, e não uma ficha de equipamento que tenha o nome do
  // produto no próprio nome.
  const grupo = screen.getByRole("group", { name: "Equipamentos" });
  const [seletor] = screen
    .getAllByRole("button", { name: /Nenhum \(opcional\)|Titan|Phoebus/ })
    .filter((botao) => !grupo.contains(botao));
  fireEvent.click(seletor);
  fireEvent.click(screen.getByRole("option", { name: nome }));
}

async function enviar() {
  fireEvent.click(screen.getByRole("button", { name: "Revisar e enviar" }));
  fireEvent.click(await screen.findByRole("button", { name: "Confirmar e enviar" }));
}

async function corpoDoPatch() {
  await waitFor(() => expect(updateTicket).toHaveBeenCalledTimes(1));
  return vi.mocked(updateTicket).mock.calls[0][1] as Record<string, unknown>;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getProducts).mockResolvedValue({ items: [TITAN, PHOEBUS], total: 2 } as never);
  // Quem edita é a equipe: a lista dela não tem os aparelhos do cliente.
  vi.mocked(getMyEquipment).mockResolvedValue([] as never);
  vi.mocked(createTicket).mockResolvedValue({ id: "t-novo" } as never);
  vi.mocked(updateTicket).mockResolvedValue({ id: "t1" } as never);
});

describe("TicketFormPage — a edição abre com os equipamentos do chamado", () => {
  it("mostra e marca os aparelhos do chamado que não estão entre os de quem edita", async () => {
    await abrirEdicao();

    expect(ficha(/Titan da portaria/)).toHaveAttribute("aria-pressed", "true");
    expect(ficha(/Titan do almoxarifado/)).toHaveAttribute("aria-pressed", "true");
  });

  it("junta os de quem edita, sem repetir e sem marcar o que o chamado não tem", async () => {
    vi.mocked(getMyEquipment).mockResolvedValue([
      DO_EDITOR,
      { ...DO_EDITOR, id: "h1", name: "Titan da portaria", serial_number: "SN-1" },
    ] as never);

    await abrirEdicao();

    expect(ficha(/Titan da portaria/)).toHaveAttribute("aria-pressed", "true");
    expect(ficha(/Titan do almoxarifado/)).toHaveAttribute("aria-pressed", "true");
    expect(ficha(/Titan da recepção/)).toHaveAttribute("aria-pressed", "false");
    expect(
      within(screen.getByRole("group", { name: "Equipamentos" })).getAllByRole("button", {
        name: /Titan d/,
      }),
    ).toHaveLength(3);
  });

  it("a lista de equipamentos que chega DEPOIS do chamado não desmarca nada", async () => {
    let entregar: (lista: unknown[]) => void = () => {};
    vi.mocked(getMyEquipment).mockReturnValue(
      new Promise((resolve) => {
        entregar = resolve as (lista: unknown[]) => void;
      }) as never,
    );
    vi.mocked(getTicket).mockResolvedValue(CHAMADO as never);
    montar("/tickets/t1/edit");
    // O chamado já respondeu; a lista de equipamentos ainda não.
    await waitFor(() => expect(getTicket).toHaveBeenCalled());
    await Promise.resolve();

    entregar([DO_EDITOR]);
    await waitFor(() =>
      expect(screen.getByLabelText("Título *")).toHaveValue("Chamado com dois aparelhos"),
    );

    expect(ficha(/Titan da portaria/)).toHaveAttribute("aria-pressed", "true");
    expect(ficha(/Titan do almoxarifado/)).toHaveAttribute("aria-pressed", "true");
    descrever();
    await enviar();
    expect(await corpoDoPatch()).not.toHaveProperty("equipment_ids");
  });
});

describe("TicketFormPage — editar sem mexer nos equipamentos não os reenvia", () => {
  it("mudar só a descrição: o PATCH NÃO leva equipment_ids", async () => {
    await abrirEdicao();
    descrever();

    await enviar();

    const corpo = await corpoDoPatch();
    expect(corpo).not.toHaveProperty("equipment_ids");
    expect(corpo).toMatchObject({
      title: "Chamado com dois aparelhos",
      description: "Só a descrição mudou.",
      product_id: "p1",
    });
  });

  it("mudar título e categoria: o PATCH NÃO leva equipment_ids", async () => {
    await abrirEdicao();
    fireEvent.change(screen.getByLabelText("Título *"), { target: { value: "Título corrigido" } });
    fireEvent.click(screen.getAllByRole("radio")[1]);
    descrever();

    await enviar();

    const corpo = await corpoDoPatch();
    expect(corpo).not.toHaveProperty("equipment_ids");
    expect(corpo).toMatchObject({ title: "Título corrigido", category: CATEGORIAS[1].value });
  });

  it("desmarcar e marcar de volta ainda é o mesmo conjunto", async () => {
    await abrirEdicao();
    fireEvent.click(ficha(/Titan do almoxarifado/));
    fireEvent.click(ficha(/Titan do almoxarifado/));
    descrever();

    await enviar();

    expect(await corpoDoPatch()).not.toHaveProperty("equipment_ids");
  });

  it("chamado que nunca teve aparelho: nada a reenviar", async () => {
    await abrirEdicao(SEM_APARELHOS);
    descrever();

    await enviar();

    expect(await corpoDoPatch()).not.toHaveProperty("equipment_ids");
  });
});

describe("TicketFormPage — o que muda de propósito vai inteiro", () => {
  it("desmarcar um aparelho manda o conjunto que sobrou", async () => {
    await abrirEdicao();
    fireEvent.click(ficha(/Titan do almoxarifado/));
    descrever();

    await enviar();

    expect((await corpoDoPatch()).equipment_ids).toEqual(["h1"]);
  });

  it("desmarcar TODOS manda a lista vazia — desvincular de propósito continua possível", async () => {
    await abrirEdicao();
    fireEvent.click(ficha(/Titan da portaria/));
    fireEvent.click(ficha(/Titan do almoxarifado/));
    descrever();

    await enviar();

    expect((await corpoDoPatch()).equipment_ids).toEqual([]);
  });

  it("acrescentar um aparelho ao chamado que não tinha nenhum", async () => {
    vi.mocked(getMyEquipment).mockResolvedValue([DO_EDITOR] as never);
    await abrirEdicao(SEM_APARELHOS);
    fireEvent.click(ficha(/Titan da recepção/));
    descrever();

    await enviar();

    expect((await corpoDoPatch()).equipment_ids).toEqual(["e9"]);
  });

  it("trocar o produto limpa a seleção, e o PATCH leva o produto novo e a lista vazia", async () => {
    await abrirEdicao();
    escolherProduto("Phoebus");
    descrever();

    await enviar();

    const corpo = await corpoDoPatch();
    expect(corpo.product_id).toBe("p2");
    expect(corpo.equipment_ids).toEqual([]);
  });

  it("voltar ao produto original mostra os aparelhos do chamado de novo, desmarcados", async () => {
    await abrirEdicao();
    escolherProduto("Phoebus");
    escolherProduto("Titan");

    expect(ficha(/Titan da portaria/)).toHaveAttribute("aria-pressed", "false");
    expect(ficha(/Titan do almoxarifado/)).toHaveAttribute("aria-pressed", "false");
  });
});

describe("TicketFormPage — a criação não muda", () => {
  async function abrirCriacao() {
    vi.mocked(getMyEquipment).mockResolvedValue([DO_EDITOR] as never);
    montar("/tickets/new");
    await waitFor(() =>
      expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText("Título *"), { target: { value: "Aparelho não liga" } });
    descrever("Parou de ligar ontem à tarde.");
    fireEvent.click(screen.getAllByRole("radio")[0]);
  }

  it("sem equipamento, o POST leva a lista vazia", async () => {
    await abrirCriacao();

    await enviar();

    await waitFor(() => expect(createTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createTicket).mock.calls[0][0]).toMatchObject({ equipment_ids: [] });
    expect(updateTicket).not.toHaveBeenCalled();
  });

  it("com equipamento marcado, o POST leva o conjunto", async () => {
    await abrirCriacao();
    escolherProduto("Titan");
    fireEvent.click(ficha(/Titan da recepção/));

    await enviar();

    await waitFor(() => expect(createTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createTicket).mock.calls[0][0]).toMatchObject({
      product_id: "p1",
      equipment_ids: ["e9"],
    });
  });

  it("trocar de produto descarta o que estava marcado", async () => {
    await abrirCriacao();
    escolherProduto("Titan");
    fireEvent.click(ficha(/Titan da recepção/));
    escolherProduto("Phoebus");

    await enviar();

    await waitFor(() => expect(createTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createTicket).mock.calls[0][0]).toMatchObject({
      product_id: "p2",
      equipment_ids: [],
    });
  });
});
