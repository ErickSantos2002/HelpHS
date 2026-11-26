import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/productService", () => ({
  getProducts: vi.fn(),
  listAllEquipments: vi.fn(),
}));
vi.mock("../../services/groupService", () => ({
  listAllCompanies: vi.fn(),
  getCompanyById: vi.fn(),
}));

import StaffEquipmentsPage from "../../pages/equipment/StaffEquipmentsPage";
import * as groupService from "../../services/groupService";
import * as productService from "../../services/productService";
import type { Equipment } from "../../services/productService";

/**
 * A empresa DO EQUIPAMENTO na consulta da equipe (ECE-01).
 *
 * A equipe recebe duas empresas oficiais por linha — a do equipamento e a do
 * responsável — nos dois modos do backend, justamente para conferir a
 * classificação antes de ligar o compartilhamento. Estes casos prendem:
 *
 *   - a empresa do equipamento é a que aparece como empresa da linha;
 *   - a divergência com a do responsável é dita, e só quando existe;
 *   - "sem empresa por decisão" não é a mesma coisa que "sem empresa";
 *   - o filtro "Sem empresa" peneira no servidor (`without_company`).
 *
 * A tela diante de uma API ANTERIOR ao campo é o que `StaffEquipmentsPage.test`
 * já prende: as fixtures de lá não têm `equipment_company_id`.
 */

const BASE: Equipment = {
  id: "x",
  product_id: "p1",
  product_name: "Titan",
  name: "x",
  serial_number: null,
  model: null,
  description: null,
  is_active: true,
  owner_id: "u1",
  owner_name: "Maria Souza",
  owner_email: "maria@alfa.com.br",
  company_name: null,
  company_cnpj: null,
  linked_company_id: "c1",
  linked_company_name: "Alfa Transportes",
  equipment_company_id: "c1",
  equipment_company_name: "Alfa Transportes",
  no_company_by_decision: false,
};

const ALINHADO: Equipment = { ...BASE, id: "e1", name: "Titan alinhado" };

/** Mudou de responsável e ficou na empresa antiga. */
const TRANSFERIDO: Equipment = {
  ...BASE,
  id: "e2",
  name: "Titan transferido",
  owner_name: "Pedro Alves",
  linked_company_id: "c2",
  linked_company_name: "Beta Logística",
};

const RESPONSAVEL_SEM_VINCULO: Equipment = {
  ...BASE,
  id: "e3",
  name: "Titan de quem saiu",
  linked_company_id: null,
  linked_company_name: null,
};

const POR_DECISAO: Equipment = {
  ...BASE,
  id: "e4",
  name: "Titan de demonstração",
  equipment_company_id: null,
  equipment_company_name: null,
  no_company_by_decision: true,
};

const A_CLASSIFICAR: Equipment = {
  ...BASE,
  id: "e5",
  name: "Titan a classificar",
  equipment_company_id: null,
  equipment_company_name: null,
  no_company_by_decision: false,
};

const SEM_RESPONSAVEL: Equipment = {
  ...BASE,
  id: "e6",
  name: "Titan do estoque",
  owner_id: null,
  owner_name: null,
  owner_email: null,
  linked_company_id: null,
  linked_company_name: null,
};

const TODOS = [ALINHADO, TRANSFERIDO, RESPONSAVEL_SEM_VINCULO, POR_DECISAO, A_CLASSIFICAR, SEM_RESPONSAVEL];

function renderPagina(rota = "/equipamentos") {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <StaffEquipmentsPage />
    </MemoryRouter>,
  );
}

function linhaDe(nome: string): HTMLElement {
  return screen.getByText(nome).closest("tr") as HTMLElement;
}

function ultimaChamada() {
  const chamadas = vi.mocked(productService.listAllEquipments).mock.calls;
  return chamadas[chamadas.length - 1][0] ?? {};
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(productService.getProducts).mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
  vi.mocked(productService.listAllEquipments).mockResolvedValue({
    items: TODOS,
    total: TODOS.length,
    limit: 20,
    offset: 0,
  });
  vi.mocked(groupService.listAllCompanies).mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
});

