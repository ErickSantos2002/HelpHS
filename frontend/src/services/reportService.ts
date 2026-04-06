import { api } from "./api";

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

export interface ReportData {
  period_days: number;
  total_tickets: number;
  tickets_by_day: DailyCount[];
  tickets_by_category: CategoryCount[];
  sla_compliance: SLAComplianceItem[];
  csat_distribution: CSATDistributionItem[];
  csat_average: number | null;
}

export async function getReports(period: number = 30): Promise<ReportData> {
  const { data } = await api.get<ReportData>("/dashboard/reports", {
    params: { period },
  });
  return data;
}

export function exportReportsUrl(
  format: "csv" | "pdf",
  period: number,
): string {
  return `/api/v1/dashboard/reports/export/${format}?period=${period}`;
}
