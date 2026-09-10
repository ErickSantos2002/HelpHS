import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getTags,
  createTag,
  updateTag,
  deleteTag,
  setTicketTags,
  type Tag,
} from "../../services/tagService";
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
const mockDelete = vi.mocked(api.delete);

const urgente: Tag = {
  id: "tag-1",
  name: "urgente",
  color: "#DC2626",
  created_by: "u1",
  created_at: "2026-08-01T00:00:00Z",
};

const hardware: Tag = {
  id: "tag-2",
  name: "hardware",
  color: "#2563EB",
  created_by: null,
  created_at: "2026-08-02T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getTags", () => {
  it("busca em /tags e devolve só os itens, sem o envelope", async () => {
    mockGet.mockResolvedValue({
      data: { items: [urgente, hardware], total: 2 },
    });

    const result = await getTags();

    expect(mockGet).toHaveBeenCalledWith("/tags");
    // O service descarta `total`: quem chama recebe a lista crua.
    expect(result).toEqual([urgente, hardware]);
  });

  it("devolve lista vazia quando o servidor não tem nenhuma etiqueta", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } });

    await expect(getTags()).resolves.toEqual([]);
  });

  it("aceita created_by nulo (etiqueta sem autor conhecido)", async () => {
    mockGet.mockResolvedValue({ data: { items: [hardware], total: 1 } });

    const result = await getTags();

    expect(result[0].created_by).toBeNull();
  });

  it("propaga o erro do servidor em vez de devolver lista vazia", async () => {
    mockGet.mockRejectedValue(new Error("500 Internal Server Error"));

    await expect(getTags()).rejects.toThrow("500 Internal Server Error");
  });
});

describe("createTag", () => {
  it("envia POST /tags com nome e cor e devolve a etiqueta criada", async () => {
    mockPost.mockResolvedValue({ data: urgente });

    const result = await createTag({ name: "urgente", color: "#DC2626" });

    expect(mockPost).toHaveBeenCalledWith("/tags", {
      name: "urgente",
      color: "#DC2626",
    });
    // O id vem do servidor, não do payload enviado.
    expect(result).toEqual(urgente);
    expect(result.id).toBe("tag-1");
  });

  it("propaga o erro quando o nome já existe", async () => {
    mockPost.mockRejectedValue(new Error("409 Conflict"));

    await expect(
      createTag({ name: "urgente", color: "#DC2626" }),
    ).rejects.toThrow("409 Conflict");
  });
});

describe("updateTag", () => {
  it("envia PATCH para /tags/<id> com o corpo informado", async () => {
    mockPatch.mockResolvedValue({ data: { ...urgente, name: "crítico" } });

    const result = await updateTag("tag-1", {
      name: "crítico",
      color: "#B91C1C",
    });

    expect(mockPatch).toHaveBeenCalledWith("/tags/tag-1", {
      name: "crítico",
      color: "#B91C1C",
    });
    expect(result.name).toBe("crítico");
  });

  it("manda só o campo alterado quando a atualização é parcial", async () => {
    mockPatch.mockResolvedValue({ data: { ...urgente, color: "#16A34A" } });

    await updateTag("tag-1", { color: "#16A34A" });

    // Nada de completar com `name: undefined`: o corpo sai como veio.
    expect(mockPatch).toHaveBeenCalledWith("/tags/tag-1", {
      color: "#16A34A",
    });
  });

  it("usa o id recebido na URL, não um id fixo", async () => {
    mockPatch.mockResolvedValue({ data: hardware });

    await updateTag("tag-2", { name: "hardware" });

    expect(mockPatch).toHaveBeenCalledWith("/tags/tag-2", {
      name: "hardware",
    });
  });
});

describe("deleteTag", () => {
  it("envia DELETE para /tags/<id>", async () => {
    mockDelete.mockResolvedValue({ data: null });

    await deleteTag("tag-1");

    expect(mockDelete).toHaveBeenCalledWith("/tags/tag-1");
  });

  it("resolve sem devolver corpo, mesmo que o servidor mande algo", async () => {
    mockDelete.mockResolvedValue({ data: { detail: "removida" } });

    await expect(deleteTag("tag-1")).resolves.toBeUndefined();
  });

  it("propaga o erro quando a etiqueta não existe", async () => {
    mockDelete.mockRejectedValue(new Error("404 Not Found"));

    await expect(deleteTag("nao-existe")).rejects.toThrow("404 Not Found");
  });
});

describe("setTicketTags", () => {
  it("envia PUT para /tickets/<id>/tags com os ids em tag_ids", async () => {
    mockPut.mockResolvedValue({ data: [urgente, hardware] });

    const result = await setTicketTags("t1", ["tag-1", "tag-2"]);

    // O contrato do backend é `tag_ids` (snake_case), não `tagIds`.
    expect(mockPut).toHaveBeenCalledWith("/tickets/t1/tags", {
      tag_ids: ["tag-1", "tag-2"],
    });
    expect(result).toEqual([urgente, hardware]);
  });

  it("manda lista vazia para limpar as etiquetas do chamado", async () => {
    mockPut.mockResolvedValue({ data: [] });

    const result = await setTicketTags("t1", []);

    expect(mockPut).toHaveBeenCalledWith("/tickets/t1/tags", { tag_ids: [] });
    expect(result).toEqual([]);
  });

  it("monta a URL com o id do chamado recebido", async () => {
    mockPut.mockResolvedValue({ data: [] });

    await setTicketTags("9f1c-abc", ["tag-1"]);

    expect(mockPut).toHaveBeenCalledWith("/tickets/9f1c-abc/tags", {
      tag_ids: ["tag-1"],
    });
  });

  it("devolve a lista que o servidor respondeu, não a que foi enviada", async () => {
    // O servidor é a autoridade: devolve a etiqueta inteira, não só o id.
    mockPut.mockResolvedValue({ data: [hardware] });

    const result = await setTicketTags("t1", ["tag-1", "tag-2"]);

    expect(result).toEqual([hardware]);
  });

  it("propaga o erro quando o chamado não aceita a alteração", async () => {
    mockPut.mockRejectedValue(new Error("403 Forbidden"));

    await expect(setTicketTags("t1", ["tag-1"])).rejects.toThrow(
      "403 Forbidden",
    );
  });
});
