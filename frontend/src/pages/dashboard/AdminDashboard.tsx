import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, Cell,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Alert, FilterSelect, Spinner } from "../../components/ui";
import { cn } from "../../lib/utils";
import { useTheme } from "../../contexts/ThemeContext";
import { getDashboardStats, type DashboardStats } from "../../services/dashboardService";
import {
  getReports, getTechnicianListReport, getTechnicianDetailReport,
  type ReportData, type TechnicianListReport, type TechnicianDetailReport,
} from "../../services/reportService";

// ── Period config ─────────────────────────────────────────────

type PeriodKey = "hoje" | "ontem" | "semana" | "mes" | "mes-passado" | "trimestre" | "ano" | "custom";
const PERIOD_OPTIONS: { key: PeriodKey; label: string; days: number }[] = [
  { key: "hoje",        label: "Hoje",            days: 1   },
  { key: "ontem",       label: "Ontem",           days: 2   },
  { key: "semana",      label: "Esta Semana",      days: 7   },
  { key: "mes",         label: "Este Mês",         days: 30  },
  { key: "mes-passado", label: "Mês Passado",      days: 60  },
  { key: "trimestre",   label: "Este Trimestre",   days: 90  },
  { key: "ano",         label: "Este Ano",         days: 365 },
  { key: "custom",      label: "Personalizado",    days: 0   },
];

function getDefaultCustomDates() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  return {
    start: start.toISOString().slice(0, 10),
    end:   end.toISOString().slice(0, 10),
  };
}

function customDays(start: string, end: string) {
  const diff = new Date(end).getTime() - new Date(start).getTime();
  return Math.max(1, Math.ceil(diff / 86400000) + 1);
}

// ── Colors ────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  Abertos:      "#0ea5e9",
  "Em andamento": "#6366f1",
  Aguardando:   "#f59e0b",
  Resolvidos:   "#10b981",
  Fechados:     "#64748b",
  Cancelados:   "#ef4444",
};

const PRIORITY_COLORS: Record<string, string> = {
  Crítico: "#ef4444",
  Alto:    "#f59e0b",
  Médio:   "#6366f1",
  Baixo:   "#64748b",
};

// ── Helpers ───────────────────────────────────────────────────