describe("StaffEquipmentsPage — empresa do equipamento e do responsável", () => {
  it("quando as duas coincidem, a linha mostra a empresa uma vez, sem aviso", async () => {
    renderPagina();
    await screen.findByRole("table");

    const linha = linhaDe("Titan alinhado");
    expect(within(linha).getAllByText("Alfa Transportes")).toHaveLength(1);
    expect(within(linha).queryByText(/Diverge/)).toBeNull();
  });

  it("aparelho transferido: a empresa da linha é a DO EQUIPAMENTO, e a do responsável vem como divergência", async () => {
    renderPagina();
    await screen.findByRole("table");

    const linha = linhaDe("Titan transferido");
    expect(within(linha).getByText("Alfa Transportes")).toBeInTheDocument();
    expect(within(linha).getByText("Diverge do responsável: Beta Logística")).toBeInTheDocument();
  });

  it("responsável sem vínculo e aparelho classificado: diverge, e diz que ele não tem empresa", async () => {
    renderPagina();
    await screen.findByRole("table");

    expect(
      within(linhaDe("Titan de quem saiu")).getByText("Diverge do responsável: sem empresa vinculada"),
    ).toBeInTheDocument();
  });

  it("sem empresa POR DECISÃO é dito assim, e não acusa divergência", async () => {
    renderPagina();
    await screen.findByRole("table");

    const linha = linhaDe("Titan de demonstração");
    expect(within(linha).getByText("Sem empresa (por decisão)")).toBeInTheDocument();
    expect(within(linha).queryByText(/Diverge/)).toBeNull();
  });

  it("a classificar diz só 'Sem empresa' — e diverge do responsável que tem empresa", async () => {
    renderPagina();
    await screen.findByRole("table");

    const linha = linhaDe("Titan a classificar");
    expect(within(linha).getByText("Sem empresa")).toBeInTheDocument();
    expect(within(linha).queryByText("Sem empresa (por decisão)")).toBeNull();
    expect(within(linha).getByText("Diverge do responsável: Alfa Transportes")).toBeInTheDocument();
  });

  it("equipamento sem responsável não tem com o que divergir", async () => {
    renderPagina();
    await screen.findByRole("table");

    const linha = linhaDe("Titan do estoque");
    expect(within(linha).getByText("Sem responsável")).toBeInTheDocument();
    expect(within(linha).getByText("Alfa Transportes")).toBeInTheDocument();
    expect(within(linha).queryByText(/Diverge/)).toBeNull();
  });

  it("a tela não oferece classificar em massa nem editar — a classificação é na tela de Produtos", async () => {
    renderPagina();
    await screen.findByRole("table");

    expect(screen.queryByRole("button", { name: /^(classificar|definir|aplicar|editar|salvar)/i })).toBeNull();
    expect(screen.getByText(/definir a empresa de um equipamento, use a tela de Produtos/)).toBeInTheDocument();
  });
});

describe("StaffEquipmentsPage — filtro 'Sem empresa'", () => {
  it("desligado, o parâmetro não vai", async () => {
    renderPagina();
    await screen.findByRole("table");

    expect(ultimaChamada().without_company).toBeUndefined();
  });

  it("ligado, peneira no SERVIDOR e volta para a primeira página", async () => {
    renderPagina();
    await screen.findByRole("table");

    fireEvent.click(screen.getByRole("checkbox", { name: "Sem empresa" }));

    await waitFor(() => expect(ultimaChamada().without_company).toBe(true));
    expect(ultimaChamada().offset).toBe(0);
    // É outro filtro, e não um apelido do vizinho.
    expect(ultimaChamada().without_owner).toBeUndefined();
  });

  it("'Limpar filtros' desliga também este", async () => {
    renderPagina();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("checkbox", { name: "Sem empresa" }));
    await waitFor(() => expect(ultimaChamada().without_company).toBe(true));

    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));

    await waitFor(() => expect(ultimaChamada().without_company).toBeUndefined());
  });
});

