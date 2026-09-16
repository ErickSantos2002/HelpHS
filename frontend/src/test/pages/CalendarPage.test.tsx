import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));
vi.mock("../../services/calendarService", () => ({
  getCalendarEvents: vi.fn(),
  getCalendarEventTypes: vi.fn(),
  createCalendarEvent: vi.fn(),
  updateCalendarEvent: vi.fn(),
  deleteCalendarEvent: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));
/*
  O fuso de quem olha é FIXADO em Recife — o resto do módulo é o real.

  Sem isto a tela usaria o fuso da máquina: Recife aqui, UTC no CI. Um caso que
  desenha "09:00" passaria num lugar e reprovaria no outro. Fixando só a origem
  do fuso, as contas continuam sendo as de produção, e o resultado deixa de
  depender de onde a suíte roda.
*/
vi.mock("../../lib/agenda", async (importOriginal) => {
  const real = await importOriginal<typeof import("../../lib/agenda")>();
  return { ...real, fusoDoNavegador: () => "America/Recife" };
});

import CalendarPage from "../../pages/calendar/CalendarPage";
import { useAuth } from "../../contexts/AuthContext";
import * as calendarService from "../../services/calendarService";
import { chaveCivil, chaveDoDia, instanteDe } from "../../lib/agenda";
import { toast } from "sonner";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Da migração do design system (§29):** seis funções `Icon*` locais, 39 classes
 * da paleta crua, três informações ditas só pela cor (hoje, mês com eventos, mês
 * atual) e dois botões sem nome. **Nenhum caso abaixo olha classe**: o happy-dom
 * não aplica CSS. Eles medem o que a pessoa alcança — o nome do controle, o texto
 * que o leitor de tela lê, a cor que o navegador pinta no atributo `style`.
 *
 * **Do round do horário (15/09/2026):** a tela passou a ter hora, a chave de dia
 * inteiro, o fuso na consulta do mês, a legenda de volta, a autoria, e perdeu as
 * dezesseis fichas de cor — a cor vem do tipo desde o #18.
 *
 * ── Por que os casos não congelam o relógio ──────────────────────────
 *
 * Relógio falso e `waitFor` do Testing Library não se entendem no vitest: a
 * biblioteca procura os temporizadores do jest, não acha, e espera em tempo real
 * enquanto o relógio está parado. Os casos derivam o dia de hoje do relógio de
 * verdade — mas NO FUSO FIXADO, e não com `getDate()`, que usaria o da máquina.
 */

const FUSO = "America/Recife";
const HOJE = chaveCivil(new Date(), FUSO);
const ANO = Number(HOJE.slice(0, 4));
const MES = Number(HOJE.slice(5, 7)) - 1;
const DIA_DE_HOJE = Number(HOJE.slice(8, 10));

/** Um dia do mês visível que não é hoje, e cujo dia seguinte existe no mês. */
const DIA = DIA_DE_HOJE === 10 ? 20 : 10;
const CHAVE = chaveDoDia(ANO, MES, DIA);
const CHAVE_SEGUINTE = chaveDoDia(ANO, MES, DIA + 1);

/** O mês para onde a navegação vai. Nunca atravessa o ano. */
const OUTRO_MES = MES === 11 ? 10 : MES + 1;
const MESES_CURTOS = [
  "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez",
];
const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

/** O mapa que a API devolve, na ordem do enum. */
const TIPOS: calendarService.CalendarEventTypeColor[] = [
  { value: "event", color: "#4f46e5" },
  { value: "meeting", color: "#2563eb" },
  { value: "training", color: "#047857" },
  { value: "deadline", color: "#b45309" },
  { value: "holiday", color: "#dc2626" },
];

function evento(over: Partial<calendarService.CalendarEvent>) {
  return {
    id: "e1",
    title: "Evento",
    description: null,
    event_type: "event",
    color: "#4f46e5",
    start_date: `${CHAVE}T00:00:00Z`,
    end_date: `${CHAVE}T23:59:59Z`,
    all_day: true,
    created_by: "u9",
    creator_name: "Maria Souza",
    created_at: `${CHAVE}T00:00:00Z`,
    updated_at: `${CHAVE}T00:00:00Z`,
    ...over,
  } as calendarService.CalendarEvent;
}

/**
 * Branco puro. A API do #18 não manda mais branco — mas a tela desenha a cor que
 * vier, e este é o caso que prova que o texto é calculado, e não fixo.
 */
const BRANCO = evento({ id: "branco", title: "Feriado municipal", color: "#ffffff", event_type: "holiday" });
const AZUL = evento({ id: "azul", title: "Reunião de equipe", color: "#2563eb", event_type: "meeting" });

type Opcoes = {
  todos?: calendarService.CalendarEvent[];
  tiposFalham?: boolean;
};

async function montar(
  papel: "admin" | "technician" | "client" = "admin",
  doMes: calendarService.CalendarEvent[] = [BRANCO, AZUL],
  { todos, tiposFalham = false }: Opcoes = {},
) {
  vi.mocked(useAuth).mockReturnValue({
    user: { id: "u1", role: papel, name: "Quem for" },
  } as never);
  // Sem ano, é a consulta de todos (a lateral); com ano, a do mês (a grade).
  vi.mocked(calendarService.getCalendarEvents).mockImplementation(async (ano) =>
    ano === undefined ? (todos ?? doMes) : doMes,
  );
  if (tiposFalham) {
    vi.mocked(calendarService.getCalendarEventTypes).mockRejectedValue(new Error("500"));
  } else {
    vi.mocked(calendarService.getCalendarEventTypes).mockResolvedValue(TIPOS);
  }

  render(<CalendarPage />);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Agenda" })).toBeInTheDocument(),
  );
  await waitFor(() =>
    expect(screen.queryByText("Carregando eventos...")).not.toBeInTheDocument(),
  );
}

