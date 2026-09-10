import { api } from "./api";

export type SLALevel = "critical" | "high" | "medium" | "low";

export interface SLAConfig {
  id: string;
  level: SLALevel;
  // A UNIDADE DE VERDADE. `int` NOT NULL no banco, sempre presente na
  // resposta — `app/models/models.py` e `SLAConfigResponse`.
  response_time_minutes: number;
  resolve_time_minutes: number;

  // Derivados dos minutos acima, e NULOS quando o prazo não é hora cheia
  // (`_em_horas_exatas`). A Crítica tem 30 min, então estes dois chegam nulos
  // todo dia, e não por exceção. O próprio backend os chama de "derivados, só
  // para a tela antiga".
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
    // Minutos, e SÓ minutos. A ponte em horas existe no backend
    // (`SLAConfigUpdate`), mas mandar as duas para o mesmo campo é erro
    // declarado lá — "com ambos preenchidos não há como saber qual vale". Não
    // declarar as horas aqui é o que impede alguém de tentar.
    response_time_minutes?: number;
    resolve_time_minutes?: number;
    warning_threshold?: number;
    is_active?: boolean;
  },
): Promise<SLAConfig> {
  const { data } = await api.patch<SLAConfig>(`/sla-configs/${id}`, payload);
  return data;
}
