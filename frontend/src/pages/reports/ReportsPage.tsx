import { useEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
  type ReportData,
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

function StatCard({ label, value, sub, colorCls = "text-slate-100" }: {
  label: string; value: string | number; sub?: string; colorCls?: string;
}) {
  return (
    <div className="rounded-xl border border-border/40 bg-background-surface p-4">
      <p className="mb-2 text-xs font-medium text-slate-500">{label}</p>
      <p className={`text-2xl font-bold leading-none ${colorCls}`}>{value}</p>
      {sub && <p className="mt-1.5 text-xs text-slate-500">{sub}</p>}
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

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Tickets no período"   value={data.total_tickets}
          sub={`últimos ${data.period_days} dias`} />
        <StatCard label="Média CSAT"
          value={data.csat_average ? `${data.csat_average} / 5` : "—"}
          sub={`${totalCsat} avaliação${totalCsat !== 1 ? "ões" : ""}`} />
        <StatCard label="SLA Crítico"  value={`${criticalSla}%`}
          sub="conformidade resolução" colorCls={slaColor(criticalSla)} />
        <StatCard label="SLA Alto"     value={`${highSla}%`}
          sub="conformidade resolução" colorCls={slaColor(highSla)} />
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
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div>
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

        <div className="flex flex-wrap items-center gap-2">
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
