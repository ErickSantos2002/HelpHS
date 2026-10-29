import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/chatService", async (importOriginal) => {
  // A normalização é a DE VERDADE: é ela que o frame do WebSocket atravessa, e
  // um dublê aqui deixaria passar justamente o defeito de esquecer de chamá-la.
  const real = await importOriginal<typeof import("../../services/chatService")>();
  return {
    buildWsUrl: (id: string) => `ws://teste/${id}`,
    getChatMessages: vi.fn(),
    improveMessage: vi.fn(),
    normalizaMensagem: real.normalizaMensagem,
    suggestReply: vi.fn(),
    summarizeConversation: vi.fn(),
    sendMessageWithLibraryFile: vi.fn(),
  };
});

vi.mock("../../services/libraryService", () => ({
  getLibraryFiles: vi.fn(),
  getLibraryFileUrl: vi.fn(),
}));

vi.mock("../../services/quickReplyService", () => ({
  listQuickReplies: vi.fn(),
  matchQuickReplies: () => [],
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { toast } from "sonner";

import { ChatPanel } from "../../components/chat/ChatPanel";
import type { ChatMessage } from "../../services/chatService";
import {
  getChatMessages,
  sendMessageWithLibraryFile,
  summarizeConversation,
} from "../../services/chatService";
import { getLibraryFileUrl, getLibraryFiles } from "../../services/libraryService";
import type { LibraryFile } from "../../services/libraryService";
import type { Attachment } from "../../services/attachmentService";
import type { EventoDeAnexo } from "../../lib/anexoNaConversa";
import { listQuickReplies } from "../../services/quickReplyService";

/**
 * O aviso do ESLint em ChatPanel pede `onStatusChange` nas deps do useCallback
 * que cria `connect`. Atender ao pedido derruba o chat: o pai passa uma arrow
 * INLINE, então a prop muda de identidade a cada render dele; `connect` mudaria
 * junto, o efeito reexecutaria, o cleanup fecharia o socket e ele reconectaria.
 *
 * Estes testes existem para que a próxima pessoa que "consertar" o aviso veja o
 * estrago na hora, e não em produção. São duas metades:
 *
 *   1. o socket é construído UMA vez, por mais que o pai re-renderize;
 *   2. a mudança de status ainda chega ao pai depois desses re-renders — que é
 *      o que torna a closure velha inofensiva e justifica deixar a dep de fora.
 *
 * Sem a segunda, o teste 1 sozinho seria satisfeito por um componente que
 * simplesmente ignora o callback.
 */

const socketsConstruidos: SocketFalso[] = [];

/**
 * O `readyState` fica em CONNECTING e o `onopen` NUNCA dispara sozinho, de
 * propósito. O `connect` real começa com
 * `if (wsRef.current?.readyState === WebSocket.OPEN) return;` — se este falso
 * se declarasse aberto, esse atalho engoliria uma reexecução do efeito e o
 * teste ficaria verde mesmo com a dependência adicionada. Em CONNECTING, toda
 * reexecução vira um socket a mais e aparece na contagem.
 */
class SocketFalso {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readyState: number = SocketFalso.CONNECTING;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  /** O que foi enviado por aqui. Era descartado, e o anexo precisa provar que
      a mensagem com arquivo NÃO sai por este caminho. */
  enviados: string[] = [];

  constructor(url: string) {
    this.url = url;
    socketsConstruidos.push(this);
  }

  close(code = 1000) {
    this.readyState = SocketFalso.CLOSED;
    this.onclose?.({ code });
  }

  send(payload: string) {
    this.enviados.push(payload);
  }
}

/** Cada render devolve uma arrow NOVA, igual ao TicketDetailPage:1437. */
const callbacksCriados: Array<(status: string) => void> = [];

function Pai({ marca }: { marca: number }) {
  const [ticket, setTicket] = useState<{ status: string } | null>({ status: "open" });

  const onStatusChange = (s: string) =>
    setTicket((prev) => (prev ? { ...prev, status: s } : prev));
  callbacksCriados.push(onStatusChange);

  return (
    <>
      <span data-testid="marca">{marca}</span>
      <span data-testid="status">{ticket?.status}</span>
      <ChatPanel ticketId="t-1" currentUserId="u-1" onStatusChange={onStatusChange} />
    </>
  );
}

async function rerenderizaOPai(vezes: number) {
  const { rerender } = render(<Pai marca={0} />);
  await act(async () => {});
  for (let i = 1; i <= vezes; i++) {
    rerender(<Pai marca={i} />);
    await act(async () => {});
  }
}

describe("ChatPanel — o pai re-renderiza, o WebSocket não reconecta", () => {
  beforeEach(() => {
    socketsConstruidos.length = 0;
    callbacksCriados.length = 0;
    vi.mocked(getChatMessages).mockResolvedValue({
      items: [],
    } as unknown as Awaited<ReturnType<typeof getChatMessages>>);
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal("WebSocket", SocketFalso);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("constrói o socket uma vez só, com o pai re-renderizando 5 vezes", async () => {
    await rerenderizaOPai(5);

    // A premissa do teste: o pai é mesmo hostil. Se alguém "consertar" o aviso
    // envolvendo o callback do pai num useCallback, esta linha avisa que o
    // cenário deixou de ser o que este teste queria exercitar.
    expect(callbacksCriados.length).toBeGreaterThanOrEqual(6);
    expect(new Set(callbacksCriados).size).toBe(callbacksCriados.length);

    expect(socketsConstruidos).toHaveLength(1);
  });

  it("a mudança de status ainda chega ao pai depois dos re-renders", async () => {
    await rerenderizaOPai(5);

    expect(screen.getByTestId("status")).toHaveTextContent("open");

    await act(async () => {
      socketsConstruidos[0].onmessage?.({
        data: JSON.stringify({ type: "status_update", data: { status: "resolved" } }),
      });
    });

    expect(screen.getByTestId("status")).toHaveTextContent("resolved");
  });
});

/**
 * ── O que o painel PROMETE ────────────────────────────────────────────
 *
 * Estes casos são da Fase 16, e nenhum deles olha classe. O happy-dom **não
 * aplica CSS**: um caso que afirmasse `toHaveClass("bg-tint-info")` passaria
 * com a classe presente e a bolha invisível, e um mutante que trocasse a classe
 * sobreviveria por um motivo que não tem nada a ver com o que o caso mede. O
 * que se mede aqui é o que a pessoa alcança — o texto que ela lê e o nome pelo
 * qual o controle se anuncia.
 *
 * Quatro deles existem por causa da **1.4.1**: quem não separa as cores precisa
 * que o autor da mensagem e o estado da conexão estejam ESCRITOS. A migração
 * trocou as tintas das três bolhas, e sem estes casos ela poderia ter trocado
 * junto o que sobra de informação quando a cor não chega.
 */

let sequencia = 0;

function mensagem(over: Partial<ChatMessage> = {}): ChatMessage {
  sequencia += 1;
  return {
    id: `m-${sequencia}`,
    ticket_id: "t-1",
    sender_id: "outra-pessoa",
    sender_name: "Bruno Lima",
    sender_role: "technician",
    content: "conteúdo",
    is_system: false,
    is_ai: false,
    // Sem anexo por padrão: é o caso comum, e a fixture o diz por escrito em
    // vez de omitir. O tipo passou a declarar os quatro campos quando o front
    // finalmente foi desenhar o anexo da biblioteca, e o `tsc -b` apontou esta
    // fixture na hora -- ela descrevia uma resposta que o servidor não manda
    // mais desde o PR #6.
    library_file_id: null,
    library_file_name: null,
    library_file_mime: null,
    library_file_size: null,
    read_at: null,
    created_at: "2026-09-08T12:00:00.000Z",
    ...over,
  };
}

async function montar({
  papel = "admin",
  historico = [],
  travado = false,
  falhaNoHistorico = false,
}: {
  papel?: string;
  historico?: ChatMessage[];
  travado?: boolean;
  falhaNoHistorico?: boolean;
} = {}) {
  if (falhaNoHistorico) {
    vi.mocked(getChatMessages).mockRejectedValue(new Error("500"));
  } else {
    vi.mocked(getChatMessages).mockResolvedValue({
      items: historico,
    } as unknown as Awaited<ReturnType<typeof getChatMessages>>);
  }

  render(
    <ChatPanel
      ticketId="t-1"
      currentUserId="eu"
      currentUserRole={papel}
      locked={travado}
    />,
  );
  await act(async () => {});
  return socketsConstruidos[0];
}

/** O falso fica em CONNECTING de propósito; abrir é passo explícito. */
async function abre(ws: SocketFalso) {
  await act(async () => {
    ws.readyState = SocketFalso.OPEN;
    ws.onopen?.();
  });
}

/**
 * O preparo é UMA função porque ele é a mesma coisa em todo bloco, e porque a
 * versão duplicada já custou: os casos do anexo nasceram fora deste `describe`
 * e sem o `stubGlobal`, então o `WebSocket` era o de verdade e o socket falso
 * nunca chegava a existir. Três casos falharam dizendo "não enviou nada" —
 * quando o que faltava era o preparo, não o envio.
 */
function preparaOPainel() {
  beforeEach(() => {
    sequencia = 0;
    socketsConstruidos.length = 0;
    vi.mocked(listQuickReplies).mockResolvedValue([]);
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal("WebSocket", SocketFalso);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });
}

describe("ChatPanel — o que o painel promete", () => {
  preparaOPainel();

  afterEach(() => {
  });

  it("o nome e o papel de quem escreveu ficam ESCRITOS", async () => {
    await montar({
      historico: [
        mensagem({ sender_name: "Bruno Lima", sender_role: "technician" }),
        mensagem({
          sender_id: "chefe",
          sender_name: "Ana Souza",
          sender_role: "admin",
        }),
      ],
    });

    expect(screen.getByText("Bruno Lima")).toBeInTheDocument();
    expect(screen.getByText("Ana Souza")).toBeInTheDocument();
    expect(screen.getByText("Técnico")).toBeInTheDocument();

    // "Administrador", e não "Admin". O rótulo vem do `lib/papel.ts`, e a
    // divergência era DESTA tela — as outras seis cópias já escreviam por
    // extenso. Muda texto na tela, e é o que o módulo existe para fazer.
    expect(screen.getByText("Administrador")).toBeInTheDocument();
    expect(screen.queryByText("Admin")).not.toBeInTheDocument();
  });

  it("a bolha da IA diz quem falou, e não só de que cor é", async () => {
    await montar({
      historico: [
        mensagem({
          is_ai: true,
          sender_id: null,
          sender_name: "Helô",
          content: "Tente reiniciar o roteador.",
        }),
      ],
    });

    expect(screen.getByText("Assistente IA")).toBeInTheDocument();
    expect(screen.getByText("Tente reiniciar o roteador.")).toBeInTheDocument();
  });

  it("a mensagem do sistema não ganha autor — ela não é de ninguém", async () => {
    await montar({
      historico: [
        mensagem({
          is_system: true,
          sender_id: null,
          sender_name: "Sistema",
          sender_role: "",
          content: "Status alterado para Em andamento.",
        }),
      ],
    });

    expect(
      screen.getByText("Status alterado para Em andamento."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Sistema")).not.toBeInTheDocument();
  });

  it("o estado da conexão está em TEXTO, e não só no ponto colorido", async () => {
    const ws = await montar();

    expect(screen.getByText("conectando…")).toBeInTheDocument();
    await abre(ws);
    expect(screen.getByText("ao vivo")).toBeInTheDocument();
  });

  it("o botão de enviar tem nome acessível", async () => {
    // Ele era um `<svg>` dentro de um `<button>`, sem título nem rótulo: o
    // nome acessível era vazio e o leitor de tela anunciava só "botão".
    await montar();
    expect(
      screen.getByRole("button", { name: "Enviar mensagem" }),
    ).toBeInTheDocument();
  });

  it("enviar só libera com o socket aberto E com texto digitado", async () => {
    const ws = await montar();
    const botao = screen.getByRole("button", { name: "Enviar mensagem" });
    const campo = screen.getByRole("textbox");

    expect(botao).toBeDisabled();

    fireEvent.change(campo, { target: { value: "oi" } });
    expect(botao).toBeDisabled();

    await abre(ws);
    expect(botao).toBeEnabled();

    fireEvent.change(campo, { target: { value: "   " } });
    expect(botao).toBeDisabled();
  });

  it("quem não é da equipe não vê nenhuma ação de IA", async () => {
    await montar({ papel: "client" });

    expect(
      screen.queryByRole("button", { name: /Sugerir resposta/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Melhorar texto/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Resumir" }),
    ).not.toBeInTheDocument();
  });

  it("a equipe vê as três ações de IA, cada uma com o próprio rótulo", async () => {
    await montar({ papel: "technician" });

    expect(
      screen.getByRole("button", { name: /Sugerir resposta \(IA\)/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Melhorar texto \(IA\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resumir" })).toBeInTheDocument();
  });

  it("chamado encerrado tira o campo, e diz por quê", async () => {
    await montar({ travado: true });

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Enviar mensagem" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/o chat está bloqueado/)).toBeInTheDocument();
  });

  it("histórico que não carrega vira aviso escrito", async () => {
    await montar({ falhaNoHistorico: true });

    expect(
      await screen.findByText("Não foi possível carregar o histórico."),
    ).toBeInTheDocument();
  });

  it("o resumo aparece, e os dois controles dele têm nome próprio", async () => {
    vi.mocked(summarizeConversation).mockResolvedValue(
      "Cliente sem internet desde ontem.",
    );
    await montar();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Resumir" }));
    });

    expect(
      screen.getByText("Cliente sem internet desde ontem."),
    ).toBeInTheDocument();
    // Gerado o resumo, o botão passa a oferecer o que já existe.
    expect(screen.getByRole("button", { name: "Resumo" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Regenerar resumo" }),
    ).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Fechar resumo" }));
    });

    await waitFor(() =>
      expect(
        screen.queryByText("Cliente sem internet desde ontem."),
      ).not.toBeInTheDocument(),
    );
  });
});


/**
 * O anexo da biblioteca (PR #6).
 *
 * Duas metades que não se encostam: a BOLHA, que todo mundo vê e cujo link é
 * buscado no clique; e o SELETOR, que só staff tem, e cujo envio sai pelo REST
 * porque o WebSocket descarta o `library_file_id`.
 */
function arquivo(over: Partial<LibraryFile> = {}): LibraryFile {
  return {
    id: "lib-7",
    title: "Manual do Phoebus",
    description: null,
    product_id: null,
    product_name: null,
    visibility: "client",
    original_name: "manual.pdf",
    mime_type: "application/pdf",
    size_bytes: 1048576,
    virus_scanned: true,
    virus_clean: true,
    uploaded_by: "u-1",
    created_at: "2026-09-01T12:00:00Z",
    updated_at: "2026-09-01T12:00:00Z",
    ...over,
  };
}

describe("anexo da biblioteca na bolha", () => {
  preparaOPainel();

  it("mostra o nome e o tamanho do arquivo anexado", async () => {
    await montar({
      historico: [
        mensagem({
          content: "Segue o manual.",
          library_file_id: "lib-7",
          library_file_name: "manual.pdf",
          library_file_size: 1048576,
        }),
      ],
    });

    expect(screen.getByText("manual.pdf")).toBeInTheDocument();
    expect(screen.getByText("1,0 MB")).toBeInTheDocument();
  });

  it("busca o link no CLIQUE, e não ao desenhar a bolha", async () => {
    // O link tem validade e a API confere a visibilidade ao EMITIR. Um href
    // gravado na bolha continuaria valendo depois de o item ser fechado.
    vi.mocked(getLibraryFileUrl).mockResolvedValue("https://exemplo/arquivo.pdf");
    const abrir = vi.spyOn(window, "open").mockReturnValue(null);

    await montar({
      historico: [
        mensagem({ library_file_id: "lib-7", library_file_name: "manual.pdf" }),
      ],
    });

    expect(getLibraryFileUrl).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Baixar manual.pdf" }));
    });

    expect(getLibraryFileUrl).toHaveBeenCalledWith("lib-7");
    await waitFor(() =>
      expect(abrir).toHaveBeenCalledWith(
        "https://exemplo/arquivo.pdf",
        "_blank",
        "noopener,noreferrer",
      ),
    );
    abrir.mockRestore();
  });

  it("o nome do arquivo entra no nome acessível do botão", async () => {
    // São vários anexos na mesma conversa. Quatro botões dizendo só "Baixar"
    // não deixam escolher qual.
    await montar({
      historico: [
        mensagem({ library_file_id: "a", library_file_name: "manual.pdf" }),
        mensagem({ library_file_id: "b", library_file_name: "ficha.pdf" }),
      ],
    });

    expect(screen.getByRole("button", { name: "Baixar manual.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Baixar ficha.pdf" })).toBeInTheDocument();
  });

  it("link recusado vira frase honesta, e não erro cru", async () => {
    // O admin pode ter fechado o item DEPOIS do envio. Para o cliente a API
    // responde 404, igual a id inexistente — ele não pode aprender que existe.
    vi.mocked(getLibraryFileUrl).mockRejectedValue(new Error("404"));

    await montar({
      historico: [
        mensagem({ library_file_id: "lib-7", library_file_name: "manual.pdf" }),
      ],
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Baixar manual.pdf" }));
    });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Este arquivo não está mais disponível para você.",
      ),
    );
  });

  it("mensagem sem anexo não desenha nada de arquivo", async () => {
    // Controle negativo: sem ele, um componente que sempre desenhasse a caixa
    // passaria nos casos acima.
    await montar({ historico: [mensagem({ content: "Sem anexo aqui." })] });

    expect(screen.queryByRole("button", { name: /^Baixar/ })).not.toBeInTheDocument();
  });
});

describe("seletor da biblioteca", () => {
  preparaOPainel();

  it("o botão de anexar é só do staff", async () => {
    // `GET /library` recusa cliente: um botão que abrisse lista vazia seria
    // pior que botão nenhum.
    await montar({ papel: "client" });
    expect(
      screen.queryByRole("button", { name: "Anexar arquivo da biblioteca" }),
    ).not.toBeInTheDocument();
  });

  it("o staff tem o botão, e ele abre a lista pedindo só o que é anexável", async () => {
    vi.mocked(getLibraryFiles).mockResolvedValue({
      items: [arquivo()],
      total: 1,
      limit: 20,
      offset: 0,
    });

    await montar({ papel: "technician" });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Anexar arquivo da biblioteca" }));
    });

    // `visibility: "client"` é o filtro da PRÓPRIA API, não a tela repetindo a
    // regra: quem define o que "client" significa segue sendo o backend.
    await waitFor(() =>
      expect(getLibraryFiles).toHaveBeenCalledWith(
        expect.objectContaining({ visibility: "client" }),
      ),
    );
    expect(await screen.findByText("Manual do Phoebus")).toBeInTheDocument();
  });

  it("escolher um arquivo mostra o chip, e enviar vai pelo REST — não pelo socket", async () => {
    // A metade que importa: o manipulador do WebSocket lê SÓ `content`, então
    // um `library_file_id` mandado por lá sumiria em silêncio.
    vi.mocked(getLibraryFiles).mockResolvedValue({
      items: [arquivo()],
      total: 1,
      limit: 20,
      offset: 0,
    });
    vi.mocked(sendMessageWithLibraryFile).mockResolvedValue(mensagem());

    const ws = await montar({ papel: "technician" });
    await abre(ws);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Anexar arquivo da biblioteca" }));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText("Manual do Phoebus"));
    });

    expect(
      screen.getByRole("button", { name: "Remover o anexo Manual do Phoebus" }),
    ).toBeInTheDocument();

    const campo = screen.getByPlaceholderText(/Escreva uma mensagem/);
    fireEvent.change(campo, { target: { value: "Segue o manual." } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    });

    await waitFor(() =>
      expect(sendMessageWithLibraryFile).toHaveBeenCalledWith("t-1", "Segue o manual.", "lib-7"),
    );
    expect(ws.enviados).toHaveLength(0);
  });

  it("sem anexo, o envio continua indo pelo socket", async () => {
    // Controle negativo do caso acima: sem ele, mandar TUDO pelo REST passaria.
    vi.mocked(sendMessageWithLibraryFile).mockResolvedValue(mensagem());
    const ws = await montar({ papel: "technician" });
    await abre(ws);

    const campo = screen.getByPlaceholderText(/Escreva uma mensagem/);
    fireEvent.change(campo, { target: { value: "só texto" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    });

    expect(sendMessageWithLibraryFile).not.toHaveBeenCalled();
    expect(ws.enviados).toHaveLength(1);
  });

  it("anexo não dispensa o texto: o envio segue travado com o campo vazio", async () => {
    // `content` é `min_length=1` no schema. Não existe mensagem só com
    // arquivo, e isso é restrição de contrato, não escolha de tela.
    vi.mocked(getLibraryFiles).mockResolvedValue({
      items: [arquivo()],
      total: 1,
      limit: 20,
      offset: 0,
    });

    const ws = await montar({ papel: "technician" });
    await abre(ws);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Anexar arquivo da biblioteca" }));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText("Manual do Phoebus"));
    });

    expect(screen.getByRole("button", { name: "Enviar mensagem" })).toBeDisabled();
  });

  it("o 422 do item interno chega ao técnico com a razão que a API escreveu", async () => {
    // A recusa é da API, e ela é quem sabe o porquê. A tela não inventa texto.
    vi.mocked(getLibraryFiles).mockResolvedValue({
      items: [arquivo()],
      total: 1,
      limit: 20,
      offset: 0,
    });
    vi.mocked(sendMessageWithLibraryFile).mockRejectedValue({
      response: { data: { detail: "Este arquivo da biblioteca é de uso interno." } },
    });

    const ws = await montar({ papel: "technician" });
    await abre(ws);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Anexar arquivo da biblioteca" }));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText("Manual do Phoebus"));
    });
    fireEvent.change(screen.getByPlaceholderText(/Escreva uma mensagem/), {
      target: { value: "Segue." },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Este arquivo da biblioteca é de uso interno."),
    );
  });

  it("o 422 de validação em lista também chega com a mensagem do campo (F1-B-02)", async () => {
    // O `detail` em lista de `{field, message}` caía no texto genérico: a tela
    // só aceitava `detail` em texto.
    vi.mocked(getLibraryFiles).mockResolvedValue({
      items: [arquivo()],
      total: 1,
      limit: 20,
      offset: 0,
    });
    vi.mocked(sendMessageWithLibraryFile).mockRejectedValue({
      response: {
        status: 422,
        data: { detail: [{ field: "content", message: "Deve ter no máximo 4000 caractere(s)" }] },
      },
    });

    const ws = await montar({ papel: "technician" });
    await abre(ws);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Anexar arquivo da biblioteca" }));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText("Manual do Phoebus"));
    });
    fireEvent.change(screen.getByPlaceholderText(/Escreva uma mensagem/), {
      target: { value: "Segue." },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Deve ter no máximo 4000 caractere(s)"),
    );
  });
});

