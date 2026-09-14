import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  deleteLibraryFile,
  getLibraryFileUrl,
  getLibraryFiles,
  updateLibraryFile,
  uploadLibraryFile,
} from "../../services/libraryService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);
const mockPut = vi.mocked(api.put);
const mockDelete = vi.mocked(api.delete);

beforeEach(() => {
  vi.clearAllMocks();
});

function arquivo(nome = "manual.pdf", bytes = 10): File {
  return new File([new Uint8Array(bytes)], nome, { type: "application/pdf" });
}

describe("getLibraryFiles", () => {
  it("sem filtro nenhum, não inventa parâmetro", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await getLibraryFiles();

    expect(mockGet.mock.calls[0][0]).toBe("/library?");
  });

  it("leva busca, produto, visibilidade e a janela", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await getLibraryFiles({
      search: "phoebus",
      product_id: "p-1",
      visibility: "client",
      limit: 20,
      offset: 40,
    });

    const url = mockGet.mock.calls[0][0] as string;
    expect(url).toContain("search=phoebus");
    expect(url).toContain("product_id=p-1");
    expect(url).toContain("visibility=client");
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=40");
  });

  /*
    `offset=0` é a primeira página, e `0` é falso em JavaScript.

    A guarda é `!== undefined` e não truthiness de propósito: com `if (offset)`
    a primeira página sairia sem o parâmetro. Aqui isso não muda nada — o
    backend também assume 0 —, mas o mesmo erro no `limit` mandaria o servidor
    devolver o default dele em vez do tamanho de página da tela, e a paginação
    passaria a contar sobre um número diferente do que recebeu.
  */
  it("manda offset=0 em vez de omitir na primeira página", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await getLibraryFiles({ offset: 0, limit: 20 });

    expect(mockGet.mock.calls[0][0]).toContain("offset=0");
  });

  it("busca vazia não vira search= vazio", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0, limit: 20, offset: 0 } });

    await getLibraryFiles({ search: "" });

    expect(mockGet.mock.calls[0][0]).not.toContain("search=");
  });
});

/**
 * Contrato do envio.
 *
 * O nome do campo é combinado com o backend e **não** é o mesmo do anexo de
 * chamado: `library.py` declara `file: UploadFile` no singular, enquanto
 * `attachments.py` lê `files` no plural. Trocar um pelo outro não quebra
 * compilação, não quebra tipo e não quebra teste de tela — só falha em
 * produção, na primeira vez que alguém tentar enviar.
 */
