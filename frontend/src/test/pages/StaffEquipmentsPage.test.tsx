import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { escolherNoMenu } from "../helpers/menu";

vi.mock("../../services/productService", () => ({
  getProducts: vi.fn(),
  listAllEquipments: vi.fn(),
}));
vi.mock("../../services/groupService", () => ({
  listAllCompanies: vi.fn(),
  getCompanyById: vi.fn(),
}));

import StaffEquipmentsPage from "../../pages/equipment/StaffEquipmentsPage";
import * as productService from "../../services/productService";
import * as groupService from "../../services/groupService";
import type { Equipment, Product } from "../../services/productService";
import type { CompanyStaffItem } from "../../services/groupService";

function empresa(id: string, name: string): CompanyStaffItem {
  return {
    id,
    name,
    group_id: "g1",
    group_name: "Grupo Norte",
    cnpj: null,
    phone: null,
    address: null,
    city: null,
    state: null,
    notes: null,
    client_count: 1,
    note_count: 0,
    equipment_count: 1,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  };
}

const ALFA = empresa("c1", "Alfa Transportes");
const BETA = empresa("c2", "Beta Logística");

/** A página lê `?empresa=` da URL, por isso sempre dentro de um roteador. */
function renderPagina(rota = "/equipamentos") {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <StaffEquipmentsPage />
    </MemoryRouter>,
  );
}

/**
 * A tela de Equipamentos da equipe: consulta, e só consulta.
 *
 * O que estes casos prendem é o que a tela promete ao técnico — achar o
 * aparelho de qualquer cliente sem abrir produto por produto — e o que ela
 * NÃO pode prometer: a empresa que o cliente digitou não é o vínculo oficial,
 * e o responsável atual não é "quem cadastrou".
 */

const TITAN: Product = { id: "p1", name: "Titan", description: null, version: null, is_active: true };
const PHOEBUS: Product = { id: "p2", name: "Phoebus", description: null, version: null, is_active: true };

const DA_MARIA: Equipment = {
  id: "e1",
  product_id: "p1",
  product_name: "Titan",
  name: "Titan da recepção",
  serial_number: "SN-MAR-1",
  model: "TN-X",
  description: "Fica no balcão",
  location: "Recepção",
  is_active: true,
  owner_id: "u1",
  owner_name: "Maria Souza",
  owner_email: "maria@alfa.com.br",
  company_name: "Alfa Transp. LTDA",
  company_cnpj: "11222333000181",
  linked_company_id: "c1",
  linked_company_name: "Alfa Transportes",
};

const DO_PEDRO: Equipment = {
  id: "e2",
  product_id: "p1",
  product_name: "Titan",
  name: "Titan do Pedro",
  serial_number: null,
  model: null,
  description: null,
  is_active: true,
  owner_id: "u2",
  owner_name: "Pedro Alves",
  owner_email: "pedro@x.com",
  company_name: "Alfa Transportes",
  company_cnpj: null,
  linked_company_id: null,
  linked_company_name: null,
};

const ORFAO: Equipment = {
  id: "e3",
  product_id: "p2",
  product_name: "Phoebus",
  name: "Phoebus sem dono",
  serial_number: "PH-ORF-3",
  model: null,
  description: null,
  is_active: false,
  owner_id: null,
  owner_name: null,
  owner_email: null,
  company_name: null,
  company_cnpj: null,
  linked_company_id: null,
  linked_company_name: null,
};

function comEquipamentos(items: Equipment[] = [DA_MARIA, DO_PEDRO, ORFAO], total = items.length) {
  vi.mocked(productService.listAllEquipments).mockResolvedValue({
    items,
    total,
    limit: 20,
    offset: 0,
  });
}

function ultimaChamada() {
  const chamadas = vi.mocked(productService.listAllEquipments).mock.calls;
  return chamadas[chamadas.length - 1][0] ?? {};
}

function linhaDe(nome: string): HTMLElement {
  return screen.getByText(nome).closest("tr") as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productService.getProducts).mockResolvedValue({
    items: [TITAN, PHOEBUS],
    total: 2,
    limit: 100,
    offset: 0,
  });
  comEquipamentos();
  vi.mocked(groupService.listAllCompanies).mockResolvedValue({
    items: [ALFA, BETA],
    total: 2,
    limit: 100,
    offset: 0,
  });
});

