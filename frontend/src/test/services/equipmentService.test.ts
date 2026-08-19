import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  createMyEquipment,
  getMyEquipment,
  updateMyEquipment,
  deleteMyEquipment,
  lookupCnpj,
  lookupCep,
} from "../../services/equipmentService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);
const mockDelete = vi.mocked(api.delete);

const equipamento = {
  id: "e1",
  product_id: "p1",
  owner_id: "u1",
  name: "Titan #001",
  serial_number: "SN-001",
  model: "TN-X",
  description: null,
  location: null,
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("createMyEquipment", () => {
  it("envia o product_id na query e o restante no corpo", async () => {
    // A assimetria é do contrato do backend: product_id é query param do
    // POST /equipment/my, não campo do payload. Mover para o corpo numa
    // refatoração quebraria o cadastro em silêncio.
    mockPost.mockResolvedValue({ data: equipamento });

    const result = await createMyEquipment("p1", {
      name: "Titan #001",
      serial_number: "SN-001",
    });

    expect(mockPost).toHaveBeenCalledWith("/equipment/my?product_id=p1", {
      name: "Titan #001",
      serial_number: "SN-001",
    });
    expect(result).toEqual(equipamento);
  });
});

describe("getMyEquipment", () => {
  it("sem filtro, chama /equipment/my e desempacota items", async () => {
    mockGet.mockResolvedValue({
      data: { items: [equipamento], total: 1, limit: 100, offset: 0 },
    });

    const result = await getMyEquipment();

    expect(mockGet).toHaveBeenCalledWith("/equipment/my");
    expect(result).toEqual([equipamento]);
  });

  it("com is_active=false, o filtro vai na query", async () => {
    // `false` é o caso que trai a checagem errada: `if (isActive)` derrubaria
    // o filtro e devolveria também os ativos.
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 100, offset: 0 },
    });

    await getMyEquipment(false);

    expect(mockGet).toHaveBeenCalledWith("/equipment/my?is_active=false");
  });
});

describe("updateMyEquipment", () => {
  it("faz PATCH em /equipment/my/{id} com o payload", async () => {
    mockPatch.mockResolvedValue({ data: { ...equipamento, name: "Novo nome" } });

    const result = await updateMyEquipment("e1", { name: "Novo nome" });

    expect(mockPatch).toHaveBeenCalledWith("/equipment/my/e1", { name: "Novo nome" });
    expect(result.name).toBe("Novo nome");
  });
});

describe("deleteMyEquipment", () => {
  it("faz DELETE em /equipment/my/{id}", async () => {
    mockDelete.mockResolvedValue({});

    await deleteMyEquipment("e1");

    expect(mockDelete).toHaveBeenCalledWith("/equipment/my/e1");
  });
});

// ── Consultas de cadastro (CNPJ e CEP) ────────────────────────

describe("lookupCnpj", () => {
  it("tira a máscara antes de consultar", async () => {
    mockGet.mockResolvedValue({
      data: {
        cnpj: "12345678000190",
        company_name: "Health & Safety",
        trade_name: "H&S",
        city: "São Paulo",
        state: "SP",
      },
    });

    await lookupCnpj("12.345.678/0001-90");

    expect(mockGet).toHaveBeenCalledWith("/auth/cnpj/12345678000190");
  });
});

describe("lookupCep", () => {
  it("tira a máscara antes de consultar", async () => {
    mockGet.mockResolvedValue({
      data: {
        cep: "01310100",
        address: "Av. Paulista",
        neighborhood: "Bela Vista",
        city: "São Paulo",
        state: "SP",
      },
    });

    await lookupCep("01310-100");

    expect(mockGet).toHaveBeenCalledWith("/auth/cep/01310100");
  });
});
