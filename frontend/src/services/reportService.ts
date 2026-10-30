import { api } from "./api";
import type { IntervaloDeDatas } from "../lib/periodoRelatorio";

export interface DailyCount {
  date: string;
  count: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface SLAComplianceItem {
  priority: string;
  total: number;
  breached: number;
  compliance_rate: number;
}

export interface CSATDistributionItem {
  rating: number;
  count: number;
}

export interface AvgResolutionItem {
  priority: string;
  avg_hours: number | null;
}

export interface CsatDailyItem {
  date: string;
  avg_rating: number | null;
  count: number;
}

export interface WeekdayCount {
  weekday: number; // 1 = Seg … 7 = Dom
  count: number;
}

export interface AvgFirstResponseItem {
  priority: string;
  avg_hours: number | null;
}

export interface ProductCount {
  product_name: string;
  count: number;
}

export interface HourlyCount {
  hour: number;
  count: number;
}

export interface TechnicianDistItem {
  technician_name: string;
  total: number;
  resolved: number;
  open_count: number;
}

export interface OldestTicketItem {
  ticket_id: string;
  protocol: string;
  title: string;
  /** Nulo enquanto o chamado nao foi triado. */
  priority: string | null;
  category: string;
  status: string;
  age_hours: number;
  sla_breached: boolean;
  assignee_name: string | null;
}

/**
 * Chamado resolvido fora do prazo, com o motivo que quem resolveu escreveu.
 *
 * O relatório de SLA só tinha número agregado: sabia-se QUANTOS estouraram,
 * nunca POR QUÊ. A contagem responde à auditoria; o motivo é o que permite
 * corrigir a causa.
 *
 * A lista vem do servidor pela PRESENÇA da justificativa, e não por uma conta
 * de datas feita na tela — é a mesma razão pela qual o front nunca decide se o
 * SLA estourou: ele não recebe a pausa acumulada (`sla_total_paused_ms`), então
 * acharia vencido o que não está.
 */
export interface SlaJustificationItem {
  ticket_id: string;
  protocol: string;
  title: string;
  priority: string | null;
  resolved_at: string | null;
  assignee_name: string | null;
  justification: string;
}

export interface ReportComparison {
  /** Os dias do período comparado (F1-B-03a). Ausentes num backend antigo. */
  start_date?: string | null;
  end_date?: string | null;
  total_tickets: number;
  csat_average: number | null;
  sla_compliance: SLAComplianceItem[];
}

export interface ReportData {
  period_days: number;
  /**
   * Os dias que o servidor de fato aplicou, e o fuso em que os leu (F1-B-03a).
   * Opcionais: um backend anterior à F1-B-03a não os manda.
   */
  start_date?: string | null;
  end_date?: string | null;
  timezone?: string | null;
  total_tickets: number;
  tickets_by_day: DailyCount[];
  tickets_by_category: CategoryCount[];
  sla_compliance: SLAComplianceItem[];
  csat_distribution: CSATDistributionItem[];
  csat_average: number | null;
  /** Média da nota "o quanto recomendaria a empresa"; null se ninguém respondeu. */
  recommend_average: number | null;
  avg_resolution_by_priority: AvgResolutionItem[];
  avg_first_response_by_priority: AvgFirstResponseItem[];
  csat_by_day: CsatDailyItem[];
  tickets_by_product: ProductCount[];
  tickets_by_weekday: WeekdayCount[];
  tickets_by_hour: HourlyCount[];
  oldest_open_tickets: OldestTicketItem[];
  technicians_dist: TechnicianDistItem[];
  reopened_count: number;
  reopen_rate: number;
  sla_justifications: SlaJustificationItem[];
  comparison: ReportComparison | null;
}

export interface TechnicianSummary {
  technician_id: string;
  technician_name: string;
  total_assigned: number;
  resolved: number;
  open_count: number;
  sla_breached: number;
  sla_compliance_rate: number;
  avg_resolution_hours: number | null;
  csat_average: number | null;
  csat_count: number;
}

export interface TechnicianListReport {
  period_days: number;
  /**
   * Os dias que o servidor de fato aplicou, e o fuso em que os leu (F1-B-03a).
   * Opcionais: um backend anterior à F1-B-03a não os manda.
   */
  start_date?: string | null;
  end_date?: string | null;
  timezone?: string | null;
  technicians: TechnicianSummary[];
}

export interface TechnicianDetailReport {
  period_days: number;
  /**
   * Os dias que o servidor de fato aplicou, e o fuso em que os leu (F1-B-03a).
   * Opcionais: um backend anterior à F1-B-03a não os manda.
   */
  start_date?: string | null;
  end_date?: string | null;
  timezone?: string | null;
  technician_id: string;
  technician_name: string;
  total_assigned: number;
  resolved: number;
  in_progress: number;
  open_count: number;
  sla_breached: number;
  sla_compliance_rate: number;
  avg_resolution_hours: number | null;
  csat_average: number | null;
  csat_count: number;
  tickets_by_day: DailyCount[];
}

export interface ReportFilters {
  period?: number;
  category?: string;
  priority?: string;
  start_date?: string;
  end_date?: string;
}

export async function getReports(filters: ReportFilters = {}): Promise<ReportData> {
  const { data } = await api.get<ReportData>("/dashboard/reports", {
    params: {
      ...(filters.period   !== undefined && { period:     filters.period   }),
      ...(filters.category !== undefined && { category:   filters.category }),
      ...(filters.priority !== undefined && { priority:   filters.priority }),
      ...(filters.start_date             && { start_date: filters.start_date }),
      ...(filters.end_date               && { end_date:   filters.end_date   }),
    },
  });
  return data;
}

/**
 * O recorte de tempo dos relatórios de técnico: as datas do calendário
 * (F1-B-03a) ou, por compatibilidade, o `period` legado em dias.
 *
 * As telas mandam as datas. O número continua aceito para quem ainda o usa, e
 * com o mesmo significado de antes: N dias contados de agora para trás.
 */
export type RecorteDeTempo = number | IntervaloDeDatas;

function paramsDoRecorte(recorte: RecorteDeTempo): Record<string, string | number> {
  return typeof recorte === "number"
    ? { period: recorte }
    : { start_date: recorte.start_date, end_date: recorte.end_date };
}

export async function getTechnicianListReport(
  recorte: RecorteDeTempo = 30,
): Promise<TechnicianListReport> {
  const { data } = await api.get<TechnicianListReport>(
    "/dashboard/reports/technicians",
    { params: paramsDoRecorte(recorte) },
  );
  return data;
}

export async function getTechnicianDetailReport(
  recorte: RecorteDeTempo = 30,
  technicianId?: string,
): Promise<TechnicianDetailReport> {
  const { data } = await api.get<TechnicianDetailReport>(
    "/dashboard/reports/technician",
    {
      params: {
        ...paramsDoRecorte(recorte),
        ...(technicianId ? { technician_id: technicianId } : {}),
      },
    },
  );
  return data;
}

export function exportReportsUrl(
  format: "csv" | "pdf",
  filters: ReportFilters,
): string {
  const params = new URLSearchParams();
  if (filters.start_date && filters.end_date) {
    params.set("start_date", filters.start_date);
    params.set("end_date",   filters.end_date);
  } else if (filters.period !== undefined) {
    params.set("period", String(filters.period));
  }
  if (filters.category) params.set("category", filters.category);
  if (filters.priority) params.set("priority", filters.priority);
  return `/api/v1/dashboard/reports/export/${format}?${params.toString()}`;
}
