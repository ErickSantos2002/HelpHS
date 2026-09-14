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


/**
 * O id entra no CAMINHO da URL, e caminho se codifica.
 *
 * ── O que o alerta viu, e o que ele não viu ───────────────────────────
 *
 * O CodeQL marcou `js/request-forgery` na linha do download: o id era
 * interpolado cru em `/library/${id}/download`. **Não era alcançável** — a
 * requisição sai do navegador da própria pessoa, contra a própria API, com o
 * token dela; não há deputado confuso, e a autorização de verdade é o
 * `ensure_pode_baixar` do servidor, que devolve 404 para cliente em item
 * interno. Os dois chamadores passam id vindo da própria resposta da API
 * (`LibraryPage` da listagem, `ChatPanel` da mensagem).
 *
 * Mas a FORMA é defeito de qualquer jeito, e o conserto custa uma chamada.
 * Um id com `../` reescreveria o caminho: `/library/../../users/me/download`
 * é normalizado pelo navegador para `/users/me/download`, e a requisição sai
 * para outra rota sem que nada na tela tenha mudado.
 *
 * ── Por que as TRÊS, e não só a que foi marcada ───────────────────────
 *
 * As linhas do PATCH e do DELETE têm a forma idêntica e não foram
 * sinalizadas. O que distingue a do download é o destino: o retorno dela vai
 * para `window.open()`, e o CodeQL fecha o fluxo em navegação. Consertar só a
 * marcada deixaria duas iguais no mesmo arquivo — e quem lesse depois
 * suporia que foram consideradas e aprovadas.
 *
 * As asserções são de igualdade EXATA de propósito. `toContain` passaria com
 * codificação dupla (`..%252F..`) e com o codificador errado — `encodeURI`
 * não toca em `/`, que é justo o caractere que importa aqui.
 */
describe("o id vai codificado no caminho", () => {
  const TRAVESSIA = "../../users/me";
  const CODIFICADO = "..%2F..%2Fusers%2Fme";

  it("no pedido do link de download", async () => {
    mockGet.mockResolvedValue({ data: { url: "/api/v1/files/tok" } });

    await getLibraryFileUrl(TRAVESSIA);

    expect(mockGet).toHaveBeenCalledWith(`/library/${CODIFICADO}/download`);
  });

  it("na edição", async () => {
    mockPatch.mockResolvedValue({ data: {} });

    await updateLibraryFile(TRAVESSIA, { title: "x" });

    expect(mockPatch).toHaveBeenCalledWith(`/library/${CODIFICADO}`, { title: "x" });
  });

  it("na exclusão", async () => {
    mockDelete.mockResolvedValue({ data: undefined });

    await deleteLibraryFile(TRAVESSIA);

    expect(mockDelete).toHaveBeenCalledWith(`/library/${CODIFICADO}`);
  });

  /*
    E o id de verdade atravessa intacto.

    Sem este caso, codificar duas vezes passaria despercebido: um UUID só tem
    hexadecimal e hífen, e nenhum dos dois muda na primeira passada NEM na
    segunda. O que ele prende é que o conserto não estragou o caminho comum —
    um id mutilado daria 404 em todo download do sistema.
  */
  it("e o id de verdade atravessa intacto", async () => {
    const uuid = "3f2b8c1a-7d4e-4b2f-9a13-6c5d0e8f7a21";
    mockGet.mockResolvedValue({ data: { url: "/api/v1/files/tok" } });

    await getLibraryFileUrl(uuid);

    expect(mockGet).toHaveBeenCalledWith(`/library/${uuid}/download`);
  });
});