describe("StaffEquipmentsPage — listagem", () => {
  it("mostra o carregamento enquanto a lista não chega", async () => {
    vi.mocked(productService.listAllEquipments).mockReturnValue(new Promise(() => {}));
    renderPagina();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("lista equipamentos de clientes e produtos diferentes, com as colunas da operação", async () => {
    renderPagina();

    const tabela = await screen.findByRole("table");
    for (const coluna of ["Equipamento", "Produto", "Série", "Responsável", "Empresa", "Status", "Ações"]) {
      expect(within(tabela).getByRole("columnheader", { name: coluna })).toBeInTheDocument();
    }
    const maria = linhaDe("Titan da recepção");
    expect(within(maria).getByText("Titan")).toBeInTheDocument();
    expect(within(maria).getByText("SN-MAR-1")).toBeInTheDocument();
    expect(within(maria).getByText("Maria Souza")).toBeInTheDocument();
    expect(within(linhaDe("Phoebus sem dono")).getByText("Phoebus")).toBeInTheDocument();
    expect(screen.getByText("3 equipamentos")).toBeInTheDocument();
  });

  it("a empresa vinculada aparece como empresa; a declarada vem marcada como declarada", async () => {
    renderPagina();

    await screen.findByRole("table");
    const maria = linhaDe("Titan da recepção");
    expect(within(maria).getByText("Alfa Transportes")).toBeInTheDocument();
    expect(within(maria).getByText("Declarada: Alfa Transp. LTDA")).toBeInTheDocument();

    // O Pedro só DIGITOU o nome da Alfa: não pode parecer vínculo.
    const pedro = linhaDe("Titan do Pedro");
    expect(within(pedro).getByText("Sem empresa vinculada")).toBeInTheDocument();
    expect(within(pedro).getByText("Declarada: Alfa Transportes")).toBeInTheDocument();
    expect(within(pedro).queryByText("Alfa Transportes")).toBeNull();
  });

  it("equipamento sem responsável diz isso, e não inventa empresa", async () => {
    renderPagina();

    await screen.findByRole("table");
    const orfao = linhaDe("Phoebus sem dono");
    expect(within(orfao).getByText("Sem responsável")).toBeInTheDocument();
    expect(within(orfao).getByText("Sem empresa vinculada")).toBeInTheDocument();
    expect(within(orfao).queryByText(/Declarada/)).toBeNull();
  });

  it("o status está escrito, não só pintado", async () => {
    renderPagina();

    await screen.findByRole("table");
    expect(within(linhaDe("Titan da recepção")).getByText("Ativo")).toBeInTheDocument();
    expect(within(linhaDe("Phoebus sem dono")).getByText("Inativo")).toBeInTheDocument();
  });

  it("não oferece criar, editar nem excluir — a tela é de consulta", async () => {
    renderPagina();
    await screen.findByRole("table");

    expect(screen.queryByRole("button", { name: /novo|criar|adicionar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /editar|excluir|desativar|ativar/i })).toBeNull();
    // Nem "cadastrado por": owner_id é o responsável ATUAL, não o autor.
    expect(screen.queryByText(/cadastrad[oa] por/i)).toBeNull();
  });
});

describe("StaffEquipmentsPage — estados", () => {
  it("vazio sem filtro diz que não há equipamentos", async () => {
    comEquipamentos([]);
    renderPagina();
    expect(await screen.findByText("Nenhum equipamento cadastrado.")).toBeInTheDocument();
  });

  it("vazio com filtro diz outra coisa, e oferece limpar", async () => {
    renderPagina();
    await screen.findByRole("table");
    comEquipamentos([]);

    fireEvent.change(screen.getByRole("textbox", { name: "Buscar equipamentos" }), {
      target: { value: "nada" },
    });

    expect(await screen.findByText("Nenhum equipamento encontrado para esses filtros.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    await waitFor(() => expect(ultimaChamada().search).toBeUndefined());
  });

  it("a falha de rede vira aviso, e não lista vazia", async () => {
    vi.mocked(productService.listAllEquipments).mockRejectedValue(new Error("rede"));
    renderPagina();

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar os equipamentos.");
    expect(screen.queryByText("Nenhum equipamento cadastrado.")).toBeNull();
  });
});

describe("StaffEquipmentsPage — busca, filtros e páginas vão ao SERVIDOR", () => {
  it("a busca vai como parâmetro e volta para a primeira página", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.change(screen.getByRole("textbox", { name: "Buscar equipamentos" }), {
      target: { value: "maria@alfa" },
    });

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ search: "maria@alfa", offset: 0 }));
  });

  it("o filtro de produto lista os produtos e manda o escolhido", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: /^Produto/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Phoebus" }));

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ product_id: "p2" }));
  });

  it("o filtro de status manda ativo ou inativo", async () => {
    renderPagina();
    await screen.findByRole("table");

    escolherNoMenu(screen.getByRole("combobox", { name: "Status do equipamento" }), "Inativos");

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ is_active: false }));
  });

  it("'Sem responsável' peneira no servidor", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("checkbox", { name: "Sem responsável" }));

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ without_owner: true }));
  });

  it("trocar de página pede o deslocamento certo", async () => {
    comEquipamentos([DA_MARIA], 45);
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Próxima" }));

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ offset: 20, limit: 20 }));
  });
});

