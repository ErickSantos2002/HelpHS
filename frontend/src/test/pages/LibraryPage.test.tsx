import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

/**
 * A biblioteca de arquivos frequentes, do lado da tela.
 *
 * O que estes casos prendem não é o desenho — é a REGRA que atravessa a tela e
 * o servidor:
 *
 * 1. **O padrão é `internal`.** Abrir para o cliente é ato explícito de um
 *    administrador, então esquecer precisa falhar do lado seguro. Um mutante
 *    que troque o valor inicial da ficha não muda nada visível numa passada de
 *    olho — muda quem enxerga um manual com senha dentro.
 * 2. **A escolha viaja.** A visibilidade escolhida tem de chegar ao serviço,
 *    não ficar só pintada na ficha.
 * 3. **A tela não monta o endereço do arquivo.** Baixar passa pelo serviço,
 *    porque é lá que o servidor confere a visibilidade antes de emitir o link.
 * 4. **Lista que não carrega precisa dizer que não carregou** — e não se passar
 *    por lista vazia.
 *
 * Nenhum caso olha classe: o happy-dom não aplica CSS, e um mutante de classe
 * sobrevive por um motivo que não tem nada a ver com o que o caso mede.
 */

/** A sessão, trocável por caso — a tela mostra coisas diferentes por papel. */
let sessao: { id: string; role: string; name: string } = {
  id: "u1",
  role: "admin",
  name: "Admin",
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: sessao }),
}));
vi.mock("../../services/libraryService", () => ({
  getLibraryFiles: vi.fn(),
  uploadLibraryFile: vi.fn(),
  updateLibraryFile: vi.fn(),
  deleteLibraryFile: vi.fn(),
  getLibraryFileUrl: vi.fn(),
}));
vi.mock("../../services/productService", () => ({
  getProducts: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import LibraryPage from "../../pages/library/LibraryPage";
import * as libraryService from "../../services/libraryService";
import * as productService from "../../services/productService";
import { toast } from "sonner";

type Arquivo = Awaited<
  ReturnType<typeof libraryService.getLibraryFiles>
>["items"][number];

/**
 * Um item interno, de 40 KB.
 *
 * O tamanho não é enfeite: `(40960 / 1024 / 1024).toFixed(1)` — a conta que a
 * linha de anexo da `TicketDetailPage` faz — dá **"0.0 MB"**. Um arquivo real
 * da biblioteca é um formulário de duas páginas, então esse é o tamanho comum,
 * não o excepcional.
 */
const ARQUIVO: Arquivo = {
  id: "l1",
  title: "Manual de operação do Phoebus",
  description: "Configuração de fábrica e calibração.",
  product_id: "p1",
  product_name: "Phoebus 3",
  visibility: "internal",
  original_name: "manual-phoebus-v3.pdf",
  mime_type: "application/pdf",
  size_bytes: 40960,
  virus_scanned: true,
  virus_clean: true,
  uploaded_by: "u1",
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

type OpcoesDeMontagem = {
  arquivos?: Arquivo[];
  total?: number;
  papel?: string;
  erroNaLista?: unknown;
};

async function montar({
  arquivos = [ARQUIVO],
  total,
  papel = "admin",
  erroNaLista,
}: OpcoesDeMontagem = {}) {
  sessao = { id: "u1", role: papel, name: "Fulano" };

  if (erroNaLista) {
    vi.mocked(libraryService.getLibraryFiles).mockRejectedValue(erroNaLista);
  } else {
    vi.mocked(libraryService.getLibraryFiles).mockResolvedValue({
      items: arquivos,
      total: total ?? arquivos.length,
      limit: 20,
      offset: 0,
    });
  }
  vi.mocked(productService.getProducts).mockResolvedValue({
    items: [{ id: "p1", name: "Phoebus 3" }],
    total: 1,
  } as never);

  render(<LibraryPage />);

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Biblioteca" })).toBeInTheDocument(),
  );
  await waitFor(() => expect(libraryService.getLibraryFiles).toHaveBeenCalled());
}

/** Abre o modal de envio e espera as fichas da decisão aparecerem. */
async function abrirEnvio() {
  await userEvent.click(screen.getByRole("button", { name: "Enviar arquivo" }));
  await waitFor(() =>
    expect(screen.getByRole("radio", { name: "Uso interno" })).toBeInTheDocument(),
  );
}

function arquivoLocal(nome = "manual.pdf", bytes = 10): File {
  return new File([new Uint8Array(bytes)], nome, { type: "application/pdf" });
}

beforeEach(() => vi.clearAllMocks());

describe("LibraryPage — a lista", () => {
  it("mostra o arquivo com a visibilidade, o tamanho e o nome de origem", async () => {
    await montar();

    expect(screen.getByText("Manual de operação do Phoebus")).toBeInTheDocument();
    expect(screen.getByText("manual-phoebus-v3.pdf")).toBeInTheDocument();
    expect(screen.getByText("PDF")).toBeInTheDocument();
    // O selo diz "Uso interno" em vez de "internal": o valor cru não é rótulo.
    expect(screen.getAllByText("Uso interno").length).toBeGreaterThan(0);
  });

  /*
    O caso que o `toFixed(1)` direto em MB reprova.

    Ele existe porque "0.0 MB" não parece defeito: parece um arquivo vazio, e
    quem vê conclui que o envio falhou. O erro é de UNIDADE, e só aparece em
    arquivo pequeno — que é o tamanho comum de um formulário.
  */
  it("escreve 40 KB em KB, e não arredonda para 0.0 MB", async () => {
    await montar();

    expect(screen.getByText("40 KB")).toBeInTheDocument();
    expect(screen.queryByText("0.0 MB")).not.toBeInTheDocument();
  });

  it("avisa quando o antivírus não chegou a verificar o arquivo", async () => {
    await montar({
      arquivos: [{ ...ARQUIVO, virus_scanned: false, virus_clean: false }],
    });

    expect(screen.getByText("Não verificado")).toBeInTheDocument();
  });

  it("não avisa nada quando o arquivo foi verificado", async () => {
    await montar();

    expect(screen.queryByText("Não verificado")).not.toBeInTheDocument();
  });

  /*
    Lista vazia e lista que não carregou são situações OPOSTAS, e antes desta
    guarda tinham a mesma pintura: "Nenhum arquivo encontrado". Quem visse isso
    numa falha de rede concluiria que a biblioteca está vazia — e um
    administrador poderia reenviar um arquivo que já existe.
  */
  it("a lista que falha diz que falhou, em vez de se passar por vazia", async () => {
    await montar({
      erroNaLista: { response: { status: 500, data: {} } },
    });

    await waitFor(() =>
      expect(screen.getByText(/Erro ao carregar/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText("Nenhum arquivo encontrado.")).not.toBeInTheDocument();
  });

  it("lista genuinamente vazia oferece enviar o primeiro arquivo", async () => {
    await montar({ arquivos: [], total: 0 });

    expect(screen.getByText("Nenhum arquivo encontrado.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "+ Enviar primeiro arquivo" }),
    ).toBeInTheDocument();
  });
});

describe("LibraryPage — quem pode o quê", () => {
  it("o técnico lê o acervo, mas não envia, edita nem exclui", async () => {
    await montar({ papel: "technician" });

    expect(screen.getByText("Manual de operação do Phoebus")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enviar arquivo" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Editar / }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Excluir / }),
    ).not.toBeInTheDocument();
  });

  it("o técnico baixa — a listagem é de staff, e o download também", async () => {
    await montar({ papel: "technician" });

    expect(
      screen.getByRole("button", { name: "Baixar Manual de operação do Phoebus" }),
    ).toBeInTheDocument();
  });

  it("o administrador tem as três ações", async () => {
    await montar({ papel: "admin" });

    expect(screen.getByRole("button", { name: "Enviar arquivo" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Editar Manual de operação do Phoebus" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Excluir Manual de operação do Phoebus" }),
    ).toBeInTheDocument();
  });

  /*
    Numa lista de vinte linhas, vinte controles chamados "Baixar" não dizem
    qual dos vinte. O nome acessível carrega o título do arquivo.
  */
  it("cada ação de linha se anuncia com o título do arquivo", async () => {
    await montar();

    expect(
      screen.queryByRole("button", { name: "Baixar" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Baixar Manual de operação do Phoebus" }),
    ).toBeInTheDocument();
  });
});

describe("LibraryPage — o download não é montado na tela", () => {
  const abrir = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("open", abrir);
    abrir.mockClear();
  });
  afterEach(() => vi.unstubAllGlobals());

  /*
    A tela nunca constrói o endereço do arquivo: ela PEDE, e o servidor confere
    a visibilidade antes de emitir o link. Um `<a href>` montado aqui faria da
    regra de visibilidade uma sugestão — bastaria ter o id.
  */
  it("pede o link ao serviço antes de abrir qualquer coisa", async () => {
    await montar();
    vi.mocked(libraryService.getLibraryFileUrl).mockResolvedValue(
      "/api/v1/files/tok?filename=manual-phoebus-v3.pdf",
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Baixar Manual de operação do Phoebus" }),
    );

    await waitFor(() =>
      expect(libraryService.getLibraryFileUrl).toHaveBeenCalledWith("l1"),
    );
    expect(abrir).toHaveBeenCalledWith(
      "/api/v1/files/tok?filename=manual-phoebus-v3.pdf",
      "_blank",
    );
  });

  it("a recusa do servidor vira aviso, e nada é aberto", async () => {
    await montar();
    vi.mocked(libraryService.getLibraryFileUrl).mockRejectedValue(
      new Error("404"),
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Baixar Manual de operação do Phoebus" }),
    );

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(abrir).not.toHaveBeenCalled();
  });
});

describe("LibraryPage — o modal de envio", () => {
  /*
    O caso mais importante do arquivo.

    O padrão `internal` é a regra inteira: abrir para o cliente é ato explícito
    de um administrador, então esquecer falha do lado seguro. Um mutante que
    troque o valor inicial não muda nada que se note numa passada de olho —
    muda quem enxerga um manual técnico com senha de configuração em texto
    aberto.
  */
  it("nasce em uso interno, com a escolha marcada", async () => {
    await montar();
    await abrirEnvio();

    expect(screen.getByRole("radio", { name: "Uso interno" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Visível ao cliente" })).not.toBeChecked();
  });

  /*
    A ficha não decide sozinha: ela explica o que a escolha FAZ, e o texto muda
    junto. Sem isso o rótulo "Visível ao cliente" precisaria ser interpretado —
    e "visível" não diz que o técnico vai poder anexar o arquivo numa conversa.
  */
  it("a consequência escrita acompanha a escolha", async () => {
    await montar();
    await abrirEnvio();

    expect(screen.getByText(/A API recusa anexá-lo a uma conversa/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: "Visível ao cliente" }));

    expect(screen.getByText(/o cliente vai baixá-lo/)).toBeInTheDocument();
    expect(
      screen.queryByText(/A API recusa anexá-lo a uma conversa/),
    ).not.toBeInTheDocument();
  });

  it("manda ao serviço a visibilidade padrão quando ninguém a toca", async () => {
    await montar();
    await abrirEnvio();
    vi.mocked(libraryService.uploadLibraryFile).mockResolvedValue(ARQUIVO);

    const entrada = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(entrada, arquivoLocal("manual.pdf"));
    await userEvent.type(screen.getByLabelText(/Título/), "Manual novo");
    await userEvent.click(screen.getByRole("button", { name: "Enviar para a biblioteca" }));

    await waitFor(() => expect(libraryService.uploadLibraryFile).toHaveBeenCalled());
    expect(vi.mocked(libraryService.uploadLibraryFile).mock.calls[0][0]).toMatchObject({
      title: "Manual novo",
      visibility: "internal",
    });
  });

  it("manda `client` quando o administrador abre para o cliente", async () => {
    await montar();
    await abrirEnvio();
    vi.mocked(libraryService.uploadLibraryFile).mockResolvedValue(ARQUIVO);

    const entrada = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(entrada, arquivoLocal("guia.pdf"));
    await userEvent.type(screen.getByLabelText(/Título/), "Guia rápido");
    await userEvent.click(screen.getByRole("radio", { name: "Visível ao cliente" }));
    await userEvent.click(screen.getByRole("button", { name: "Enviar para a biblioteca" }));

    await waitFor(() => expect(libraryService.uploadLibraryFile).toHaveBeenCalled());
    expect(vi.mocked(libraryService.uploadLibraryFile).mock.calls[0][0]).toMatchObject({
      visibility: "client",
    });
  });

  /*
    O `FileUpload` é controlado e não participa da validação do zod. Sem a
    guarda, o botão de enviar não fazia nada — e a tela que não explica o que
    falta é a que a pessoa clica três vezes antes de desistir.
  */
  it("enviar sem escolher arquivo avisa, em vez de não fazer nada", async () => {
    await montar();
    await abrirEnvio();

    await userEvent.type(screen.getByLabelText(/Título/), "Manual sem arquivo");
    await userEvent.click(screen.getByRole("button", { name: "Enviar para a biblioteca" }));

    await waitFor(() =>
      expect(
        screen.getByText("Escolha o arquivo que vai para a biblioteca."),
      ).toBeInTheDocument(),
    );
    expect(libraryService.uploadLibraryFile).not.toHaveBeenCalled();
  });

  it("a recusa do servidor fica no modal, com o que a pessoa escreveu", async () => {
    await montar();
    await abrirEnvio();
    vi.mocked(libraryService.uploadLibraryFile).mockRejectedValue({
      response: { status: 422, data: { detail: "O tipo de arquivo '.exe' não é aceito." } },
    });

    const entrada = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(entrada, arquivoLocal("manual.pdf"));
    await userEvent.type(screen.getByLabelText(/Título/), "Manual");
    await userEvent.click(screen.getByRole("button", { name: "Enviar para a biblioteca" }));

    await waitFor(() =>
      expect(
        screen.getByText("O tipo de arquivo '.exe' não é aceito."),
      ).toBeInTheDocument(),
    );
    // O modal continua aberto: o título digitado não se perde.
    expect(screen.getByLabelText(/Título/)).toHaveValue("Manual");
  });
});

describe("LibraryPage — a edição", () => {
  /*
    Quem fecha um arquivo para o cliente está tentando tirá-lo das vistas dele,
    e é razoável supor que isso alcance as conversas onde ele já foi mandado.
    Não alcança — o histórico não é reescrito. Se o conteúdo vazou, fechar aqui
    não é a contenção, e a tela precisa dizer isso no momento da escolha.
  */
  it("rebaixar para interno avisa que o histórico não muda", async () => {
    await montar({ arquivos: [{ ...ARQUIVO, visibility: "client" }] });

    await userEvent.click(
      screen.getByRole("button", { name: "Editar Manual de operação do Phoebus" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "Uso interno" })).toBeInTheDocument(),
    );

    expect(screen.queryByText(/O histórico não muda/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: "Uso interno" }));

    expect(screen.getByText(/O histórico não muda/)).toBeInTheDocument();
  });

  it("abre com a visibilidade que o arquivo tem hoje, não com o padrão", async () => {
    await montar({ arquivos: [{ ...ARQUIVO, visibility: "client" }] });

    await userEvent.click(
      screen.getByRole("button", { name: "Editar Manual de operação do Phoebus" }),
    );

    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "Visível ao cliente" })).toBeChecked(),
    );
  });

  /*
    `null` e não `undefined`: o PATCH só grava o que recebe, e `undefined` some
    do JSON. Apagar a descrição mandando `undefined` deixaria o texto antigo no
    banco — a tela mostraria vazio, o servidor teria o de antes.
  */
  it("descrição apagada chega ao servidor como apagada", async () => {
    await montar();
    vi.mocked(libraryService.updateLibraryFile).mockResolvedValue(ARQUIVO);

    await userEvent.click(
      screen.getByRole("button", { name: "Editar Manual de operação do Phoebus" }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText(/Descrição/)).toBeInTheDocument(),
    );

    await userEvent.clear(screen.getByLabelText(/Descrição/));
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(libraryService.updateLibraryFile).toHaveBeenCalled());
    expect(vi.mocked(libraryService.updateLibraryFile).mock.calls[0][1]).toMatchObject({
      description: null,
    });
  });
});

describe("LibraryPage — a exclusão", () => {
  it("diz o que acontece com as conversas que já anexaram o arquivo", async () => {
    await montar();

    await userEvent.click(
      screen.getByRole("button", { name: "Excluir Manual de operação do Phoebus" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText(/continuam existindo — só deixam de ter o arquivo/),
      ).toBeInTheDocument(),
    );
  });

  it("exclui e tira o arquivo da lista", async () => {
    await montar();
    vi.mocked(libraryService.deleteLibraryFile).mockResolvedValue(undefined);

    await userEvent.click(
      screen.getByRole("button", { name: "Excluir Manual de operação do Phoebus" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(libraryService.deleteLibraryFile).toHaveBeenCalledWith("l1"),
    );
    await waitFor(() =>
      expect(screen.queryByText("Manual de operação do Phoebus")).not.toBeInTheDocument(),
    );
  });

  it("a exclusão que falha avisa e não tira nada da lista", async () => {
    await montar();
    vi.mocked(libraryService.deleteLibraryFile).mockRejectedValue(new Error("500"));

    await userEvent.click(
      screen.getByRole("button", { name: "Excluir Manual de operação do Phoebus" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    // Pela AÇÃO da linha, e não pelo título: o modal continua aberto e mostra
    // o mesmo título na prévia, então `getByText` acharia dois.
    expect(
      screen.getByRole("button", { name: "Excluir Manual de operação do Phoebus" }),
    ).toBeInTheDocument();
  });
});

describe("LibraryPage — os filtros", () => {
  it("a busca chega ao serviço", async () => {
    await montar();

    await userEvent.type(
      screen.getByLabelText("Buscar arquivos na biblioteca"),
      "phoebus",
    );

    await waitFor(() =>
      expect(libraryService.getLibraryFiles).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: "phoebus" }),
      ),
    );
  });

  it("o filtro de visibilidade chega ao serviço com o valor cru", async () => {
    await montar();

    await userEvent.selectOptions(
      screen.getByLabelText("Visibilidade"),
      "client",
    );

    await waitFor(() =>
      expect(libraryService.getLibraryFiles).toHaveBeenLastCalledWith(
        expect.objectContaining({ visibility: "client" }),
      ),
    );
  });

  /*
    O filtro se anunciava pelo VALOR escolhido — "Uso interno" — sem dizer de
    que filtro era. O rótulo é `sr-only` porque a barra não tem espaço para
    ele, mas ele existe.
  */
  it("o filtro tem nome, e não só o valor escolhido", async () => {
    await montar();

    expect(screen.getByLabelText("Visibilidade")).toBeInTheDocument();
  });
});
