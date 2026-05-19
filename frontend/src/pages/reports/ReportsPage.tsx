import { useEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { FilterSelect, Spinner } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { useTheme } from "../../contexts/ThemeContext";
import {
  exportReportsUrl,
  getReports,
  getTechnicianDetailReport,
  getTechnicianListReport,
  type AvgFirstResponseItem,
  type CsatDailyItem,
  type HourlyCount,
  type OldestTicketItem,
  type ProductCount,
  type ReportData,
  type TechnicianDistItem,
  type ReportFilters,
  type TechnicianDetailReport,
  type TechnicianListReport,
} from "../../services/reportService";

// ── Constants ─────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { value: "7",           label: "Últimos 7 dias"   },
  { value: "14",          label: "Últimos 14 dias"  },
  { value: "30",          label: "Últimos 30 dias"  },
  { value: "90",          label: "Últimos 90 dias"  },
  { value: "personalizado", label: "Personalizado"  },
];

const CATEGORY_OPTIONS = [
  { value: "hardware", label: "Hardware"  },
  { value: "software", label: "Software"  },
  { value: "network",  label: "Rede"      },
  { value: "access",   label: "Acesso"    },
  { value: "email",    label: "E-mail"    },
  { value: "security", label: "Segurança" },
  { value: "general",  label: "Geral"     },
  { value: "other",    label: "Outro"     },
];

const PRIORITY_OPTIONS = [
  { value: "critical", label: "Crítica" },
  { value: "high",     label: "Alta"    },
  { value: "medium",   label: "Média"   },
  { value: "low",      label: "Baixa"   },
];

const PRIORITY_COLORS: Record<string, string> = {
  critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e",
};
const PRIORITY_LABELS: Record<string, string> = {
  critical: "Crítica", high: "Alta", medium: "Média", low: "Baixa",
};
const CATEGORY_LABELS: Record<string, string> = {
  hardware: "Hardware", software: "Software", network: "Rede",
  access: "Acesso",   email: "E-mail",       security: "Segurança",
  general: "Geral",   other: "Outro",
};
const CSAT_COLORS = ["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e"];

const WEEKDAY_LABELS: Record<number, string> = {
  1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb", 7: "Dom",
};
const WEEKDAY_FULL: Record<number, string> = {
  1: "Segunda-feira", 2: "Terça-feira", 3: "Quarta-feira",
  4: "Quinta-feira", 5: "Sexta-feira", 6: "Sábado", 7: "Domingo",
};

const tooltipWrapperStyle = { outline: "none", border: "none" };

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  Download:  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>,
  ChevLeft:  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>,
  ChevDown:  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>,
  Chart:     <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>,
  Users:     <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
  Calendar:  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>,
};

// ── Shared sub-components ─────────────────────────────────────

function Delta({ current, prev }: { current: number; prev: number | null }) {
  if (prev === null || prev === 0) return null;
  const pct = Math.round(((current - prev) / prev) * 100);
  if (pct === 0) return <span className="text-[10px] font-semibold text-slate-500">= igual</span>;
  const up = pct > 0;
  return (
    <span className={`flex items-center gap-0.5 text-[10px] font-semibold ${up ? "text-success-700 dark:text-success-400" : "text-danger-700 dark:text-danger-400"}`}>
      {up ? "▲" : "▼"} {Math.abs(pct)}% vs anterior
    </span>
  );
}