describe("StaffEquipmentsPage — filtro de empresa (só a oficial)", () => {
  it("as opções são as empresas cadastradas; a declarada nunca vira opção", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: /^Empresa/ }));

    const opcoes = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(opcoes).toContain("Alfa Transportes");
    expect(opcoes).toContain("Beta Logística");
    // "Alfa Transp. LTDA" é o que a Maria DIGITOU — está na lista, não no filtro.
    expect(opcoes).not.toContain("Alfa Transp. LTDA");
  });

  it("escolher a empresa manda company_id", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: /^Empresa/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Beta Logística" }));

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ company_id: "c2", offset: 0 }));
  });

  it("chegando com ?empresa= da URL, a lista já vem filtrada", async () => {
    renderPagina("/equipamentos?empresa=c1");

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ company_id: "c1" }));
    expect(await screen.findByRole("button", { name: /^Empresa Alfa Transportes/ })).toBeInTheDocument();
    // A Alfa veio na lista: não há por que pedi-la de novo pelo id.
    expect(groupService.getCompanyById).not.toHaveBeenCalled();
  });

  it("empresa da URL fora das cem primeiras busca o nome dela", async () => {
    vi.mocked(groupService.getCompanyById).mockResolvedValue({
      ...empresa("c9", "Zeta Distante"),
      clients: [],
    });
    renderPagina("/equipamentos?empresa=c9");

    expect(await screen.findByRole("button", { name: /^Empresa Zeta Distante/ })).toBeInTheDocument();
    expect(groupService.getCompanyById).toHaveBeenCalledWith("c9");
  });

  it("limpar os filtros tira a empresa também", async () => {
    renderPagina("/equipamentos?empresa=c1");
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => expect(ultimaChamada().company_id).toBeUndefined());
  });
});

describe("StaffEquipmentsPage — detalhe", () => {
  it("abre o detalhe só de leitura, com responsável e as duas empresas separadas", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Ver detalhes de Titan da recepção" }));

    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByText("Maria Souza")).toBeInTheDocument();
    expect(within(modal).getByText("Empresa vinculada")).toBeInTheDocument();
    expect(within(modal).getByText("Alfa Transportes")).toBeInTheDocument();
    expect(within(modal).getByText("Empresa declarada")).toBeInTheDocument();
    expect(within(modal).getByText("Alfa Transp. LTDA")).toBeInTheDocument();
    expect(within(modal).getByText("Titan")).toBeInTheDocument();
    // Somente leitura: o modal não oferece editar nesta tela.
    expect(within(modal).queryByRole("button", { name: /editar/i })).toBeNull();
  });

  it("o nome do equipamento também abre o detalhe — no celular a coluna de ações some", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Titan da recepção" }));

    expect(await screen.findByRole("dialog")).toHaveTextContent("Maria Souza");
  });

  it("no detalhe de quem não tem vínculo, a empresa vinculada diz que não há", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Ver detalhes de Titan do Pedro" }));

    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByText("Sem empresa vinculada")).toBeInTheDocument();
    expect(within(modal).getByText("Empresa declarada")).toBeInTheDocument();
  });
});
