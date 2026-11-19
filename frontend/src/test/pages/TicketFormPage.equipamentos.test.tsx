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
 * Equipamentos no formulário de chamado, com o compartilhamento por empresa
 * (ECE-01).
 *
 * O formulário não decide o que pode ser associado — o backend decide, no
 * `POST` e no `PATCH`. O que estes casos prendem é o que a tela faz com as
 * respostas:
 *
 *   - oferece o que `/equipment/my` devolveu, próprio ou da empresa;
 *   - a recusa por MISTURA de empresas (400) é explicada com a frase do backend;
 *   - a recusa por FORA DO ESCOPO (403) e a de id inexistente (400) viram a
 *     MESMA frase — a tela não conta qual das duas foi;
 *   - na edição, o conjunto que não mudou não é reenviado (é o que mantém
 *     editável o chamado antigo); o que mudou vai inteiro;
 *   - na criação o conjunto vai sempre — a exceção não existe para quem abre.
 */

const PRODUTO = { id: "p1", name: "Titan", description: null, version: null, is_active: true };
const OUTRO_PRODUTO = { id: "p2", name: "Phoebus", description: null, version: null, is_active: true };

const BASE = {
  product_id: "p1",
  model: null,
  description: null,
  location: null,
  is_active: true,
  created_at: "2026-11-01T12:00:00Z",
  updated_at: "2026-11-01T12:00:00Z",
};

const PROPRIO = { ...BASE, id: "e1", owner_id: "u1", name: "Titan da portaria", serial_number: "SN-1", is_mine: true };
const DE_COLEGA = { ...BASE, id: "e2", owner_id: null, name: "Titan do almoxarifado", serial_number: "SN-2", is_mine: false };
const OUTRO_PROPRIO = { ...BASE, id: "e3", owner_id: "u1", name: "Titan reserva", serial_number: null, is_mine: true };

const MISTURA =
  "Os equipamentos de um chamado precisam ser todos da mesma empresa — a de quem abriu o chamado, quando ele tem uma — ou todos ainda sem empresa.";
const FORA_DO_ESCOPO = "Só é possível vincular equipamentos que pertencem a você ou à sua empresa.";
const INEXISTENTE = "Um ou mais equipamentos informados não existem.";
const NEUTRA =
  "Um dos equipamentos selecionados não está mais disponível. A lista foi atualizada: confira a seleção e tente de novo.";

function recusa(status: number, detail: string) {
  return { request: {}, response: { status, data: { detail }, headers: {} } };
}