function slaColor(r: number) {
  return r >= 90 ? "text-emerald-600 dark:text-emerald-400" : r >= 70 ? "text-warning" : "text-danger";
}
function slaBg(r: number) {
  return r >= 90 ? "bg-emerald-500" : r >= 70 ? "bg-warning" : "bg-danger";
}
function fmtHours(h: number | null) {
  if (h == null) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)} dias`;
}
function fmtDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

// ── KPI Card ──────────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: number | string;
  sub?: string;
  icon: React.ReactNode;
  accent: string;  // border-l color class
  iconBg: string;
  valueCls?: string;
}

function KpiCard({ label, value, sub, icon, accent, iconBg, valueCls = "text-slate-900 dark:text-slate-100" }: KpiCardProps) {
  return (
    <div className={cn("relative rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border p-5 overflow-hidden border-l-4", accent)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
          <p className={cn("text-3xl font-bold mt-2 tabular-nums", valueCls)}>{value}</p>
          {sub && <p className="text-xs text-slate-500 mt-1.5">{sub}</p>}
        </div>
        <div className={cn("w-11 h-11 rounded-xl flex items-center justify-center shrink-0", iconBg)}>
          {icon}
        </div>
      </div>
    </div>
  );
}

// ── Status distribution bar ───────────────────────────────────

function StatusBar({ t }: { t: DashboardStats["tickets"] }) {
  const total = t.total || 1;
  const segs = [
    { label: "Abertos",       value: t.open,        color: "#0ea5e9" },
    { label: "Em andamento",  value: t.in_progress,  color: "#6366f1" },
    { label: "Aguardando",    value: t.awaiting,    color: "#f59e0b" },
    { label: "Resolvidos",    value: t.resolved,    color: "#10b981" },
    { label: "Fechados",      value: t.closed,      color: "#64748b" },
    { label: "Cancelados",    value: t.cancelled,   color: "#ef4444" },
  ].filter((s) => s.value > 0);

  return (
    <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Distribuição de status</p>
      <div className="flex h-3 rounded-full overflow-hidden gap-px">
        {segs.map((s) => (
          <div
            key={s.label}
            style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.color }}
            title={`${s.label}: ${s.value}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3">
        {segs.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
            <span className="text-xs text-slate-500">
              {s.label}: <span className="font-semibold text-slate-700 dark:text-slate-200">{s.value}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Section card ──────────────────────────────────────────────

function SectionCard({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-border/60">
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</p>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

// ── AdminDashboard ────────────────────────────────────────────

export default function AdminDashboard() {
  const { theme } = useTheme();

  // Period state
  const [periodKey, setPeriodKey] = useState<PeriodKey>("mes");
  const [customDates, setCustomDates] = useState(getDefaultCustomDates);

  // Technician filter
  const [selectedTechId, setSelectedTechId] = useState<string>("all");

  // Data
  const [stats, setStats]         = useState<DashboardStats | null>(null);
  const [report, setReport]       = useState<ReportData | null>(null);
  const [techList, setTechList]   = useState<TechnicianListReport | null>(null);
  const [techDetail, setTechDetail] = useState<TechnicianDetailReport | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  const activePeriod = periodKey === "custom"
    ? customDays(customDates.start, customDates.end)
    : PERIOD_OPTIONS.find((p) => p.key === periodKey)!.days;

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboardStats(),
      getReports({ period: activePeriod }),
      getTechnicianListReport(activePeriod),
    ])
      .then(([s, r, tl]) => { setStats(s); setReport(r); setTechList(tl); setTechDetail(null); })
      .catch(() => setError("Não foi possível carregar as estatísticas."))
      .finally(() => setLoading(false));
  }, [activePeriod]);

  useEffect(() => {
    if (selectedTechId === "all") { setTechDetail(null); return; }
    getTechnicianDetailReport(activePeriod, selectedTechId)
      .then(setTechDetail)
      .catch(() => setTechDetail(null));
  }, [selectedTechId, activePeriod]);


  const tooltipBg     = theme === "dark" ? "#132238" : "#ffffff";
  const tooltipBorder = theme === "dark" ? "#1E3A5F" : "#e2e8f0";
  const tooltipColor  = theme === "dark" ? "#f1f5f9" : "#0f172a";
  const tooltipStyle = {
    backgroundColor: tooltipBg,
    border: `1px solid ${tooltipBorder}`,
    borderRadius: "8px",
    color: tooltipColor,
    fontSize: "12px",
  };
  const tooltipWrapper = {
    backgroundColor: tooltipBg,
    border: `1px solid ${tooltipBorder}`,
    borderRadius: "8px",
    outline: "none",
  };
  const axisColor = theme === "dark" ? "#475569" : "#94a3b8";
  const gridColor = theme === "dark" ? "#1E3A5F" : "#f1f5f9";

  if (loading) return <div className="flex h-64 items-center justify-center"><Spinner size="lg" /></div>;
  if (error || !stats || !report) return <Alert variant="danger">{error ?? "Erro desconhecido."}</Alert>;

  const { tickets, surveys, sla } = stats;
  const avgRating = surveys.average_rating?.toFixed(1) ?? "—";

  const avgResolutionHours = (() => {
    if (!techList?.technicians.length) return null;
    const withData = techList.technicians.filter((t) => t.avg_resolution_hours != null);
    if (!withData.length) return null;
    return withData.reduce((s, t) => s + (t.avg_resolution_hours ?? 0), 0) / withData.length;
  })();

  const categoryData = [...(report.tickets_by_category ?? [])]
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
  const categoryMax = categoryData[0]?.count || 1;

  const statusData = [
    { name: "Abertos",       value: tickets.open         },
    { name: "Em andamento",  value: tickets.in_progress  },
    { name: "Aguardando",    value: tickets.awaiting     },
    { name: "Resolvidos",    value: tickets.resolved     },
    { name: "Fechados",      value: tickets.closed       },
    { name: "Cancelados",    value: tickets.cancelled    },
  ].filter((d) => d.value > 0);

  const priorityData = [
    { name: "Crítico", value: tickets.by_priority_critical },
    { name: "Alto",    value: tickets.by_priority_high     },
    { name: "Médio",   value: tickets.by_priority_medium   },
    { name: "Baixo",   value: tickets.by_priority_low      },
  ];

  const chartData      = techDetail ? techDetail.tickets_by_day  : report.tickets_by_day;
  const slaCompliance  = report.sla_compliance;
  const periodLabel    = PERIOD_OPTIONS.find((p) => p.key === periodKey)?.label ?? "";

  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-slate-100">Dashboard</h1>
          <p className="mt-0.5 text-sm text-slate-500">Visão geral do sistema de atendimento</p>
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Technician filter */}
          {techList && (
            <FilterSelect
              value={selectedTechId}
              onChange={setSelectedTechId}
              options={[
                { value: "all", label: "Todos os técnicos" },
                ...techList.technicians.map((t) => ({ value: t.technician_id, label: t.technician_name })),
              ]}
              placeholder="Todos os técnicos"
            />
          )}

          {/* Period filter */}
          <FilterSelect
            value={periodKey}
            onChange={(v) => setPeriodKey(v as PeriodKey)}
            options={PERIOD_OPTIONS.map((p) => ({ value: p.key, label: p.label }))}
            placeholder="Período"
          />

          {/* Custom date range */}
          {periodKey === "custom" && (
            <div className="flex h-9 items-center gap-1.5 rounded-lg border border-border/60 bg-background-elevated px-3 text-sm">
              <svg className="w-3.5 h-3.5 shrink-0 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
              <input
                type="date"
                value={customDates.start}
                max={customDates.end}
                onChange={(e) => setCustomDates((d) => ({ ...d, start: e.target.value }))}
                className="bg-transparent text-slate-700 dark:text-slate-300 text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
              />
              <span className="text-slate-500 text-xs">até</span>
              <input
                type="date"
                value={customDates.end}
                min={customDates.start}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setCustomDates((d) => ({ ...d, end: e.target.value }))}
                className="bg-transparent text-slate-700 dark:text-slate-300 text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
              />
            </div>
          )}
        </div>
      </div>

      {/* ── KPI Row ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="Total de tickets"
          value={tickets.total}
          sub="Todos os status"
          accent="border-l-slate-300 dark:border-l-slate-600"
          iconBg="bg-slate-100 dark:bg-background-elevated"
          icon={<svg className="w-5 h-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" /></svg>}
        />
        <KpiCard
          label="Abertos"
          value={tickets.open}
          sub="Aguardando atendimento"
          accent="border-l-sky-500"
          iconBg="bg-sky-500/10"
          valueCls="text-sky-600 dark:text-sky-400"
          icon={<svg className="w-5 h-5 text-sky-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>}
        />
        <KpiCard
          label="Em andamento"
          value={tickets.in_progress}
          sub="Sendo atendidos"
          accent="border-l-indigo-500"
          iconBg="bg-indigo-500/10"
          valueCls="text-indigo-600 dark:text-indigo-400"
          icon={<svg className="w-5 h-5 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>}
        />
        <KpiCard
          label="Aguardando"
          value={tickets.awaiting}
          sub="Resp. do cliente"
          accent="border-l-amber-500"
          iconBg="bg-amber-500/10"
          valueCls="text-amber-600 dark:text-amber-400"
          icon={<svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <KpiCard
          label="Resolvidos"
          value={tickets.resolved}
          sub={`+ ${tickets.closed} fechados`}
          accent="border-l-emerald-500"
          iconBg="bg-emerald-500/10"
          valueCls="text-emerald-600 dark:text-emerald-400"
          icon={<svg className="w-5 h-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <KpiCard
          label="SLA violado"
          value={sla.resolve_breached}
          sub={`${sla.response_breached} resposta · ${sla.resolve_breached} resolução`}
          accent={sla.resolve_breached > 0 ? "border-l-red-500" : "border-l-slate-300 dark:border-l-slate-600"}
          iconBg={sla.resolve_breached > 0 ? "bg-red-500/10" : "bg-slate-100 dark:bg-background-elevated"}
          valueCls={sla.resolve_breached > 0 ? "text-red-600 dark:text-red-400" : "text-slate-900 dark:text-slate-100"}
          icon={<svg className={cn("w-5 h-5", sla.resolve_breached > 0 ? "text-red-500" : "text-slate-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
        />
      </div>

      {/* ── Status bar ──────────────────────────────────────── */}
      <StatusBar t={tickets} />

      {/* ── Stats row ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="CSAT médio"
          value={avgRating === "—" ? "—" : `${avgRating} / 5`}
          sub={`${surveys.total} avaliações`}
          accent="border-l-amber-400"
          iconBg="bg-amber-500/10"
          valueCls="text-amber-600 dark:text-amber-400"
          icon={<svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>}
        />
        <KpiCard
          label="Tempo médio resolução"
          value={fmtHours(avgResolutionHours)}
          sub={avgResolutionHours != null ? "Média da equipe" : "Sem dados"}
          accent="border-l-violet-500"
          iconBg="bg-violet-500/10"
          valueCls="text-violet-600 dark:text-violet-400"
          icon={<svg className="w-5 h-5 text-violet-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>}
        />
        <KpiCard
          label="SLA Resposta violado"
          value={sla.response_breached}
          sub="1º atendimento fora do prazo"
          accent={sla.response_breached > 0 ? "border-l-amber-500" : "border-l-slate-300 dark:border-l-slate-600"}
          iconBg={sla.response_breached > 0 ? "bg-amber-500/10" : "bg-slate-100 dark:bg-background-elevated"}
          valueCls={sla.response_breached > 0 ? "text-amber-600 dark:text-amber-400" : "text-slate-900 dark:text-slate-100"}
          icon={<svg className={cn("w-5 h-5", sla.response_breached > 0 ? "text-amber-500" : "text-slate-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <KpiCard
          label="SLA Resolução violado"
          value={sla.resolve_breached}
          sub="Resolução fora do prazo"
          accent={sla.resolve_breached > 0 ? "border-l-red-500" : "border-l-slate-300 dark:border-l-slate-600"}
          iconBg={sla.resolve_breached > 0 ? "bg-red-500/10" : "bg-slate-100 dark:bg-background-elevated"}
          valueCls={sla.resolve_breached > 0 ? "text-red-600 dark:text-red-400" : "text-slate-900 dark:text-slate-100"}
          icon={<svg className={cn("w-5 h-5", sla.resolve_breached > 0 ? "text-red-500" : "text-slate-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
        />
      </div>

      {/* ── Charts row 1 ────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Area chart */}
        <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-border/60">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              {selectedTechId !== "all" && techDetail
                ? `Atendimentos de ${techDetail.technician_name} — ${periodLabel}`
                : `Tickets abertos por dia — ${periodLabel}`}
            </p>
          </div>
          <div className="p-5">
            {chartData.length === 0 ? (
              <div className="flex h-48 items-center justify-center text-slate-400 text-sm">Sem dados para o período</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="aGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#0ea5e9" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0}    />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: axisColor, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: axisColor, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} wrapperStyle={tooltipWrapper} labelFormatter={(v) => fmtDate(String(v))} formatter={(v) => [v, "Tickets"]} />
                  <Area type="monotone" dataKey="count" stroke="#0ea5e9" strokeWidth={2.5} fill="url(#aGrad)" dot={false} activeDot={{ r: 4, fill: "#0ea5e9", strokeWidth: 0 }} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Donut */}
        <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-border/60">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Tickets por Status</p>
          </div>
          <div className="p-5">
            {statusData.length === 0 ? (
              <div className="flex h-48 items-center justify-center text-slate-400 text-sm">Nenhum ticket</div>
            ) : (
              <>
                <div className="relative">
                  <ResponsiveContainer width="100%" height={180}>
                    <PieChart>
                      <Pie data={statusData} cx="50%" cy="50%" innerRadius={55} outerRadius={82} paddingAngle={3} dataKey="value">
                        {statusData.map((e) => <Cell key={e.name} fill={STATUS_COLORS[e.name] ?? "#475569"} />)}
                      </Pie>
                      <Tooltip contentStyle={tooltipStyle} wrapperStyle={tooltipWrapper} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <p className="text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">{statusData.reduce((a, b) => a + b.value, 0)}</p>
                    <p className="text-xs text-slate-500">total</p>
                  </div>
                </div>
                <div className="flex flex-col gap-1.5 mt-2">
                  {statusData.map((d) => (
                    <div key={d.name} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: STATUS_COLORS[d.name] ?? "#475569" }} />
                        <span className="text-xs text-slate-500">{d.name}</span>
                      </div>
                      <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 tabular-nums">{d.value}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Category + Charts row 2 ─────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Category breakdown */}
        <SectionCard title="Chamados por Categoria">
          {categoryData.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-slate-400 text-sm">Sem categorias no período</div>
          ) : (
            <div className="space-y-3">
              {categoryData.map((cat) => (
                <div key={cat.category}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-slate-600 dark:text-slate-300 truncate max-w-[70%]">{cat.category}</span>
                    <span className="text-xs font-bold tabular-nums text-slate-700 dark:text-slate-200">{cat.count}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-slate-100 dark:bg-background-elevated overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-700"
                      style={{ width: `${(cat.count / categoryMax) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        {/* Priority */}
        <SectionCard title="Tickets por Prioridade">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={priorityData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }} barSize={36}>
              <XAxis dataKey="name" tick={{ fill: axisColor, fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: axisColor, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: gridColor }}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div style={{ backgroundColor: tooltipBg, border: `1px solid ${tooltipBorder}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: tooltipColor }}>
                      <p style={{ fontWeight: 600, marginBottom: 4 }}>{label}</p>
                      <p style={{ color: "#0ea5e9" }}>Tickets : {payload[0].value}</p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} name="Tickets">
                {priorityData.map((e) => <Cell key={e.name} fill={PRIORITY_COLORS[e.name] ?? "#475569"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* SLA compliance */}
        <SectionCard title={`Conformidade SLA — ${periodLabel}`}>
          {slaCompliance.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-slate-400 text-sm">Sem dados de SLA</div>
          ) : (
            <div className="space-y-5 py-1">
              {slaCompliance.map((item) => (
                <div key={item.priority}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={cn("w-2 h-2 rounded-full", slaBg(item.compliance_rate))} />
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-200 capitalize">{item.priority}</span>
                    </div>
                    <div className="text-right">
                      <span className={cn("text-sm font-bold tabular-nums", slaColor(item.compliance_rate))}>
                        {item.compliance_rate.toFixed(0)}%
                      </span>
                      <span className="text-xs text-slate-400 ml-2">({item.breached} violados)</span>
                    </div>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100 dark:bg-background-elevated overflow-hidden">
                    <div className={cn("h-full rounded-full transition-all duration-700", slaBg(item.compliance_rate))} style={{ width: `${item.compliance_rate}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Team table ───────────────────────────────────────── */}
      {techList && techList.technicians.length > 0 && (
        <SectionCard title={`Performance da equipe — ${periodLabel}`}>
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b border-slate-100 dark:border-border/60">
                  {["Técnico", "Atribuídos", "Resolvidos", "Em aberto", "Conformidade SLA", "Tempo médio", "CSAT"].map((h) => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 pb-3 pr-4 last:pr-0">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50 dark:divide-border/30">
                {techList.technicians.map((t) => {
                  const initials = t.technician_name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase();
                  const isSelected = selectedTechId === t.technician_id;
                  return (
                    <tr
                      key={t.technician_id}
                      onClick={() => setSelectedTechId(isSelected ? "all" : t.technician_id)}
                      className={cn(
                        "transition-colors cursor-pointer",
                        isSelected
                          ? "bg-primary/5 dark:bg-primary/10"
                          : "hover:bg-slate-50 dark:hover:bg-background-elevated",
                      )}
                    >
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2.5">
                          <div className={cn("w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold", isSelected ? "bg-primary text-white" : "bg-primary/10 text-primary border border-primary/20")}>
                            {initials}
                          </div>
                          <span className="font-medium text-slate-700 dark:text-slate-200 truncate">{t.technician_name}</span>
                          {isSelected && <span className="text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded">filtrado</span>}
                        </div>
                      </td>
                      <td className="py-3 pr-4 tabular-nums text-slate-600 dark:text-slate-300">{t.total_assigned}</td>
                      <td className="py-3 pr-4 tabular-nums text-emerald-600 dark:text-emerald-400 font-medium">{t.resolved}</td>
                      <td className="py-3 pr-4 tabular-nums text-sky-600 dark:text-sky-400">{t.open_count}</td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-1.5 rounded-full bg-slate-100 dark:bg-background-elevated overflow-hidden">
                            <div className={cn("h-full rounded-full", slaBg(t.sla_compliance_rate))} style={{ width: `${t.sla_compliance_rate}%` }} />
                          </div>
                          <span className={cn("text-xs font-bold tabular-nums", slaColor(t.sla_compliance_rate))}>
                            {t.sla_compliance_rate.toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 tabular-nums text-slate-600 dark:text-slate-300">{fmtHours(t.avg_resolution_hours)}</td>
                      <td className="py-3">
                        {t.csat_average != null ? (
                          <div className="flex items-center gap-1">
                            <span className="tabular-nums font-bold text-amber-600 dark:text-amber-400">{t.csat_average.toFixed(1)}</span>
                            <svg className="w-3.5 h-3.5 text-amber-400" viewBox="0 0 20 20" fill="currentColor">
                              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                            </svg>
                            <span className="text-xs text-slate-400">({t.csat_count})</span>
                          </div>
                        ) : <span className="text-slate-400">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