describe("StaffEquipmentsPage — detalhe com as duas empresas", () => {
  async function abrirDetalhe(nome: string) {
    renderPagina();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: `Ver detalhes de ${nome}` }));
    return screen.findByRole("dialog");
  }

  it("mostra a empresa do equipamento e a do responsável, cada uma com o seu rótulo", async () => {
    const modal = await abrirDetalhe("Titan transferido");

    expect(within(modal).getByText("Empresa do equipamento")).toBeInTheDocument();
    expect(within(modal).getByText("Alfa Transportes")).toBeInTheDocument();
    expect(within(modal).getByText("Empresa do responsável")).toBeInTheDocument();
    expect(within(modal).getByText("Beta Logística")).toBeInTheDocument();
    expect(within(modal).getByText("Diferente da empresa do responsável.")).toBeInTheDocument();
  });

  it("alinhado não traz o aviso", async () => {
    const modal = await abrirDetalhe("Titan alinhado");

    expect(within(modal).queryByText("Diferente da empresa do responsável.")).toBeNull();
  });

  it("por decisão explica que foi de propósito", async () => {
    const modal = await abrirDetalhe("Titan de demonstração");

    expect(within(modal).getByText("Sem empresa (por decisão)")).toBeInTheDocument();
    expect(within(modal).getByText(/sem empresa de propósito/)).toBeInTheDocument();
    expect(within(modal).queryByText("Ainda não classificado.")).toBeNull();
  });

  it("a classificar diz que falta classificar", async () => {
    const modal = await abrirDetalhe("Titan a classificar");

    expect(within(modal).getByText("Ainda não classificado.")).toBeInTheDocument();
  });

  it("continua só de leitura", async () => {
    const modal = await abrirDetalhe("Titan transferido");

    expect(within(modal).queryByRole("button", { name: /editar/i })).toBeNull();
  });
});

describe("StaffEquipmentsPage — filtro por empresa × coluna Empresa", () => {
  const AVISO = /Este filtro trouxe equipamentos pela empresa do responsável/;

  function comLista(items: Equipment[]) {
    vi.mocked(productService.listAllEquipments).mockResolvedValue({
      items,
      total: items.length,
      limit: 20,
      offset: 0,
    });
    vi.mocked(groupService.listAllCompanies).mockResolvedValue({
      items: [
        { id: "c1", name: "Alfa Transportes" },
        { id: "c2", name: "Beta Logística" },
      ],
      total: 2,
      limit: 100,
      offset: 0,
    } as never);
  }

  it("linha que não é da empresa filtrada só entrou pelo responsável: a tela avisa", async () => {
    // O backend, casando a empresa do RESPONSÁVEL, devolve o aparelho que é da
    // Alfa para quem filtrou Beta. Sem aviso, filtro e coluna parecem discordar.
    comLista([TRANSFERIDO]);
    renderPagina("/equipamentos?empresa=c2");
    await screen.findByRole("table");

    expect(await screen.findByText(AVISO)).toBeInTheDocument();
    expect(ultimaChamada().company_id).toBe("c2");
  });

  it("equipamento sem empresa trazido pelo filtro também conta", async () => {
    comLista([A_CLASSIFICAR]);
    renderPagina("/equipamentos?empresa=c1");
    await screen.findByRole("table");

    expect(await screen.findByText(AVISO)).toBeInTheDocument();
  });

  it("todas as linhas são da empresa filtrada: nada a esclarecer", async () => {
    comLista([ALINHADO, SEM_RESPONSAVEL]);
    renderPagina("/equipamentos?empresa=c1");
    await screen.findByRole("table");
    await waitFor(() => expect(ultimaChamada().company_id).toBe("c1"));

    expect(screen.queryByText(AVISO)).toBeNull();
  });

  it("sem filtro de empresa não há aviso, mesmo com linhas divergentes", async () => {
    comLista(TODOS);
    renderPagina();
    await screen.findByRole("table");

    expect(screen.queryByText(AVISO)).toBeNull();
  });

  it("API anterior ao campo: a tela não tem como constatar, e não avisa", async () => {
    const antigo: Equipment = { ...TRANSFERIDO };
    delete antigo.equipment_company_id;
    delete antigo.equipment_company_name;
    delete antigo.no_company_by_decision;
    comLista([antigo]);
    renderPagina("/equipamentos?empresa=c2");
    await screen.findByRole("table");
    await waitFor(() => expect(ultimaChamada().company_id).toBe("c2"));

    expect(screen.queryByText(AVISO)).toBeNull();
  });
});
