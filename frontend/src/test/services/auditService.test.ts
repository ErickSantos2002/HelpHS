import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getAuditLogs,
  type AuditLog,
  type AuditLogListResponse,
} from "../../services/auditService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);

const log: AuditLog = {
  id: "a1",
  user_id: "u1",
  user_name: "Rickelme David",
  action: "status_change",
  entity_type: "ticket",
  entity_id: "t1",
  old_data: { status: "open" },
  new_data: { status: "resolved" },
  ip_address: "10.0.0.1",
  user_agent: "Mozilla/5.0",
  created_at: "2026-09-01T12:00:00Z",
};

const pagina: AuditLogListResponse = {
  items: [log],
  total: 1,
  limit: 50,
  offset: 0,
};

// Lê o objeto `params` que o service entregou ao axios. As chaves presentes
// importam tanto quanto os valores: `toHaveBeenCalledWith` considera uma chave
// de valor `undefined` igual a chave ausente, e aqui a diferença é o teste.
function paramsDaChamada(n = 0): Record<string, unknown> {
  const config = mockGet.mock.calls[n][1] as
    | { params?: Record<string, unknown> }
    | undefined;
  return config?.params ?? {};
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getAuditLogs", () => {
  it("busca em /audit-logs sem nenhum parâmetro quando não há filtro", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getAuditLogs();

    expect(mockGet).toHaveBeenCalledWith("/audit-logs", { params: {} });
    expect(Object.keys(paramsDaChamada())).toEqual([]);
  });

  it("devolve o corpo da resposta sem transformar", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    const result = await getAuditLogs();

    expect(result).toEqual(pagina);
    expect(result.items[0].action).toBe("status_change");
    expect(result.items[0].old_data).toEqual({ status: "open" });
  });

  it("envia todos os filtros preenchidos como params", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getAuditLogs({
      action: "delete",
      entity_type: "user",
      user_id: "u9",
      date_from: "2026-08-01",
      date_to: "2026-08-31",
      offset: 100,
      limit: 25,
    });

    expect(mockGet).toHaveBeenCalledWith("/audit-logs", {
      params: {
        action: "delete",
        entity_type: "user",
        user_id: "u9",
        date_from: "2026-08-01",
        date_to: "2026-08-31",
        offset: 100,
        limit: 25,
      },
    });
    // Paginação vai como número, não como texto.
    expect(paramsDaChamada().limit).toBe(25);
  });

  it("não cria chave para o filtro que ficou de fora", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getAuditLogs({ action: "login" });

    expect(Object.keys(paramsDaChamada())).toEqual(["action"]);
  });

  it("descarta filtro de texto vazio em vez de mandar chave vazia", async () => {
    mockGet.mockResolvedValue({ data: pagina });

    await getAuditLogs({
      action: "",
      entity_type: "",
      user_id: "",
      date_from: "",
      date_to: "",
      limit: 10,
    });

    expect(Object.keys(paramsDaChamada())).toEqual(["limit"]);
  });

  it("mantém offset e limit iguais a zero, porque 0 não é ausência", async () => {
    mockGet.mockResolvedValue({ data: { ...pagina, items: [], total: 0 } });

    await getAuditLogs({ offset: 0, limit: 0 });

    expect(paramsDaChamada()).toEqual({ offset: 0, limit: 0 });
  });

  it("aceita a página vazia devolvida pelo servidor", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 50, offset: 200 },
    });

    const result = await getAuditLogs({ action: "anonymize", offset: 200 });

    expect(result.items).toEqual([]);
    expect(result.total).toBe(0);
    expect(result.offset).toBe(200);
  });

  it("preserva os campos nulos do registro (ação sem usuário)", async () => {
    const semAutor: AuditLog = {
      ...log,
      user_id: null,
      user_name: null,
      entity_id: null,
      old_data: null,
      new_data: null,
      ip_address: null,
      user_agent: null,
    };
    mockGet.mockResolvedValue({ data: { ...pagina, items: [semAutor] } });

    const result = await getAuditLogs();

    expect(result.items[0].user_id).toBeNull();
    expect(result.items[0].user_name).toBeNull();
    expect(result.items[0].old_data).toBeNull();
    expect(result.items[0].ip_address).toBeNull();
  });

  it("propaga o erro do servidor em vez de engolir", async () => {
    mockGet.mockRejectedValue(new Error("403 Forbidden"));

    await expect(getAuditLogs({ action: "export" })).rejects.toThrow(
      "403 Forbidden",
    );
    expect(mockGet).toHaveBeenCalledTimes(1);
  });
});