describe("uploadLibraryFile — contrato com o backend", () => {
  it("manda multipart para /library", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await uploadLibraryFile({
      file: arquivo(),
      title: "Manual do Phoebus",
      visibility: "internal",
    });

    expect(mockPost).toHaveBeenCalledWith("/library", expect.any(FormData), {
      headers: { "Content-Type": "multipart/form-data" },
    });
  });

  it("o campo do arquivo é `file`, no singular", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await uploadLibraryFile({
      file: arquivo("manual.pdf"),
      title: "Manual",
      visibility: "internal",
    });

    const form = mockPost.mock.calls[0][1] as FormData;
    const enviados = form.getAll("file");
    expect(enviados).toHaveLength(1);
    expect((enviados[0] as File).name).toBe("manual.pdf");

    // E nada sob `files`, que é o contrato do anexo de chamado — outro
    // endpoint, outro campo.
    expect(form.getAll("files")).toHaveLength(0);
  });

  /*
    A visibilidade sai na requisição mesmo quando é a mais restritiva.

    Este é o teste que pega a "otimização" de só mandar quando for `client`:
    ela funcionaria hoje, porque o default da coluna é `internal` — e deixaria
    a escolha do administrador ser transmitida por AUSÊNCIA. No dia em que o
    default do banco mudasse, a tela continuaria calando e o significado do
    silêncio teria virado outro, sem nada vermelho no caminho.
  */
  it("manda `visibility=internal` explicitamente, sem contar com o default do banco", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await uploadLibraryFile({ file: arquivo(), title: "Manual", visibility: "internal" });

    const form = mockPost.mock.calls[0][1] as FormData;
    expect(form.get("visibility")).toBe("internal");
  });

  it("manda `visibility=client` quando o administrador abre para o cliente", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await uploadLibraryFile({ file: arquivo(), title: "Guia", visibility: "client" });

    const form = mockPost.mock.calls[0][1] as FormData;
    expect(form.get("visibility")).toBe("client");
  });

  /*
    Campo em branco SOME da requisição, não vai vazio.

    `product_id: ""` chegaria ao servidor como string vazia, que não é UUID:
    422 para um campo que a pessoa simplesmente não preencheu. E `description`
    em branco gravaria `""` onde o banco espera `NULL` — a diferença entre "não
    tem descrição" e "tem uma, vazia".
  */
  it("não manda produto nem descrição quando ficaram em branco", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await uploadLibraryFile({
      file: arquivo(),
      title: "Manual",
      description: "",
      product_id: "",
      visibility: "internal",
    });

    const form = mockPost.mock.calls[0][1] as FormData;
    expect(form.has("product_id")).toBe(false);
    expect(form.has("description")).toBe(false);
  });

  it("manda produto e descrição quando foram preenchidos", async () => {
    mockPost.mockResolvedValue({ data: {} });

    await uploadLibraryFile({
      file: arquivo(),
      title: "Manual",
      description: "Versão 3 do manual de campo.",
      product_id: "p-1",
      visibility: "internal",
    });

    const form = mockPost.mock.calls[0][1] as FormData;
    expect(form.get("product_id")).toBe("p-1");
    expect(form.get("description")).toBe("Versão 3 do manual de campo.");
  });

  it("devolve o item que o backend gravou", async () => {
    const gravado = { id: "l-1", title: "Manual", visibility: "internal" };
    mockPost.mockResolvedValue({ data: gravado });

    await expect(
      uploadLibraryFile({ file: arquivo(), title: "Manual", visibility: "internal" }),
    ).resolves.toEqual(gravado);
  });

  it("não engole o erro do servidor", async () => {
    mockPost.mockRejectedValue(new Error("422"));

    await expect(
      uploadLibraryFile({ file: arquivo(), title: "Manual", visibility: "internal" }),
    ).rejects.toThrow("422");
  });
});

describe("updateLibraryFile", () => {
  it("é PATCH, e não PUT: manda só o que mudou", async () => {
    mockPatch.mockResolvedValue({ data: {} });

    await updateLibraryFile("l-1", { visibility: "client" });

    expect(mockPatch).toHaveBeenCalledWith("/library/l-1", { visibility: "client" });
    // PUT substituiria o item inteiro, apagando título e descrição que não
    // foram mandados.
    expect(mockPut).not.toHaveBeenCalled();
  });

  it("aceita desvincular o produto mandando null", async () => {
    mockPatch.mockResolvedValue({ data: {} });

    await updateLibraryFile("l-1", { product_id: null });

    expect(mockPatch).toHaveBeenCalledWith("/library/l-1", { product_id: null });
  });
});

describe("deleteLibraryFile", () => {
  it("chama DELETE no item", async () => {
    mockDelete.mockResolvedValue({ data: undefined });

    await deleteLibraryFile("l-1");

    expect(mockDelete).toHaveBeenCalledWith("/library/l-1");
  });
});

/**
 * O link de download é pedido, não montado.
 *
 * A tela nunca constrói o endereço do arquivo: ela pede, e o servidor confere a
 * visibilidade ANTES de emitir. Um link já emitido não volta atrás — montar na
 * tela faria a regra depender de quem não a executa.
 */
describe("getLibraryFileUrl", () => {
  it("pede o link em /library/{id}/download", async () => {
    mockGet.mockResolvedValue({ data: { url: "/api/v1/files/tok?filename=Manual.pdf" } });

    await getLibraryFileUrl("l-1");

    expect(mockGet).toHaveBeenCalledWith("/library/l-1/download");
  });

  it("preserva o nome original que o backend anexou ao link", async () => {
    mockGet.mockResolvedValue({
      data: { url: "/api/v1/files/tok?filename=Manual%20do%20Phoebus.pdf" },
    });

    const url = await getLibraryFileUrl("l-1");

    // Sem isto o usuário baixaria "a1b2c3.pdf": em disco o arquivo tem nome
    // interno, e o nome de verdade viaja no parâmetro.
    expect(url).toContain("filename=Manual%20do%20Phoebus.pdf");
  });

  it("deixa o 404 do item interno subir para a tela", async () => {
    mockGet.mockRejectedValue(new Error("404"));

    await expect(getLibraryFileUrl("l-1")).rejects.toThrow("404");
  });
});
