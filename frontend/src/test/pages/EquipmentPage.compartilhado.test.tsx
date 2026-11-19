import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/api", () => ({ api: { get: vi.fn() } }));
vi.mock("../../services/equipmentService", () => ({
  createMyEquipment: vi.fn(),
  deleteMyEquipment: vi.fn(),
  getMyEquipment: vi.fn(),
  updateMyEquipment: vi.fn(),
}));

import EquipmentPage from "../../pages/equipment/EquipmentPage";
import { api } from "../../services/api";
import * as equipmentService from "../../services/equipmentService";
import type { Equipment } from "../../services/equipmentService";

/**
 * "Meus equipamentos" com o compartilhamento por empresa (ECE-01).
 *
 * Com a flag ligada no backend, `/equipment/my` traz também os equipamentos
 * ativos da empresa do cliente, cadastrados por colegas: `is_mine=false` e sem
 * dado nenhum do responsável. A tela não sabe se a flag está ligada — lê o
 * campo, item por item.
 *
 * O que estes casos prendem:
 *   - o compartilhado se diz compartilhado em PALAVRA;
 *   - ele não oferece editar nem excluir (o backend recusaria com 404 de
 *     qualquer forma — a tela só não convida);
 *   - o próprio continua com as duas ações;
 *   - nada do responsável aparece, nem se a API mandasse por engano;
 *   - com a flag desligada a tela é a de antes.
 */

const PRODUTO = { id: "p1", name: "Detector de Gases", version: null, is_active: true };

const BASE = {
  product_id: "p1",
  model: null,
  description: null,
  location: null,
  created_at: "2026-11-01T12:00:00Z",
  updated_at: "2026-11-01T12:00:00Z",
};

const PROPRIO: Equipment = {
  ...BASE,
  id: "e1",
  owner_id: "u1",
  name: "Detector da portaria",
  serial_number: "SN-MEU-1",
  is_active: true,
  is_mine: true,
};

const PROPRIO_INATIVO: Equipment = {
  ...BASE,
  id: "e2",
  owner_id: "u1",
  name: "Detector antigo",
  serial_number: null,
  is_active: false,
  is_mine: true,
};

/** Como o backend o entrega ao colega: sem `owner_id`, `is_mine=false`. */
const DE_COLEGA: Equipment = {
  ...BASE,
  id: "e3",
  owner_id: null,
  name: "Detector do almoxarifado",
  serial_number: "SN-COL-3",
  is_active: true,
  is_mine: false,
};

/** Da empresa, sem responsável nenhum — para o cliente é igual ao de colega. */
const SEM_RESPONSAVEL: Equipment = {
  ...BASE,
  id: "e4",
  owner_id: null,
  name: "Detector reserva",
  serial_number: "SN-RES-4",
  is_active: true,
  is_mine: false,
};

async function montar(equipamentos: Equipment[]) {
  vi.mocked(api.get).mockResolvedValue({ data: { items: [PRODUTO] } } as never);
  vi.mocked(equipmentService.getMyEquipment).mockResolvedValue(equipamentos);
  render(<EquipmentPage />);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Meus equipamentos" })).toBeInTheDocument(),
  );
}