/**
 * ── Anexo enviado, contado na conversa ───────────────────────────────
 *
 * O acontecimento NÃO é mensagem: não vem do `getChatMessages`, não tem bolha e
 * não tem autor no cabeçalho. Vem do histórico do chamado, pronto, pelo pai. O
 * que se mede é o que a pessoa lê — a 1.4.1 de novo: "Anexo adicionado" fica
 * ESCRITO, e não só um estilo diferente.
 */
describe("ChatPanel — anexo adicionado aparece na conversa", () => {
  preparaOPainel();

  const ANEXO: Attachment = {
    id: "a1",
    ticket_id: "t-1",
    uploaded_by: "outra-pessoa",
    uploaded_by_name: "Bruno Lima",
    uploaded_by_role: "technician",
    original_name: "laudo.pdf",
    mime_type: "application/pdf",
    size_bytes: 1024,
    virus_scanned: true,
    virus_clean: true,
    created_at: "2026-09-08T12:05:00.000Z",
  };

  function evento(over: Partial<EventoDeAnexo> = {}): EventoDeAnexo {
    return {
      id: "h1",
      created_at: "2026-09-08T12:05:00.000Z",
      autor: "Bruno Lima",
      papel: "technician",
      anexo: ANEXO,
      ...over,
    };
  }

  async function montarComEventos(
    eventos: EventoDeAnexo[],
    historico: ChatMessage[] = [],
    onAbrirAnexo = vi.fn(),
  ) {
    vi.mocked(getChatMessages).mockResolvedValue({
      items: historico,
    } as unknown as Awaited<ReturnType<typeof getChatMessages>>);
    render(
      <ChatPanel
        ticketId="t-1"
        currentUserId="eu"
        currentUserRole="client"
        eventosDeAnexo={eventos}
        onAbrirAnexo={onAbrirAnexo}
      />,
    );
    await act(async () => {});
    return onAbrirAnexo;
  }

  it("diz quem anexou, com o papel, por escrito", async () => {
    await montarComEventos([evento()]);
    expect(screen.getByText(/Anexo adicionado por Bruno Lima \(Técnico\)/)).toBeInTheDocument();
  });

  it("entra na ordem do tempo, entre as mensagens", async () => {
    await montarComEventos(
      [evento()],
      [
        mensagem({ content: "antes", created_at: "2026-09-08T12:00:00.000Z" }),
        mensagem({ content: "depois", created_at: "2026-09-08T12:10:00.000Z" }),
      ],
    );
    const antes = screen.getByText("antes");
    const ev = screen.getByText(/Anexo adicionado por/);
    const depois = screen.getByText("depois");
    expect(antes.compareDocumentPosition(ev) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(ev.compareDocumentPosition(depois) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("não é bolha de mensagem: o nome não vira cabeçalho de autor", async () => {
    await montarComEventos([evento()]);
    // A bolha de outra pessoa escreve o nome sozinho num <span>. No evento o
    // nome está dentro da frase — nenhum elemento tem só "Bruno Lima".
    expect(screen.queryByText("Bruno Lima", { exact: true })).not.toBeInTheDocument();
    expect(
      screen.queryByText("Nenhuma mensagem ainda. Seja o primeiro a escrever."),
    ).not.toBeInTheDocument();
  });

  it("o nome do arquivo abre pelo mesmo caminho da aba Anexos", async () => {
    const onAbrir = await montarComEventos([evento()]);
    fireEvent.click(screen.getByRole("button", { name: "Abrir laudo.pdf" }));
    expect(onAbrir).toHaveBeenCalledWith(ANEXO);
  });

  it("anexo excluído depois: o acontecimento fica, sem botão para abrir", async () => {
    await montarComEventos([evento({ anexo: null })]);
    expect(screen.getByText(/arquivo removido depois/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Abrir/ })).not.toBeInTheDocument();
  });

  it("sem autor no histórico, não inventa um", async () => {
    await montarComEventos([evento({ autor: null, papel: null })]);
    expect(screen.getByText(/Anexo adicionado/)).toBeInTheDocument();
    expect(screen.queryByText(/ por /)).not.toBeInTheDocument();
  });

  it("não envia nada pelo socket nem conta como mensagem", async () => {
    const ws = await (async () => {
      await montarComEventos([evento()]);
      return socketsConstruidos[0];
    })();
    expect(ws.enviados).toEqual([]);
  });
});

// ── Foto de quem falou (Fase 3B) ──────────────────────────────

describe("ChatPanel — a foto de quem falou", () => {
  preparaOPainel();

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("a mensagem de outra pessoa mostra a foto que o backend mandou", async () => {
    await montar({
      historico: [
        mensagem({ sender_name: "Bruno Lima", sender_avatar_url: "https://cdn.x/b.png" }),
      ],
    });

    expect(screen.getByRole("img", { name: "Bruno Lima" })).toHaveAttribute(
      "src",
      "https://cdn.x/b.png",
    );
  });

  it("sem foto, continua nas iniciais", async () => {
    await montar({
      historico: [mensagem({ sender_name: "Bruno Lima", sender_avatar_url: null })],
    });

    expect(screen.queryByRole("img", { name: "Bruno Lima" })).not.toBeInTheDocument();
    expect(screen.getByText("BL")).toBeInTheDocument();
  });

  it("a mensagem nova pelo WebSocket já chega com a foto, sem recarregar", async () => {
    vi.stubEnv("VITE_API_URL", "https://api.exemplo.com/api/v1");
    const ws = await montar();

    await act(async () => {
      ws.onmessage?.({
        data: JSON.stringify({
          type: "message",
          data: mensagem({
            sender_name: "Ana Souza",
            sender_avatar_url: "/api/v1/files/tok",
          }),
        }),
      });
    });

    // Relativo vira absoluto pela MESMA regra do histórico: com a API em
    // outro domínio, um <img> com caminho relativo pediria ao front.
    expect(screen.getByRole("img", { name: "Ana Souza" })).toHaveAttribute(
      "src",
      "https://api.exemplo.com/api/v1/files/tok",
    );
  });

  it("link que falha cai nas iniciais e um link novo volta a ser tentado", async () => {
    const ws = await montar({
      historico: [
        mensagem({ sender_name: "Bruno Lima", sender_avatar_url: "https://cdn.x/velho.png" }),
      ],
    });

    fireEvent.error(screen.getByRole("img", { name: "Bruno Lima" }));
    expect(screen.queryByRole("img", { name: "Bruno Lima" })).not.toBeInTheDocument();

    await act(async () => {
      ws.onmessage?.({
        data: JSON.stringify({
          type: "message",
          data: mensagem({ sender_name: "Bruno Lima", sender_avatar_url: "https://cdn.x/novo.png" }),
        }),
      });
    });

    expect(screen.getByRole("img", { name: "Bruno Lima" })).toHaveAttribute(
      "src",
      "https://cdn.x/novo.png",
    );
  });

  it("Helô e sistema mantêm a identidade própria, mesmo se viesse um link", async () => {
    await montar({
      historico: [
        mensagem({
          is_ai: true,
          sender_id: null,
          sender_name: "Helô",
          sender_avatar_url: "https://cdn.x/h.png",
        }),
        mensagem({
          is_system: true,
          sender_id: null,
          sender_name: "Sistema",
          sender_avatar_url: "https://cdn.x/s.png",
          content: "Status alterado.",
        }),
      ],
    });

    expect(screen.queryAllByRole("img")).toHaveLength(0);
    expect(screen.getByText("Assistente IA")).toBeInTheDocument();
  });

  it("a minha mensagem continua sem avatar ao lado", async () => {
    await montar({
      historico: [
        mensagem({ sender_id: "eu", sender_name: "Eu Mesmo", sender_avatar_url: "https://cdn.x/eu.png" }),
      ],
    });

    expect(screen.queryByRole("img", { name: "Eu Mesmo" })).not.toBeInTheDocument();
  });
});

/**
 * ── O 4428: aceite da Política pendente ───────────────────────────────
 *
 * O backend aceita a conexão e fecha com 4428 quando falta o aceite (ou quando
 * a pessoa revoga com o chat aberto). Reconectar só repetiria o 4428 a cada
 * 3 s, sem fim — foi o que a sondagem de 28/10/2026 mediu com o painel antigo.
 */
describe("ChatPanel — fechamento 4428 (aceite da Política pendente)", () => {
  beforeEach(() => {
    socketsConstruidos.length = 0;
    vi.mocked(getChatMessages).mockResolvedValue({
      items: [],
    } as unknown as Awaited<ReturnType<typeof getChatMessages>>);
    Element.prototype.scrollIntoView = vi.fn();
    vi.stubGlobal("WebSocket", SocketFalso);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  async function fechaCom(codigo: number) {
    const { aoAceitePoliticaPendente } = await import("../../services/aceitePolitica");
    const aviso = vi.fn();
    const para = aoAceitePoliticaPendente(aviso);
    render(<ChatPanel ticketId="t-1" currentUserId="u-1" />);
    await act(async () => {});
    vi.useFakeTimers();
    act(() => socketsConstruidos[0].close(codigo));
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    para();
    return aviso;
  }

  it("não reconecta e leva à tela de aceite", async () => {
    const aviso = await fechaCom(4428);

    expect(socketsConstruidos).toHaveLength(1);
    expect(aviso).toHaveBeenCalledTimes(1);
  });

  it("queda comum continua reconectando, sem abrir a tela de aceite", async () => {
    const aviso = await fechaCom(1006);

    expect(socketsConstruidos.length).toBeGreaterThan(1);
    expect(aviso).not.toHaveBeenCalled();
  });
});
