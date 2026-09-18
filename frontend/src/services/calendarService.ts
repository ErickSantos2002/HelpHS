import { api } from "./api";

export type CalendarEventType = "event" | "meeting" | "training" | "deadline" | "holiday";

export interface CalendarEvent {
  id: string;
  title: string;
  description: string | null;
  event_type: CalendarEventType;
  /**
   * Derivada do tipo pela API desde o #18 — nunca a que alguém escolheu. É só
   * leitura: não existe mais campo de cor no contrato de escrita.
   */
  color: string;
  start_date: string;
  end_date: string;
  /**
   * Dia inteiro é data FLUTUANTE: vale a data em UTC, sem fuso. Evento com hora é
   * instante. As duas se leem diferente — ver `lib/agenda.ts`.
   */
  all_day: boolean;
  created_by: string | null;
  /**
   * `null` quando o autor foi apagado (a coluna é `ondelete=SET NULL`). Autor
   * anonimizado continua com nome, e o nome já diz que é anônimo.
   */
  creator_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface CalendarEventListResponse {
  items: CalendarEvent[];
  total: number;
}

/**
 * O que a tela manda ao criar ou editar.
 *
 * **Sem `color`**: a cor vem do tipo (#18), e a API ignora o campo se ele vier.
 *
 * **`all_day` sempre presente.** A API infere dia inteiro quando a chave NÃO vem
 * e as bordas são exatamente 00:00:00 e 23:59:59 (#17) — uma regra feita para a
 * tela antiga, que não conhecia a chave. A tela nova diz o que quer, e explícito
 * vence.
 */
export interface CalendarEventPayload {
  title: string;
  description?: string | null;
  event_type: CalendarEventType;
  start_date: string;
  end_date: string;
  all_day: boolean;
}

/** Um tipo e a cor que a API dá a ele. O rótulo é da tela. */
export interface CalendarEventTypeColor {
  value: CalendarEventType;
  color: string;
}

/**
 * Os eventos, todos ou os de um mês.
 *
 * **O mês vai de 1 a 12, como na API** — não de 0 a 11, como no `Date` do
 * JavaScript. Quem chama a partir de um mês de tela soma um.
 *
 * O `timezone` é o de quem olha. Com ele a API calcula a janela do mês no relógio
 * dessa pessoa, e o evento das 22:00 do dia 31 cai no mês em que ela o criou.
 */
export async function getCalendarEvents(
  year?: number,
  month?: number,
  timezone?: string,
): Promise<CalendarEvent[]> {
  const params = new URLSearchParams();
  if (year !== undefined) params.set("year", String(year));
  if (month !== undefined) params.set("month", String(month));
  if (timezone) params.set("timezone", timezone);
  const { data } = await api.get<CalendarEventListResponse>(`/calendar/events?${params}`);
  return data.items;
}

export async function getCalendarEventTypes(): Promise<CalendarEventTypeColor[]> {
  const { data } = await api.get<CalendarEventTypeColor[]>("/calendar/event-types");
  return data;
}

export async function createCalendarEvent(payload: CalendarEventPayload): Promise<CalendarEvent> {
  const { data } = await api.post<CalendarEvent>("/calendar/events", payload);
  return data;
}

export async function updateCalendarEvent(
  id: string,
  payload: Partial<CalendarEventPayload>,
): Promise<CalendarEvent> {
  const { data } = await api.patch<CalendarEvent>(`/calendar/events/${id}`, payload);
  return data;
}

export async function deleteCalendarEvent(id: string): Promise<void> {
  await api.delete(`/calendar/events/${id}`);
}
