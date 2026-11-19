import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { campoDeMenu, escolherNoMenu, opcoesDoMenu } from "../helpers/menu";

vi.mock("../../services/productService", () => ({
  createEquipment: vi.fn(),
  createProduct: vi.fn(),
  getEquipments: vi.fn(),
  getProducts: vi.fn(),
  setEquipmentActive: vi.fn(),
  setProductActive: vi.fn(),
  updateEquipment: vi.fn(),
  updateProduct: vi.fn(),
}));
vi.mock("../../services/userService", () => ({ getUsers: vi.fn() }));
vi.mock("../../services/groupService", () => ({ listAllCompanies: vi.fn() }));

import ProductsPage from "../../pages/products/ProductsPage";
import * as groupService from "../../services/groupService";
import * as productService from "../../services/productService";
import type { Equipment, Product } from "../../services/productService";

/**
 * A classificação da empresa do equipamento pela equipe (ECE-01).
 *
 * O backend distingue três coisas no corpo, e a diferença entre as duas
 * primeiras é a presença da CHAVE:
 *
 *   1. `company_id` ausente  → não mexe (edição) / herda do dono (cadastro);
 *   2. `company_id: "<id>"`  → atribui a empresa;
 *   3. `company_id: null`    → tira a empresa e marca "por decisão".
 *
 * O risco que estes casos prendem é o formulário transformar (1) em (3): editar
 * o nome de um equipamento e, sem querer, apagar a empresa dele e marcá-lo como
 * decisão. Por isso cada caso olha se a chave EXISTE no corpo, não só o valor.
 */

const PRODUTO: Product = {
  id: "p1",
  name: "Detector de Gases",
  description: null,
  version: null,
  is_active: true,
};

const EQUIPAMENTO: Equipment = {
  id: "e1",
  product_id: "p1",
  name: "Detector 04",
  serial_number: "SN-001234",
  model: "Detector de Gases",
  description: null,
  is_active: true,
  owner_id: "u1",
  owner_name: "Maria Souza",
  owner_email: "maria@exemplo.com",
  linked_company_id: "c1",
  linked_company_name: "Alfa Transportes",
  equipment_company_id: "c1",
  equipment_company_name: "Alfa Transportes",
  no_company_by_decision: false,
};

function comEquipamento(e: Equipment) {
  vi.mocked(productService.getEquipments).mockResolvedValue({
    items: [e],
    total: 1,
    limit: 10,
    offset: 0,
  });
}

async function abrirEdicao(user: ReturnType<typeof userEvent.setup>) {
  render(<ProductsPage />);
  await user.click(await screen.findByText("Detector de Gases"));
  await waitFor(() => expect(productService.getEquipments).toHaveBeenCalled());
  await user.click(await screen.findByRole("button", { name: "Visualizar" }));
  await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Editar" }));
  return screen.findByRole("dialog", { name: /editar equipamento/i });
}

async function abrirCadastro(user: ReturnType<typeof userEvent.setup>) {
  render(<ProductsPage />);
  await user.click(await screen.findByText("Detector de Gases"));
  await waitFor(() => expect(productService.getEquipments).toHaveBeenCalled());
  await user.click(screen.getByRole("button", { name: /Novo\s*Equipamento/ }));
  return screen.findByRole("dialog", { name: /novo equipamento/i });
}

function corpoDaEdicao(): Record<string, unknown> {
  return vi.mocked(productService.updateEquipment).mock.calls[0][1] as Record<string, unknown>;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productService.getProducts).mockResolvedValue({
    items: [PRODUTO],
    total: 1,
    limit: 10,
    offset: 0,
  });
  comEquipamento(EQUIPAMENTO);
  vi.mocked(productService.updateEquipment).mockResolvedValue(EQUIPAMENTO);
  vi.mocked(productService.createEquipment).mockResolvedValue(EQUIPAMENTO);
  vi.mocked(groupService.listAllCompanies).mockResolvedValue({
    items: [
      { id: "c2", name: "Beta Logística", group_name: "Grupo Sul" },
      { id: "c1", name: "Alfa Transportes", group_name: "Grupo Norte" },
    ],
    total: 2,
    limit: 20,
    offset: 0,
  } as never);
});

