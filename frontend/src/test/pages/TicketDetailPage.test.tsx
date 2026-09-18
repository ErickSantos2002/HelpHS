import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../components/chat/ChatPanel", () => ({ ChatPanel: () => null }));
vi.mock("../../components/kb/KBSuggestionsPanel", () => ({
  KBSuggestionsPanel: () => null,
}));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", role: "admin", name: "Admin" } }),
}));
vi.mock("../../services/attachmentService", () => ({
  getAttachments: vi.fn(),
  uploadAttachments: vi.fn(),
  deleteAttachment: vi.fn(),
  downloadAttachment: vi.fn(),
  attachmentPreviewUrl: vi.fn(),
}));
vi.mock("../../services/ticketService", () => ({
  assignTicket: vi.fn(),
  toggleTicketAi: vi.fn(),
  createTicketNote: vi.fn(),
  deleteTicketNote: vi.fn(),
  getTicket: vi.fn(),
  getTicketHistory: vi.fn(),
  listTicketNotes: vi.fn(),
  reopenTicket: vi.fn(),
  resolveTicket: vi.fn(),
  updateClientObservation: vi.fn(),
  updateTicketStatus: vi.fn(),
}));
vi.mock("../../services/surveyService", () => ({
  getTicketSurvey: vi.fn(),
  submitSurvey: vi.fn(),
}));
vi.mock("../../services/userService", () => ({ getTechnicians: vi.fn() }));
vi.mock("../../services/tagService", () => ({
  getTags: vi.fn(),
  setTicketTags: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import TicketDetailPage from "../../pages/tickets/TicketDetailPage";
import * as ticketService from "../../services/ticketService";
import * as attachmentService from "../../services/attachmentService";
import * as surveyService from "../../services/surveyService";
import * as userService from "../../services/userService";
import * as tagService from "../../services/tagService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Quatro mapas locais**, nenhum concordando com o resto: `STATUS_LABEL`
 * duplicava o módulo, `PRIORITY_LABEL` era o nono mapa de prioridade,
 * `PRIORITY_COLOR` era o décimo — com um quarto esquema de cor, sky/yellow/
 * orange/red — e `CATEGORY_LABEL` era a terceira cópia das categorias.
 *
 * **Duas navegações vestidas de botão.** A trilha era um `<button
 * onClick={navigate(-1)}>` com a linha inteira dentro, então o nome acessível
 * do controle era "Tickets / HS-2026-0001" — a página de onde se vem e a página
 * onde se está, num controle só. E o "Editar ticket" navegava por `onClick`.
 */
const TICKET = {
  id: "t1",
  protocol: "HS-2026-0001",
  title: "Impressora não imprime",
  description: "Não imprime nada",
  status: "open",
  priority: "high",
  category: "hardware",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  equipments: [],
  tags: [],
  creator_name: "Cliente",
} as unknown as Awaited<ReturnType<typeof ticketService.getTicket>>;

/** Uma nota interna, para os casos do diálogo de exclusão. */
const NOTA = {
  id: "n1",
  ticket_id: "t1",
  author_id: "u9",
  author_name: "Bruno Lima",
  content: "Cliente ligou de novo.",
  created_at: new Date().toISOString(),
} as unknown as Awaited<
  ReturnType<typeof ticketService.listTicketNotes>
>[number];

/**
 * Leva a outro chamado sem remontar a página — o que o sino do Topbar faz.
 * A rota `/tickets/:id` não tem `key`, então a instância é a mesma.
 */
function IrPara({ destino }: { destino: string }) {
  const navegar = useNavigate();
  return (
    <button type="button" onClick={() => navegar(destino)}>
      ir para o outro chamado
    </button>
  );
}

async function montar(
  notas: (typeof NOTA)[] = [],
  chamado: typeof TICKET = TICKET,
  historico: unknown[] = [],
  extra?: ReactNode,
) {
  vi.mocked(ticketService.getTicket).mockResolvedValue(chamado as never);
  vi.mocked(ticketService.getTicketHistory).mockResolvedValue({
    items: historico,
  } as never);
  vi.mocked(ticketService.listTicketNotes).mockResolvedValue(notas as never);
  vi.mocked(attachmentService.getAttachments).mockResolvedValue({ items: [] } as never);
  vi.mocked(surveyService.getTicketSurvey).mockResolvedValue(null as never);
  vi.mocked(userService.getTechnicians).mockResolvedValue([] as never);
  vi.mocked(tagService.getTags).mockResolvedValue([] as never);

  render(
    <MemoryRouter initialEntries={["/tickets/t1"]}>
      {extra}
      <Routes>
        <Route path="/tickets/:id" element={<TicketDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Impressora não imprime" }),
    ).toBeInTheDocument(),
  );
}

describe("TicketDetailPage", () => {
  it("a trilha é um link para a lista, e o protocolo não finge ser clicável", async () => {
    await montar();
    expect(screen.getByRole("link", { name: "Tickets" })).toHaveAttribute(
      "href",
      "/tickets",
    );
    expect(
      screen.queryByRole("link", { name: /HS-2026-0001/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /HS-2026-0001/ }),
    ).not.toBeInTheDocument();
  });

  it("Editar ticket é um LINK, e não um botão", async () => {
    // Navegação é link. O botão tirava dele abrir em aba nova, menu de
    // contexto, destino na barra de status e o anúncio certo.
    await montar();
    expect(
      screen.getByRole("link", { name: /Editar ticket/ }),
    ).toHaveAttribute("href", "/tickets/t1/edit");
  });

  it("a prioridade fala a língua do módulo", async () => {
    // `PRIORITY_LABEL` daqui já dizia o feminino certo — foi este mapa que a
    // emenda E17 citou como o lado correto da divergência. O que saiu foi a
    // duplicação, não o texto.
    await montar();
    expect(screen.getAllByText("Alta").length).toBeGreaterThan(0);
  });

  it("a categoria sai do módulo, e não da terceira cópia", async () => {
    await montar();
    expect(screen.getAllByText("Hardware").length).toBeGreaterThan(0);
  });

  /**
   * O `confirm()` nativo desta tela saiu pela D9.3. Ele perguntava "Deletar
   * esta nota?" — a mesma frase para todas as notas da coluna —, e o
   * `confirm()` do jsdom devolve `undefined`: o caminho de exclusão da nota
   * NUNCA foi exercido por caso nenhum até aqui.
   *
   * O caso mede a FRASE do diálogo, e cobra o nome NO MESMO parágrafo — o
   * autor já está escrito na lista atrás, então contar ocorrências na tela
   * deixaria passar uma frase que não nomeia nada.
   */
  it("o diálogo se anuncia nomeando o que será excluído", async () => {
    // O título do `Modal` é o NOME ACESSÍVEL do diálogo: o componente põe
    // `role="dialog"` com `aria-labelledby` apontando para o `<h2>` do título.
    // É a primeira coisa que o leitor de tela anuncia — e um título "Excluir"
    // seco deixaria quem não vê a tela sem saber o quê. O corpo também nomeia,
    // mas o corpo vem DEPOIS do nome, e só se a pessoa continuar.
    await montar([NOTA]);

    fireEvent.click(await screen.findByText("Cliente ligou de novo."));
    fireEvent.click(await screen.findByRole("button", { name: "Deletar" }));

    expect(
      await screen.findByRole("dialog", { name: "Excluir nota interna" }),
    ).toBeInTheDocument();
  });

  it("excluir nota interna nomeia a nota, e só apaga ao confirmar", async () => {
    vi.mocked(ticketService.deleteTicketNote).mockClear();
    vi.mocked(ticketService.deleteTicketNote).mockResolvedValue(
      undefined as never,
    );
    await montar([NOTA]);

    fireEvent.click(await screen.findByText("Cliente ligou de novo."));
    fireEvent.click(await screen.findByRole("button", { name: "Deletar" }));

    const frase = await screen.findByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Bruno Lima");
    expect(ticketService.deleteTicketNote).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByText(/não pode ser desfeita/)).not.toBeInTheDocument(),
    );
    expect(ticketService.deleteTicketNote).not.toHaveBeenCalled();

    fireEvent.click(await screen.findByText("Cliente ligou de novo."));
    fireEvent.click(await screen.findByRole("button", { name: "Deletar" }));
    await screen.findByText(/não pode ser desfeita/);
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(ticketService.deleteTicketNote).toHaveBeenCalledWith("t1", "n1"),
    );
  });
});

