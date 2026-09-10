import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));
vi.mock("../../services/calendarService", () => ({
  getCalendarEvents: vi.fn(),
  createCalendarEvent: vi.fn(),
  updateCalendarEvent: vi.fn(),
  deleteCalendarEvent: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import CalendarPage from "../../pages/calendar/CalendarPage";
import { useAuth } from "../../contexts/AuthContext";
import * as calendarService from "../../services/calendarService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Seis funções `Icon*` locais** — variante local do pacote, o defeito que a
 * migração existe para tirar — e **39 classes da paleta crua** do Tailwind.
 * Nenhuma das duas coisas é visível daqui: o happy-dom não aplica CSS, e um
 * caso que afirmasse `toHaveClass("bg-action")` passaria com a classe presente
 * e o elemento invisível de verdade. Por isso **nenhum caso abaixo olha
 * classe**. Eles medem o que a pessoa alcança: o nome do controle, o texto que
 * o leitor de tela lê, a cor que o navegador realmente pinta no atributo
 * `style`.
 *
 * As três coisas que a tela dizia **só pela cor**, e que agora estão escritas:
 * o dia de hoje (disco azul), o mês que tem eventos (ponto no canto) e o mês
 * atual (traço embaixo). Quem não distingue a cor não tinha nenhuma das três.
 *
 * E os **dois botões sem nome**: editar e remover eram um `<svg>` dentro de um
 * `<button>` vazio — o leitor de tela anunciava "botão", e só.
 *
 * ── Por que a cor do texto do evento é verificada no `style` ──────────
 *
 * A cor de fundo do evento é **dado**: vem do banco, quem escolhe é o usuário,
 * e a paleta oferecida inclui branco e amarelo. O `text-white` cravado sumia
 * sobre os dois. Quem decide agora é `readableTextColor`, por luminância, e o
 * resultado sai no atributo `style` — que é exatamente o que o navegador pinta.
 * Não é classe: é o valor final.
 */

const AGORA = new Date();
const ANO = AGORA.getFullYear();
const MES = AGORA.getMonth();

/** Um dia do mês visível que **não** é hoje, para o clique não colidir com o
 *  sufixo "(hoje)" que o dia de hoje passou a carregar. */
const DIA = AGORA.getDate() === 10 ? 20 : 10;

/** O mês para onde a navegação vai. Muda só o índice do mês, nunca o ano —
 *  atravessar o ano faria os eventos de teste saírem do mês visível. */
const OUTRO_MES = (MES + 1) % 12;
const MESES_CURTOS = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
];
const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

function emUtc(dia: number) {
  return `${ANO}-${String(MES + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}

function evento(over: Partial<calendarService.CalendarEvent>) {
  return {
    id: "e1",
    title: "Evento",
    description: null,
    event_type: "event",
    color: "#6366f1",
    start_date: `${emUtc(DIA)}T00:00:00Z`,
    end_date: `${emUtc(DIA)}T23:59:59Z`,
    created_by: null,
    creator_name: null,
    created_at: `${emUtc(DIA)}T00:00:00Z`,
    updated_at: `${emUtc(DIA)}T00:00:00Z`,
    ...over,
  } as calendarService.CalendarEvent;
}

/** Branco puro: o caso em que `text-white` deixava o título invisível. */
const BRANCO = evento({
  id: "branco",
  title: "Feriado municipal",
  color: "#ffffff",
  event_type: "holiday",
});

/** Índigo escuro: o caso em que o texto claro é o certo. */
const INDIGO = evento({
  id: "indigo",
  title: "Reunião de equipe",
  color: "#6366f1",
  event_type: "meeting",
});

async function montar(
  papel: "admin" | "technician" | "client" = "admin",
  eventos: calendarService.CalendarEvent[] = [BRANCO, INDIGO],
) {
  vi.mocked(useAuth).mockReturnValue({
    user: { id: "u1", role: papel, name: "Quem for" },
  } as never);
  vi.mocked(calendarService.getCalendarEvents).mockResolvedValue(eventos);

  render(<CalendarPage />);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Agenda" })).toBeInTheDocument(),
  );
  // A grade só existe depois que os eventos chegam; antes dela a tela mostra
  // "Carregando eventos...", e um caso que consultasse nesse quadro mediria a
  // ausência do carregamento, não a presença do que veio.
  await waitFor(() =>
    expect(screen.queryByText("Carregando eventos...")).not.toBeInTheDocument(),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CalendarPage", () => {
  it("as setas de mês têm nome, e mudam o mês de fato", async () => {
    // Eram dois `<svg>` dentro de dois `<button>` vazios: a interface mostrava
    // uma seta e a árvore de acessibilidade dizia "botão".
    await montar();

    const seletorMes = screen.getByLabelText("Mês") as HTMLSelectElement;
    expect(seletorMes.value).toBe(String(MES));

    fireEvent.click(screen.getByRole("button", { name: "Próximo mês" }));
    expect(seletorMes.value).toBe(String(OUTRO_MES));

    fireEvent.click(screen.getByRole("button", { name: "Mês anterior" }));
    expect(seletorMes.value).toBe(String(MES));
  });

  it("os dois seletores da navegação dizem o que selecionam", async () => {
    await montar();
    expect(screen.getByLabelText("Mês")).toHaveValue(String(MES));
    expect(screen.getByLabelText("Ano")).toHaveValue(String(ANO));
  });

  it("o dia de hoje é dito em texto, e não só pelo disco", async () => {
    await montar();

    const marca = screen.getByText(/\(hoje\)/);
    // O sufixo mora dentro do mesmo elemento que mostra o número do dia —
    // então quem ouve a célula ouve "12 (hoje)", e não só "12".
    expect(marca.parentElement).toHaveTextContent(
      new RegExp(`^${AGORA.getDate()}\\s*\\(hoje\\)$`),
    );
  });

  it("o título do evento é legível sobre a cor que o usuário escolheu", async () => {
    // O caso que o `text-white` cravado quebrava: fundo branco, texto branco.
    await montar();

    expect(screen.getByTitle("Feriado municipal")).toHaveStyle({
      backgroundColor: "#ffffff",
      color: "#0f172a",
    });
    expect(screen.getByTitle("Reunião de equipe")).toHaveStyle({
      backgroundColor: "#6366f1",
      color: "#ffffff",
    });
  });

  it("o mês com eventos e o mês atual são ditos no nome do botão", async () => {
    // Eram um ponto e um traço, sem texto nenhum. Ver o mapa dos meses de
    // outro mês é a única forma de os dois marcadores aparecerem juntos: eles
    // só existem quando o mês NÃO é o que está aberto.
    await montar();
    fireEvent.click(
      screen.getByRole("button", { name: MESES_CURTOS[OUTRO_MES] }),
    );

    expect(
      screen.getByRole("button", {
        name: `${MESES_CURTOS[MES]} — com eventos — mês atual`,
      }),
    ).toBeInTheDocument();
  });

  it("editar e remover dizem de QUAL evento são, nos DOIS lugares", async () => {
    // Os dois pares existem duas vezes na tela — no detalhe do dia e na lista
    // de gerenciar do mês —, e a primeira versão deste caso só alcançava a
    // segunda. A mutação pegou: trocar o nome do par do detalhe do dia não
    // reprovava nada, porque o caso nunca abria o dia.
    await montar();
    expect(
      screen.getAllByRole("button", { name: "Editar Feriado municipal" }),
    ).toHaveLength(1);

    fireEvent.click(screen.getByText(String(DIA)));

    expect(
      await screen.findAllByRole("button", { name: "Editar Feriado municipal" }),
    ).toHaveLength(2);
    expect(
      screen.getAllByRole("button", { name: "Remover Reunião de equipe" }),
    ).toHaveLength(2);
  });

  it("remover abre um diálogo que NOMEIA o evento, e não o `confirm()` mudo", async () => {
    // O `confirm()` nativo saiu pela D9.3. Ele dizia "Remover este evento?" —
    // a mesma frase para os dois eventos do mês —, então quem clicasse no
    // botão errado lia uma pergunta que não desmentia o engano.
    await montar();

    fireEvent.click(
      screen.getByRole("button", { name: "Remover Feriado municipal" }),
    );

    const dialogo = await screen.findByRole("dialog");
    const frase = within(dialogo).getByText(/não pode ser desfeita/);
    expect(frase).toHaveTextContent("Feriado municipal");
    expect(calendarService.deleteCalendarEvent).not.toHaveBeenCalled();
  });

  it("o diálogo se anuncia nomeando o que será excluído", async () => {
    // O título do `Modal` é o NOME ACESSÍVEL do diálogo: o componente põe
    // `role="dialog"` com `aria-labelledby` apontando para o `<h2>` do título.
    // É a primeira coisa que o leitor de tela anuncia — e um título "Excluir"
    // seco deixaria quem não vê a tela sem saber o quê. O corpo também nomeia,
    // mas o corpo vem DEPOIS do nome, e só se a pessoa continuar.
    await montar();

    fireEvent.click(
      screen.getByRole("button", { name: "Remover Feriado municipal" }),
    );

    expect(
      await screen.findByRole("dialog", { name: "Excluir evento" }),
    ).toBeInTheDocument();
  });

  it("cancelar fecha o diálogo e não remove o evento", async () => {
    await montar();

    fireEvent.click(
      screen.getByRole("button", { name: "Remover Feriado municipal" }),
    );
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(calendarService.deleteCalendarEvent).not.toHaveBeenCalled();
    expect(screen.getByTitle("Feriado municipal")).toBeInTheDocument();
  });

  it("só o «Excluir» do diálogo chama o serviço, e com o evento clicado", async () => {
    vi.mocked(calendarService.deleteCalendarEvent).mockResolvedValue(undefined);
    await montar();

    fireEvent.click(
      screen.getByRole("button", { name: "Remover Feriado municipal" }),
    );
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(calendarService.deleteCalendarEvent).toHaveBeenCalledWith("branco"),
    );
  });

  it("o cliente lê a agenda e não encontra controle de edição nenhum", async () => {
    await montar("client");

    expect(
      screen.queryByRole("button", { name: "Novo evento" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Editar / }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Remover / }),
    ).not.toBeInTheDocument();
    // Mas os eventos continuam lá para ler.
    expect(screen.getByTitle("Feriado municipal")).toBeInTheDocument();
  });

  it("a grade de cores é um grupo com nome, e a cor em uso está marcada", async () => {
    // O `<label>Cor</label>` não apontava para nada: não há um campo para
    // rotular, são dezesseis botões. O nome agora é do GRUPO.
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Novo evento" }));

    const grupo = await screen.findByRole("group", { name: "Cor" });
    expect(grupo).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Índigo", pressed: true }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Branco" }));
    expect(
      screen.getByRole("button", { name: "Branco", pressed: true }),
    ).toBeInTheDocument();
  });

  it("o tipo do evento é alcançável pelo próprio rótulo", async () => {
    // Sem `htmlFor`, o rótulo ficava só POR CIMA do campo: visualmente ligado,
    // e para o leitor de tela sem relação nenhuma.
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Novo evento" }));

    const tipo = await screen.findByLabelText("Tipo");
    expect(tipo).toHaveValue("event");
    fireEvent.change(tipo, { target: { value: "meeting" } });
    expect(tipo).toHaveValue("meeting");
  });

  it("sem evento nenhum, a tela diz que não há — e o mês continua navegável", async () => {
    await montar("admin", []);

    expect(screen.getByText("Nenhum evento próximo.")).toBeInTheDocument();
    // O bloco de gerenciar some quando não há o que gerenciar; o mapa dos
    // meses não, porque ele é navegação.
    expect(
      screen.queryByText(new RegExp(`Gerenciar eventos`)),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: MESES_CURTOS[MES] }),
    ).toBeInTheDocument();
  });

  it("o dia escolhido abre o detalhe com o nome do dia por extenso", async () => {
    await montar();
    fireEvent.click(screen.getByText(String(DIA)));

    expect(
      await screen.findByText(`${DIA} de ${MESES[MES]}`),
    ).toBeInTheDocument();
    // Os dois eventos do dia, com o tipo escrito ao lado — a cor do ponto é
    // reforço, não a única fonte.
    expect(screen.getByText("Feriado")).toBeInTheDocument();
    expect(screen.getByText("Reunião")).toBeInTheDocument();
  });
});
