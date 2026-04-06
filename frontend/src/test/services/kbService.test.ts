import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getKBArticles,
  getKBArticle,
  createKBArticle,
  updateKBArticle,
  deleteKBArticle,
  submitKBFeedback,
  suggestArticlesForTicket,
} from "../../services/kbService";
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

const article = {
  id: "a1",
  title: "Como resetar senha",
  content: "Passo a passo...",
  slug: "como-resetar-senha",
  category: "access",
  tags: ["senha", "acesso"],
  status: "published",
  author_id: "u1",
  author_name: "Admin",
  view_count: 10,
  helpful: 5,
  not_helpful: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getKBArticles", () => {
  it("calls GET /kb/articles with no filters", async () => {
    mockGet.mockResolvedValue({
      data: { items: [article], total: 1, limit: 20, offset: 0 },
    });

    const result = await getKBArticles();

    expect(mockGet).toHaveBeenCalledWith("/kb/articles?");
    expect(result.items).toHaveLength(1);
  });

  it("appends search, category and status filters", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
    });

    await getKBArticles({
      search: "senha",
      category: "access",
      status: "published",
    });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("search=senha");
    expect(url).toContain("category=access");
    expect(url).toContain("status=published");
  });
});

describe("getKBArticle", () => {
  it("calls GET /kb/articles/:id", async () => {
    mockGet.mockResolvedValue({ data: article });

    const result = await getKBArticle("a1");

    expect(mockGet).toHaveBeenCalledWith("/kb/articles/a1");
    expect(result.id).toBe("a1");
  });
});

describe("createKBArticle", () => {
  it("posts to /kb/articles and returns the article", async () => {
    mockPost.mockResolvedValue({ data: article });

    const result = await createKBArticle({
      title: "Como resetar senha",
      content: "Passo a passo...",
      category: "access",
      tags: ["senha"],
      status: "published",
    });

    expect(mockPost).toHaveBeenCalledWith(
      "/kb/articles",
      expect.objectContaining({
        title: "Como resetar senha",
        status: "published",
      }),
    );
    expect(result.slug).toBe("como-resetar-senha");
  });
});

describe("updateKBArticle", () => {
  it("patches /kb/articles/:id with the payload", async () => {
    mockPatch.mockResolvedValue({ data: { ...article, title: "Novo título" } });

    const result = await updateKBArticle("a1", { title: "Novo título" });

    expect(mockPatch).toHaveBeenCalledWith("/kb/articles/a1", {
      title: "Novo título",
    });
    expect(result.title).toBe("Novo título");
  });
});

describe("deleteKBArticle", () => {
  it("calls DELETE /kb/articles/:id", async () => {
    mockDelete.mockResolvedValue({});

    await deleteKBArticle("a1");

    expect(mockDelete).toHaveBeenCalledWith("/kb/articles/a1");
  });
});

describe("submitKBFeedback", () => {
  it("posts helpful=true to /kb/articles/:id/feedback", async () => {
    mockPost.mockResolvedValue({});

    await submitKBFeedback("a1", true);

    expect(mockPost).toHaveBeenCalledWith("/kb/articles/a1/feedback", {
      helpful: true,
    });
  });

  it("posts helpful=false for negative feedback", async () => {
    mockPost.mockResolvedValue({});

    await submitKBFeedback("a1", false);

    expect(mockPost).toHaveBeenCalledWith("/kb/articles/a1/feedback", {
      helpful: false,
    });
  });
});

describe("suggestArticlesForTicket", () => {
  it("calls GET /kb/articles/suggestions with ticket_id and default limit", async () => {
    mockGet.mockResolvedValue({
      data: { items: [article], total: 1, limit: 5, offset: 0 },
    });

    const result = await suggestArticlesForTicket("t1");

    expect(mockGet).toHaveBeenCalledWith(
      "/kb/articles/suggestions?ticket_id=t1&limit=5",
    );
    expect(result).toHaveLength(1);
  });

  it("accepts a custom limit", async () => {
    mockGet.mockResolvedValue({
      data: { items: [], total: 0, limit: 3, offset: 0 },
    });

    await suggestArticlesForTicket("t1", 3);

    expect(mockGet).toHaveBeenCalledWith(
      "/kb/articles/suggestions?ticket_id=t1&limit=3",
    );
  });
});
