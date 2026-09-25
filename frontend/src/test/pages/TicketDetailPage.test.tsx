import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../components/chat/ChatPanel", () => ({ ChatPanel: () => null }));
vi.mock("../../components/kb/KBSuggestionsPanel", () => ({
  KBSuggestionsPanel: () => null,
}));
// O papel e lido a CADA render (dentro do `useAuth`), entao a variavel pode
// ser trocada por teste — o `vi.mock` so e hoisted na definicao da fabrica.
let papelDoUsuario = "admin";
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", role: papelDoUsuario, name: "Admin" } }),
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
  createTicketCall: vi.fn(),
  createTicketNote: vi.fn(),
  deleteTicketNote: vi.fn(),
  getTicket: vi.fn(),
  getTicketHistory: vi.fn(),
  listTicketNotes: vi.fn(),
  reopenTicket: vi.fn(),
  resolveTicket: vi.fn(),
  extendSla: vi.fn(),
  previewSlaExtension: vi.fn(),
  updateClientObservation: vi.fn(),
  updateTicketPriority: vi.fn(),
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
import { escolherNoMenu } from "../helpers/menu";

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
  // O contrato do relógio de SLA (23/09/2026). Sem prazo nenhum aqui: o chip
  // não desenha, e os casos desta tela não são sobre ele.
  sla_response_vence_em: null,
  sla_resolve_vence_em: null,
  sla_response_restante_min: null,
  sla_resolve_restante_min: null,
  sla_response_total_min: null,
  sla_resolve_total_min: null,
  expediente: null,
  sla_resolve_extension_total_min: 0,
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

    // O campo é um menu, e o menu escolhe pelo RÓTULO — "Aguardando cliente" é
    // o `awaiting_client`, "Resolvido" é o `resolved`. O painel abre num portal
    // fora do diálogo, e quem cuida disso é o auxiliar.
    escolherNoMenu(status, "Aguardando cliente");
    expect(within(dialogo).queryByLabelText("Motivo do atraso *")).not.toBeInTheDocument();

    escolherNoMenu(status, "Resolvido");
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

    escolherNoMenu(status, "Resolvido");
    fireEvent.change(within(dialogo).getByLabelText("Motivo do atraso *"), {
      target: { value: "Peça importada atrasou." },
    });
    escolherNoMenu(status, "Aguardando cliente");
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
    escolherNoMenu(within(dialogo).getByLabelText("Novo status"), "Resolvido");
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
    escolherNoMenu(within(dialogo).getByLabelText("Novo status"), "Resolvido");
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
    escolherNoMenu(within(dialogo).getByLabelText("Novo status"), "Resolvido");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Confirmar" }));
    await within(dialogo).findByLabelText("Motivo do atraso *");

    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Alterar status" })).not.toBeInTheDocument(),
    );

    dialogo = await abrirStatus();
    escolherNoMenu(within(dialogo).getByLabelText("Novo status"), "Resolvido");
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
    escolherNoMenu(status, "Resolvido");
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


/**
 * A triagem (22/09/2026).
 *
 * O chamado nasce sem prioridade, e quem a define e tecnico ou administrador.
 * O que estes casos prendem: o cliente nao ve o controle, a ausencia se le em
 * palavras, e a triagem passa pelo endpoint de prioridade — nao pelo PATCH
 * generico, que abriria junto titulo, categoria e produto.
 */