/**
 * O backend exige `sla_breach_justification` para resolver chamado fora do
 * prazo (`105878d`), e o front nunca ganhou o campo. Em 11/09 isso estava em
 * produção: quem tentava concluir um chamado vencido via um toast de 4 s com o
 * nome técnico do campo, e o modal ficava aberto sem ter onde escrever — cada
 * nova tentativa devolvia o mesmo 422.
 *
 * O campo aparece quando o SERVIDOR tem certeza: marca de violação ligada (que
 * ele sempre respeita), ou o próprio 422. Prever pela data no front foi
 * recusado — sem a pausa acumulada, o cálculo acha vencido o que não está, e o
 * relatório de SLA violado filtra pela presença da justificativa. Pela mesma
 * razão, nada pode sobrar de um pedido para o outro: um texto esquecido que
 * saísse no corpo de um chamado sem violação o poria no relatório.
 */
describe("justificativa de SLA violado", () => {
  const DETAIL_422 =
    "Este chamado passou do prazo (o de resolução). Informe 'sla_breach_justification' com o motivo do atraso para resolvê-lo.";
  const ERRO_422 = { response: { status: 422, data: { detail: DETAIL_422 } } };
  const EM_ATENDIMENTO = { ...TICKET, status: "in_progress" } as typeof TICKET;
  const VENCIDO = { ...EM_ATENDIMENTO, sla_resolve_breach: true } as typeof TICKET;

  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
    vi.mocked(ticketService.resolveTicket).mockReset();
    vi.mocked(ticketService.updateTicketStatus).mockReset();
  });

  async function abrirConclusao() {
    fireEvent.click(screen.getAllByRole("button", { name: "Concluir ticket" })[0]);
    const dialogo = await screen.findByRole("dialog", { name: "Concluir ticket" });
    fireEvent.change(within(dialogo).getByLabelText("Nota de resolução"), {
      target: { value: "Placa trocada." },
    });
    return dialogo;
  }

  async function abrirStatus() {
    fireEvent.click(screen.getByRole("button", { name: "Alterar status" }));
    return screen.findByRole("dialog", { name: "Alterar status" });
  }

  it("com a marca de violação ligada, o motivo é pedido antes de concluir", async () => {
    vi.mocked(ticketService.resolveTicket).mockResolvedValue({
      ...VENCIDO,
      status: "resolved",
    } as never);
    await montar([], VENCIDO);
    const dialogo = await abrirConclusao();

    expect(
      within(dialogo).getByText(/passou do prazo \(o de resolução\)/),
    ).toBeInTheDocument();
    // Aberto já com o aviso, ele é conteúdo do diálogo, e não região viva:
    // anunciá-lo de novo leria a consequência fora de ordem (emenda E12).
    expect(within(dialogo).queryByRole("status")).not.toBeInTheDocument();
    const campo = within(dialogo).getByLabelText("Motivo do atraso *");
    // O limite do backend. Sem ele, o excedente voltaria como 422 de
    // validação — que não é pedido de justificativa e cai no toast em inglês.
    expect(campo).toHaveAttribute("maxlength", "2000");
    const confirmar = within(dialogo).getByRole("button", { name: "Confirmar conclusão" });
    expect(confirmar).toBeDisabled();

    fireEvent.change(campo, { target: { value: "Peça importada atrasou." } });
    expect(confirmar).toBeEnabled();
    fireEvent.click(confirmar);

    await waitFor(() =>
      expect(vi.mocked(ticketService.resolveTicket).mock.lastCall).toEqual([
        "t1",
        "Placa trocada.",
        "Peça importada atrasou.",
      ]),
    );
  });

  it("sem marca, conclui sem pedir motivo e sem mandar justificativa", async () => {
    vi.mocked(ticketService.resolveTicket).mockResolvedValue({
      ...EM_ATENDIMENTO,
      status: "resolved",
    } as never);
    await montar([], EM_ATENDIMENTO);
    const dialogo = await abrirConclusao();

    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar conclusão" }));

    await waitFor(() =>
      expect(vi.mocked(ticketService.resolveTicket).mock.lastCall).toEqual([
        "t1",
        "Placa trocada.",
        undefined,
      ]),
    );
  });

  it("o 422 da justificativa abre o campo no modal, e não vira toast", async () => {
    vi.mocked(ticketService.resolveTicket)
      .mockRejectedValueOnce(ERRO_422)
      .mockResolvedValueOnce({ ...EM_ATENDIMENTO, status: "resolved" } as never);
    await montar([], EM_ATENDIMENTO);
    const dialogo = await abrirConclusao();
    const confirmar = within(dialogo).getByRole("button", { name: "Confirmar conclusão" });
    fireEvent.click(confirmar);

    const campo = await within(dialogo).findByLabelText("Motivo do atraso *");
    expect(toast.error).not.toHaveBeenCalled();
    // O aviso CHEGOU: aqui ele é região viva.
    expect(within(dialogo).getByRole("status")).toHaveTextContent(
      "passou do prazo (o de resolução)",
    );
    // A pessoa acabou de clicar em confirmar: o foco vai para o que falta, e
    // quem chega pelo foco ouve o porquê na descrição do campo — região viva
    // inserida já preenchida não tem anúncio garantido.
    await waitFor(() => expect(campo).toHaveFocus());
    expect(campo).toHaveAccessibleDescription(
      expect.stringContaining("passou do prazo (o de resolução)"),
    );
    // A nota que a pessoa escreveu não se perde no caminho.
    expect(within(dialogo).getByLabelText("Nota de resolução")).toHaveValue(
      "Placa trocada.",
    );
    expect(confirmar).toBeDisabled();

    fireEvent.change(campo, { target: { value: "Peça importada atrasou." } });
    fireEvent.click(confirmar);

    await waitFor(() =>
      expect(vi.mocked(ticketService.resolveTicket).mock.lastCall).toEqual([
        "t1",
        "Placa trocada.",
        "Peça importada atrasou.",
      ]),
    );
  });

  it("outro erro da API continua no toast, e não pede motivo", async () => {
    vi.mocked(ticketService.resolveTicket).mockRejectedValue({
      response: { status: 409, data: { detail: "Este chamado já foi resolvido." } },
    });
    await montar([], EM_ATENDIMENTO);
    const dialogo = await abrirConclusao();
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar conclusão" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();
  });

  it("Cancelar descarta o motivo e o veredito do 422", async () => {
    // Antes, só o X, o Esc e o fundo limpavam. O Cancelar guardava o texto e o
    // 422 — e o próximo chamado aberto na mesma tela herdava os dois.
    vi.mocked(ticketService.resolveTicket).mockRejectedValueOnce(ERRO_422);
    await montar([], EM_ATENDIMENTO);
    let dialogo = await abrirConclusao();
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar conclusão" }));
    fireEvent.change(await within(dialogo).findByLabelText("Motivo do atraso *"), {
      target: { value: "Peça importada atrasou." },
    });

    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Concluir ticket" })).not.toBeInTheDocument(),
    );

    dialogo = await abrirConclusao();
    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();
  });

  it("trocar de chamado na mesma tela não leva o motivo junto", async () => {
    // O sino leva a outro chamado sem remontar a página. Os dois estão
    // vencidos, então o campo aparece nos dois — e no segundo tem de vir vazio.
    const OUTRO_VENCIDO = { ...VENCIDO, id: "t2", protocol: "HS-2026-0002" } as typeof TICKET;
    await montar([], VENCIDO, [], <IrPara destino="/tickets/t2" />);
    vi.mocked(ticketService.getTicket).mockImplementation(
      async (id: string) => (id === "t2" ? OUTRO_VENCIDO : VENCIDO) as never,
    );
    const dialogo = await abrirConclusao();
    fireEvent.change(within(dialogo).getByLabelText("Motivo do atraso *"), {
      target: { value: "Peça importada atrasou." },
    });

    fireEvent.click(screen.getByText("ir para o outro chamado"));

    await waitFor(() => expect(ticketService.getTicket).toHaveBeenLastCalledWith("t2"));
    await waitFor(() =>
      expect(within(dialogo).getByLabelText("Motivo do atraso *")).toHaveValue(""),
    );
  });

  it("fechar com a resposta a caminho não engole o 422", async () => {
    // Fechado antes de o 422 chegar, o modal sumia e o erro também: nem toast,
    // nem campo, e o chamado continuava sem resolver.
    let rejeitar: (motivo: unknown) => void = () => {};
    vi.mocked(ticketService.resolveTicket).mockReturnValueOnce(
      new Promise((_, r) => {
        rejeitar = r;
      }) as never,
    );
    await montar([], EM_ATENDIMENTO);
    const dialogo = await abrirConclusao();
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar conclusão" }));

    fireEvent.keyDown(within(dialogo).getByLabelText("Nota de resolução"), {
      key: "Escape",
    });
    expect(screen.getByRole("dialog", { name: "Concluir ticket" })).toBeInTheDocument();

    rejeitar(ERRO_422);
    expect(await within(dialogo).findByLabelText("Motivo do atraso *")).toBeInTheDocument();
  });

  it("Alterar status pede o motivo só quando o destino é Resolvido", async () => {
    vi.mocked(ticketService.updateTicketStatus).mockResolvedValue({
      ...EM_ATENDIMENTO,
      status: "resolved",
    } as never);
    await montar([], { ...EM_ATENDIMENTO, sla_response_breach: true } as typeof TICKET);
    const dialogo = await abrirStatus();
    const status = within(dialogo).getByLabelText("Novo status");

    fireEvent.change(status, { target: { value: "awaiting_client" } });
    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();

    fireEvent.change(status, { target: { value: "resolved" } });
    expect(
      within(dialogo).getByText(/passou do prazo \(o de primeira resposta\)/),
    ).toBeInTheDocument();
    // Dois campos de "motivo" lado a lado induziam a escrever a justificativa
    // no comentário — que o cliente vê no histórico dele.
    expect(within(dialogo).queryAllByPlaceholderText(/motivo/i)).toHaveLength(0);
    const confirmar = within(dialogo).getByRole("button", { name: "Confirmar" });
    expect(confirmar).toBeDisabled();

    fireEvent.change(within(dialogo).getByLabelText("Motivo do atraso *"), {
      target: { value: "Peça importada atrasou." },
    });
    fireEvent.click(confirmar);

    await waitFor(() =>
      expect(vi.mocked(ticketService.updateTicketStatus).mock.lastCall).toEqual([
        "t1",
        "resolved",
        undefined,
        "Peça importada atrasou.",
      ]),
    );
  });

  it("o texto que ficou no campo não vai de carona para outro status", async () => {
    vi.mocked(ticketService.updateTicketStatus).mockResolvedValue({
      ...VENCIDO,
      status: "awaiting_client",
    } as never);
    await montar([], VENCIDO);
    const dialogo = await abrirStatus();
    const status = within(dialogo).getByLabelText("Novo status");

    fireEvent.change(status, { target: { value: "resolved" } });
    fireEvent.change(within(dialogo).getByLabelText("Motivo do atraso *"), {
      target: { value: "Peça importada atrasou." },
    });
    fireEvent.change(status, { target: { value: "awaiting_client" } });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar" }));

    await waitFor(() =>
      expect(vi.mocked(ticketService.updateTicketStatus).mock.lastCall).toEqual([
        "t1",
        "awaiting_client",
        undefined,
        undefined,
      ]),
    );
  });

  it("no Alterar status, o 422 da justificativa também abre o campo", async () => {
    vi.mocked(ticketService.updateTicketStatus)
      .mockRejectedValueOnce(ERRO_422)
      .mockResolvedValueOnce({ ...EM_ATENDIMENTO, status: "resolved" } as never);
    await montar([], EM_ATENDIMENTO);
    const dialogo = await abrirStatus();
    fireEvent.change(within(dialogo).getByLabelText("Novo status"), {
      target: { value: "resolved" },
    });
    const confirmar = within(dialogo).getByRole("button", { name: "Confirmar" });
    fireEvent.click(confirmar);

    const campo = await within(dialogo).findByLabelText("Motivo do atraso *");
    expect(toast.error).not.toHaveBeenCalled();
    fireEvent.change(campo, { target: { value: "Peça importada atrasou." } });
    fireEvent.click(confirmar);

    await waitFor(() =>
      expect(vi.mocked(ticketService.updateTicketStatus).mock.lastCall).toEqual([
        "t1",
        "resolved",
        undefined,
        "Peça importada atrasou.",
      ]),
    );
  });

  it("no Alterar status, outro erro da API continua no toast", async () => {
    vi.mocked(ticketService.updateTicketStatus).mockRejectedValue({
      response: { status: 409, data: { detail: "Transição de status não permitida." } },
    });
    await montar([], EM_ATENDIMENTO);
    const dialogo = await abrirStatus();
    fireEvent.change(within(dialogo).getByLabelText("Novo status"), {
      target: { value: "resolved" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();
  });

  it("fechar pelo X também descarta o veredito do 422", async () => {
    vi.mocked(ticketService.resolveTicket).mockRejectedValueOnce(ERRO_422);
    await montar([], EM_ATENDIMENTO);
    let dialogo = await abrirConclusao();
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar conclusão" }));
    await within(dialogo).findByLabelText("Motivo do atraso *");

    fireEvent.click(within(dialogo).getByRole("button", { name: "Fechar" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Concluir ticket" })).not.toBeInTheDocument(),
    );

    dialogo = await abrirConclusao();
    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();
  });

  it("no Alterar status, Cancelar também descarta o veredito do 422", async () => {
    vi.mocked(ticketService.updateTicketStatus).mockRejectedValueOnce(ERRO_422);
    await montar([], EM_ATENDIMENTO);
    let dialogo = await abrirStatus();
    fireEvent.change(within(dialogo).getByLabelText("Novo status"), {
      target: { value: "resolved" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar" }));
    await within(dialogo).findByLabelText("Motivo do atraso *");

    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Alterar status" })).not.toBeInTheDocument(),
    );

    dialogo = await abrirStatus();
    fireEvent.change(within(dialogo).getByLabelText("Novo status"), {
      target: { value: "resolved" },
    });
    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();
  });

  it("no Alterar status, a resposta a caminho trava o fechar e o destino", async () => {
    // Trocar o destino ou fechar com a requisição correndo faria o 422 chegar
    // sem ter onde aparecer: sem toast e sem campo.
    let rejeitar: (motivo: unknown) => void = () => {};
    vi.mocked(ticketService.updateTicketStatus).mockReturnValueOnce(
      new Promise((_, r) => {
        rejeitar = r;
      }) as never,
    );
    await montar([], EM_ATENDIMENTO);
    const dialogo = await abrirStatus();
    const status = within(dialogo).getByLabelText("Novo status");
    fireEvent.change(status, { target: { value: "resolved" } });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar" }));

    expect(status).toBeDisabled();
    fireEvent.keyDown(within(dialogo).getByLabelText("Comentário (opcional)"), {
      key: "Escape",
    });
    expect(screen.getByRole("dialog", { name: "Alterar status" })).toBeInTheDocument();

    rejeitar(ERRO_422);
    expect(await within(dialogo).findByLabelText("Motivo do atraso *")).toBeInTheDocument();
  });

  it("o histórico mostra a justificativa com nome legível e o texto", async () => {
    // Antes, a entrada aparecia com o nome cru do campo, e o texto — a razão de
    // a entrada existir — não era desenhado.
    await montar([], TICKET, [
      {
        id: "h1",
        ticket_id: "t1",
        user_id: "u1",
        user_name: "Admin",
        field: "sla_breach_justification",
        old_value: null,
        new_value: "Peça importada atrasou.",
        comment: "Justificativa do SLA violado",
        created_at: new Date().toISOString(),
      },
    ]);
    fireEvent.click(screen.getByText("Atividade"));

    expect(
      await screen.findByText("Peça importada atrasou.", { exact: false }),
    ).toBeInTheDocument();
    // O rótulo aparece UMA vez. O comentário que o backend grava junto só o
    // repete — desenhado, diria a mesma coisa duas vezes, entre aspas.
    expect(screen.getAllByText(/Justificativa do SLA violado/)).toHaveLength(1);
    expect(screen.queryByText("sla_breach_justification")).not.toBeInTheDocument();
  });
});
