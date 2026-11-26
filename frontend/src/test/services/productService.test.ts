import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getProducts,
  createProduct,
  updateProduct,
  setProductActive,
  getEquipments,
  listAllEquipments,
  createEquipment,
  updateEquipment,
  setEquipmentActive,
} from "../../services/productService";
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

const product = {
  id: "p1",
  name: "ERP Sistema",
  description: "Sistema de gestão",
  version: "2.0",
  is_active: true,
};

const equipment = {
  id: "e1",
  product_id: "p1",
  name: "Servidor A",
  serial_number: "SN-001",
  model: "Dell PowerEdge",
  description: null,
  is_active: true,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getProducts", () => {
  it("calls GET /products with no params", async () => {
    mockGet.mockResolvedValue({
      data: { items: [product], total: 1, limit: 20, offset: 0 },
    });

    const result = await getProducts();

    expect(mockGet).toHaveBeenCalledWith("/products?");
    expect(result.items).toHaveLength(1);
  });

  it("appends search and is_active params", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getProducts({ search: "ERP", is_active: true });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("search=ERP");
    expect(url).toContain("is_active=true");
  });
});

describe("createProduct", () => {
  it("posts to /products and returns the product", async () => {
    mockPost.mockResolvedValue({ data: product });

    const result = await createProduct({ name: "ERP Sistema", version: "2.0" });

    expect(mockPost).toHaveBeenCalledWith("/products", {
      name: "ERP Sistema",
      version: "2.0",
    });
    expect(result.id).toBe("p1");
  });
});

describe("updateProduct", () => {
  it("patches /products/:id", async () => {
    mockPatch.mockResolvedValue({ data: { ...product, name: "ERP v3" } });

    const result = await updateProduct("p1", { name: "ERP v3" });

    expect(mockPatch).toHaveBeenCalledWith("/products/p1", { name: "ERP v3" });
    expect(result.name).toBe("ERP v3");
  });
});

describe("setProductActive", () => {
  it("patches /products/:id with is_active flag", async () => {
    mockPatch.mockResolvedValue({ data: { ...product, is_active: false } });

    await setProductActive("p1", false);

    expect(mockPatch).toHaveBeenCalledWith("/products/p1", {
      is_active: false,
    });
  });
});

describe("getEquipments", () => {
  it("calls GET /products/:id/equipments with no extra params", async () => {
    mockGet.mockResolvedValue({
      data: { items: [equipment], total: 1, limit: 20, offset: 0 },
    });

    const result = await getEquipments("p1");

    expect(mockGet).toHaveBeenCalledWith("/products/p1/equipments?");
    expect(result.items).toHaveLength(1);
  });

  it("appends is_active param", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getEquipments("p1", { is_active: true });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("is_active=true");
  });

  // O filtro de órfãos precisa viajar até o servidor: a listagem é paginada,
  // então peneirar no navegador só olharia a página aberta.
  it("manda without_owner quando o filtro de órfãos está ligado", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getEquipments("p1", { without_owner: true });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("without_owner=true");
  });

  it("omite without_owner quando o filtro está desligado", async () => {
    // Mandar `without_owner=false` funcionaria, mas sujaria a URL de toda
    // listagem normal — e a diferença some nos logs de acesso.
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getEquipments("p1", { without_owner: false });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).not.toContain("without_owner");
  });

  it("soma without_owner aos outros filtros", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getEquipments("p1", { without_owner: true, search: "titan", is_active: true });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("without_owner=true");
    expect(url).toContain("search=titan");
    expect(url).toContain("is_active=true");
  });
});

describe("createEquipment", () => {
  it("posts to /products/:id/equipments", async () => {
    mockPost.mockResolvedValue({ data: equipment });

    const result = await createEquipment("p1", {
      name: "Servidor A",
      serial_number: "SN-001",
    });

    expect(mockPost).toHaveBeenCalledWith("/products/p1/equipments", {
      name: "Servidor A",
      serial_number: "SN-001",
    });
    expect(result.id).toBe("e1");
  });
});

describe("updateEquipment", () => {
  it("patches /equipments/:id", async () => {
    mockPatch.mockResolvedValue({ data: { ...equipment, name: "Servidor B" } });

    const result = await updateEquipment("e1", { name: "Servidor B" });

    expect(mockPatch).toHaveBeenCalledWith("/equipments/e1", {
      name: "Servidor B",
    });
    expect(result.name).toBe("Servidor B");
  });
});