function linhaDe(nome: string): HTMLElement {
  // A linha é o ancestral que contém o nome E a coluna de ações.
  return screen.getByText(nome).closest("div.flex.items-center.gap-4") as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EquipmentPage — equipamento compartilhado pela empresa", () => {
  it("o compartilhado se diz 'Da empresa', e o próprio não", async () => {
    await montar([PROPRIO, DE_COLEGA]);

    expect(within(linhaDe("Detector do almoxarifado")).getByText("Da empresa")).toBeInTheDocument();
    expect(within(linhaDe("Detector da portaria")).queryByText("Da empresa")).toBeNull();
  });

  it("o compartilhado não oferece editar nem excluir", async () => {
    await montar([PROPRIO, DE_COLEGA, SEM_RESPONSAVEL]);

    for (const nome of ["Detector do almoxarifado", "Detector reserva"]) {
      expect(screen.queryByRole("button", { name: `Editar ${nome}` })).toBeNull();
      expect(screen.queryByRole("button", { name: `Excluir ${nome}` })).toBeNull();
      expect(within(linhaDe(nome)).queryAllByRole("button")).toHaveLength(0);
    }
  });

  it("o próprio continua com editar e excluir — ativo ou inativo", async () => {
    await montar([PROPRIO, PROPRIO_INATIVO, DE_COLEGA]);

    for (const nome of ["Detector da portaria", "Detector antigo"]) {
      expect(screen.getByRole("button", { name: `Editar ${nome}` })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: `Excluir ${nome}` })).toBeInTheDocument();
    }
  });

  it("nada do responsável aparece — nem se a API o mandasse por engano", async () => {
    // O backend zera estes campos no equipamento de colega. O caso prende que
    // a TELA também não os desenha: se um dia vazarem na resposta, não chegam
    // aos olhos de ninguém por aqui.
    const vazado = {
      ...DE_COLEGA,
      owner_id: "u-colega",
      owner_name: "Carlos Colega",
      owner_email: "carlos@empresa.com.br",
      company_name: "Empresa Declarada LTDA",
      company_cnpj: "11222333000181",
    } as Equipment;
    await montar([PROPRIO, vazado]);

    const tela = document.body.textContent ?? "";
    for (const dado of ["Carlos Colega", "carlos@empresa.com.br", "Empresa Declarada", "u-colega", "11222333000181", "11.222.333"]) {
      expect(tela).not.toContain(dado);
    }
  });

  it("owner_id nulo não quebra a linha", async () => {
    await montar([DE_COLEGA, SEM_RESPONSAVEL]);

    expect(screen.getByText("Detector do almoxarifado")).toBeInTheDocument();
    expect(screen.getByText("SN-RES-4")).toBeInTheDocument();
  });

  it("a explicação só aparece quando há compartilhado na lista", async () => {
    await montar([PROPRIO, DE_COLEGA]);

    expect(screen.getByText(/foram cadastrados por colegas/)).toBeInTheDocument();
    expect(screen.getByText(/não alterá-los/)).toBeInTheDocument();
  });

  it("os compartilhados entram nas contagens das abas", async () => {
    await montar([PROPRIO, PROPRIO_INATIVO, DE_COLEGA]);

    expect(screen.getByRole("button", { name: "Todos (3)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ativos (2)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inativos (1)" })).toBeInTheDocument();
  });
});

describe("EquipmentPage — compartilhamento desligado (regressão)", () => {
  it("com is_mine=true em tudo, a tela é a de antes: sem selo, sem explicação, com ações", async () => {
    await montar([PROPRIO, PROPRIO_INATIVO]);

    expect(screen.queryByText("Da empresa")).toBeNull();
    expect(screen.queryByText(/cadastrados por colegas/)).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Editar / })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /^Excluir / })).toHaveLength(2);
  });

  it("resposta SEM o campo is_mine (API anterior) trata tudo como próprio", async () => {
    const semCampo = [PROPRIO, PROPRIO_INATIVO].map((e) => {
      const copia: Partial<Equipment> = { ...e };
      delete copia.is_mine;
      return copia as Equipment;
    });
    await montar(semCampo);

    expect(screen.queryByText("Da empresa")).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Editar / })).toHaveLength(2);
  });
});

describe("EquipmentPage — estados", () => {
  it("lista vazia convida a cadastrar", async () => {
    await montar([]);

    expect(screen.getByText("Nenhum equipamento cadastrado ainda.")).toBeInTheDocument();
  });

  it("a falha de carga vira aviso, e não 'nenhum equipamento'", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [PRODUTO] } } as never);
    vi.mocked(equipmentService.getMyEquipment).mockRejectedValue(new Error("rede"));
    render(<EquipmentPage />);

    expect(
      await screen.findByText(/Não foi possível carregar os equipamentos/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Nenhum equipamento cadastrado ainda.")).toBeNull();
    expect(screen.queryByRole("button", { name: "Adicionar equipamento" })).toBeNull();
  });
});