/** Abre o detalhe do dia `DIA` e clica em adicionar. */
async function novoEventoNoDia() {
  fireEvent.click(screen.getByText(String(DIA)));
  fireEvent.click(await screen.findByTitle("Adicionar evento"));
  return screen.findByRole("dialog", { name: "Novo evento" });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── O que veio da migração (§29) ──────────────────────────────

describe("CalendarPage — navegação e acessibilidade", () => {
  it("as setas de mês têm nome, e mudam o mês de fato", async () => {
    await montar();

    const seletorMes = screen.getByLabelText("Mês") as HTMLSelectElement;
    expect(seletorMes.value).toBe(String(MES));

    fireEvent.click(screen.getByRole("button", { name: "Próximo mês" }));
    expect(seletorMes.value).toBe(String((MES + 1) % 12));

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
    expect(marca.parentElement).toHaveTextContent(
      new RegExp(`^${DIA_DE_HOJE}\\s*\\(hoje\\)$`),
    );
  });

  it("o título do evento é legível sobre a cor que a API manda", async () => {
    await montar();

    expect(screen.getByTitle("Feriado municipal")).toHaveStyle({
      backgroundColor: "#ffffff",
      color: "#0f172a",
    });
    expect(screen.getByTitle("Reunião de equipe")).toHaveStyle({
      backgroundColor: "#2563eb",
      color: "#ffffff",
    });
  });

  it("o mês com eventos e o mês atual são ditos no nome do botão", async () => {
    await montar();
    fireEvent.click(screen.getByRole("button", { name: MESES_CURTOS[OUTRO_MES] }));

    expect(
      screen.getByRole("button", { name: `${MESES_CURTOS[MES]} — com eventos — mês atual` }),
    ).toBeInTheDocument();
  });

  it("editar e remover dizem de QUAL evento são, nos DOIS lugares", async () => {
    await montar();
    expect(screen.getAllByRole("button", { name: "Editar Feriado municipal" })).toHaveLength(1);

    fireEvent.click(screen.getByText(String(DIA)));

    expect(
      await screen.findAllByRole("button", { name: "Editar Feriado municipal" }),
    ).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Remover Reunião de equipe" })).toHaveLength(2);
  });

  it("remover abre um diálogo que NOMEIA o evento, e não o `confirm()` mudo", async () => {
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Remover Feriado municipal" }));

    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText(/não pode ser desfeita/)).toHaveTextContent("Feriado municipal");
    expect(calendarService.deleteCalendarEvent).not.toHaveBeenCalled();
  });

  it("o diálogo se anuncia nomeando o que será excluído", async () => {
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Remover Feriado municipal" }));

    expect(await screen.findByRole("dialog", { name: "Excluir evento" })).toBeInTheDocument();
  });

  it("cancelar fecha o diálogo e não remove o evento", async () => {
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Remover Feriado municipal" }));
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calendarService.deleteCalendarEvent).not.toHaveBeenCalled();
    expect(screen.getByTitle("Feriado municipal")).toBeInTheDocument();
  });

  it("só o «Excluir» do diálogo chama o serviço, e com o evento clicado", async () => {
    vi.mocked(calendarService.deleteCalendarEvent).mockResolvedValue(undefined);
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Remover Feriado municipal" }));
    const dialogo = await screen.findByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(calendarService.deleteCalendarEvent).toHaveBeenCalledWith("branco"),
    );
  });

  it("o cliente lê a agenda e não encontra controle de edição nenhum", async () => {
    await montar("client");

    expect(screen.queryByRole("button", { name: "Novo evento" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Editar / })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remover / })).not.toBeInTheDocument();
    expect(screen.getByTitle("Feriado municipal")).toBeInTheDocument();
  });

  it("o tipo do evento é alcançável pelo próprio rótulo", async () => {
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
    expect(screen.queryByText(/Gerenciar eventos/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: MESES_CURTOS[MES] })).toBeInTheDocument();
  });

  it("o dia escolhido abre o detalhe com o nome do dia por extenso", async () => {
    await montar();
    fireEvent.click(screen.getByText(String(DIA)));

    const detalhe = await screen.findByRole("region", { name: `${DIA} de ${MESES[MES]}` });
    // Dentro do detalhe, e não na tela inteira: a legenda do rodapé também
    // escreve "Feriado" e "Reunião", e um `getByText` solto acharia os dois.
    expect(within(detalhe).getByText("Feriado")).toBeInTheDocument();
    expect(within(detalhe).getByText("Reunião")).toBeInTheDocument();
  });
});