function montar(rota = "/tickets/new") {
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

async function esperarFormulario() {
  await waitFor(() =>
    expect(screen.getByRole("group", { name: "Categoria" })).toBeInTheDocument(),
  );
}

function preencherTexto() {
  fireEvent.change(screen.getByLabelText("Título *"), {
    target: { value: "Aparelho não liga" },
  });
  fireEvent.change(screen.getByLabelText("Descrição *"), {
    target: { value: "Parou de ligar ontem à tarde." },
  });
}

function escolherCategoria() {
  fireEvent.click(screen.getAllByRole("radio")[0]);
}

function escolherProduto(nome: string) {
  fireEvent.click(screen.getByRole("button", { name: /Nenhum \(opcional\)|Titan|Phoebus/ }));
  fireEvent.click(screen.getByRole("option", { name: nome }));
}

function grupoDeEquipamentos(): HTMLElement {
  return screen.getByRole("group", { name: "Equipamentos" });
}

function ficha(nome: string | RegExp): HTMLElement {
  return within(grupoDeEquipamentos()).getByRole("button", { name: nome });
}

async function enviar() {
  fireEvent.click(screen.getByRole("button", { name: "Revisar e enviar" }));
  fireEvent.click(await screen.findByRole("button", { name: "Confirmar e enviar" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getProducts).mockResolvedValue({ items: [PRODUTO, OUTRO_PRODUTO], total: 2 } as never);
  vi.mocked(getMyEquipment).mockResolvedValue([PROPRIO, DE_COLEGA, OUTRO_PROPRIO] as never);
  vi.mocked(createTicket).mockResolvedValue({ id: "t-novo" } as never);
  vi.mocked(updateTicket).mockResolvedValue({ id: "t1" } as never);
});

describe("TicketFormPage — abrir chamado com equipamento próprio e da empresa", () => {
  async function abrir() {
    montar();
    await esperarFormulario();
    preencherTexto();
    escolherCategoria();
    escolherProduto("Titan");
  }

  it("oferece os próprios e os da empresa; o da empresa vem marcado em palavra", async () => {
    await abrir();

    expect(ficha(/Titan da portaria/)).not.toHaveTextContent("Da empresa");
    expect(ficha(/Titan do almoxarifado/)).toHaveTextContent("Da empresa");
    expect(ficha(/Titan reserva/)).toBeInTheDocument();
  });

  it("manda no POST os ids escolhidos, próprio e da empresa juntos", async () => {
    await abrir();
    fireEvent.click(ficha(/Titan da portaria/));
    fireEvent.click(ficha(/Titan do almoxarifado/));

    await enviar();

    await waitFor(() => expect(createTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createTicket).mock.calls[0][0]).toMatchObject({
      product_id: "p1",
      equipment_ids: ["e1", "e2"],
    });
  });

  it("na criação o conjunto vai SEMPRE, mesmo vazio — a exceção do conjunto inalterado não é de quem abre", async () => {
    await abrir();

    await enviar();

    await waitFor(() => expect(createTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createTicket).mock.calls[0][0]).toHaveProperty("equipment_ids", []);
    expect(updateTicket).not.toHaveBeenCalled();
  });

  it("sem compartilhamento (tudo is_mine=true), nenhuma ficha vem marcada", async () => {
    vi.mocked(getMyEquipment).mockResolvedValue([PROPRIO, OUTRO_PROPRIO] as never);
    await abrir();

    expect(within(grupoDeEquipamentos()).queryByText(/Da empresa/)).toBeNull();
    expect(within(grupoDeEquipamentos()).queryByRole("button", { name: /almoxarifado/ })).toBeNull();
  });

  it("sem nada a oferecer, diz que não há equipamento DISPONÍVEL — não que a pessoa não cadastrou", async () => {
    // Com o compartilhamento, a lista vazia não é mais só "você não cadastrou":
    // pode haver equipamento do produto na empresa que não está ao alcance.
    vi.mocked(getMyEquipment).mockResolvedValue([] as never);
    await abrir();

    expect(screen.getByText("Nenhum equipamento disponível para este produto.")).toBeInTheDocument();
    expect(screen.queryByText(/Você não tem equipamentos/)).toBeNull();
  });

  it("400 de mistura de empresas: mostra o motivo e mantém a seleção para a pessoa corrigir", async () => {
    vi.mocked(createTicket).mockRejectedValue(recusa(400, MISTURA));
    await abrir();
    fireEvent.click(ficha(/Titan da portaria/));
    fireEvent.click(ficha(/Titan do almoxarifado/));

    await enviar();

    expect(await screen.findByText(MISTURA)).toBeInTheDocument();
    // Voltou ao formulário, com as duas ainda marcadas.
    expect(ficha(/Titan da portaria/)).toHaveAttribute("aria-pressed", "true");
    expect(ficha(/Titan do almoxarifado/)).toHaveAttribute("aria-pressed", "true");
    expect(getMyEquipment).toHaveBeenCalledTimes(1);
  });

  it("403 de fora do escopo: frase neutra, lista recarregada e seleção limpa", async () => {
    vi.mocked(createTicket).mockRejectedValue(recusa(403, FORA_DO_ESCOPO));
    await abrir();
    fireEvent.click(ficha(/Titan do almoxarifado/));
    // O aparelho saiu do alcance entre a carga e o envio.
    vi.mocked(getMyEquipment).mockResolvedValue([PROPRIO, OUTRO_PROPRIO] as never);

    await enviar();

    expect(await screen.findByText(NEUTRA)).toBeInTheDocument();
    expect(screen.queryByText(FORA_DO_ESCOPO)).toBeNull();
    await waitFor(() => expect(getMyEquipment).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(within(grupoDeEquipamentos()).queryByRole("button", { name: /almoxarifado/ })).toBeNull(),
    );
    for (const botao of within(grupoDeEquipamentos()).getAllByRole("button", { pressed: false })) {
      expect(botao).toHaveAttribute("aria-pressed", "false");
    }
    expect(within(grupoDeEquipamentos()).queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });

  it("400 de id inexistente dá a MESMA frase do 403 — a tela não conta qual das duas foi", async () => {
    vi.mocked(createTicket).mockRejectedValue(recusa(400, INEXISTENTE));
    await abrir();
    fireEvent.click(ficha(/Titan da portaria/));

    await enviar();

    expect(await screen.findByText(NEUTRA)).toBeInTheDocument();
    expect(screen.queryByText(INEXISTENTE)).toBeNull();
    expect(document.body.textContent).not.toMatch(/não existem|pertencem a você/);
  });

  it("outro erro continua com a mensagem do servidor, ou a genérica quando não há", async () => {
    vi.mocked(createTicket).mockRejectedValue(new Error("sem resposta"));
    await abrir();

    await enviar();

    expect(await screen.findByText("Erro ao salvar o chamado. Tente novamente.")).toBeInTheDocument();
  });
});

describe("TicketFormPage — edição pela equipe e o conjunto histórico", () => {
  /** Chamado antigo, de antes da regra: dois aparelhos que hoje não iriam juntos. */
  const CHAMADO = {
    id: "t1",
    protocol: "HS-2026-0042",
    title: "Chamado antigo",
    category: CATEGORIAS[0].value,
    product_id: "p1",
    equipments: [
      { id: "h1", name: "Aparelho da empresa X", serial_number: "SN-X", product_id: "p1" },
      { id: "h2", name: "Aparelho sem empresa", serial_number: null, product_id: "p1" },
    ],
  };

  async function abrirEdicao(daEquipe: unknown[] = []) {
    // Quem edita é a equipe: `/equipment/my` dela não tem os aparelhos do cliente.
    vi.mocked(getMyEquipment).mockResolvedValue(daEquipe as never);
    vi.mocked(getTicket).mockResolvedValue(CHAMADO as never);
    montar("/tickets/t1/edit");
    await esperarFormulario();
    await waitFor(() => expect(screen.getByLabelText("Título *")).toHaveValue("Chamado antigo"));
    fireEvent.change(screen.getByLabelText("Descrição *"), {
      target: { value: "Ajuste do título pela equipe." },
    });
  }

  it("abre com os aparelhos do chamado na lista e MARCADOS — antes abria com a seleção vazia", async () => {
    await abrirEdicao();

    expect(ficha(/Aparelho da empresa X/)).toHaveAttribute("aria-pressed", "true");
    expect(ficha(/Aparelho sem empresa/)).toHaveAttribute("aria-pressed", "true");
  });

  it("sem mexer nos aparelhos, o PATCH NÃO leva equipment_ids — o conjunto histórico fica como está", async () => {
    await abrirEdicao();

    await enviar();

    await waitFor(() => expect(updateTicket).toHaveBeenCalledTimes(1));
    const [id, corpo] = vi.mocked(updateTicket).mock.calls[0];
    expect(id).toBe("t1");
    expect(corpo).not.toHaveProperty("equipment_ids");
    expect(corpo).toMatchObject({ title: "Chamado antigo", product_id: "p1" });
  });

  it("desmarcar e marcar de volta ainda é o mesmo conjunto: não reenvia", async () => {
    await abrirEdicao();
    fireEvent.click(ficha(/Aparelho sem empresa/));
    fireEvent.click(ficha(/Aparelho sem empresa/));

    await enviar();

    await waitFor(() => expect(updateTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateTicket).mock.calls[0][1]).not.toHaveProperty("equipment_ids");
  });

  it("mudar o conjunto manda o conjunto novo inteiro — e aí o backend confere a regra", async () => {
    await abrirEdicao();
    fireEvent.click(ficha(/Aparelho sem empresa/));

    await enviar();

    await waitFor(() => expect(updateTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateTicket).mock.calls[0][1]).toHaveProperty("equipment_ids", ["h1"]);
  });

  it("trocar um aparelho por outro mantém a QUANTIDADE e muda o conjunto: vai", async () => {
    await abrirEdicao([PROPRIO]);
    fireEvent.click(ficha(/Aparelho sem empresa/));
    fireEvent.click(ficha(/Titan da portaria/));

    await enviar();

    await waitFor(() => expect(updateTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateTicket).mock.calls[0][1]).toHaveProperty("equipment_ids", ["h1", "e1"]);
  });

  it("trocar de produto limpa a seleção, e isso é mudança: vai lista vazia", async () => {
    await abrirEdicao();
    escolherProduto("Phoebus");

    await enviar();

    await waitFor(() => expect(updateTicket).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateTicket).mock.calls[0][1]).toMatchObject({
      product_id: "p2",
      equipment_ids: [],
    });
  });

  it("a recusa do backend ao conjunto alterado aparece, e a seleção volta ao que o chamado tinha", async () => {
    vi.mocked(updateTicket).mockRejectedValue(recusa(400, INEXISTENTE));
    await abrirEdicao();
    fireEvent.click(ficha(/Aparelho sem empresa/));

    await enviar();

    expect(await screen.findByText(NEUTRA)).toBeInTheDocument();
    await waitFor(() =>
      expect(ficha(/Aparelho sem empresa/)).toHaveAttribute("aria-pressed", "true"),
    );
    expect(ficha(/Aparelho da empresa X/)).toHaveAttribute("aria-pressed", "true");
  });

  it("a recusa por mistura na edição mostra o motivo do backend", async () => {
    vi.mocked(updateTicket).mockRejectedValue(recusa(400, MISTURA));
    await abrirEdicao();
    fireEvent.click(ficha(/Aparelho da empresa X/));

    await enviar();

    expect(await screen.findByText(MISTURA)).toBeInTheDocument();
  });
});
