import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../../services/notificationService", () => ({
  getNotifications: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
  deleteNotification: vi.fn(),
}));

import { MemoryRouter, Route, Routes } from "react-router-dom";
import NotificationsPage, { TIPO } from "../../pages/notifications/NotificationsPage";
import * as notificationService from "../../services/notificationService";
import type {
  Notification,
  NotificationType,
} from "../../services/notificationService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Duas tabelas para o mesmo tipo de notificação** — `TYPE_LABEL` dava o nome
 * e `TYPE_META` dava o ícone mais uma string de classe —, **13 `<svg>` soltos**
 * (a maior concentração do sistema), **32 classes de paleta crua** e **5 cores
 * cheias de significado usadas como cor de texto**. A aba valendo era dita só
 * pelo fundo, e "não lida" era dito só pela barrinha, pelo fundo e pelo peso da
 * fonte — nada disso chega à árvore de acessibilidade.
 *
 * Os casos abaixo não olham classe nenhuma. O ambiente de teste **não aplica
 * CSS**: afirmar `toHaveClass` provaria que a string está escrita, não que a
 * pessoa vê alguma coisa — e trocar `sr-only` por `hidden` não esconderia nada
 * de um `getByText`. Eles olham o que a pessoa alcança: o nome que ela lê no
 * selo, o estado que o leitor de tela anuncia, o que o clique faz.
 */

const AGORA = new Date().toISOString();

function notif(over: Partial<Notification> = {}): Notification {
  return {
    id: "n1",
    user_id: "u1",
    type: "ticket_created",
    title: "Impressora do 2º andar",
    message: "Não imprime desde ontem",
    data: null,
    read: false,
    read_at: null,
    email_sent: false,
    created_at: AGORA,
    ...over,
  };
}

async function montar(items: Notification[], total = items.length) {
  vi.mocked(notificationService.getNotifications).mockResolvedValue({
    items,
    total,
    unread: items.filter((n) => !n.read).length,
    limit: 20,
    offset: 0,
  });

  render(
    <MemoryRouter initialEntries={["/notificacoes"]}>
      <Routes>
        <Route path="/notificacoes" element={<NotificationsPage />} />
        <Route path="/tickets/:id" element={<p>detalhe do chamado</p>} />
      </Routes>
    </MemoryRouter>,
  );

  // Esperar o cabeçalho não basta: ele já está na árvore antes da promessa
  // resolver. O que prova que a lista chegou é o conteúdo dela.
  if (items.length > 0) await screen.findByText(items[0].title);
  else await screen.findByText(/Nenhuma notificação/);
}

beforeEach(() => {
  vi.mocked(notificationService.markRead).mockResolvedValue(notif());
  vi.mocked(notificationService.markAllRead).mockResolvedValue(undefined);
  vi.mocked(notificationService.deleteNotification).mockResolvedValue(undefined);
});