// ── A consulta ────────────────────────────────────────────────

describe("CalendarPage — a consulta do mês vai com o fuso", () => {
  /*
    O mês da API vai de 1 a 12; o da tela, de 0 a 11. Somar um é a linha que
    decide se a grade de setembro mostra setembro ou agosto — e nenhum outro
    caso notaria, porque o mock devolve a mesma lista para qualquer mês.
  */
  it("pede à API o mês visível, de 1 a 12, com o fuso de quem olha", async () => {
    await montar();

    expect(calendarService.getCalendarEvents).toHaveBeenCalledWith(ANO, MES + 1, FUSO);
  });

  it("trocar de mês pede o mês novo", async () => {
    await montar();
    vi.mocked(calendarService.getCalendarEvents).mockClear();

    fireEvent.change(screen.getByLabelText("Mês"), { target: { value: String(OUTRO_MES) } });

    await waitFor(() =>
      expect(calendarService.getCalendarEvents).toHaveBeenCalledWith(ANO, OUTRO_MES + 1, FUSO),
    );
  });

  /*
    Trocar de mês duas vezes seguidas dispara duas consultas, e nada garante a
    ordem em que elas voltam. Sem o descarte, a resposta do mês que ficou para
    trás, chegando por último, pintaria a grade do mês que está na tela.
  */
  it("resposta de um mês que ficou para trás não sobrescreve a do mês na tela", async () => {
    await montar("admin", []);

    const soltas: Array<(v: calendarService.CalendarEvent[]) => void> = [];
    vi.mocked(calendarService.getCalendarEvents).mockImplementation(
      (ano) =>
        ano === undefined
          ? Promise.resolve([])
          : new Promise((resolve) => { soltas.push(resolve); }),
    );

    const seletor = screen.getByLabelText("Mês");
    fireEvent.change(seletor, { target: { value: String(OUTRO_MES) } });
    fireEvent.change(seletor, { target: { value: String(MES) } });
    await waitFor(() => expect(soltas).toHaveLength(2));

    // A do mês atual volta primeiro; a do mês abandonado, depois — e ela traz um
    // evento que cairia num dia visível, para o defeito ser visto se existir.
    soltas[1]([evento({ id: "certo", title: "Resposta do mês na tela" })]);
    await screen.findByTitle("Resposta do mês na tela");
    soltas[0]([evento({ id: "velho", title: "Resposta do mês abandonado" })]);

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTitle("Resposta do mês abandonado")).not.toBeInTheDocument();
    expect(screen.getByTitle("Resposta do mês na tela")).toBeInTheDocument();
  });

  /*
    A lista de próximos e o mapa dos meses olham além do mês visível, e a API
    não tem consulta de ano nem de "próximos". Por isso a lateral faz a consulta
    sem mês — e a grade, a do mês.
  */
  it("a lateral pede todos os eventos, sem mês", async () => {
    await montar();

    expect(calendarService.getCalendarEvents).toHaveBeenCalledWith();
  });
});

