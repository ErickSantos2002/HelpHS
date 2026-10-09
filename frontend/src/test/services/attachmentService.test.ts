import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  canPreview,
  getAttachmentUrl,
  uploadAttachments,
} from "../../services/attachmentService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);

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

/**
 * Contrato do upload, prendido ANTES da extração do `FileUpload`.
 *
 * Existe para uma coisa: garantir que refatorar a interface não mexa no que vai
 * para a rede. O nome do campo, o endpoint e o cabeçalho são combinados com o
 * backend — `attachments.py` lê `files` (plural), e um `file` singular chegaria
 * como corpo vazio, sem erro de compilação e sem teste vermelho.
 *
 * O mesmo payload roda antes e depois da extração.
 */
describe("uploadAttachments — contrato com o backend", () => {
  function arquivo(nome: string, bytes = 10): File {
    return new File([new Uint8Array(bytes)], nome, { type: "application/pdf" });
  }

  it("manda para /tickets/{id}/attachments", async () => {
    mockPost.mockResolvedValue({ data: [] });
    await uploadAttachments("t-1", [arquivo("laudo.pdf")]);
    expect(mockPost).toHaveBeenCalledWith(
      "/tickets/t-1/attachments",
      expect.any(FormData),
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  });

  it("o campo do FormData é `files`, no plural, um por arquivo", async () => {
    mockPost.mockResolvedValue({ data: [] });
    await uploadAttachments("t-1", [arquivo("a.pdf"), arquivo("b.pdf")]);

    const form = mockPost.mock.calls[0][1] as FormData;
    const enviados = form.getAll("files");
    expect(enviados).toHaveLength(2);
    expect((enviados[0] as File).name).toBe("a.pdf");
    expect((enviados[1] as File).name).toBe("b.pdf");

    // E nada sob `file` singular, que é o campo do upload de avatar — outro
    // endpoint, outro contrato. Trocar um pelo outro não quebra o build.
    expect(form.getAll("file")).toHaveLength(0);
  });

  it("devolve os anexos que o backend gravou", async () => {
    const gravado = {
      id: "a-1",
      ticket_id: "t-1",
      original_name: "laudo.pdf",
      virus_scanned: true,
      virus_clean: true,
    };
    mockPost.mockResolvedValue({ data: [gravado] });
    await expect(uploadAttachments("t-1", [arquivo("laudo.pdf")])).resolves.toEqual([
      gravado,
    ]);
  });

  it("deixa o erro subir, com o motivo que o backend deu", async () => {
    // O antivírus rejeita ANTES de persistir: um arquivo infectado nunca vira
    // linha, volta como 422 com `detail: "File 'X' rejected: Virus: …"`. Quem
    // mostra o motivo é o `toastApiError` da tela; o serviço não pode engolir.
    const erro = Object.assign(new Error("Request failed"), {
      response: {
        status: 422,
        data: { detail: "File 'evil.pdf' rejected: Virus: Eicar-Test-Signature" },
      },
    });
    mockPost.mockRejectedValue(erro);
    await expect(uploadAttachments("t-1", [arquivo("evil.pdf")])).rejects.toBe(erro);
  });
});
