import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  listQuickReplies,
  createQuickReply,
  updateQuickReply,
  deleteQuickReply,
  matchQuickReplies,
  type QuickReply,
} from "../../services/quickReplyService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);
const mockDelete = vi.mocked(api.delete);

const reply: QuickReply = {
  id: "q1",
  shortcut: "bomdia",
  title: "Saudação inicial",
  content: "Bom dia! Sou Gabriel Moura, da equipe de suporte da H&S.",
  is_active: true,
  created_by: "u1",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listQuickReplies", () => {
  it("busca em /quick-replies e devolve os itens", async () => {
    mockGet.mockResolvedValue({ data: { items: [reply], total: 1 } });

    const result = await listQuickReplies();

    expect(mockGet).toHaveBeenCalledWith("/quick-replies");
    expect(result).toHaveLength(1);
    expect(result[0].shortcut).toBe("bomdia");
  });
});

describe("createQuickReply", () => {
  it("envia POST com o payload", async () => {
    mockPost.mockResolvedValue({ data: reply });

    await createQuickReply({
      shortcut: "bomdia",
      title: "Saudação inicial",
      content: "Bom dia!",
    });

    expect(mockPost).toHaveBeenCalledWith("/quick-replies", {
      shortcut: "bomdia",
      title: "Saudação inicial",
      content: "Bom dia!",
    });
  });
});

describe("updateQuickReply", () => {
  it("envia PATCH para o id informado", async () => {
    mockPatch.mockResolvedValue({ data: reply });

    await updateQuickReply("q1", { content: "Bom dia! Tudo bem?" });

    expect(mockPatch).toHaveBeenCalledWith("/quick-replies/q1", {
      content: "Bom dia! Tudo bem?",
    });
  });
});

describe("deleteQuickReply", () => {
  it("envia DELETE para o id informado", async () => {
    mockDelete.mockResolvedValue({ data: null });

    await deleteQuickReply("q1");

    expect(mockDelete).toHaveBeenCalledWith("/quick-replies/q1");
  });
});

describe("matchQuickReplies", () => {
  const outra: QuickReply = { ...reply, id: "q2", shortcut: "endereco", title: "Endereço da empresa" };
  const inativa: QuickReply = { ...reply, id: "q3", shortcut: "antiga", is_active: false };
  const todas = [reply, outra, inativa];

  it("devolve todas as ativas quando só a barra foi digitada", () => {
    const result = matchQuickReplies(todas, "");
    expect(result.map((r) => r.id)).toEqual(["q1", "q2"]);
  });

  it("filtra pelo atalho", () => {
    expect(matchQuickReplies(todas, "bom").map((r) => r.id)).toEqual(["q1"]);
  });

  it("filtra pelo título", () => {
    expect(matchQuickReplies(todas, "endere").map((r) => r.id)).toEqual(["q2"]);
  });

  it("ignora acento e maiúscula na busca", () => {
    expect(matchQuickReplies(todas, "ENDEREÇO").map((r) => r.id)).toEqual(["q2"]);
  });

  it("nunca devolve resposta inativa", () => {
    expect(matchQuickReplies(todas, "antiga")).toHaveLength(0);
  });

  it("devolve vazio quando nada casa", () => {
    expect(matchQuickReplies(todas, "xyz")).toHaveLength(0);
  });
});