// ── A cor vem do tipo, e a legenda volta ──────────────────────

describe("CalendarPage — a cor vem do tipo", () => {
  it("o modal não oferece mais cor para escolher", async () => {
    // As dezesseis fichas saíram: desde o #18 a API ignora a cor mandada, e uma
    // ficha que não faz nada é pior do que ficha nenhuma.
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Novo evento" }));
    await screen.findByRole("dialog");

    expect(screen.queryByRole("group", { name: "Cor" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Índigo" })).not.toBeInTheDocument();
  });

  it("o modal mostra a cor que o tipo escolhido vai ter, lida da API", async () => {
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Novo evento" }));
    await screen.findByRole("dialog");

    const amostra = screen.getByTestId("cor-do-tipo");
    expect(amostra).toHaveStyle({ backgroundColor: "#4f46e5" });

    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "holiday" } });
    expect(screen.getByTestId("cor-do-tipo")).toHaveStyle({ backgroundColor: "#dc2626" });
  });

  it("a legenda volta ao rodapé, com as cores da API e os nomes da tela", async () => {
    // Saiu em 04/08 quando a cor era livre — e nessa época ela mentia. Com a cor
    // derivada do tipo, ela passa a dizer a verdade.
    await montar();

    const legenda = screen.getByRole("list", { name: "Legenda dos tipos de evento" });
    const itens = within(legenda).getAllByRole("listitem");
    expect(itens.map((i) => i.textContent)).toEqual([
      "Evento", "Reunião", "Treinamento", "Prazo", "Feriado",
    ]);
    expect(within(itens[3]).getByTestId("cor-da-legenda")).toHaveStyle({
      backgroundColor: "#b45309",
    });
  });

  it("sem o mapa da API, não há legenda — e nenhuma cor inventada no lugar", async () => {
    // Um mapa local de reserva seria a segunda fonte voltando pela porta dos fundos.
    await montar("admin", [BRANCO, AZUL], { tiposFalham: true });

    expect(
      screen.queryByRole("list", { name: "Legenda dos tipos de evento" }),
    ).not.toBeInTheDocument();
  });
});

// ── Horário e dia inteiro ─────────────────────────────────────

