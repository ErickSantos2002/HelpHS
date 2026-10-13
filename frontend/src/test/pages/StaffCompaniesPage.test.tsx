import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/groupService", () => ({
  listAllCompanies: vi.fn(),
  listGroups: vi.fn(),
  getCompanyById: vi.fn(),
  listCompanyNotes: vi.fn(),
  getCompany: vi.fn(),
}));
vi.mock("../../services/productService", () => ({
  listAllEquipments: vi.fn(),
}));

import StaffCompaniesPage from "../../pages/groups/StaffCompaniesPage";
import * as groupService from "../../services/groupService";
import * as productService from "../../services/productService";
import type { CompanyStaffItem, GroupResponse } from "../../services/groupService";

/**
 * A tela de Empresas da equipe: consulta, e só consulta.
 *
 * Prende o que ela promete — achar a empresa sem abrir grupo por grupo, por
 * nome ou CNPJ — e o que ela não pode fazer: nenhuma ação de manutenção, que
 * continua sendo da tela de Grupos.
 */

function empresa(over: Partial<CompanyStaffItem>): CompanyStaffItem {
  return {
    id: "c1",
    group_id: "g1",
    group_name: "Grupo Norte",
    name: "Alfa Transportes",
    cnpj: "11222333000181",
    phone: null,
    address: null,
    city: null,
    state: null,
    notes: null,
    client_count: 2,
    note_count: 0,
    equipment_count: 3,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...over,
  };
}

const ALFA = empresa({});
const VAZIA = empresa({
  id: "c2",
  group_id: "g2",
  group_name: "Grupo Sul",
  name: "Gama Vazia",
  cnpj: null,
  client_count: 0,
  equipment_count: 0,
});

const GRUPOS: GroupResponse[] = [
  { id: "g1", name: "Grupo Norte", description: null, notes: null, company_count: 1, created_at: "", updated_at: "" },
  { id: "g2", name: "Grupo Sul", description: null, notes: null, company_count: 1, created_at: "", updated_at: "" },
];

function comEmpresas(items: CompanyStaffItem[] = [ALFA, VAZIA], total = items.length) {
  vi.mocked(groupService.listAllCompanies).mockResolvedValue({ items, total, limit: 20, offset: 0 });
}

function ultimaChamada() {
  const chamadas = vi.mocked(groupService.listAllCompanies).mock.calls;
  return chamadas[chamadas.length - 1][0] ?? {};
}

function linhaDe(nome: string): HTMLElement {
  return screen.getByRole("button", { name: nome }).closest("tr") as HTMLElement;
}

function renderPagina() {
  return render(
    <MemoryRouter>
      <StaffCompaniesPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(groupService.listGroups).mockResolvedValue(GRUPOS);
  vi.mocked(groupService.listCompanyNotes).mockResolvedValue([]);
  vi.mocked(productService.listAllEquipments).mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });
  comEmpresas();
});

describe("StaffCompaniesPage — listagem", () => {
  it("mostra o carregamento enquanto a lista não chega", () => {
    vi.mocked(groupService.listAllCompanies).mockReturnValue(new Promise(() => {}));
    renderPagina();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("lista as empresas de todos os grupos, com as colunas pedidas", async () => {
    renderPagina();

    const tabela = await screen.findByRole("table");
    for (const coluna of ["Empresa", "CNPJ", "Grupo", "Clientes vinculados", "Equipamentos", "Ações"]) {
      expect(within(tabela).getByRole("columnheader", { name: coluna })).toBeInTheDocument();
    }
    const alfa = linhaDe("Alfa Transportes");
    expect(within(alfa).getByText("11.222.333/0001-81")).toBeInTheDocument();
    expect(within(alfa).getByText("Grupo Norte")).toBeInTheDocument();
    expect(within(alfa).getByText("2")).toBeInTheDocument();
    expect(within(alfa).getByText("3")).toBeInTheDocument();
    const vazia = linhaDe("Gama Vazia");
    expect(within(vazia).getByText("Grupo Sul")).toBeInTheDocument();
    expect(within(vazia).getByText("—")).toBeInTheDocument();
    expect(screen.getByText("2 empresas")).toBeInTheDocument();
  });

  it("não oferece criar, editar, excluir nem vincular — é consulta", async () => {
    renderPagina();
    await screen.findByRole("table");

    expect(screen.queryByRole("button", { name: /nova|novo|criar|adicionar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /editar|excluir|vincular/i })).toBeNull();
  });
});

describe("StaffCompaniesPage — estados", () => {
  it("vazio sem filtro", async () => {
    comEmpresas([]);
    renderPagina();
    expect(await screen.findByText("Nenhuma empresa cadastrada.")).toBeInTheDocument();
  });

  it("vazio com filtro diz outra coisa, e oferece limpar", async () => {
    renderPagina();
    await screen.findByRole("table");
    comEmpresas([]);

    fireEvent.change(screen.getByRole("textbox", { name: "Buscar empresas" }), { target: { value: "nada" } });

    expect(await screen.findByText("Nenhuma empresa encontrada para esses filtros.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    await waitFor(() => expect(ultimaChamada().search).toBeUndefined());
  });

  it("a falha de rede vira aviso, e não lista vazia", async () => {
    vi.mocked(groupService.listAllCompanies).mockRejectedValue(new Error("rede"));
    renderPagina();

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as empresas.");
    expect(screen.queryByText("Nenhuma empresa cadastrada.")).toBeNull();
  });
});

describe("StaffCompaniesPage — busca, filtro e páginas vão ao SERVIDOR", () => {
  it("a busca (nome ou CNPJ) vai como parâmetro e volta para a primeira página", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.change(screen.getByRole("textbox", { name: "Buscar empresas" }), {
      target: { value: "11.222.333" },
    });

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ search: "11.222.333", offset: 0 }));
  });

  it("o filtro de grupo lista os grupos e manda o escolhido", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: /^Grupo/ }));
    fireEvent.click(await screen.findByRole("option", { name: "Grupo Sul" }));

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ group_id: "g2" }));
  });

  it("trocar de página pede o deslocamento certo", async () => {
    comEmpresas([ALFA], 45);
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Próxima" }));

    await waitFor(() => expect(ultimaChamada()).toMatchObject({ offset: 20, limit: 20 }));
  });
});

describe("StaffCompaniesPage — detalhe", () => {
  it("abre o modal de Grupos em modo somente leitura, pela rota da consulta", async () => {
    vi.mocked(groupService.getCompanyById).mockResolvedValue({
      ...ALFA,
      clients: [{ id: "u1", name: "Maria Souza", email: "maria@alfa.com", phone: null, client_notes: null }],
    });
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Ver detalhes de Alfa Transportes" }));

    const modal = await screen.findByRole("dialog");
    expect(await within(modal).findByText("Maria Souza")).toBeInTheDocument();
    expect(groupService.getCompanyById).toHaveBeenCalledWith("c1");
    expect(groupService.getCompany).not.toHaveBeenCalled();
    expect(within(modal).queryByRole("button", { name: /vincular|editar empresa/i })).toBeNull();
  });

  it("o nome da empresa também abre o detalhe — no celular a coluna de ações some", async () => {
    vi.mocked(groupService.getCompanyById).mockResolvedValue({ ...VAZIA, clients: [] });
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("button", { name: "Gama Vazia" }));

    const modal = await screen.findByRole("dialog");
    expect(await within(modal).findByText("Nenhum cliente vinculado.")).toBeInTheDocument();
  });
});
