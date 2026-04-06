import { api } from "./api";

export type SLALevel = "critical" | "high" | "medium" | "low";

export interface SLAConfig {
  id: string;
  level: SLALevel;
  response_time_hours: number;
  resolve_time_hours: number;
  warning_threshold: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export async function getSLAConfigs(): Promise<SLAConfig[]> {
  const { data } = await api.get<SLAConfig[]>("/sla-configs");
  return data;
}

export async function updateSLAConfig(
  id: string,
  payload: {
    response_time_hours?: number;
    resolve_time_hours?: number;
    warning_threshold?: number;
    is_active?: boolean;
  },
): Promise<SLAConfig> {
  const { data } = await api.patch<SLAConfig>(`/sla-configs/${id}`, payload);
  return data;
}