describe("CalendarPage — horário e dia inteiro", () => {
  it("evento novo abre como dia inteiro, sem campo de hora", async () => {
    // O padrão que não perde dado: quem esquece a chave cria dia inteiro, e não
    // evento de duração errada.
    await montar();
    await novoEventoNoDia();

    expect(screen.getByRole("switch", { name: "Dia inteiro" })).toBeChecked();
    expect(screen.queryByLabelText("Hora de início")).not.toBeInTheDocument();
  });

  it("dia inteiro manda a data, a chave, e nenhuma cor", async () => {
    vi.mocked(calendarService.createCalendarEvent).mockResolvedValue(BRANCO);
    await montar();
    const dialogo = await novoEventoNoDia();

    fireEvent.change(within(dialogo).getByLabelText("Título"), { target: { value: "Treinamento NR-35" } });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(calendarService.createCalendarEvent).toHaveBeenCalled());
    const payload = vi.mocked(calendarService.createCalendarEvent).mock.calls[0][0];
    expect(payload).toEqual({
      title: "Treinamento NR-35",
      description: null,
      event_type: "event",
      start_date: `${CHAVE}T00:00:00Z`,
      end_date: `${CHAVE}T00:00:00Z`,
      all_day: true,
    });
    expect(payload).not.toHaveProperty("color");
  });

  it("desligar a chave mostra a hora, em minutos, e manda o instante em UTC", async () => {
    vi.mocked(calendarService.createCalendarEvent).mockResolvedValue(AZUL);
    await montar();
    const dialogo = await novoEventoNoDia();

    fireEvent.change(within(dialogo).getByLabelText("Título"), { target: { value: "Reunião da virada" } });
    fireEvent.click(within(dialogo).getByRole("switch", { name: "Dia inteiro" }));

    const inicio = within(dialogo).getByLabelText("Hora de início");
    // Minutos, e não segundos: a pegada do #17 é 23:59:59 com os segundos, e um
    // campo com segundos a acionaria por acidente.
    expect(inicio).toHaveAttribute("step", "60");
    fireEvent.change(inicio, { target: { value: "22:00" } });
    fireEvent.change(within(dialogo).getByLabelText("Hora de fim"), { target: { value: "23:30" } });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(calendarService.createCalendarEvent).toHaveBeenCalled());
    const payload = vi.mocked(calendarService.createCalendarEvent).mock.calls[0][0];
    expect(payload.all_day).toBe(false);
    expect(payload.start_date).toBe(instanteDe(CHAVE, "22:00", FUSO));
    expect(payload.end_date).toBe(instanteDe(CHAVE, "23:30", FUSO));
    expect(payload.end_date).toMatch(/:00\.000Z$/);
  });

  it("fim igual ou antes do início trava o salvar e diz por quê", async () => {
    await montar();
    const dialogo = await novoEventoNoDia();

    fireEvent.change(within(dialogo).getByLabelText("Título"), { target: { value: "Zero minutos" } });
    fireEvent.click(within(dialogo).getByRole("switch", { name: "Dia inteiro" }));
    fireEvent.change(within(dialogo).getByLabelText("Hora de início"), { target: { value: "10:00" } });
    fireEvent.change(within(dialogo).getByLabelText("Hora de fim"), { target: { value: "10:00" } });

    expect(within(dialogo).getByText("O fim precisa ser depois do início.")).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: "Salvar" })).toBeDisabled();
  });

  it("editar evento com hora abre com a chave desligada e a hora de Recife", async () => {
    const reuniao = evento({
      id: "reuniao",
      title: "Reunião de meio de semana",
      all_day: false,
      start_date: instanteDe(CHAVE, "09:00", FUSO)!,
      end_date: instanteDe(CHAVE, "17:00", FUSO)!,
    });
    await montar("admin", [reuniao]);

    fireEvent.click(screen.getAllByRole("button", { name: "Editar Reunião de meio de semana" })[0]);
    const dialogo = await screen.findByRole("dialog", { name: "Editar evento" });

    expect(within(dialogo).getByRole("switch", { name: "Dia inteiro" })).not.toBeChecked();
    expect(within(dialogo).getByLabelText("Data de início")).toHaveValue(CHAVE);
    expect(within(dialogo).getByLabelText("Hora de início")).toHaveValue("09:00");
    expect(within(dialogo).getByLabelText("Hora de fim")).toHaveValue("17:00");
  });

  it("editar dia inteiro abre com a data flutuante, sem deslocar para o dia anterior", async () => {
    // `00:00Z` é 21:00 do dia anterior em Recife. Lida como instante, a data do
    // campo mostraria a véspera — e salvar gravaria o evento um dia antes.
    await montar();

    fireEvent.click(screen.getAllByRole("button", { name: "Editar Feriado municipal" })[0]);
    const dialogo = await screen.findByRole("dialog", { name: "Editar evento" });

    expect(within(dialogo).getByRole("switch", { name: "Dia inteiro" })).toBeChecked();
    expect(within(dialogo).getByLabelText("Data de início")).toHaveValue(CHAVE);
  });

  it("a recusa da API chega a quem salvou, com o motivo que ela deu", async () => {
    vi.mocked(calendarService.createCalendarEvent).mockRejectedValue({
      response: { status: 422, data: { detail: "A data de fim precisa ser posterior à data de início." } },
    });
    await montar();
    const dialogo = await novoEventoNoDia();

    fireEvent.change(within(dialogo).getByLabelText("Título"), { target: { value: "Recusado" } });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(vi.mocked(toast.error).mock.calls[0][1]).toEqual({
      description: "A data de fim precisa ser posterior à data de início.",
    });
  });
});

