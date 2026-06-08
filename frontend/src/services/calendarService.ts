import { api } from "./api";

export type CalendarEventType = "event" | "meeting" | "training" | "deadline" | "holiday";

export interface CalendarEvent {
  id: string;
  title: string;
  description: string | null;
  event_type: CalendarEventType;
  color: string;
  start_date: string;
  end_date: string;
  created_by: string | null;
  creator_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface CalendarEventListResponse {
  items: CalendarEvent[];
  total: number;
}

export interface CalendarEventPayload {
  title: string;
  description?: string | null;
  event_type: CalendarEventType;
  color: string;
  start_date: string;
  end_date: string;
}

export async function getCalendarEvents(year?: number, month?: number): Promise<CalendarEvent[]> {
  const params = new URLSearchParams();
  if (year !== undefined) params.set("year", String(year));
  if (month !== undefined) params.set("month", String(month));
  const { data } = await api.get<CalendarEventListResponse>(`/calendar/events?${params}`);
  return data.items;
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
