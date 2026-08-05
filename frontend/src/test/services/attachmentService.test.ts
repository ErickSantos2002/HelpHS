import { describe, it, expect, vi, beforeEach } from "vitest";
import { canPreview, getAttachmentUrl } from "../../services/attachmentService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockGet = vi.mocked(api.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("canPreview", () => {
  it("abre imagem, PDF e texto no navegador", () => {
    expect(canPreview("laudo.pdf")).toBe(true);
    expect(canPreview("print.PNG")).toBe(true);
    expect(canPreview("erro.txt")).toBe(true);
  });

  it("não tenta abrir o que o navegador não renderiza", () => {
    expect(canPreview("planilha.xlsx")).toBe(false);
    expect(canPreview("pacote.zip")).toBe(false);
    expect(canPreview("documento.docx")).toBe(false);
  });

  it("não oferece visualização para formato que o backend recusa servir inline", () => {
    // SVG e HTML descem como download por segurança
    expect(canPreview("icone.svg")).toBe(false);
    expect(canPreview("pagina.html")).toBe(false);
  });

  it("lida com arquivo sem extensão", () => {
    expect(canPreview("arquivo")).toBe(false);
  });
});

describe("getAttachmentUrl", () => {
  it("devolve o link de visualização por padrão", async () => {
    mockGet.mockResolvedValue({ data: { url: "/api/v1/files/tok?filename=laudo.pdf" } });

    const url = await getAttachmentUrl("a1");

    expect(url).not.toContain("download=true");
  });

  it("acrescenta download=true quando pedido", async () => {
    mockGet.mockResolvedValue({ data: { url: "/api/v1/files/tok?filename=laudo.pdf" } });

    const url = await getAttachmentUrl("a1", { download: true });

    expect(url).toContain("download=true");
  });
});
