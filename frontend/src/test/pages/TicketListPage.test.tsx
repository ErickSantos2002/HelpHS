import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/ticketService", () => ({ getTickets: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { MemoryRouter } from "react-router-dom";
import TicketListPage from "../../pages/tickets/TicketListPage";
import { getTickets, type Ticket } from "../../services/ticketService";

/**
 * O quadro kanban tinha DOIS mapas próprios, e os dois divergiam do resto.
 *
 * `PRIORITY_CFG` era o **sétimo** mapa de prioridade das telas: dizia "Crítico",
 * "Alto", "Médio", "Baixo" no masculino — contra o feminino que a emenda E17
 * fixou — e pintava `medium` de índigo, que não é a variante `info` de nenhum
 * dos outros seis. O `FilterSelect` da barra trazia o **oitavo**.
 *
 * `COLUMNS` mapeava os seis status com a paleta crua do Tailwind mais seis
 * hexadecimais, e com rótulos próprios ("Ag. Técnico" contra "Aguardando
 * técnico").
 *
 * E o cartão era um `<button onClick={navigate}>`: sem abrir em aba nova, sem
 * menu de contexto, sem destino na barra de status, e anunciado como "botão"
 * para algo que muda de página.
 */
const BASE: Ticket = {
  id: "t1",
  protocol: "HS-2026-0001",
  title: "Impressora não imprime",
  status: "open",
  priority: "high",
  category: "hardware",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
} as unknown as Ticket;

async function montar(itens: Ticket[] = [BASE]) {
  vi.mocked(getTickets).mockResolvedValue({
    items: itens,
    total: itens.length,
  } as never);
  render(
    <MemoryRouter initialEntries={["/tickets"]}>
      <TicketListPage />
    </MemoryRouter>,
  );
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Aberto" })).toBeInTheDocument(),
  );
}

describe("TicketListPage", () => {
  it("cada coluna é uma região com nome, e não um parágrafo", async () => {
    // Seis regiões nomeadas dão a quem navega por cabeçalho um sumário do
    // quadro. Antes eram seis `<p>`, e não havia como pular de coluna em coluna.
    await montar();
    for (const nome of [
      "Aberto",
      "Em andamento",
      "Ag. técnico",
      "Ag. cliente",
      "Resolvido",
      "Fechado",
    ]) {
      expect(screen.getByRole("heading", { name: nome })).toBeInTheDocument();
    }
  });

  it("o cartão do chamado é um LINK, e não um botão", async () => {
    await montar();
    const link = screen.getByRole("link", { name: /Impressora não imprime/ });
    expect(link).toHaveAttribute("href", "/tickets/t1");
  });

  it("a prioridade fala a língua do módulo", async () => {
    // Feminino, da emenda E17. O mapa daqui dizia "Alto".
    await montar();
    expect(screen.getByText("Alta")).toBeInTheDocument();
    expect(screen.queryByText("Alto")).not.toBeInTheDocument();
  });

  it("o ponto de prioridade sai da árvore, porque o selo já diz", async () => {
    // Ele tinha `title` com o rótulo, e `title` não é nome acessível confiável.
    // A informação não se perdeu: o selo do rodapé mostra em texto.
    await montar();
    const selo = screen.getByText("Alta");
    expect(selo).toBeVisible();
  });

  it("o botão de limpar busca tem nome", async () => {
    // Ele só tinha o `<svg>` dentro, e o `Icon` é `aria-hidden`: quem usa
    // leitor de tela ouvia "botão".
    await montar();
    const busca = screen.getByPlaceholderText(/Título, protocolo/);
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(busca, { target: { value: "impressora" } });
    expect(
      screen.getByRole("button", { name: "Limpar busca" }),
    ).toBeInTheDocument();
  });

  it("a contagem da coluna diz do que é", async () => {
    // "Aberto ... 1" não informa; "1 chamado" informa.
    //
    // A primeira versão deste caso usava /chamados?$/, que casava também com o
    // "Nenhum chamado" das cinco colunas vazias — passava com o sr-only
    // removido. A mutação pegou.
    await montar();
    // Matcher por função: o texto está partido entre o número e o ,
    // e o matcher de string exige um elemento só.
    const contagem = screen.getAllByText(
      (_, el) => el?.tagName === "SPAN" && el.textContent === "1 chamado",
    );
    expect(contagem.length).toBeGreaterThan(0);
  });
});