function StatCard({ label, value, sub, colorCls = "text-slate-100", delta }: {
  label: string; value: string | number; sub?: string; colorCls?: string;
  delta?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border/40 bg-background-surface p-4">
      <p className="mb-2 text-xs font-medium text-slate-500">{label}</p>
      <p className={`text-2xl font-bold leading-none ${colorCls}`}>{value}</p>
      <div className="mt-1.5 flex items-center gap-2 flex-wrap">
        {sub && <p className="text-xs text-slate-500">{sub}</p>}
        {delta}
      </div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border/40 bg-background-surface">
      <div className="border-b border-border/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

// ── Avg first response chart ──────────────────────────────────

function FirstResponseChart({ data, gridColor, tooltipBg, tooltipBorder, tooltipColor, fmtHours }: {
  data: AvgFirstResponseItem[]; gridColor: string;
  tooltipBg: string; tooltipBorder: string; tooltipColor: string;
  fmtHours: (h: number | null) => string;
}) {
  const chartData = data.filter((r) => r.avg_hours != null).map((r) => ({ priority: r.priority, avg_hours: r.avg_hours ?? 0 }));
  if (chartData.length === 0) return null;
  return (
    <ChartCard title="Tempo médio de 1ª resposta por prioridade">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barSize={48}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
          <XAxis dataKey="priority" tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickFormatter={(v: string) => PRIORITY_LABELS[v] ?? v} />
          <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickFormatter={(v: number) => v >= 24 ? `${(v / 24).toFixed(0)}d` : `${v}h`} />
          <Tooltip cursor={{ fill: gridColor }} wrapperStyle={{ outline: "none", border: "none" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              return (
                <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor, outline: "none" }}>
                  <p style={{ fontWeight: 600, marginBottom: 4 }}>{PRIORITY_LABELS[String(label)] ?? label}</p>
                  <p style={{ color: "#6366f1" }}>Tempo médio: {fmtHours(payload[0].value as number)}</p>
                </div>
              );
            }} />
          <Bar dataKey="avg_hours" radius={[4, 4, 0, 0]}>
            {chartData.map((e) => <Cell key={e.priority} fill={PRIORITY_COLORS[e.priority] ?? "#6366f1"} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Tickets by product chart ──────────────────────────────────

function ProductChart({ data, gridColor, tooltipBg, tooltipBorder, tooltipColor }: {
  data: ProductCount[]; gridColor: string;
  tooltipBg: string; tooltipBorder: string; tooltipColor: string;
}) {
  if (data.length === 0) return null;
  return (
    <ChartCard title="Tickets por produto">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
          <YAxis dataKey="product_name" type="category" tick={{ fontSize: 10, fill: "#94a3b8" }} width={80}
            tickFormatter={(v: string) => v.length > 12 ? `${v.slice(0, 12)}…` : v} />
          <Tooltip cursor={{ fill: gridColor }} wrapperStyle={{ outline: "none", border: "none" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              return (
                <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor, outline: "none" }}>
                  <p style={{ fontWeight: 600, marginBottom: 4 }}>{label}</p>
                  <p style={{ color: "#6366f1" }}>Tickets: {payload[0].value ?? 0}</p>
                </div>
              );
            }} />
          <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Hourly distribution chart ─────────────────────────────────

function HourlyChart({ data, gridColor, tooltipBg, tooltipBorder, tooltipColor }: {
  data: HourlyCount[]; gridColor: string;
  tooltipBg: string; tooltipBorder: string; tooltipColor: string;
}) {
  const hasData = data.some((d) => d.count > 0);
  if (!hasData) return null;

  function hourColor(h: number): string {
    if (h >= 6 && h < 12)  return "#6366f1";  // manhã
    if (h >= 12 && h < 18) return "#8b5cf6";  // tarde
    if (h >= 18 && h < 22) return "#a78bfa";  // noite
    return "#475569";                           // madrugada
  }

  return (
    <ChartCard title="Tickets por hora do dia">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
          <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickFormatter={(v: number) => v % 3 === 0 ? `${v}h` : ""} />
          <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
          <Tooltip cursor={{ fill: gridColor }} wrapperStyle={{ outline: "none", border: "none" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const h = Number(label ?? 0);
              const period = h >= 6 && h < 12 ? "Manhã" : h >= 12 && h < 18 ? "Tarde" : h >= 18 && h < 22 ? "Noite" : "Madrugada";
              return (
                <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor, outline: "none" }}>
                  <p style={{ fontWeight: 600, marginBottom: 4 }}>{h}h — {period}</p>
                  <p style={{ color: hourColor(h) }}>Tickets: {payload[0].value ?? 0}</p>
                </div>
              );
            }} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((e) => <Cell key={e.hour} fill={hourColor(e.hour)} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-2 text-center text-[10px] text-slate-500">
        <span style={{ color: "#6366f1" }}>■</span> manhã &nbsp;
        <span style={{ color: "#8b5cf6" }}>■</span> tarde &nbsp;
        <span style={{ color: "#a78bfa" }}>■</span> noite &nbsp;
        <span style={{ color: "#475569" }}>■</span> madrugada
      </p>
    </ChartCard>
  );
}

// ── Technician distribution chart ────────────────────────────

function TechnicianDistChart({ data, gridColor, tooltipBg, tooltipBorder, tooltipColor }: {
  data: TechnicianDistItem[];
  gridColor: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipColor: string;
}) {
  const chartData = [...data].reverse();
  const chartHeight = Math.max(200, chartData.length * 40);

  return (
    <ChartCard title="Distribuição de tickets por técnico">
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 0, right: 8, left: 4, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
          <YAxis dataKey="technician_name" type="category" tick={{ fontSize: 10, fill: "#94a3b8" }}
            width={90} tickFormatter={(v: string) => v.length > 12 ? `${v.slice(0, 12)}…` : v} />
          <Tooltip
            cursor={{ fill: gridColor }}
            wrapperStyle={{ outline: "none", border: "none" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const resolved = (payload.find((p) => p.dataKey === "resolved")?.value as number) ?? 0;
              const open = (payload.find((p) => p.dataKey === "open_count")?.value as number) ?? 0;
              return (
                <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor, outline: "none" }}>
                  <p style={{ fontWeight: 600, marginBottom: 4 }}>{label}</p>
                  <p style={{ color: "#22c55e" }}>Resolvidos: {resolved}</p>
                  <p style={{ color: "#f59e0b" }}>Em aberto: {open}</p>
                  <p style={{ color: "#94a3b8", marginTop: 2 }}>Total: {resolved + open}</p>
                </div>
              );
            }}
          />
          <Legend
            formatter={(v) => v === "resolved" ? "Resolvidos" : "Em aberto"}
            wrapperStyle={{ fontSize: 11, color: "#94a3b8", paddingTop: 8 }}
          />
          <Bar dataKey="resolved" stackId="a" fill="#22c55e" radius={[0, 0, 0, 0]} name="resolved" />
          <Bar dataKey="open_count" stackId="a" fill="#f59e0b" radius={[0, 4, 4, 0]} name="open_count" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Oldest open tickets table ─────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  open: "Aberto", in_progress: "Em andamento",
  awaiting_client: "Aguard. cliente", awaiting_technical: "Aguard. técnico",
};

function fmtAge(hours: number): string {
  if (hours < 1)   return `${Math.round(hours * 60)} min`;
  if (hours < 24)  return `${hours.toFixed(1)}h`;
  if (hours < 168) return `${(hours / 24).toFixed(1)} dias`;
  return `${(hours / 168).toFixed(1)} sem`;
}

const OLDEST_PAGE_SIZE = 10;

function OldestOpenTable({ tickets }: { tickets: OldestTicketItem[] }) {
  const [page, setPage] = useState(0);
  const totalPages = Math.ceil(tickets.length / OLDEST_PAGE_SIZE);
  const paged = tickets.slice(page * OLDEST_PAGE_SIZE, (page + 1) * OLDEST_PAGE_SIZE);

  return (
    <div className="rounded-xl border border-border/40 bg-background-surface overflow-hidden">
      <div className="border-b border-border/40 px-5 py-3.5 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-200">Tickets em aberto há mais tempo</h2>
        <span className="rounded-full bg-danger-500/15 px-2 py-0.5 text-[10px] font-semibold text-danger-400">
          {tickets.length} ticket{tickets.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40">
              {["Protocolo", "Título", "Prioridade", "Categoria", "Status", "Técnico", "Tempo em aberto"].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {paged.map((t) => (
              <tr key={t.ticket_id} className="hover:bg-background-elevated/50 transition-colors">
                <td className="px-4 py-3 font-mono text-xs text-primary">{t.protocol}</td>
                <td className="px-4 py-3 text-slate-300 max-w-[220px] truncate" title={t.title}>{t.title}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    style={{ backgroundColor: `${PRIORITY_COLORS[t.priority]}22`, color: PRIORITY_COLORS[t.priority] }}>
                    {PRIORITY_LABELS[t.priority] ?? t.priority}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs">{CATEGORY_LABELS[t.category] ?? t.category}</td>
                <td className="px-4 py-3 text-slate-400 text-xs">{STATUS_LABELS[t.status] ?? t.status}</td>
                <td className="px-4 py-3 text-slate-400 text-xs">{t.assignee_name ?? <span className="text-slate-600">—</span>}</td>
                <td className="px-4 py-3">
                  <span className={`font-semibold text-xs ${t.sla_breached ? "text-danger-400" : "text-slate-300"}`}>
                    {fmtAge(t.age_hours)}
                    {t.sla_breached && <span className="ml-1.5 rounded bg-danger-500/20 px-1 py-0.5 text-[9px] font-bold text-danger-400">SLA</span>}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Paginação */}
      <div className="flex items-center justify-between border-t border-border/40 px-5 py-3">
        <span className="text-xs text-slate-500">
          {page * OLDEST_PAGE_SIZE + 1}–{Math.min((page + 1) * OLDEST_PAGE_SIZE, tickets.length)} de {tickets.length}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-lg border border-border/40 px-2.5 py-1.5 text-xs text-slate-400 hover:bg-background-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            ‹
          </button>
          {Array.from({ length: totalPages }, (_, i) => (
            <button
              key={i}
              onClick={() => setPage(i)}
              className={`rounded-lg border px-2.5 py-1.5 text-xs transition-colors cursor-pointer ${
                i === page
                  ? "border-primary bg-primary/20 text-primary font-semibold"
                  : "border-border/40 text-slate-400 hover:bg-background-elevated"
              }`}
            >
              {i + 1}
            </button>
          ))}
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="rounded-lg border border-border/40 px-2.5 py-1.5 text-xs text-slate-400 hover:bg-background-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            ›
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Global report (admin) ─────────────────────────────────────

function GlobalReport({ data, period }: { data: ReportData; period: number }) {
  const { theme } = useTheme();
  const totalCsat = data.csat_distribution.reduce((s, d) => s + d.count, 0);
  const criticalSla = data.sla_compliance.find((s) => s.priority === "critical")?.compliance_rate ?? 100;
  const highSla     = data.sla_compliance.find((s) => s.priority === "high")?.compliance_rate ?? 100;

  const tooltipBg     = theme === "dark" ? "#132238" : "#ffffff";
  const tooltipBorder = theme === "dark" ? "#1E3A5F" : "#e2e8f0";
  const tooltipColor  = theme === "dark" ? "#f1f5f9" : "#0f172a";
  const tooltipStyle = {
    backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`,
    borderRadius: "8px", fontSize: "12px", color: tooltipColor,
  };
  const gridColor = theme === "dark" ? "#132238" : "#ffffff";

  function BarTooltip({ active, payload, label, labelFn, valueFn, valueLabel }: {
    active?: boolean; payload?: { value: number }[]; label?: string;
    labelFn: (v: string) => string; valueFn: (v: number) => string; valueLabel: string;
  }) {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor, outline: "none" }}>
        <p style={{ fontWeight: 600, marginBottom: 4 }}>{labelFn(String(label ?? ""))}</p>
        <p style={{ color: "#6366f1" }}>{valueLabel}: {valueFn(payload[0].value)}</p>
      </div>
    );
  }

  function slaColor(rate: number) {
    if (rate >= 90) return "text-success-700 dark:text-success-400";
    if (rate >= 70) return "text-warning-700 dark:text-warning-400";
    return "text-danger-700 dark:text-danger-400";
  }

  function fmtHours(h: number | null): string {
    if (h == null) return "—";
    if (h < 1)  return `${Math.round(h * 60)} min`;
    if (h < 24) return `${h.toFixed(1)}h`;
    return `${(h / 24).toFixed(1)}d`;
  }

  const cmp = data.comparison;
  const prevCriticalSla = cmp?.sla_compliance.find((s) => s.priority === "critical")?.compliance_rate ?? null;
  const prevHighSla     = cmp?.sla_compliance.find((s) => s.priority === "high")?.compliance_rate ?? null;

  const resolutionChartData = (data.avg_resolution_by_priority ?? [])
    .filter((r) => r.avg_hours != null)
    .map((r) => ({ priority: r.priority, avg_hours: r.avg_hours ?? 0 }));

  const csatTrendData: CsatDailyItem[] = (data.csat_by_day ?? []).filter((d) => d.avg_rating != null);
  const hasCsatTrend = csatTrendData.length >= 2;

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <StatCard label="Tickets no período" value={data.total_tickets}
          sub={`últimos ${data.period_days} dias`}
          delta={<Delta current={data.total_tickets} prev={cmp?.total_tickets ?? null} />} />
        <StatCard label="Média CSAT"
          value={data.csat_average ? `${data.csat_average} / 5` : "—"}
          sub={`${totalCsat} avaliação${totalCsat !== 1 ? "ões" : ""}`}
          delta={data.csat_average != null && cmp?.csat_average != null
            ? <Delta current={data.csat_average * 10} prev={cmp.csat_average * 10} />
            : undefined} />
        <StatCard label="SLA Crítico" value={`${criticalSla}%`}
          sub="conformidade resolução" colorCls={slaColor(criticalSla)}
          delta={<Delta current={criticalSla} prev={prevCriticalSla} />} />
        <StatCard label="SLA Alto" value={`${highSla}%`}
          sub="conformidade resolução" colorCls={slaColor(highSla)}
          delta={<Delta current={highSla} prev={prevHighSla} />} />
        <StatCard label="Taxa de reabertura"
          value={`${data.reopen_rate ?? 0}%`}
          sub={`${data.reopened_count ?? 0} ticket${(data.reopened_count ?? 0) !== 1 ? "s" : ""} reaberto${(data.reopened_count ?? 0) !== 1 ? "s" : ""}`}
          colorCls={(data.reopen_rate ?? 0) === 0 ? "text-success-700 dark:text-success-400" : (data.reopen_rate ?? 0) <= 5 ? "text-slate-100" : (data.reopen_rate ?? 0) <= 15 ? "text-warning-700 dark:text-warning-400" : "text-danger-700 dark:text-danger-400"} />
      </div>

      {/* Tickets por dia */}
      <ChartCard title="Tickets criados por dia">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data.tickets_by_day} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="ticketGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }}
              tickFormatter={(v: string) => v.slice(5)}
              interval={Math.max(1, Math.floor(data.tickets_by_day.length / 6))} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
            <Tooltip contentStyle={tooltipStyle} wrapperStyle={tooltipWrapperStyle}
              labelFormatter={(v) => `Data: ${v}`} formatter={(v) => [v ?? 0, "Tickets"]} />
            <Area type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={2}
              fill="url(#ticketGradient)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* 3-column row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ChartCard title="Tickets por categoria">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.tickets_by_category.filter((c) => c.count > 0)}
              layout="vertical" margin={{ top: 0, right: 8, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
              <YAxis dataKey="category" type="category" tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v: string) => CATEGORY_LABELS[v] ?? v} width={60} />
              <Tooltip
                cursor={{ fill: gridColor }}
                wrapperStyle={tooltipWrapperStyle}
                content={({ active, payload, label }) => (
                  <BarTooltip active={active} payload={payload as { value: number }[]} label={String(label ?? "")}
                    labelFn={(v) => CATEGORY_LABELS[v] ?? v}
                    valueFn={(v) => String(v ?? 0)}
                    valueLabel="Tickets" />
                )} />
              <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Conformidade SLA por prioridade">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.sla_compliance} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis dataKey="priority" tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v: string) => PRIORITY_LABELS[v] ?? v} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`} />
              <Tooltip
                cursor={{ fill: gridColor }}
                wrapperStyle={tooltipWrapperStyle}
                content={({ active, payload, label }) => (
                  <BarTooltip active={active} payload={payload as { value: number }[]} label={String(label ?? "")}
                    labelFn={(v) => PRIORITY_LABELS[v] ?? v}
                    valueFn={(v) => `${v ?? 0}%`}
                    valueLabel="Conformidade" />
                )} />
              <Bar dataKey="compliance_rate" radius={[4, 4, 0, 0]}>
                {data.sla_compliance.map((entry) => (
                  <Cell key={entry.priority} fill={PRIORITY_COLORS[entry.priority] ?? "#6366f1"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Distribuição CSAT (1–5)">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.csat_distribution} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis dataKey="rating" tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v: number) => `★ ${v}`} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: gridColor }}
                wrapperStyle={tooltipWrapperStyle}
                content={({ active, payload, label }) => (
                  <BarTooltip active={active} payload={payload as { value: number }[]} label={String(label ?? "")}
                    labelFn={(v) => { const n = Number(v ?? 0); return `${n} estrela${n !== 1 ? "s" : ""}`; }}
                    valueFn={(v) => String(v ?? 0)}
                    valueLabel="Avaliações" />
                )} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {data.csat_distribution.map((entry) => (
                  <Cell key={entry.rating} fill={CSAT_COLORS[entry.rating - 1]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* 3-col: Tempo médio resolução | Tempo médio 1ª resposta | Tickets por produto */}
      {((resolutionChartData?.length ?? 0) > 0 || (data.avg_first_response_by_priority ?? []).some((r) => r.avg_hours != null) || (data.tickets_by_product?.length ?? 0) > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {(resolutionChartData?.length ?? 0) > 0 && (
            <ChartCard title="Tempo médio de resolução por prioridade">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={resolutionChartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barSize={36}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
                  <XAxis dataKey="priority" tick={{ fontSize: 10, fill: "#94a3b8" }}
                    tickFormatter={(v: string) => PRIORITY_LABELS[v] ?? v} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }}
                    tickFormatter={(v: number) => v >= 24 ? `${(v / 24).toFixed(0)}d` : `${v}h`} />
                  <Tooltip cursor={{ fill: gridColor }} wrapperStyle={tooltipWrapperStyle}
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      return (
                        <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor, outline: "none" }}>
                          <p style={{ fontWeight: 600, marginBottom: 4 }}>{PRIORITY_LABELS[String(label)] ?? label}</p>
                          <p style={{ color: "#6366f1" }}>Tempo médio: {fmtHours(payload[0].value as number)}</p>
                        </div>
                      );
                    }} />
                  <Bar dataKey="avg_hours" radius={[4, 4, 0, 0]}>
                    {resolutionChartData.map((e) => <Cell key={e.priority} fill={PRIORITY_COLORS[e.priority] ?? "#6366f1"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          )}
          <FirstResponseChart data={data.avg_first_response_by_priority ?? []}
            gridColor={gridColor} tooltipBg={tooltipBg} tooltipBorder={tooltipBorder}
            tooltipColor={tooltipColor} fmtHours={fmtHours} />
          <ProductChart data={data.tickets_by_product ?? []}
            gridColor={gridColor} tooltipBg={tooltipBg} tooltipBorder={tooltipBorder} tooltipColor={tooltipColor} />
        </div>
      )}

      {/* Tendência CSAT */}
      {hasCsatTrend && (
        <ChartCard title="Tendência CSAT ao longo do tempo">
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.csat_by_day} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="csatGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}   />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v: string) => v.slice(5)}
                interval={Math.max(1, Math.floor(data.csat_by_day.length / 6))} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} />
              <ReferenceLine y={4} stroke="#10b981" strokeDasharray="4 3"
                label={{ value: "Meta 4.0", fill: "#10b981", fontSize: 10, position: "insideTopRight" }} />
              <Tooltip contentStyle={tooltipStyle} wrapperStyle={tooltipWrapperStyle}
                labelFormatter={(v) => `Data: ${v}`}
                formatter={(v: number, _: string, props: { payload: CsatDailyItem }) => [
                  v != null ? `${Number(v).toFixed(2)} ★ (${props.payload.count} avaliações)` : "—",
                  "CSAT",
                ]} />
              <Area type="monotone" dataKey="avg_rating" stroke="#f59e0b" strokeWidth={2}
                fill="url(#csatGradient)" dot={false} connectNulls={false} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Tickets em aberto há mais tempo */}
      {(data.oldest_open_tickets?.length ?? 0) > 0 && (
        <OldestOpenTable tickets={data.oldest_open_tickets} />
      )}

      {/* 2-col: Dia da semana | Hora do dia */}
      {((data.tickets_by_weekday ?? []).some((d) => d.count > 0) || (data.tickets_by_hour ?? []).some((d) => d.count > 0)) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {(data.tickets_by_weekday?.length ?? 0) > 0 && (
            <ChartCard title="Volume por dia da semana">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.tickets_by_weekday} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barSize={40}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
                  <XAxis dataKey="weekday" tick={{ fontSize: 10, fill: "#94a3b8" }}
                    tickFormatter={(v: number) => WEEKDAY_LABELS[v] ?? v} />
                  <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
                  <Tooltip cursor={{ fill: gridColor }} wrapperStyle={tooltipWrapperStyle}
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      const wd = Number(label ?? 0);
                      return (
                        <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor, outline: "none" }}>
                          <p style={{ fontWeight: 600, marginBottom: 4 }}>{WEEKDAY_FULL[wd] ?? label}</p>
                          <p style={{ color: wd >= 6 ? "#f59e0b" : "#6366f1" }}>Tickets: {payload[0].value ?? 0}</p>
                        </div>
                      );
                    }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {data.tickets_by_weekday.map((e) => <Cell key={e.weekday} fill={e.weekday >= 6 ? "#f59e0b" : "#6366f1"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 text-center text-[10px] text-slate-500">
                <span style={{ color: "#f59e0b" }}>■</span> fim de semana
              </p>
            </ChartCard>
          )}
          <HourlyChart data={data.tickets_by_hour ?? []}
            gridColor={gridColor} tooltipBg={tooltipBg} tooltipBorder={tooltipBorder} tooltipColor={tooltipColor} />
        </div>
      )}

      {/* Distribuição de tickets por técnico */}
      {(data.technicians_dist?.length ?? 0) > 0 && (
        <TechnicianDistChart data={data.technicians_dist} gridColor={gridColor}
          tooltipBg={tooltipBg} tooltipBorder={tooltipBorder} tooltipColor={tooltipColor} />
      )}

    </div>
  );
}

// ── Technician detail ─────────────────────────────────────────

function TechnicianDetail({ data }: { data: TechnicianDetailReport }) {
  const { theme } = useTheme();
  const tooltipBg     = theme === "dark" ? "#132238" : "#ffffff";
  const tooltipBorder = theme === "dark" ? "#1E3A5F" : "#e2e8f0";
  const tooltipColor  = theme === "dark" ? "#f1f5f9" : "#0f172a";
  const tooltipStyle = {
    backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`,
    borderRadius: "8px", fontSize: "12px", color: tooltipColor,
  };

  function slaColor(rate: number) {
    if (rate >= 90) return "text-success-700 dark:text-success-400";
    if (rate >= 70) return "text-warning-700 dark:text-warning-400";
    return "text-danger-700 dark:text-danger-400";
  }

  function resolutionStr(h: number | null) {
    if (h == null) return "—";
    return h >= 24 ? `${(h / 24).toFixed(1)}d` : `${h.toFixed(1)}h`;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Atribuídos no período"  value={data.total_assigned}
          sub={`últimos ${data.period_days} dias`} />
        <StatCard label="Resolvidos / Fechados"  value={data.resolved}
          sub={data.total_assigned > 0 ? `${Math.round((data.resolved / data.total_assigned) * 100)}% do total` : "—"}
          colorCls="text-success-700 dark:text-success-400" />
        <StatCard label="Conformidade SLA"  value={`${data.sla_compliance_rate}%`}
          sub={`${data.sla_breached} violação${data.sla_breached !== 1 ? "ões" : ""}`}
          colorCls={slaColor(data.sla_compliance_rate)} />
        <StatCard label="CSAT médio"
          value={data.csat_average ? `${data.csat_average} / 5` : "—"}
          sub={data.csat_count > 0 ? `${data.csat_count} avaliação${data.csat_count !== 1 ? "ões" : ""}` : "sem avaliações"} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Em andamento"           value={data.in_progress} />
        <StatCard label="Em aberto"              value={data.open_count} />
        <StatCard label="Tempo médio resolução"  value={resolutionStr(data.avg_resolution_hours)}
          sub="tickets fechados" />
        <StatCard label="Taxa de resolução"
          value={data.total_assigned > 0 ? `${Math.round((data.resolved / data.total_assigned) * 100)}%` : "—"} />
      </div>

      <ChartCard title="Tickets atribuídos por dia">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data.tickets_by_day} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="techGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }}
              tickFormatter={(v: string) => v.slice(5)}
              interval={Math.max(1, Math.floor(data.tickets_by_day.length / 6))} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} allowDecimals={false} />
            <Tooltip contentStyle={tooltipStyle} wrapperStyle={tooltipWrapperStyle}
              labelFormatter={(v) => `Data: ${v}`} formatter={(v) => [v ?? 0, "Tickets"]} />
            <Area type="monotone" dataKey="count" stroke="#22c55e" strokeWidth={2}
              fill="url(#techGradient)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

// ── Technician ranking table (admin) ─────────────────────────

function TechnicianRanking({ data, onSelect }: { data: TechnicianListReport; onSelect: (id: string) => void }) {
  function slaColor(rate: number) {
    if (rate >= 90) return "text-success-700 dark:text-success-400";
    if (rate >= 70) return "text-warning-700 dark:text-warning-400";
    return "text-danger-700 dark:text-danger-400";
  }

  return (
    <div className="rounded-xl border border-border/40 bg-background-surface overflow-hidden">
      <div className="border-b border-border/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-slate-200">Desempenho por técnico</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40">
              {["Técnico", "Atribuídos", "Resolvidos", "Em aberto", "SLA", "Tempo médio", "CSAT", ""].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {data.technicians.map((t) => (
              <tr key={t.technician_id} className="hover:bg-background-elevated/50 transition-colors">
                <td className="px-4 py-3 font-medium text-slate-200">{t.technician_name}</td>
                <td className="px-4 py-3 text-slate-400">{t.total_assigned}</td>
                <td className={`px-4 py-3 font-medium text-success-700 dark:text-success-400`}>{t.resolved}</td>
                <td className="px-4 py-3 text-slate-400">{t.open_count}</td>
                <td className={`px-4 py-3 font-semibold ${slaColor(t.sla_compliance_rate)}`}>{t.sla_compliance_rate}%</td>
                <td className="px-4 py-3 text-slate-400">
                  {t.avg_resolution_hours != null
                    ? t.avg_resolution_hours >= 24
                      ? `${(t.avg_resolution_hours / 24).toFixed(1)}d`
                      : `${t.avg_resolution_hours.toFixed(1)}h`
                    : "—"}
                </td>
                <td className="px-4 py-3 text-slate-400">{t.csat_average != null ? `${t.csat_average} ★` : "—"}</td>
                <td className="px-4 py-3">
                  <button onClick={() => onSelect(t.technician_id)}
                    className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/20 transition-colors cursor-pointer">
                    Detalhes
                  </button>
                </td>
              </tr>
            ))}
            {data.technicians.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-sm text-slate-500">
                  Nenhum técnico ativo encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Technician detail panel (admin drill-down) ────────────────

function TechnicianDetailPanel({ techDetail, techDetailLoading, onClose }: {
  techDetail: TechnicianDetailReport | null;
  techDetailLoading: boolean;
  onClose: () => void;
}) {
  return (
    <div className="rounded-xl border border-border/40 bg-background-surface">
      <div className="flex items-center justify-between border-b border-border/40 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-200">
            {techDetail ? `Detalhes — ${techDetail.technician_name}` : "Carregando detalhes…"}
          </span>
        </div>
        <button onClick={onClose}
          className="rounded-lg border border-border/40 px-3 py-1 text-xs font-medium text-slate-400 hover:bg-background-elevated hover:text-slate-200 transition-colors cursor-pointer">
          {IC.ChevLeft} Fechar
        </button>
      </div>
      <div className="p-5">
        {techDetailLoading && (
          <div className="flex h-32 items-center justify-center"><Spinner size="md" /></div>
        )}
        {!techDetailLoading && techDetail && <TechnicianDetail data={techDetail} />}
      </div>
    </div>
  );
}

// ── Export dropdown ───────────────────────────────────────────

function ExportDropdown({ filters }: { filters: ReportFilters }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 items-center gap-1.5 rounded-lg border border-border/40 bg-background-elevated px-3 text-xs font-medium text-slate-400 hover:bg-background-surface hover:text-slate-200 transition-colors cursor-pointer"
      >
        {IC.Download}
        Exportar
        <span className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
          {IC.ChevDown}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-20 min-w-[140px] rounded-xl border border-border/40 bg-background-surface shadow-lg overflow-hidden">
          <a
            href={exportReportsUrl("csv", filters)}
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-slate-300 hover:bg-background-elevated transition-colors"
          >
            {IC.Download} Exportar CSV
          </a>
          <a
            href={exportReportsUrl("pdf", filters)}
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-slate-300 hover:bg-background-elevated transition-colors border-t border-border/30"
          >
            {IC.Download} Exportar PDF
          </a>
        </div>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────

type Tab = "global" | "technicians";

export default function ReportsPage() {
  const { user } = useAuth();
  const isAdmin      = user?.role === "admin";
  const isTechnician = user?.role === "technician";

  const [period,      setPeriod]      = useState("30");
  const [customStart, setCustomStart] = useState("");
  const [customEnd,   setCustomEnd]   = useState("");
  const [category,    setCategory]    = useState("");
  const [priority,    setPriority]    = useState("");
  const [tab,         setTab]         = useState<Tab>(isAdmin ? "global" : "technicians");

  const [globalData,        setGlobalData]        = useState<ReportData | null>(null);
  const [globalLoading,     setGlobalLoading]     = useState(false);

  const [techList,          setTechList]          = useState<TechnicianListReport | null>(null);
  const [techListLoading,   setTechListLoading]   = useState(false);

  const [selectedTechId,    setSelectedTechId]    = useState<string | undefined>(isTechnician ? user?.id : undefined);
  const [techDetail,        setTechDetail]        = useState<TechnicianDetailReport | null>(null);
  const [techDetailLoading, setTechDetailLoading] = useState(false);

  const isCustom = period === "personalizado" && !!customStart && !!customEnd;
  const p = isCustom
    ? Math.max(1, Math.ceil((new Date(customEnd).getTime() - new Date(customStart).getTime()) / 86400000))
    : Number(period) || 30;

  const reportFilters: ReportFilters = {
    ...(isCustom ? { start_date: customStart, end_date: customEnd } : { period: p }),
    ...(category ? { category } : {}),
    ...(priority ? { priority } : {}),
  };

  useEffect(() => {
    if (tab !== "global" || !isAdmin) return;
    setGlobalLoading(true);
    getReports(reportFilters).then(setGlobalData).catch(() => {}).finally(() => setGlobalLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, p, isAdmin, category, priority, customStart, customEnd]);

  useEffect(() => {
    if (tab !== "technicians" || !isAdmin) return;
    setTechListLoading(true);
    getTechnicianListReport(p).then(setTechList).catch(() => {}).finally(() => setTechListLoading(false));
  }, [tab, p, isAdmin]);

  useEffect(() => {
    if (isTechnician) {
      setTechDetailLoading(true);
      getTechnicianDetailReport(p).then(setTechDetail).catch(() => {}).finally(() => setTechDetailLoading(false));
      return;
    }
    if (!selectedTechId) return;
    setTechDetailLoading(true);
    getTechnicianDetailReport(p, selectedTechId).then(setTechDetail).catch(() => {}).finally(() => setTechDetailLoading(false));
  }, [p, selectedTechId, isTechnician]);

  function handleSelectTechnician(id: string) {
    setSelectedTechId(id);
    setTechDetail(null);
  }

  const activeFiltersCount = (category ? 1 : 0) + (priority ? 1 : 0);

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "global",       label: "Visão geral", icon: IC.Chart  },
    { key: "technicians",  label: "Por técnico", icon: IC.Users  },
  ];

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-slate-100">Relatórios</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            {isTechnician ? "Suas métricas de desempenho" : "Visão geral e desempenho da equipe"}
            {activeFiltersCount > 0 && (
              <span className="ml-2 rounded-full bg-primary/20 px-2 py-0.5 text-[10px] font-semibold text-primary">
                {activeFiltersCount} filtro{activeFiltersCount > 1 ? "s" : ""} ativo{activeFiltersCount > 1 ? "s" : ""}
              </span>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Tabs inline (admin only) */}
          {isAdmin && (
            <div className="flex h-9 items-center gap-0.5 rounded-xl border border-border/40 bg-background-elevated px-1">
              {tabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`flex h-7 items-center gap-2 rounded-lg px-4 text-sm font-medium transition-all cursor-pointer ${
                    tab === t.key
                      ? "bg-primary text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-background-surface"
                  }`}
                >
                  {t.icon}
                  {t.label}
                </button>
              ))}
            </div>
          )}

          <FilterSelect value={period} onChange={setPeriod} options={PERIOD_OPTIONS} placeholder="Período" />

          {period === "personalizado" && (
            <div className="flex h-9 items-center gap-1.5 rounded-lg border border-border/60 bg-background-elevated px-3 text-sm">
              <span className="shrink-0 text-slate-400">{IC.Calendar}</span>
              <input type="date" value={customStart} max={customEnd || undefined}
                onChange={(e) => setCustomStart(e.target.value)}
                className="bg-transparent text-slate-300 text-xs outline-none cursor-pointer w-28 [color-scheme:dark]" />
              <span className="text-slate-500 text-xs">até</span>
              <input type="date" value={customEnd} min={customStart || undefined}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="bg-transparent text-slate-300 text-xs outline-none cursor-pointer w-28 [color-scheme:dark]" />
            </div>
          )}

          {/* Filtros de categoria e prioridade (visão geral apenas) */}
          {(isAdmin && tab === "global") || isTechnician ? (
            <>
              <FilterSelect value={category} onChange={setCategory} options={CATEGORY_OPTIONS} placeholder="Todas as categorias" />
              <FilterSelect value={priority} onChange={setPriority} options={PRIORITY_OPTIONS} placeholder="Todas as prioridades" />
            </>
          ) : null}

          {isAdmin && <ExportDropdown filters={reportFilters} />}
        </div>
      </div>

      {/* ── Global tab (admin) ── */}
      {isAdmin && tab === "global" && (
        globalLoading
          ? <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
          : globalData
            ? <GlobalReport data={globalData} period={p} />
            : null
      )}

      {/* ── Technicians tab (admin) ── */}
      {isAdmin && tab === "technicians" && (
        <div className="space-y-4">
          {/* Seletor rápido de técnico */}
          {techList && techList.technicians.length > 0 && (
            <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-background-surface px-4 py-3">
              <span className="text-xs font-medium text-slate-500 shrink-0">Ver detalhes de:</span>
              <FilterSelect
                value={selectedTechId ?? ""}
                onChange={(v) => v ? handleSelectTechnician(v) : (setSelectedTechId(undefined), setTechDetail(null))}
                options={techList.technicians.map((t) => ({ value: t.technician_id, label: t.technician_name }))}
                placeholder="Selecione um técnico"
              />
              {selectedTechId && (
                <button
                  onClick={() => { setSelectedTechId(undefined); setTechDetail(null); }}
                  className="text-xs text-slate-500 hover:text-slate-200 transition-colors cursor-pointer shrink-0"
                >
                  Limpar
                </button>
              )}
            </div>
          )}

          {techListLoading
            ? <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
            : techList && <TechnicianRanking data={techList} onSelect={handleSelectTechnician} />
          }

          {selectedTechId && (
            <TechnicianDetailPanel
              techDetail={techDetail}
              techDetailLoading={techDetailLoading}
              onClose={() => { setSelectedTechId(undefined); setTechDetail(null); }}
            />
          )}
        </div>
      )}

      {/* ── Technician own view ── */}
      {isTechnician && (
        techDetailLoading
          ? <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
          : techDetail
            ? <TechnicianDetail data={techDetail} />
            : null
      )}
    </div>
  );
}
