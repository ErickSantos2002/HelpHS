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
  technicians: TechnicianSummary[];
}

export interface TechnicianDetailReport {
  period_days: number;
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

export async function getReports(period: number = 30): Promise<ReportData> {
  const { data } = await api.get<ReportData>("/dashboard/reports", {
    params: { period },
  });
  return data;
}

export async function getTechnicianListReport(
  period: number = 30,
): Promise<TechnicianListReport> {
  const { data } = await api.get<TechnicianListReport>(
    "/dashboard/reports/technicians",
    { params: { period } },
  );
  return data;
}

export async function getTechnicianDetailReport(
  period: number = 30,
  technicianId?: string,
): Promise<TechnicianDetailReport> {
  const { data } = await api.get<TechnicianDetailReport>(
    "/dashboard/reports/technician",
    {
      params: {
        period,
        ...(technicianId ? { technician_id: technicianId } : {}),
      },
    },
  );
  return data;
}

export function exportReportsUrl(
  format: "csv" | "pdf",
  period: number,
): string {
  return `/api/v1/dashboard/reports/export/${format}?period=${period}`;
}
