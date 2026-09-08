import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/groupService", () => ({
  getCompany: vi.fn(),
  listCompanyNotes: vi.fn(),
  updateCompany: vi.fn(),
  deleteCompany: vi.fn(),
  assignClient: vi.fn(),
  unassignClient: vi.fn(),
  updateClientNotes: vi.fn(),
  listUnassignedClients: vi.fn(),
  createCompanyNote: vi.fn(),
  deleteCompanyNote: vi.fn(),
  // A página inteira, que os casos da Fase 16 montam. Um nome que falta aqui
  // só estoura quando a tela CHAMA a função — por isso a lista antiga passava
  // sem eles, e por isso ela precisa crescer junto com o que se monta.
  listGroups: vi.fn(),
  getGroup: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  deleteGroup: vi.fn(),
  createCompany: vi.fn(),
  getCompanySuggestions: vi.fn(),
  createCompanyFromSuggestion: vi.fn(),
  listGroupNotes: vi.fn(),
  createGroupNote: vi.fn(),
  deleteGroupNote: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import GroupsPage, { CompanyDetailModal } from "../../pages/groups/GroupsPage";
import {
  getCompany,
  getGroup,
  listCompanyNotes,
  listGroupNotes,
  listGroups,
} from "../../services/groupService";
import type {
  CompanyNote,
  CompanyResponse,
  GroupDetail,
  GroupResponse,
} from "../../services/groupService";

/**
 * O aviso do ESLint pedia `load` nas deps do efeito deste modal. Atender ao
 * pedido do jeito ingênuo — só acrescentar `load` — dá laço infinito, porque
 * `load` era redefinido a cada render e chama `setState`.
 *
 * A correção foi `useCallback(load, [groupId, company.id])` com
 * `useEffect(() => load(), [load])`. Estes testes prendem as duas metades
 * dessa correção:
 *
 *   1. o efeito NÃO dispara em re-render sem mudança — se disparasse, seria o
 *      laço que a correção ingênua causaria;
 *   2. o efeito dispara quando `groupId` muda — que é a dependência que estava
 *      FALTANDO antes e a razão de a correção não ser só cosmética.
 *
 * O teste 2 é o que importa: tirar `groupId` das deps do useCallback deixa o
 * teste 1 verde e derruba só ele.
 */