describe("CalendarPage — o evento no calendário", () => {
  it("evento com hora mostra a hora no chip e no detalhe do dia", async () => {
    const reuniao = evento({
      id: "reuniao",
      title: "Reunião de meio de semana",
      all_day: false,
      start_date: instanteDe(CHAVE, "09:00", FUSO)!,
      end_date: instanteDe(CHAVE, "17:00", FUSO)!,
    });
    await montar("admin", [reuniao]);

    expect(screen.getByTitle("Reunião de meio de semana")).toHaveTextContent("09:00");

    fireEvent.click(screen.getByText(String(DIA)));
    expect(await screen.findByText("09:00–17:00")).toBeInTheDocument();
  });

  it("dia inteiro diz que é dia inteiro no detalhe do dia", async () => {
    await montar("admin", [BRANCO]);
    fireEvent.click(screen.getByText(String(DIA)));

    expect(await screen.findByText("Dia inteiro")).toBeInTheDocument();
  });

  it("evento que atravessa a meia-noite aparece nos dois dias", async () => {
    const plantao = evento({
      id: "plantao",
      title: "Plantão da virada",
      all_day: false,
      start_date: instanteDe(CHAVE, "22:00", FUSO)!,
      end_date: instanteDe(CHAVE_SEGUINTE, "02:00", FUSO)!,
    });
    await montar("admin", [plantao]);

    const chips = screen.getAllByTitle("Plantão da virada");
    expect(chips).toHaveLength(2);
    // A hora só no dia em que COMEÇA. No dia seguinte, "22:00" diria que o
    // plantão começa de novo.
    expect(chips[0]).toHaveTextContent("22:00");
    expect(chips[1]).not.toHaveTextContent("22:00");
  });

  it("evento das 22:00 aparece no dia em que foi criado, e não no seguinte", async () => {
    // 22:00 em Recife é 01:00Z do dia seguinte. Pela data UTC — como a grade
    // fazia —, ele cairia na célula do dia seguinte.
    const noite = evento({
      id: "noite",
      title: "Reunião da noite",
      all_day: false,
      start_date: instanteDe(CHAVE, "22:00", FUSO)!,
      end_date: instanteDe(CHAVE, "23:00", FUSO)!,
    });
    await montar("admin", [noite]);

    fireEvent.click(screen.getByText(String(DIA)));
    expect(await screen.findByText("22:00–23:00")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Fechar o dia" }));
    fireEvent.click(screen.getByText(String(DIA + 1)));
    expect(await screen.findByText("Nenhum evento neste dia.")).toBeInTheDocument();
  });
});

describe("CalendarPage — quem criou", () => {
  it("o detalhe do dia diz quem criou o evento", async () => {
    await montar("admin", [BRANCO]);
    fireEvent.click(screen.getByText(String(DIA)));

    expect(await screen.findByText("Criado por Maria Souza")).toBeInTheDocument();
  });

  it("autor apagado aparece como removido, e não some calado", async () => {
    // A coluna é `ondelete=SET NULL`: apagar o usuário esvazia a autoria.
    await montar("admin", [evento({ id: "orfao", title: "Órfão", created_by: null, creator_name: null })]);
    fireEvent.click(screen.getByText(String(DIA)));

    expect(await screen.findByText("Criado por um usuário removido")).toBeInTheDocument();
  });

  it("autor anonimizado aparece com o nome que a anonimização deu", async () => {
    // A linha continua — só o nome muda. Não é o mesmo caso do removido, e a tela
    // não pode confundir os dois.
    await montar("admin", [
      evento({ id: "anon", title: "Anônimo", created_by: "u7", creator_name: "Usuário Anonimizado 1a2b3c4d" }),
    ]);
    fireEvent.click(screen.getByText(String(DIA)));

    expect(await screen.findByText("Criado por Usuário Anonimizado 1a2b3c4d")).toBeInTheDocument();
    expect(screen.queryByText("Criado por um usuário removido")).not.toBeInTheDocument();
  });
});

// ── O que a revisão independente achou ────────────────────────
//
// Quatro lentes leram a mudança sem escrever nada, cada uma obrigada a trazer um
// cenário que falha. Cada caso abaixo reprovou ANTES do conserto.

const FUTURO = evento({
  id: "futuro",
  title: "Vistoria anual",
  event_type: "deadline",
  color: "#b45309",
  start_date: `${ANO + 1}-01-05T00:00:00Z`,
  end_date: `${ANO + 1}-01-05T23:59:59Z`,
});

describe("CalendarPage — achados da revisão", () => {
  it("apagar a hora não derruba a tela: trava o salvar e diz o que falta", async () => {
    // As quatro lentes acharam este, cada uma sozinha. Um Backspace no campo de
    // hora deixa o valor vazio, e a conta lançava durante a renderização.
    await montar();
    const dialogo = await novoEventoNoDia();
    fireEvent.change(within(dialogo).getByLabelText("Título"), { target: { value: "X" } });
    fireEvent.click(within(dialogo).getByRole("switch", { name: "Dia inteiro" }));

    fireEvent.change(within(dialogo).getByLabelText("Hora de fim"), { target: { value: "" } });

    expect(screen.getByRole("dialog", { name: "Novo evento" })).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: "Salvar" })).toBeDisabled();
    expect(within(dialogo).getByLabelText("Hora de fim")).toHaveAttribute("aria-invalid", "true");
  });

  it("abrir um evento com hora e salvar sem mexer manda os instantes que já estavam gravados", async () => {
    // Recalcular a hora que ninguém mexeu reescreve o instante — e na hora que se
    // repete no fim do horário de verão, recua uma hora e muda a duração. Aqui o
    // sinal é o formato: o gravado não tem milissegundos, o recalculado tem.
    vi.mocked(calendarService.updateCalendarEvent).mockResolvedValue(AZUL);
    const gravado = evento({
      id: "gravado",
      title: "Reunião gravada",
      all_day: false,
      start_date: `${CHAVE}T12:00:00Z`,
      end_date: `${CHAVE}T20:00:00Z`,
    });
    await montar("admin", [gravado]);

    fireEvent.click(screen.getAllByRole("button", { name: "Editar Reunião gravada" })[0]);
    const dialogo = await screen.findByRole("dialog", { name: "Editar evento" });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(calendarService.updateCalendarEvent).toHaveBeenCalled());
    const payload = vi.mocked(calendarService.updateCalendarEvent).mock.calls[0][1];
    expect(payload.start_date).toBe(`${CHAVE}T12:00:00Z`);
    expect(payload.end_date).toBe(`${CHAVE}T20:00:00Z`);
  });

  it("o tipo é dito em texto nos próximos eventos, e não só pela cor do ponto", async () => {
    // Com a cor derivada do tipo e a legenda de volta, a cor passou a CARREGAR o
    // tipo — e nos próximos ela era a única portadora. É a regra do §29.
    await montar("admin", [], { todos: [FUTURO] });

    const bloco = screen.getByRole("heading", { name: "Próximos eventos" }).parentElement!;
    expect(within(bloco).getByText(/Prazo/)).toBeInTheDocument();
  });

  it("o tipo é dito em texto no chip da grade e na lista de gerenciar", async () => {
    const vistoria = evento({ id: "vistoria", title: "Vistoria", event_type: "deadline", color: "#b45309" });
    await montar("admin", [vistoria]);

    expect(screen.getByTitle("Vistoria")).toHaveTextContent(/Prazo/);
    const gerenciar = screen.getByRole("heading", { name: /Gerenciar eventos/ }).parentElement!;
    expect(within(gerenciar).getByText(/Vistoria/)).toHaveTextContent(/Prazo/);
  });

  it("data de fim antes do início marca a DATA como inválida, e não a hora", async () => {
    await montar();
    const dialogo = await novoEventoNoDia();
    fireEvent.click(within(dialogo).getByRole("switch", { name: "Dia inteiro" }));

    fireEvent.change(within(dialogo).getByLabelText("Data de fim"), {
      target: { value: chaveDoDia(ANO, MES, DIA - 1) },
    });

    expect(within(dialogo).getByLabelText("Data de fim")).toHaveAttribute("aria-invalid", "true");
    expect(within(dialogo).getByLabelText("Hora de fim")).not.toHaveAttribute("aria-invalid");
  });

  it("se a consulta do mês falha, a grade diz que falhou, e não se passa por vazia", async () => {
    vi.mocked(useAuth).mockReturnValue({ user: { id: "u1", role: "admin", name: "X" } } as never);
    vi.mocked(calendarService.getCalendarEventTypes).mockResolvedValue(TIPOS);
    vi.mocked(calendarService.getCalendarEvents).mockImplementation(async (ano) => {
      if (ano === undefined) return [BRANCO];
      throw new Error("500");
    });
    render(<CalendarPage />);

    expect(await screen.findByText("Não foi possível carregar os eventos deste mês.")).toBeInTheDocument();
    expect(screen.queryByText("Nenhum evento neste dia.")).not.toBeInTheDocument();
  });

  it("excluir e a recarga falhar não deixa o evento apagado na grade", async () => {
    vi.mocked(calendarService.deleteCalendarEvent).mockResolvedValue(undefined);
    await montar("admin", [BRANCO]);
    vi.mocked(calendarService.getCalendarEvents).mockImplementation(async (ano) => {
      if (ano === undefined) return [];
      throw new Error("500");
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Remover Feriado municipal" })[0]);
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Excluir" }));

    await screen.findByText("Não foi possível carregar os eventos deste mês.");
    expect(screen.queryByTitle("Feriado municipal")).not.toBeInTheDocument();
    // E a lista de gerenciar, que lê a mesma lista e não some com a grade. A
    // mutação achou este buraco: sem esta linha, o caso passava com o evento
    // apagado ainda listado ali, com botão de remover e tudo.
    expect(screen.queryByRole("button", { name: "Remover Feriado municipal" })).not.toBeInTheDocument();
  });

  it("editar com o dia aberto e a recarga falhar não diz que o dia ficou vazio", async () => {
    // Excluir e trocar de mês fecham o detalhe do dia; editar não. Se a recarga
    // depois de salvar falha, o detalhe diria "Nenhum evento neste dia." de um dia
    // que ninguém conseguiu consultar.
    vi.mocked(calendarService.updateCalendarEvent).mockResolvedValue(BRANCO);
    await montar("admin", [BRANCO]);
    fireEvent.click(screen.getByText(String(DIA)));
    const detalhe = await screen.findByRole("region", { name: `${DIA} de ${MESES[MES]}` });

    vi.mocked(calendarService.getCalendarEvents).mockImplementation(async (ano) => {
      if (ano === undefined) return [BRANCO];
      throw new Error("500");
    });
    fireEvent.click(within(detalhe).getByRole("button", { name: "Editar Feriado municipal" }));
    const dialogo = await screen.findByRole("dialog", { name: "Editar evento" });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Salvar" }));

    await screen.findByText("Não foi possível carregar os eventos deste mês.");
    expect(screen.queryByText("Nenhum evento neste dia.")).not.toBeInTheDocument();
  });

  it("resposta velha da lateral não sobrescreve a nova", async () => {
    vi.mocked(calendarService.deleteCalendarEvent).mockResolvedValue(undefined);
    const soltas: Array<(v: calendarService.CalendarEvent[]) => void> = [];
    vi.mocked(useAuth).mockReturnValue({ user: { id: "u1", role: "admin", name: "X" } } as never);
    vi.mocked(calendarService.getCalendarEventTypes).mockResolvedValue(TIPOS);
    vi.mocked(calendarService.getCalendarEvents).mockImplementation((ano) =>
      ano === undefined
        ? new Promise((resolve) => { soltas.push(resolve); })
        : Promise.resolve([BRANCO]),
    );
    render(<CalendarPage />);
    await screen.findByTitle("Feriado municipal");

    fireEvent.click(screen.getAllByRole("button", { name: "Remover Feriado municipal" })[0]);
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(soltas).toHaveLength(2));

    soltas[1]([]); // a da recarga, nova, volta primeiro
    await screen.findByText("Nenhum evento próximo.");
    soltas[0]([FUTURO]); // a da montagem, velha, volta depois

    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("Vistoria anual")).not.toBeInTheDocument();
  });

  it("excluir evento que outra pessoa já removeu fecha o diálogo e recarrega", async () => {
    vi.mocked(calendarService.deleteCalendarEvent).mockRejectedValue({
      response: { status: 404, data: { detail: "Evento não encontrado. Ele pode ter sido removido da agenda." } },
    });
    await montar("admin", [BRANCO]);
    vi.mocked(calendarService.getCalendarEvents).mockClear();

    fireEvent.click(screen.getAllByRole("button", { name: "Remover Feriado municipal" })[0]);
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calendarService.getCalendarEvents).toHaveBeenCalled();
  });

  it("salvar evento que outra pessoa já removeu fecha o modal e recarrega", async () => {
    vi.mocked(calendarService.updateCalendarEvent).mockRejectedValue({
      response: { status: 404, data: { detail: "Evento não encontrado. Ele pode ter sido removido da agenda." } },
    });
    await montar("admin", [BRANCO]);
    vi.mocked(calendarService.getCalendarEvents).mockClear();

    fireEvent.click(screen.getAllByRole("button", { name: "Editar Feriado municipal" })[0]);
    const dialogo = await screen.findByRole("dialog", { name: "Editar evento" });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calendarService.getCalendarEvents).toHaveBeenCalled();
  });
});