describe("NotificationsPage", () => {
  it("o tipo está escrito no selo — não é dito só pelo ícone e pela cor", async () => {
    // O ponto da tela. Dez tipos, seis variantes e nove desenhos (o "certo" do
    // resolvido e o do encerrado são o mesmo, pela unificação da E21): quem não
    // distingue as cores, ou não vê os ícones, continua tendo a informação
    // inteira porque ela está escrita.
    const tipos = Object.keys(TIPO) as NotificationType[];
    await montar(
      tipos.map((type, i) => notif({ id: `n${i}`, type, title: `Aviso ${i}` })),
    );

    for (const type of tipos) {
      expect(screen.getByText(TIPO[type].rotulo)).toBeInTheDocument();
    }
  });

  it("tipo que o front não conhece não derruba a tela, e aparece cru", async () => {
    // O dado vem da REDE: um tipo novo no backend não pode virar tela branca.
    await montar([notif({ type: "webhook_failed" as NotificationType })]);

    expect(screen.getByText("webhook_failed")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Notificações" }),
    ).toBeInTheDocument();
  });

  it("«não lida» é dito por escrito, e some quando a notificação é lida", async () => {
    await montar([
      notif({ id: "a", title: "Nova", read: false }),
      notif({ id: "b", title: "Velha", read: true }),
    ]);

    // Uma marca, não duas — e na linha CERTA. Contar sem dizer onde deixaria
    // passar uma condição invertida: continuaria sendo uma marca só.
    expect(screen.getAllByText("Não lida.")).toHaveLength(1);
    const marca = screen.getByText("Não lida.");
    expect(marca.parentElement).toHaveTextContent("Nova");
    expect(marca.parentElement).not.toHaveTextContent("Velha");
  });

  it("a aba valendo é anunciada, e não apenas pintada", async () => {
    await montar([notif()]);

    expect(screen.getByRole("button", { name: "Todas" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.getByRole("button", { name: /Não lidas/ }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("trocar de aba refaz a busca com o filtro, e volta para a primeira página", async () => {
    await montar([notif()]);

    await userEvent.click(screen.getByRole("button", { name: /Não lidas/ }));

    await waitFor(() =>
      expect(vi.mocked(notificationService.getNotifications)).toHaveBeenCalledWith(
        expect.objectContaining({ unread_only: true, offset: 0 }),
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Não lidas/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
  });

  it("a contagem de não lidas está escrita, e o singular é singular", async () => {
    await montar([notif({ id: "a", read: false })]);
    expect(screen.getByText(/não lida$/)).toBeInTheDocument();
  });

  it("com tudo lido, a tela diz «Todas lidas» e não oferece marcar todas", async () => {
    await montar([notif({ read: true })]);

    expect(screen.getByText("Todas lidas")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Marcar todas como lidas" }),
    ).not.toBeInTheDocument();
  });

  it("marcar todas como lidas apaga a marca de cada linha", async () => {
    await montar([
      notif({ id: "a", title: "Uma", read: false }),
      notif({ id: "b", title: "Outra", read: false }),
    ]);

    expect(screen.getAllByText("Não lida.")).toHaveLength(2);

    await userEvent.click(
      screen.getByRole("button", { name: "Marcar todas como lidas" }),
    );

    await waitFor(() =>
      expect(vi.mocked(notificationService.markAllRead)).toHaveBeenCalled(),
    );
    await waitFor(() =>
      expect(screen.queryByText("Não lida.")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Todas lidas")).toBeInTheDocument();
  });

  it("clicar na notificação marca como lida e leva ao chamado", async () => {
    await montar([notif({ id: "a", data: { ticket_id: "t1" } })]);

    await userEvent.click(screen.getByText("Impressora do 2º andar"));

    await waitFor(() =>
      expect(vi.mocked(notificationService.markRead)).toHaveBeenCalledWith("a"),
    );
    expect(await screen.findByText("detalhe do chamado")).toBeInTheDocument();
  });

  it("notificação sem chamado não navega — e ainda assim é marcada como lida", async () => {
    await montar([notif({ id: "a", data: null })]);

    await userEvent.click(screen.getByText("Impressora do 2º andar"));

    await waitFor(() =>
      expect(vi.mocked(notificationService.markRead)).toHaveBeenCalledWith("a"),
    );
    expect(screen.queryByText("detalhe do chamado")).not.toBeInTheDocument();

    // E a linha para de se dizer não lida. Sem esta afirmação, o clique podia
    // avisar o servidor e não mexer na tela — a pessoa continuaria vendo a
    // notificação em negrito, com a barrinha e a marca, até recarregar.
    await waitFor(() =>
      expect(screen.queryByText("Não lida.")).not.toBeInTheDocument(),
    );
  });

  it("remover tem nome próprio, tira a linha e NÃO abre o chamado", async () => {
    // O botão vive dentro de uma superfície clicável. Sem o `stopPropagation`,
    // apagar uma notificação levaria a pessoa para o chamado que ela acabou de
    // apagar da lista.
    await montar([notif({ id: "a", data: { ticket_id: "t1" } })]);

    await userEvent.click(
      screen.getByRole("button", { name: "Remover notificação" }),
    );

    await waitFor(() =>
      expect(
        vi.mocked(notificationService.deleteNotification),
      ).toHaveBeenCalledWith("a"),
    );
    await waitFor(() =>
      expect(screen.queryByText("Impressora do 2º andar")).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("detalhe do chamado")).not.toBeInTheDocument();
  });

  it("o estado vazio diz qual vazio é — e muda com o filtro", async () => {
    await montar([]);
    expect(screen.getByText("Nenhuma notificação")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Todas" }));
    await userEvent.click(screen.getByRole("button", { name: /Não lidas/ }));

    expect(
      await screen.findByText("Nenhuma notificação não lida"),
    ).toBeInTheDocument();
  });

  it("falha de rede vira aviso, e não uma lista vazia silenciosa", async () => {
    vi.mocked(notificationService.getNotifications).mockRejectedValue(
      new Error("sem rede"),
    );

    render(
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Não foi possível carregar as notificações."),
    ).toBeInTheDocument();
  });

  it("a paginação só existe quando há mais de uma página", async () => {
    await montar([notif()], 3);
    expect(screen.queryByRole("button", { name: "2" })).not.toBeInTheDocument();

    await montar([notif({ id: "z", title: "Outra tela" })], 60);
    expect(screen.getAllByRole("button", { name: "2" }).length).toBeGreaterThan(0);
  });

  it("a tabela TIPO é esta, literal — os dez tipos, os nove ícones, as seis variantes", () => {
    // Comparada LITERAL, e não derivada, pelo mesmo motivo que `SLOT_DE_STATUS`
    // é: **nada no código deduz este agrupamento**. Dez tipos couberam em seis
    // variantes porque alguém decidiu que "encerrado" e "sistema" não pedem
    // nada de quem lê, e que a pesquisa de satisfação pede o mesmo grau de
    // atenção que um aviso de SLA. É decisão de desenho, aprovada fora daqui.
    //
    // Sem este caso, trocar `danger` por `muted` no SLA violado é uma edição de
    // uma palavra que nenhum outro caso reprova: a tela continua renderizando,
    // o selo continua dizendo "SLA violado", e só a cor muda — que é justamente
    // o que o ambiente de teste não vê.
    expect(TIPO).toEqual({
      ticket_created: {
        rotulo: "Chamado criado",
        icone: "ticket",
        variante: "primary",
      },
      ticket_assigned: {
        rotulo: "Chamado atribuído",
        icone: "user",
        variante: "info",
      },
      ticket_updated: {
        rotulo: "Chamado atualizado",
        icone: "refresh",
        variante: "primary",
      },
      ticket_resolved: {
        rotulo: "Chamado resolvido",
        icone: "check",
        variante: "success",
      },
      ticket_closed: {
        rotulo: "Chamado encerrado",
        icone: "check",
        variante: "muted",
      },
      sla_warning: { rotulo: "Aviso SLA", icone: "clock", variante: "warning" },
      sla_breached: {
        rotulo: "SLA violado",
        icone: "warning",
        variante: "danger",
      },
      chat_message: {
        rotulo: "Nova mensagem",
        icone: "chat",
        variante: "primary",
      },
      satisfaction_survey: {
        rotulo: "Pesquisa de satisfação",
        icone: "star",
        variante: "warning",
      },
      system: { rotulo: "Sistema", icone: "settings", variante: "muted" },
    });
  });

  it("os tipos que dividem variante continuam dividindo, e os que não, não", () => {
    // O agrupamento não é uma lista de dez escolhas soltas: é a afirmação de
    // que certos tipos são o MESMO grau. Se um dia "encerrado" deixar de pintar
    // como "sistema", o agrupamento registrado na ficha deixou de valer — e
    // isso tem de reprovar aqui, não ser descoberto na tela.
    expect(TIPO.ticket_created.variante).toBe(TIPO.ticket_updated.variante);
    expect(TIPO.ticket_created.variante).toBe(TIPO.chat_message.variante);
    expect(TIPO.sla_warning.variante).toBe(TIPO.satisfaction_survey.variante);
    expect(TIPO.ticket_closed.variante).toBe(TIPO.system.variante);

    // E que resolvido e encerrado NÃO são o mesmo grau, embora dividam o
    // desenho: o "certo" sem círculo e o "certo" com círculo viraram um ícone
    // só na E21, e o que os separa passou a ser a variante e o rótulo.
    expect(TIPO.ticket_closed.icone).toBe(TIPO.ticket_resolved.icone);
    expect(TIPO.ticket_closed.variante).not.toBe(TIPO.ticket_resolved.variante);
  });
});