describe("ProductsPage — empresa do equipamento na edição", () => {
  it("abre em 'Manter como está', e diz como o equipamento está hoje", async () => {
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    const campo = campoDeMenu("Empresa do equipamento");
    expect(campo).toHaveTextContent("Manter como está");
    expect(within(modal).getByText(/Hoje: Alfa Transportes\./)).toBeInTheDocument();
    expect(within(modal).getByText(/Salvar não altera a empresa/)).toBeInTheDocument();
    expect(opcoesDoMenu(campo)).toEqual([
      "Manter como está",
      "Definir a empresa…",
      "Sem empresa (por decisão)",
    ]);
  });

  it("OMITIDO: salvar sem tocar na empresa não manda a chave company_id", async () => {
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);
    fireEvent.change(within(modal).getByLabelText("Nome *"), { target: { value: "Detector 04-B" } });

    await user.click(within(modal).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(productService.updateEquipment).toHaveBeenCalledTimes(1));
    expect(corpoDaEdicao()).toMatchObject({ name: "Detector 04-B" });
    // Nem `null`, nem `undefined` dentro do objeto: a chave não existe.
    expect(Object.keys(corpoDaEdicao())).not.toContain("company_id");
    expect(JSON.parse(JSON.stringify(corpoDaEdicao()))).not.toHaveProperty("company_id");
  });

  it("NULL EXPLÍCITO: 'Sem empresa (por decisão)' manda company_id: null", async () => {
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    escolherNoMenu(campoDeMenu("Empresa do equipamento"), "Sem empresa (por decisão)");
    expect(within(modal).getByText(/marcado como decisão da equipe/)).toBeInTheDocument();
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(productService.updateEquipment).toHaveBeenCalledTimes(1));
    expect(Object.keys(corpoDaEdicao())).toContain("company_id");
    expect(corpoDaEdicao().company_id).toBeNull();
    // É `null` que atravessa o JSON — `undefined` sumiria e viraria "omitido".
    expect(JSON.parse(JSON.stringify(corpoDaEdicao()))).toHaveProperty("company_id", null);
  });

  it("EMPRESA DEFINIDA: escolher a empresa manda o id dela", async () => {
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    escolherNoMenu(campoDeMenu("Empresa do equipamento"), "Definir a empresa…");
    await user.click(within(modal).getByRole("button", { name: /Selecionar/ }));
    await user.type(screen.getByPlaceholderText("Buscar empresa por nome ou CNPJ…"), "beta");
    await user.click(await screen.findByText("Beta Logística"));
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(productService.updateEquipment).toHaveBeenCalledTimes(1));
    expect(corpoDaEdicao().company_id).toBe("c2");
    expect(groupService.listAllCompanies).toHaveBeenCalledWith(
      expect.objectContaining({ search: "beta" }),
    );
  });

  it("'Definir' sem escolher empresa NÃO vira null: recusa, explica e não salva", async () => {
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    escolherNoMenu(campoDeMenu("Empresa do equipamento"), "Definir a empresa…");
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));

    expect(await within(modal).findByText("Selecione a empresa.")).toBeInTheDocument();
    expect(productService.updateEquipment).not.toHaveBeenCalled();
  });

  it("voltar para 'Manter como está' depois de escolher empresa volta a omitir", async () => {
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    escolherNoMenu(campoDeMenu("Empresa do equipamento"), "Sem empresa (por decisão)");
    escolherNoMenu(campoDeMenu("Empresa do equipamento"), "Manter como está");
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(productService.updateEquipment).toHaveBeenCalledTimes(1));
    expect(Object.keys(corpoDaEdicao())).not.toContain("company_id");
  });

  it.each([
    [{ equipment_company_id: null, equipment_company_name: null, no_company_by_decision: true }, /Hoje: sem empresa, por decisão da equipe\./],
    [{ equipment_company_id: null, equipment_company_name: null, no_company_by_decision: false }, /Hoje: sem empresa \(ainda não classificado\)\./],
  ])("diz a situação de hoje quando não há empresa", async (campos, texto) => {
    comEquipamento({ ...EQUIPAMENTO, ...campos });
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    expect(within(modal).getByText(texto)).toBeInTheDocument();
  });

  it("API anterior ao campo: não inventa 'Hoje', e o padrão continua sendo omitir", async () => {
    const antigo: Equipment = { ...EQUIPAMENTO };
    delete antigo.equipment_company_id;
    delete antigo.equipment_company_name;
    delete antigo.no_company_by_decision;
    comEquipamento(antigo);
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    expect(within(modal).queryByText(/Hoje:/)).toBeNull();
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(productService.updateEquipment).toHaveBeenCalledTimes(1));
    expect(Object.keys(corpoDaEdicao())).not.toContain("company_id");
  });

  it("a recusa do backend à empresa aparece no formulário", async () => {
    vi.mocked(productService.updateEquipment).mockRejectedValue({
      request: {},
      response: { status: 400, data: { detail: "A empresa informada não existe." }, headers: {} },
    });
    const user = userEvent.setup();
    const modal = await abrirEdicao(user);

    escolherNoMenu(campoDeMenu("Empresa do equipamento"), "Sem empresa (por decisão)");
    await user.click(within(modal).getByRole("button", { name: "Salvar" }));

    expect(await within(modal).findByText("A empresa informada não existe.")).toBeInTheDocument();
  });
});

describe("ProductsPage — empresa do equipamento no cadastro", () => {
  it("abre em 'Automática', e criar sem tocar não manda company_id — o backend herda a do dono", async () => {
    const user = userEvent.setup();
    const modal = await abrirCadastro(user);

    expect(campoDeMenu("Empresa do equipamento")).toHaveTextContent("Automática: a empresa do dono");
    fireEvent.change(within(modal).getByLabelText("Nome *"), { target: { value: "Detector novo" } });
    await user.click(within(modal).getByRole("button", { name: "Criar equipamento" }));

    await waitFor(() => expect(productService.createEquipment).toHaveBeenCalledTimes(1));
    const corpo = vi.mocked(productService.createEquipment).mock.calls[0][1] as Record<string, unknown>;
    expect(Object.keys(corpo)).not.toContain("company_id");
  });

  it("criar 'Sem empresa (por decisão)' manda null explícito", async () => {
    const user = userEvent.setup();
    const modal = await abrirCadastro(user);

    fireEvent.change(within(modal).getByLabelText("Nome *"), { target: { value: "Detector de feira" } });
    escolherNoMenu(campoDeMenu("Empresa do equipamento"), "Sem empresa (por decisão)");
    await user.click(within(modal).getByRole("button", { name: "Criar equipamento" }));

    await waitFor(() => expect(productService.createEquipment).toHaveBeenCalledTimes(1));
    const corpo = vi.mocked(productService.createEquipment).mock.calls[0][1] as Record<string, unknown>;
    expect(corpo).toHaveProperty("company_id", null);
  });
});
