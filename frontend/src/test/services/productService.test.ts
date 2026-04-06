import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getProducts,
  createProduct,
  updateProduct,
  setProductActive,
  getEquipments,
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
