import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getCalendarEvents,
  createCalendarEvent,
  updateCalendarEvent,
  deleteCalendarEvent,
  type CalendarEvent,
  type CalendarEventPayload,
} from "../../services/calendarService";
import { api } from "../../services/api";

vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockPatch = vi.mocked(api.patch);
const mockDelete = vi.mocked(api.delete);

const evento: CalendarEvent = {
  id: "e1",
  title: "Treinamento de NR-35",
  description: "Trabalho em altura",
  event_type: "training",
  color: "#2563eb",
  start_date: "2026-09-10",
  end_date: "2026-09-10",
  created_by: "u1",
  creator_name: "Rickelme David",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

/** URL do primeiro (e único) GET registrado no mock. */
function urlDoGet(): string {
  return mockGet.mock.calls[0][0] as string;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getCalendarEvents", () => {
  it("sem ano nem mês, chama a rota com a query vazia", async () => {
    mockGet.mockResolvedValue({ data: { items: [evento], total: 1 } });

    await getCalendarEvents();

    expect(mockGet).toHaveBeenCalledWith("/calendar/events?");
  });

  it("monta a query com ano e mês, nessa ordem", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } });

    await getCalendarEvents(2026, 9);

    expect(urlDoGet()).toBe("/calendar/events?year=2026&month=9");
  });

  it("com só o ano, não inventa o parâmetro do mês", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } });

    await getCalendarEvents(2026);

    expect(urlDoGet()).toBe("/calendar/events?year=2026");
  });

  it("com só o mês, não inventa o parâmetro do ano", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } });

    await getCalendarEvents(undefined, 12);

    expect(urlDoGet()).toBe("/calendar/events?month=12");
  });

  it("trata o zero como valor, não como filtro ausente", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } });

    await getCalendarEvents(0, 0);

    expect(urlDoGet()).toBe("/calendar/events?year=0&month=0");
  });

  it("devolve só a lista de itens, descartando o envelope", async () => {
    mockGet.mockResolvedValue({ data: { items: [evento], total: 1 } });

    const result = await getCalendarEvents(2026, 9);

    expect(result).toEqual([evento]);
  });

  it("devolve lista vazia quando o mês não tem evento", async () => {
    mockGet.mockResolvedValue({ data: { items: [], total: 0 } });

    const result = await getCalendarEvents(2026, 2);

    expect(result).toEqual([]);
  });

  it("propaga o erro do servidor", async () => {
    mockGet.mockRejectedValue(new Error("500"));

    await expect(getCalendarEvents(2026, 9)).rejects.toThrow("500");
  });
});

describe("createCalendarEvent", () => {
  const payload: CalendarEventPayload = {
    title: "Treinamento de NR-35",
    description: "Trabalho em altura",
    event_type: "training",
    color: "#2563eb",
    start_date: "2026-09-10",
    end_date: "2026-09-10",
  };

  it("envia POST na rota da coleção com o payload intacto", async () => {
    mockPost.mockResolvedValue({ data: evento });

    await createCalendarEvent(payload);

    expect(mockPost).toHaveBeenCalledWith("/calendar/events", payload);
  });

  it("devolve o evento criado pelo servidor", async () => {
    const criado = { ...evento, id: "e2" };
    mockPost.mockResolvedValue({ data: criado });

    const result = await createCalendarEvent(payload);

    expect(result).toEqual(criado);
  });

  it("propaga o erro de validação do servidor", async () => {
    mockPost.mockRejectedValue(new Error("422"));

    await expect(createCalendarEvent(payload)).rejects.toThrow("422");
  });
});

describe("updateCalendarEvent", () => {
  it("envia PATCH na rota do id com o payload parcial", async () => {
    mockPatch.mockResolvedValue({ data: evento });

    await updateCalendarEvent("e1", { title: "Treinamento remarcado" });

    expect(mockPatch).toHaveBeenCalledWith("/calendar/events/e1", {
      title: "Treinamento remarcado",
    });
  });

  it("não completa os campos que o chamador omitiu", async () => {
    mockPatch.mockResolvedValue({ data: evento });

    await updateCalendarEvent("e1", { color: "#dc2626" });

    expect(mockPatch.mock.calls[0][1]).toEqual({ color: "#dc2626" });
  });

  it("devolve o evento já atualizado", async () => {
    const atualizado = { ...evento, title: "Treinamento remarcado" };
    mockPatch.mockResolvedValue({ data: atualizado });

    const result = await updateCalendarEvent("e1", {
      title: "Treinamento remarcado",
    });

    expect(result).toEqual(atualizado);
  });

  it("propaga o erro quando o evento não existe", async () => {
    mockPatch.mockRejectedValue(new Error("404"));

    await expect(updateCalendarEvent("sumiu", {})).rejects.toThrow("404");
  });
});

describe("deleteCalendarEvent", () => {
  it("envia DELETE na rota do id, sem corpo", async () => {
    mockDelete.mockResolvedValue({ data: null });

    await deleteCalendarEvent("e1");

    expect(mockDelete).toHaveBeenCalledWith("/calendar/events/e1");
    expect(mockDelete.mock.calls[0]).toHaveLength(1);
  });

  it("não devolve nada, mesmo se o servidor responder com corpo", async () => {
    mockDelete.mockResolvedValue({ data: evento });

    await expect(deleteCalendarEvent("e1")).resolves.toBeUndefined();
  });

  it("propaga o erro de permissão", async () => {
    mockDelete.mockRejectedValue(new Error("403"));

    await expect(deleteCalendarEvent("e1")).rejects.toThrow("403");
  });
});
