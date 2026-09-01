import { render, waitFor } from "@testing-library/react";
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
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { CompanyDetailModal } from "../../pages/groups/GroupsPage";
import { getCompany, listCompanyNotes } from "../../services/groupService";
import type { CompanyResponse } from "../../services/groupService";

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
