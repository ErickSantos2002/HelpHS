import { api } from "./api";

export interface DashboardStats {
  tickets: {
    total: number;
    open: number;
    in_progress: number;
    awaiting: number;
    resolved: number;
    closed: number;
    cancelled: number;
    by_priority_critical: number;
    by_priority_high: number;
    by_priority_medium: number;
    by_priority_low: number;
  };
  surveys: {
    total: number;
    average_rating: number | null;
  };
  sla: {
    response_breached: number;
    resolve_breached: number;
  };
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>("/dashboard/stats");
  return data;
}
