import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getSLAConfigs,
  updateSLAConfig,
  type SLAConfig,
} from "../../services/slaService";
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
const mockPost = vi.mocked(api.post);
const mockPut = vi.mocked(api.put);
const mockPatch = vi.mocked(api.patch);

const critico: SLAConfig = {
  id: "sla-critico",
  level: "critical",
  response_time_hours: 1,
  resolve_time_hours: 4,
  warning_threshold: 0.8,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const baixo: SLAConfig = {
  ...critico,
  id: "sla-baixo",
  level: "low",
  response_time_hours: 24,
  resolve_time_hours: 72,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getSLAConfigs", () => {
  it("busca em /sla-configs sem query string", async () => {
    mockGet.mockResolvedValue({ data: [critico, baixo] });

    await getSLAConfigs();

    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith("/sla-configs");
  });

  it("devolve a lista do corpo da resposta, não a resposta inteira", async () => {
    mockGet.mockResolvedValue({ data: [critico, baixo] });

    const result = await getSLAConfigs();

    expect(Array.isArray(result)).toBe(true);
    expect(result.map((c) => c.level)).toEqual(["critical", "low"]);
    expect(result[0].response_time_hours).toBe(1);
  });

  it("devolve lista vazia quando o servidor não tem nenhuma config", async () => {
    mockGet.mockResolvedValue({ data: [] });

    const result = await getSLAConfigs();

    expect(result).toEqual([]);
  });

  it("propaga o erro da requisição em vez de engolir num array vazio", async () => {
    mockGet.mockRejectedValue(new Error("500 no servidor"));

    await expect(getSLAConfigs()).rejects.toThrow("500 no servidor");
  });
});

describe("updateSLAConfig", () => {
  it("envia PATCH para /sla-configs/<id> com o payload recebido", async () => {
    mockPatch.mockResolvedValue({ data: critico });

    await updateSLAConfig("sla-critico", {
      response_time_hours: 2,
      resolve_time_hours: 8,
    });

    expect(mockPatch).toHaveBeenCalledTimes(1);
    expect(mockPatch).toHaveBeenCalledWith("/sla-configs/sla-critico", {
      response_time_hours: 2,
      resolve_time_hours: 8,
    });
    // A rota é de edição parcial: um PUT/POST aqui trocaria o contrato.
    expect(mockPut).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("monta a URL com o id informado, e não com um id fixo", async () => {
    mockPatch.mockResolvedValue({ data: baixo });

    await updateSLAConfig("sla-baixo", { resolve_time_hours: 96 });

    expect(mockPatch.mock.calls[0][0]).toBe("/sla-configs/sla-baixo");
  });

  it("envia só os campos informados, sem completar os que faltam", async () => {
    mockPatch.mockResolvedValue({ data: critico });

    await updateSLAConfig("sla-critico", { warning_threshold: 0.5 });

    expect(mockPatch.mock.calls[0][1]).toEqual({ warning_threshold: 0.5 });
  });

  it("preserva valores falsos como is_active false e limiar zero", async () => {
    mockPatch.mockResolvedValue({ data: { ...critico, is_active: false } });

    await updateSLAConfig("sla-critico", {
      is_active: false,
      warning_threshold: 0,
    });

    expect(mockPatch).toHaveBeenCalledWith("/sla-configs/sla-critico", {
      is_active: false,
      warning_threshold: 0,
    });
  });

  it("devolve a config atualizada que veio do servidor", async () => {
    const atualizada: SLAConfig = {
      ...critico,
      response_time_hours: 2,
      updated_at: "2026-02-01T00:00:00Z",
    };
    mockPatch.mockResolvedValue({ data: atualizada });

    const result = await updateSLAConfig("sla-critico", {
      response_time_hours: 2,
    });

    expect(result.response_time_hours).toBe(2);
    expect(result.updated_at).toBe("2026-02-01T00:00:00Z");
  });

  it("propaga o erro quando a edição é recusada", async () => {
    mockPatch.mockRejectedValue(new Error("403 sem permissão"));

    await expect(
      updateSLAConfig("sla-critico", { is_active: false }),
    ).rejects.toThrow("403 sem permissão");
  });
});
