import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

import { MemoryRouter, Route, Routes } from "react-router-dom";
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

async function montar() {
  vi.mocked(ticketService.getTicket).mockResolvedValue(TICKET as never);
  vi.mocked(ticketService.getTicketHistory).mockResolvedValue({ items: [] } as never);
  vi.mocked(ticketService.listTicketNotes).mockResolvedValue([] as never);
  vi.mocked(attachmentService.getAttachments).mockResolvedValue({ items: [] } as never);
  vi.mocked(surveyService.getTicketSurvey).mockResolvedValue(null as never);
  vi.mocked(userService.getTechnicians).mockResolvedValue([] as never);
  vi.mocked(tagService.getTags).mockResolvedValue([] as never);

  render(
    <MemoryRouter initialEntries={["/tickets/t1"]}>
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
});
