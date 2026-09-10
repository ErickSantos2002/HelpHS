import { api } from "./api";

export type SLALevel = "critical" | "high" | "medium" | "low";

export interface SLAConfig {
  id: string;
  level: SLALevel;
  // Derivados de `*_time_minutes` no backend, e NULOS quando o prazo não é
  // hora cheia — `app/schemas/sla.py`, `_em_horas_exatas`. A Crítica tem
  // 30 min, então estes dois chegam nulos todo dia, e não por exceção.
  //
  // Estavam declarados `number`. O tipo mentia, e por mentir desligou a única
  // checagem que existia: a tela interpolava `${null}h` e mostrava "nullh" em
  // produção sem erro de compilação nem exceção em runtime.
  response_time_hours: number | null;
  resolve_time_hours: number | null;
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