describe("prioridade na triagem", () => {
  const SEM_PRIORIDADE = { ...TICKET, priority: null } as typeof TICKET;

  beforeEach(() => {
    papelDoUsuario = "admin";
    vi.mocked(ticketService.updateTicketPriority).mockReset();
  });

  it("antes da triagem a tela diz 'Sem prioridade' nos tres lugares", async () => {
    // TRES: o cabecalho (ao lado do status) e o painel de Propriedades, que
    // ficam a vista; e a ficha "Informacoes do chamado", que mora na aba
    // Detalhes. Contar e o que distingue um deles regredindo —
    // `toBeGreaterThan(0)` continuava verde com dois dos tres quebrados, e foi
    // a mutacao do painel que mostrou isso.
    await montar([], SEM_PRIORIDADE);
    expect(screen.getAllByText("Sem prioridade")).toHaveLength(2);
    // E nao inventa um nivel no lugar.
    expect(screen.queryByText("Média")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Detalhes"));
    expect(screen.getAllByText("Sem prioridade")).toHaveLength(3);
  });

  it("o cliente nao ve controle de prioridade", async () => {
    papelDoUsuario = "client";
    await montar([], SEM_PRIORIDADE);
    expect(
      screen.queryByRole("button", { name: /prioridade/i }),
    ).not.toBeInTheDocument();
    // Mas continua vendo o estado do chamado.
    expect(screen.getAllByText("Sem prioridade").length).toBeGreaterThan(0);
  });

  it("o cliente com a secao de acoes ABERTA ainda nao ve a triagem", async () => {
    // O caso acima passa pelo guarda de FORA (`isStaff || canReopen`): com o
    // chamado aberto, o cliente nao recebe a secao de Acoes, e o guarda do
    // botao nunca chega a ser consultado. A mutacao mostrou isso — trocar o
    // `isStaff` do botao por `true` nao derrubava nada.
    //
    // Aqui a secao EXISTE para o cliente: chamado dele, resolvido, dentro do
    // prazo de reabertura. Ele ve "Reabrir chamado" ao lado, e e o guarda do
    // proprio botao que precisa segurar a triagem.
    papelDoUsuario = "client";
    const amanha = new Date(Date.now() + 86_400_000).toISOString();
    await montar([], {
      ...SEM_PRIORIDADE,
      status: "resolved",
      creator_id: "u1",
      reopen_deadline: amanha,
    } as typeof TICKET);

    // Dois controles levam a reabertura (a barra lateral e o rodape da
    // conversa); o que importa e que a secao de Acoes esta na tela.
    expect(screen.getAllByRole("button", { name: /Reabrir/i }).length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: /prioridade/i }),
    ).not.toBeInTheDocument();
  });

  it.each(["admin", "technician"])("%s pode definir a prioridade", async (papel) => {
    papelDoUsuario = papel;
    await montar([], SEM_PRIORIDADE);
    expect(
      screen.getByRole("button", { name: "Definir prioridade" }),
    ).toBeInTheDocument();
  });

  it("com prioridade ja definida o botao diz 'Alterar'", async () => {
    await montar([], TICKET);
    expect(
      screen.getByRole("button", { name: "Alterar prioridade" }),
    ).toBeInTheDocument();
  });

  it("confirmar chama o endpoint de prioridade e fecha o modal", async () => {
    vi.mocked(ticketService.updateTicketPriority).mockResolvedValue({
      ...SEM_PRIORIDADE,
      priority: "critical",
    } as never);
    await montar([], SEM_PRIORIDADE);

    fireEvent.click(screen.getByRole("button", { name: "Definir prioridade" }));
    const modal = screen.getByRole("dialog");
    // O campo e um menu (`SelectMenu`, D9.2), nao um `<select>`: o gatilho tem
    // `role="combobox"`, a escolha e pelo ROTULO, e o painel abre num portal
    // fora do dialogo. Quem cuida dos dois ultimos e o auxiliar de menu.
    escolherNoMenu(
      within(modal).getByRole("combobox", { name: "Prioridade" }),
      "Crítica",
    );
    fireEvent.click(within(modal).getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(ticketService.updateTicketPriority).toHaveBeenCalledWith("t1", "critical"),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});


/**
 * Estender o SLA de resolução (23/09/2026).
 *
 * O que estes casos prendem: o cliente nunca vê o botão mas vê o RESULTADO, o
 * novo prazo do modal vem do backend, e a concessão passa pelo endpoint
 * próprio — nunca por um cálculo de calendário na tela.
 */
describe("estender SLA de resolução", () => {
  const COM_PRAZO = {
    ...TICKET,
    sla_resolve_due_at: "2026-09-24T15:11:00Z",
    sla_resolve_vence_em: "2026-09-24T15:11:00Z",
    sla_resolve_restante_min: 692,
    sla_resolve_total_min: 720,
    expediente: {
      agora: "2026-09-23T12:39:00Z",
      aberto: true,
      proxima_virada: "2026-09-23T20:00:00Z",
      fuso: "America/Sao_Paulo",
    },
  } as typeof TICKET;

  const PRORROGADO = {
    ...COM_PRAZO,
    sla_resolve_extension_total_min: 1620,
  } as typeof TICKET;

  beforeEach(() => {
    papelDoUsuario = "admin";
    vi.mocked(ticketService.extendSla).mockReset();
    vi.mocked(ticketService.previewSlaExtension).mockReset();
  });

  it("a equipe vê a ação de estender", async () => {
    await montar([], COM_PRAZO);
    expect(screen.getByRole("button", { name: "Estender SLA" })).toBeInTheDocument();
  });

  it("o cliente NÃO vê a ação", async () => {
    papelDoUsuario = "client";
    await montar([], COM_PRAZO);
    expect(screen.queryByRole("button", { name: "Estender SLA" })).not.toBeInTheDocument();
  });

  it("sem prazo de resolução não há o que estender", async () => {
    await montar([], TICKET);
    expect(screen.queryByRole("button", { name: "Estender SLA" })).not.toBeInTheDocument();
  });

  it("o indicativo aparece quando há extensão — e o CLIENTE também o vê", async () => {
    papelDoUsuario = "client";
    await montar([], PRORROGADO);
    expect(screen.getByText(/SLA estendido/)).toBeInTheDocument();
    expect(screen.getByText(/\+3 dias úteis/)).toBeInTheDocument();
  });

  it("sem extensão, nenhum indicativo", async () => {
    await montar([], COM_PRAZO);
    expect(screen.queryByText(/SLA estendido/)).not.toBeInTheDocument();
  });

  it("o novo prazo do modal vem do BACKEND, não de conta na tela", async () => {
    vi.mocked(ticketService.previewSlaExtension).mockResolvedValue({
      days: 3,
      business_minutes: 1620,
      prazo_atual: "2026-09-24T15:11:00Z",
      novo_prazo: "2026-09-29T15:11:00Z",
    } as never);
    await montar([], COM_PRAZO);

    fireEvent.click(screen.getByRole("button", { name: "Estender SLA" }));
    const modal = screen.getByRole("dialog");
    escolherNoMenu(
      within(modal).getByRole("combobox", { name: "Prazo adicional" }),
      "3 dias úteis",
    );

    await waitFor(() =>
      expect(ticketService.previewSlaExtension).toHaveBeenCalledWith("t1", 3),
    );
    expect(await within(modal).findByText("29/09/2026 às 12:11")).toBeInTheDocument();
    expect(within(modal).getByText("24/09/2026 às 12:11")).toBeInTheDocument();
  });

  it("a justificativa avisa que o cliente vai ler", async () => {
    await montar([], COM_PRAZO);
    fireEvent.click(screen.getByRole("button", { name: "Estender SLA" }));
    expect(
      screen.getByText(/ficará visível para o cliente/i),
    ).toBeInTheDocument();
  });

  it("sem justificativa o botão não confirma", async () => {
    vi.mocked(ticketService.previewSlaExtension).mockResolvedValue({
      days: 3,
      business_minutes: 1620,
      prazo_atual: "2026-09-24T15:11:00Z",
      novo_prazo: "2026-09-29T15:11:00Z",
    } as never);
    await montar([], COM_PRAZO);

    fireEvent.click(screen.getByRole("button", { name: "Estender SLA" }));
    const modal = screen.getByRole("dialog");
    escolherNoMenu(
      within(modal).getByRole("combobox", { name: "Prazo adicional" }),
      "3 dias úteis",
    );

    expect(within(modal).getByRole("button", { name: "Estender prazo" })).toBeDisabled();
  });

  it("confirmar chama o endpoint próprio e fecha o modal", async () => {
    vi.mocked(ticketService.previewSlaExtension).mockResolvedValue({
      days: 3,
      business_minutes: 1620,
      prazo_atual: "2026-09-24T15:11:00Z",
      novo_prazo: "2026-09-29T15:11:00Z",
    } as never);
    vi.mocked(ticketService.extendSla).mockResolvedValue(PRORROGADO as never);
    await montar([], COM_PRAZO);

    fireEvent.click(screen.getByRole("button", { name: "Estender SLA" }));
    const modal = screen.getByRole("dialog");
    escolherNoMenu(
      within(modal).getByRole("combobox", { name: "Prazo adicional" }),
      "3 dias úteis",
    );
    fireEvent.change(within(modal).getByLabelText(/Justificativa ao cliente/), {
      target: { value: "Aguardando peça de reposição do fabricante." },
    });
    fireEvent.click(within(modal).getByRole("button", { name: "Estender prazo" }));

    await waitFor(() =>
      expect(ticketService.extendSla).toHaveBeenCalledWith(
        "t1",
        3,
        "Aguardando peça de reposição do fabricante.",
      ),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("o cliente vê a extensão na Atividade, com prazo e justificativa", async () => {
    papelDoUsuario = "client";
    await montar([], PRORROGADO, [
      {
        id: "h1",
        ticket_id: "t1",
        user_id: "u9",
        user_name: "Rickelme David",
        field: "sla_extension",
        old_value: "2026-09-24T15:11:00Z",
        new_value: "2026-09-29T15:11:00Z",
        comment: "Aguardando peça de reposição do fabricante.",
        created_at: new Date().toISOString(),
      },
    ]);
    fireEvent.click(screen.getByText("Atividade"));

    expect(await screen.findByText("SLA de resolução estendido")).toBeInTheDocument();
    expect(screen.getByText(/Novo prazo: 29\/09\/2026 às 12:11/)).toBeInTheDocument();
    expect(
      screen.getByText(/Aguardando peça de reposição do fabricante\./),
    ).toBeInTheDocument();
  });
});

// ── Ligar para cliente ────────────────────────────────────────

/** Erro no formato que o axios entrega, para o `toastApiError` ler. */
function erroDaApi(status: number, detail?: string) {
  return {
    request: {},
    response: { status, data: detail ? { detail } : {}, headers: {} },
  };
}

const TENTATIVA = {
  id: "c1",
  creation_status: "confirmed",
  created_at: new Date().toISOString(),
};

describe("TicketDetailPage — Ligar para cliente", () => {
  beforeEach(() => {
    papelDoUsuario = "admin";
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
    vi.mocked(ticketService.createTicketCall).mockReset();
  });

  const botao = () => screen.getByRole("button", { name: /Ligar para cliente/ });

  it("o administrador vê a ação", async () => {
    await montar();
    expect(botao()).toBeInTheDocument();
  });

  it("o técnico vê a ação", async () => {
    papelDoUsuario = "technician";
    await montar();
    expect(botao()).toBeInTheDocument();
  });

  it("o cliente NÃO vê a ação — mesmo com o card de Ações na tela", async () => {
    // Esconder não é autorizar: o backend recusa cliente com 403 de qualquer
    // jeito. Isto é para não oferecer o que não é dele.
    //
    // ⚠️ O chamado aqui é `resolved` com prazo de reabertura aberto DE
    // PROPÓSITO. Num chamado `open`, o card "Ações" inteiro não renderiza
    // para cliente — `{(isStaff || canReopen) && ...}` —, e o caso passaria
    // sem provar nada sobre o botão. Medido: tirar o `isStaff` da linha do
    // botão não fazia este caso falhar. Com "Reabrir chamado" na tela, o
    // card existe, e a única coisa que segura o botão é a guarda dele.
    papelDoUsuario = "client";
    const daquiUmaSemana = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();
    await montar([], {
      ...TICKET,
      status: "resolved",
      creator_id: "u1",
      reopen_deadline: daquiUmaSemana,
    } as unknown as typeof TICKET);

    // O card existe — esta é a pré-condição que dá sentido ao caso.
    // Há dois na tela (o do corpo e o do card lateral) — o que importa é
    // que o card exista.
    expect(screen.getAllByRole("button", { name: /Reabrir chamado/ }).length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: /Ligar para cliente/ }),
    ).not.toBeInTheDocument();
  });

  it("some em chamado cancelado, que o backend não aceita", async () => {
    await montar([], { ...TICKET, status: "cancelled" } as typeof TICKET);
    expect(
      screen.queryByRole("button", { name: /Ligar para cliente/ }),
    ).not.toBeInTheDocument();
  });

  it("CONTINUA em chamado resolvido — a telefonia aceita esse estado", async () => {
    // `isClosed` da tela inclui `resolved`; a telefonia NÃO. Reaproveitar
    // aquele guarda esconderia o botão numa situação válida — ligar para
    // confirmar que o problema resolveu é exatamente um caso de uso.
    await montar([], { ...TICKET, status: "resolved" } as typeof TICKET);
    expect(botao()).toBeInTheDocument();
  });

  it("um clique manda uma requisição, com o id do chamado", async () => {
    vi.mocked(ticketService.createTicketCall).mockResolvedValue(TENTATIVA as never);
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(ticketService.createTicketCall).toHaveBeenCalledWith("t1"),
    );
    expect(ticketService.createTicketCall).toHaveBeenCalledTimes(1);
  });

  it("durante a espera o botão bloqueia e anuncia que está ligando", async () => {
    let libera: (v: unknown) => void = () => {};
    vi.mocked(ticketService.createTicketCall).mockReturnValue(
      new Promise((r) => {
        libera = r;
      }) as never,
    );
    await montar();
    fireEvent.click(botao());

    const emEspera = await screen.findByRole("button", { name: /Ligando/ });
    expect(emEspera).toBeDisabled();
    expect(emEspera).toHaveAttribute("aria-busy", "true");

    libera(TENTATIVA);
    await waitFor(() => expect(botao()).toBeEnabled());
  });

  it("clique duplo rápido continua sendo UMA requisição", async () => {
    // O telefone do cliente tocando duas vezes é o defeito que este caso
    // impede. O backend tem trava própria; isto evita chegar lá.
    //
    // Os cliques vão dentro de UM `act` só, e isso é o ponto: fora dele, o
    // `fireEvent` faz flush do estado a cada chamada, o botão já volta
    // `disabled` no segundo clique e a guarda de dentro do handler nunca é
    // exercitada — medido, a mutação que removia `|| ligando` sobrevivia.
    // Dois cliques antes de a tela repintar é o que acontece de verdade
    // quando alguém clica rápido.
    let libera: (v: unknown) => void = () => {};
    vi.mocked(ticketService.createTicketCall).mockReturnValue(
      new Promise((r) => {
        libera = r;
      }) as never,
    );
    await montar();
    const b = botao();
    act(() => {
      fireEvent.click(b);
      fireEvent.click(b);
      fireEvent.click(b);
    });

    await screen.findByRole("button", { name: /Ligando/ });
    expect(ticketService.createTicketCall).toHaveBeenCalledTimes(1);
    libera(TENTATIVA);
  });

  it("e o botão desabilitado barra o clique seguinte, depois do repintar", async () => {
    // A segunda linha de defesa, provada separadamente: depois que a tela
    // repinta, o próprio `disabled` impede o evento de sair.
    let libera: (v: unknown) => void = () => {};
    vi.mocked(ticketService.createTicketCall).mockReturnValue(
      new Promise((r) => {
        libera = r;
      }) as never,
    );
    await montar();
    fireEvent.click(botao());
    const emEspera = await screen.findByRole("button", { name: /Ligando/ });

    fireEvent.click(emEspera);
    fireEvent.click(emEspera);

    expect(ticketService.createTicketCall).toHaveBeenCalledTimes(1);
    libera(TENTATIVA);
  });

  it("confirmed avisa que a ligação saiu", async () => {
    vi.mocked(ticketService.createTicketCall).mockResolvedValue(TENTATIVA as never);
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Ligação iniciada com sucesso."),
    );
  });

  it("rejected avisa a falha sem detalhar o fornecedor", async () => {
    vi.mocked(ticketService.createTicketCall).mockResolvedValue({
      ...TENTATIVA,
      creation_status: "rejected",
    } as never);
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível iniciar a ligação."),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("unavailable diz que a telefonia está fora", async () => {
    vi.mocked(ticketService.createTicketCall).mockResolvedValue({
      ...TENTATIVA,
      creation_status: "unavailable",
    } as never);
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Serviço de telefonia indisponível no momento.",
      ),
    );
  });

  it("indeterminate manda NÃO repetir — pode ter havido efeito", async () => {
    vi.mocked(ticketService.createTicketCall).mockResolvedValue({
      ...TENTATIVA,
      creation_status: "indeterminate",
    } as never);
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Não foi possível confirmar o resultado da ligação.",
        { description: "Não tente novamente imediatamente." },
      ),
    );
  });

  it("409 mostra o motivo que o backend deu", async () => {
    // ⚠️ O motivo mudou em 25/09/2026. Este caso usava a mensagem da
    // antirrepetição temporal ("há poucos minutos"), que saiu do backend com a
    // regra. O 409 continua existindo — hoje quem o produz é o lock de
    // concorrência, e o tratamento do front sempre foi genérico: ele mostra o
    // `detail` que vier, sem conhecer nenhum motivo em particular.
    vi.mocked(ticketService.createTicketCall).mockRejectedValue(
      erroDaApi(409, "Já há uma ligação em andamento para este chamado."),
    );
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível iniciar a ligação.", {
        description: "Já há uma ligação em andamento para este chamado.",
      }),
    );
  });

  it("409 sem detail cai na mensagem genérica da casa", async () => {
    // Prova que o front NÃO depende de conhecer o motivo: um 409 de qualquer
    // regra futura continua legível.
    vi.mocked(ticketService.createTicketCall).mockRejectedValue(erroDaApi(409));
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível iniciar a ligação.", {
        description:
          "Esta ação conflita com o estado atual do registro. Atualize a página e tente de novo.",
      }),
    );
  });

  it("422 mostra o motivo que o backend deu", async () => {
    vi.mocked(ticketService.createTicketCall).mockRejectedValue(
      erroDaApi(422, "Você não tem ramal de telefonia configurado."),
    );
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível iniciar a ligação.", {
        description: "Você não tem ramal de telefonia configurado.",
      }),
    );
  });

  it("403 cai na mensagem de permissão da casa", async () => {
    vi.mocked(ticketService.createTicketCall).mockRejectedValue(erroDaApi(403));
    await montar();
    fireEvent.click(botao());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Não foi possível iniciar a ligação.", {
        description: "Você não tem permissão para realizar esta ação.",
      }),
    );
  });

  it("falha na tentativa devolve o botão — sem travar a tela", async () => {
    vi.mocked(ticketService.createTicketCall).mockRejectedValue(erroDaApi(409, "x"));
    await montar();
    fireEvent.click(botao());
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(botao()).toBeEnabled();
  });

  it("nenhum desfecho dispara nova tentativa sozinho", async () => {
    // Sem retry automático em caminho nenhum: depois de cruzar a fronteira,
    // "deu erro" não significa "nada aconteceu".
    vi.mocked(ticketService.createTicketCall).mockResolvedValue({
      ...TENTATIVA,
      creation_status: "indeterminate",
    } as never);
    await montar();
    fireEvent.click(botao());
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(ticketService.createTicketCall).toHaveBeenCalledTimes(1);
  });

  it("a aba Atividade recarrega, e o evento aparece com nome legível", async () => {
    vi.mocked(ticketService.createTicketCall).mockResolvedValue(TENTATIVA as never);
    await montar();
    const antes = vi.mocked(ticketService.getTicketHistory).mock.calls.length;

    vi.mocked(ticketService.getTicketHistory).mockResolvedValue({
      items: [
        {
          id: "h1",
          field: "ligacao",
          old_value: null,
          new_value: "tentativa",
          user_name: "Suelen Patricia",
          created_at: new Date().toISOString(),
        },
      ],
    } as never);

    fireEvent.click(botao());
    await waitFor(() =>
      expect(vi.mocked(ticketService.getTicketHistory).mock.calls.length).toBe(
        antes + 1,
      ),
    );

    fireEvent.click(screen.getByText("Atividade"));
    expect(
      await screen.findByText("Tentativa de contato por telefone"),
    ).toBeInTheDocument();
    // E não o nome cru do campo.
    expect(screen.queryByText("ligacao")).not.toBeInTheDocument();
  });

  it("nada do fornecedor aparece na tela", async () => {
    vi.mocked(ticketService.createTicketCall).mockResolvedValue(TENTATIVA as never);
    await montar();
    fireEvent.click(botao());
    await waitFor(() => expect(toast.success).toHaveBeenCalled());

    const texto = document.body.textContent ?? "";
    for (const proibido of [
      "provider_call_id",
      "caller",
      "called",
      "extension",
      "api4com",
      "API4COM",
      "1019",
    ]) {
      expect(texto).not.toContain(proibido);
    }
  });
});