describe("setEquipmentActive", () => {
  it("patches /equipments/:id with is_active flag", async () => {
    mockPatch.mockResolvedValue({ data: { ...equipment, is_active: false } });

    await setEquipmentActive("e1", false);

    expect(mockPatch).toHaveBeenCalledWith("/equipments/e1", {
      is_active: false,
    });
  });
});


// ── owner_id no payload de equipamento ────────────────────────
//
// O backend aceita owner_id nos endpoints de staff desde 51a9cb8, mas o
// service omitia o campo — então equipamento criado pela tela de Produtos
// nascia órfão e a coluna de dono ficava em "—" sem como preencher.

describe("createEquipment — dono", () => {
  it("envia o owner_id quando um dono é escolhido", async () => {
    mockPost.mockResolvedValue({ data: { ...equipment, owner_id: "u1" } });

    await createEquipment("p1", { name: "Servidor A", owner_id: "u1" });

    expect(mockPost).toHaveBeenCalledWith("/products/p1/equipments", {
      name: "Servidor A",
      owner_id: "u1",
    });
  });

  it("sem dono escolhido, não inventa o campo", async () => {
    mockPost.mockResolvedValue({ data: equipment });

    await createEquipment("p1", { name: "Servidor A" });

    expect(mockPost).toHaveBeenCalledWith("/products/p1/equipments", {
      name: "Servidor A",
    });
  });
});

describe("updateEquipment — dono", () => {
  it("envia o owner_id na edição — é como se conserta um equipamento órfão", async () => {
    mockPatch.mockResolvedValue({ data: { ...equipment, owner_id: "u1" } });

    await updateEquipment("e1", { owner_id: "u1" });

    expect(mockPatch).toHaveBeenCalledWith("/equipments/e1", { owner_id: "u1" });
  });

  it("owner_id nulo desvincula de propósito, e precisa chegar ao servidor", async () => {
    // `null` explícito é diferente de campo ausente: um desvincula, o outro
    // deixa como está. Um `if (owner_id)` no meio do caminho comeria o null.
    mockPatch.mockResolvedValue({ data: { ...equipment, owner_id: null } });

    await updateEquipment("e1", { owner_id: null });

    expect(mockPatch).toHaveBeenCalledWith("/equipments/e1", { owner_id: null });
  });
});

describe("listAllEquipments", () => {
  it("chama GET /equipments, sem produto no caminho", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await listAllEquipments();

    expect(mockGet).toHaveBeenCalledWith("/equipments?");
  });

  it("manda busca, filtros e página como parâmetros", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await listAllEquipments({
      search: "maria",
      product_id: "p1",
      is_active: false,
      company_id: "c1",
      without_owner: true,
      limit: 20,
      offset: 40,
    });

    const params = new URL(`http://x${mockGet.mock.calls[0][0] as string}`).searchParams;
    expect(Object.fromEntries(params)).toEqual({
      search: "maria",
      product_id: "p1",
      is_active: "false",
      company_id: "c1",
      without_owner: "true",
      limit: "20",
      offset: "40",
    });
  });

  it("sem responsável desligado não vai na URL", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await listAllEquipments({ without_owner: false });

    expect(mockGet.mock.calls[0][0]).not.toContain("without_owner");
  });
});

describe("ECE-01 — empresa do equipamento no serviço", () => {
  it("without_company ligado vai na URL; desligado, não", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await listAllEquipments({ without_company: true });
    await listAllEquipments({ without_company: false });

    expect(mockGet.mock.calls[0][0]).toBe("/equipments?without_company=true");
    expect(mockGet.mock.calls[1][0]).toBe("/equipments?");
  });

  it("os três estados de company_id atravessam o serviço sem serem trocados", async () => {
    mockPatch.mockResolvedValue({ data: {} });

    await updateEquipment("e1", { name: "A" });
    await updateEquipment("e1", { name: "A", company_id: "c1" });
    await updateEquipment("e1", { name: "A", company_id: null });

    const corpos = mockPatch.mock.calls.map((c) => JSON.parse(JSON.stringify(c[1])));
    expect(corpos[0]).not.toHaveProperty("company_id");
    expect(corpos[1]).toHaveProperty("company_id", "c1");
    expect(corpos[2]).toHaveProperty("company_id", null);
  });

  it("no cadastro, company_id omitido não aparece no corpo", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await createEquipment("p1", { name: "A" });
    await createEquipment("p1", { name: "A", company_id: null });

    expect(JSON.parse(JSON.stringify(mockPost.mock.calls[0][1]))).not.toHaveProperty("company_id");
    expect(JSON.parse(JSON.stringify(mockPost.mock.calls[1][1]))).toHaveProperty("company_id", null);
  });
});
