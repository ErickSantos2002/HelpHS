import { api } from "./api";

export interface Survey {
  id: string;
  ticket_id: string;
  user_id: string;
  rating: number;
  comment: string | null;
  created_at: string;
}

export interface SurveyCreate {
  rating: number;
  comment?: string;
}

export async function submitSurvey(
  ticketId: string,
  payload: SurveyCreate,
): Promise<Survey> {
  const { data } = await api.post<Survey>(
    `/tickets/${ticketId}/survey`,
    payload,
  );
  return data;
}

export async function getTicketSurvey(
  ticketId: string,
): Promise<Survey | null> {
  try {
    const { data } = await api.get<Survey>(`/tickets/${ticketId}/survey`);
    return data;
  } catch {
    return null;
  }
}