const EMPRESA: CompanyResponse = {
  id: "empresa-1",
  group_id: "grupo-A",
  name: "Transportes Alfa",
  cnpj: "12.345.678/0001-90",
  phone: null,
  address: null,
  city: null,
  state: null,
  notes: null,
  client_count: 0,
  note_count: 0,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

const DETALHE = { ...EMPRESA, clients: [] };

describe("CompanyDetailModal — recarga do efeito", () => {
  beforeEach(() => {
    vi.mocked(getCompany).mockResolvedValue(DETALHE);
    vi.mocked(listCompanyNotes).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("carrega uma vez só, por mais que o pai re-renderize", async () => {
    const { rerender } = render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(1));

    // Cinco re-renders com as MESMAS props, e callbacks inline novos a cada vez
    // — que é como o pai realmente renderiza este modal.
    for (let i = 0; i < 5; i++) {
      rerender(
        <CompanyDetailModal
          groupId="grupo-A"
          company={EMPRESA}
          onClose={() => {}}
          onUpdated={() => {}}
        />,
      );
    }

    expect(getCompany).toHaveBeenCalledTimes(1);
  });

  it("recarrega quando o grupo muda, mesmo com a mesma empresa", async () => {
    // Esta é a dependência que faltava. Antes da correção o efeito olhava só
    // `company.id`: com `groupId` novo e a mesma empresa, o modal seguiria
    // mostrando o que carregou pelo grupo anterior.
    const { rerender } = render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(1));
    expect(getCompany).toHaveBeenLastCalledWith("grupo-A", "empresa-1");

    rerender(
      <CompanyDetailModal
        groupId="grupo-B"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(2));
    expect(getCompany).toHaveBeenLastCalledWith("grupo-B", "empresa-1");
  });

  it("recarrega quando a empresa muda", async () => {
    const { rerender } = render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(1));

    rerender(
      <CompanyDetailModal
        groupId="grupo-A"
        company={{ ...EMPRESA, id: "empresa-2" }}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    await waitFor(() => expect(getCompany).toHaveBeenCalledTimes(2));
    expect(getCompany).toHaveBeenLastCalledWith("grupo-A", "empresa-2");
  });
});

/**
 * Os casos abaixo entraram com a migração da Fase 16, e todos medem o que a
 * tela PROMETE — o rótulo que a pessoa lê, o nome acessível do controle, o
 * estado vazio —, nunca a classe que pinta.
 *
 * A distinção não é preciosismo: o jsdom não aplica CSS nenhum, então um caso
 * escrito sobre classe passaria com o elemento invisível e reprovaria com ele
 * visível. Cada um destes foi validado por mutação no próprio arquivo da tela.
 */

const NOTA_EMPRESA: CompanyNote = {
  id: "nota-1",
  company_id: "empresa-1",
  author_id: "user-1",
  author_name: "Ana Souza",
  content: "Contrato renovado em janeiro.",
  created_at: "2026-09-02T10:00:00Z",
};

describe("CompanyDetailModal — a aba de notas", () => {
  beforeEach(() => {
    vi.mocked(getCompany).mockResolvedValue(DETALHE);
    vi.mocked(listCompanyNotes).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("mostra o estado vazio quando a empresa não tem nota", async () => {
    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(0\)/ }));

    expect(screen.getByText("Nenhuma nota ainda.")).toBeInTheDocument();
  });

  it("dá nome acessível ao botão de deletar de cada nota", async () => {
    // O botão é só o ícone, e o `Icon` do pacote é `aria-hidden`. Sem
    // `aria-label` quem usa leitor de tela ouve "botão" e mais nada — foi o
    // mesmo defeito achado no `TicketListPage`.
    vi.mocked(listCompanyNotes).mockResolvedValue([NOTA_EMPRESA]);

    render(
      <CompanyDetailModal
        groupId="grupo-A"
        company={EMPRESA}
        onClose={() => {}}
        onUpdated={() => {}}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Notas \(1\)/ }));

    expect(
      screen.getByRole("button", { name: "Deletar nota" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Contrato renovado em janeiro.")).toBeInTheDocument();
  });
});

const GRUPO_ALFA: GroupResponse = {
  id: "grupo-A",
  name: "Grupo Alfa",
  description: "Transportadoras do litoral",
  notes: null,
  company_count: 1,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

const GRUPO_BETA: GroupResponse = {
  ...GRUPO_ALFA,
  id: "grupo-B",
  name: "Grupo Beta",
  description: null,
  company_count: 0,
};

const DETALHE_ALFA: GroupDetail = { ...GRUPO_ALFA, companies: [EMPRESA] };

describe("GroupsPage — a lista de grupos", () => {
  beforeEach(() => {
    vi.mocked(listGroups).mockResolvedValue([GRUPO_ALFA, GRUPO_BETA]);
    vi.mocked(getGroup).mockResolvedValue(DETALHE_ALFA);
    vi.mocked(listGroupNotes).mockResolvedValue([]);
    vi.mocked(getCompany).mockResolvedValue(DETALHE);
    vi.mocked(listCompanyNotes).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("lista os grupos e pede que se escolha um", async () => {
    render(<GroupsPage />);

    expect(await screen.findByText("Grupo Alfa")).toBeInTheDocument();
    expect(screen.getByText("Grupo Beta")).toBeInTheDocument();
    expect(screen.getByText("Selecione um grupo")).toBeInTheDocument();
  });

  it("dá nome acessível ao campo de busca de grupos", async () => {
    // O campo só tinha `placeholder`, e placeholder some ao digitar: quem
    // volta ao campo depois não tem como saber o que ele filtra.
    render(<GroupsPage />);
    await screen.findByText("Grupo Alfa");

    expect(
      screen.getByRole("textbox", { name: "Pesquisar grupos" }),
    ).toBeInTheDocument();
  });

  it("a busca esconde o grupo que não casa com o texto", async () => {
    render(<GroupsPage />);
    await screen.findByText("Grupo Alfa");

    fireEvent.change(screen.getByRole("textbox", { name: "Pesquisar grupos" }), {
      target: { value: "beta" },
    });

    expect(screen.queryByText("Grupo Alfa")).not.toBeInTheDocument();
    expect(screen.getByText("Grupo Beta")).toBeInTheDocument();
  });

  it("escolher um grupo traz as empresas dele", async () => {
    render(<GroupsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Grupo Alfa/ }));

    expect(await screen.findByText("Transportes Alfa")).toBeInTheDocument();
    expect(getGroup).toHaveBeenCalledWith("grupo-A");
  });
});
