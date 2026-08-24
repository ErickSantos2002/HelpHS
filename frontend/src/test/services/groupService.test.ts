import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getCompanySuggestions,
  createCompanyFromSuggestion,
  type CompanySuggestion,
} from "../../services/groupService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);

beforeEach(() => {
  vi.clearAllMocks();
});

const sugestao: CompanySuggestion = {
  company_name: "Acme",
  cnpj: "11222333000181",
  city: "Recife",
  state: "PE",
  address: "Rua A, 10",
  client_count: 2,
  clients: [
    { id: "u1", name: "Um", email: "um@x.com", phone: null, client_notes: null },
    { id: "u2", name: "Dois", email: "dois@x.com", phone: null, client_notes: null },
  ],
};

describe("getCompanySuggestions", () => {
  it("traz os clientes de cada sugestão, para o admin conferir antes de vincular", async () => {
    mockGet.mockResolvedValueOnce({ data: [sugestao] });

    const resultado = await getCompanySuggestions();

    expect(mockGet).toHaveBeenCalledWith("/companies/suggestions");
    expect(resultado[0].clients.map((c) => c.name)).toEqual(["Um", "Dois"]);
  });
});

describe("createCompanyFromSuggestion", () => {
  it("envia os ids que a tela mostrou, não a sugestão inteira", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        company: { id: "c1", name: "Acme" },
        company_created: true,
        linked_clients: sugestao.clients,
      },
    });

    await createCompanyFromSuggestion("g1", sugestao, ["u1", "u2"]);

    expect(mockPost).toHaveBeenCalledWith("/groups/g1/companies/from-suggestion", {
      name: "Acme",
      cnpj: "11222333000181",
      address: "Rua A, 10",
      city: "Recife",
      state: "PE",
      client_ids: ["u1", "u2"],
    });
  });

  it("omite o CNPJ quando a sugestão não tem", async () => {
    mockPost.mockResolvedValueOnce({
      data: { company: { id: "c1" }, company_created: true, linked_clients: [] },
    });

    await createCompanyFromSuggestion("g1", { ...sugestao, cnpj: null }, ["u1"]);

    expect(mockPost.mock.calls[0][1]).not.toHaveProperty("cnpj");
  });

  it("devolve se a empresa foi criada ou reaproveitada", async () => {
    mockPost.mockResolvedValueOnce({
      data: { company: { id: "c1" }, company_created: false, linked_clients: [] },
    });

    const resultado = await createCompanyFromSuggestion("g1", sugestao, ["u1"]);

    expect(resultado.company_created).toBe(false);
  });
});
