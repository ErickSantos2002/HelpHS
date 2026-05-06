import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Alert, Spinner, StatusBadge } from "../../components/ui";
import { cn } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";
import { useTheme } from "../../contexts/ThemeContext";
import { getDashboardStats } from "../../services/dashboardService";
import { getTechnicianDetailReport, type TechnicianDetailReport } from "../../services/reportService";
import { getTickets, type Ticket } from "../../services/ticketService";

// ── Period config (same as AdminDashboard) ────────────────────

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
  return Math.max(1, Math.ceil((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 1);
}

// ── Helpers ───────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function formatHours(h: number | null): string {
  if (h == null) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)} dias`;
}

const PRIORITY_DOT: Record<string, string> = {
  critical: "bg-danger",
  high:     "bg-warning",
  medium:   "bg-primary",
  low:      "bg-slate-400",
};

// ── Sub-components ────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: number | string;
  sub?: string;
  icon: React.ReactNode;
  iconBg: string;
  accent: string;
  valueCls?: string;
}

function KpiCard({ label, value, sub, icon, iconBg, accent, valueCls = "text-slate-900 dark:text-slate-100" }: KpiCardProps) {
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

function TicketRow({ ticket, showTech }: { ticket: Ticket; showTech?: boolean }) {
  const navigate = useNavigate();
  const hasBreach = ticket.sla_response_breach || ticket.sla_resolve_breach;

  return (
    <button
      onClick={() => navigate(`/tickets/${ticket.id}`)}
      className="w-full group flex items-start gap-3 rounded-lg px-3 py-3 text-left hover:bg-slate-50 dark:hover:bg-background-elevated transition-colors"
    >
      <div className={cn("mt-2 w-1.5 h-1.5 rounded-full shrink-0", PRIORITY_DOT[ticket.priority] ?? "bg-slate-400")} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-xs font-mono text-slate-400">{ticket.protocol}</span>
          {hasBreach && (
            <span className="text-[10px] font-bold text-danger bg-danger/10 px-1.5 py-0.5 rounded">SLA</span>
          )}
        </div>
        <p className="text-sm text-slate-700 dark:text-slate-200 truncate">{ticket.title}</p>
        {showTech && ticket.assignee_name && (
          <p className="text-xs text-slate-500 mt-0.5">{ticket.assignee_name}</p>
        )}
      </div>
      <StatusBadge status={ticket.status} />
    </button>
  );
}

function TicketListCard({
  title, count, tickets, emptyMsg, showTech,
}: {
  title: string; count: number; tickets: Ticket[]; emptyMsg: string; showTech?: boolean;
}) {
  return (
    <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-slate-100 dark:border-border/60 shrink-0">
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</p>
        <span className="text-xs font-medium text-slate-500 bg-slate-100 dark:bg-background-elevated px-2 py-0.5 rounded-full">{count}</span>
      </div>
      {tickets.length === 0 ? (
        <div className="flex flex-col items-center justify-center flex-1 py-10 gap-2">
          <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-background-elevated flex items-center justify-center">
            <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-sm text-slate-500">{emptyMsg}</p>
        </div>
      ) : (
        <div className="overflow-y-auto max-h-80 p-2 space-y-0.5">
          {tickets.map((t) => <TicketRow key={t.id} ticket={t} showTech={showTech} />)}
        </div>
      )}
    </div>
  );
}

// ── TechnicianDashboard ───────────────────────────────────────

interface TechGroup { name: string; tickets: Ticket[] }

export default function TechnicianDashboard() {
  const { user } = useAuth();
  const { theme } = useTheme();

  // Period state
  const [periodKey, setPeriodKey] = useState<PeriodKey>("mes");
  const [customDates, setCustomDates] = useState(getDefaultCustomDates);
  const [periodOpen, setPeriodOpen] = useState(false);
  const periodRef = useRef<HTMLDivElement>(null);

  const activePeriod = periodKey === "custom"
    ? customDays(customDates.start, customDates.end)
    : PERIOD_OPTIONS.find((p) => p.key === periodKey)!.days;

  const periodLabel = PERIOD_OPTIONS.find((p) => p.key === periodKey)?.label ?? "";

  // Data
  const [detail, setDetail]       = useState<TechnicianDetailReport | null>(null);
  const [openCount, setOpenCount] = useState(0);
  const [myTickets, setMyTickets] = useState<Ticket[]>([]);
  const [queue, setQueue]         = useState<Ticket[]>([]);
  const [teamGroups, setTeamGroups] = useState<TechGroup[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  const emptyDetail: TechnicianDetailReport = {
    period_days: activePeriod,
    technician_id: user?.id ?? "",
    technician_name: user?.name ?? "",
    total_assigned: 0, resolved: 0, in_progress: 0, open_count: 0,
    sla_breached: 0, sla_compliance_rate: 100,
    avg_resolution_hours: null, csat_average: null, csat_count: 0,
    tickets_by_day: [],
  };

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (periodRef.current && !periodRef.current.contains(e.target as Node)) setPeriodOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    Promise.all([
      getTechnicianDetailReport(activePeriod).catch(() => emptyDetail),
      getDashboardStats(),
      getTickets({ assignee_id: user.id, limit: 200 }),
      getTickets({ status: "open", limit: 200 }),
      Promise.all([
        getTickets({ status: "open", limit: 200 }),
        getTickets({ status: "in_progress", limit: 200 }),
        getTickets({ status: "awaiting_client", limit: 200 }),
        getTickets({ status: "awaiting_technical", limit: 200 }),
      ]).then((r) => r.flatMap((x) => x.items)),
    ])
      .then(([detailData, statsData, myData, queueData, activeTickets]) => {
        setDetail(detailData);
        setOpenCount(statsData.tickets.open);
        setMyTickets(myData.items);
        setQueue(queueData.items);

        const map = new Map<string, TechGroup>();
        for (const t of activeTickets) {
          if (!t.assignee_id || t.assignee_id === user.id) continue;
          if (!map.has(t.assignee_id)) map.set(t.assignee_id, { name: t.assignee_name ?? "Técnico", tickets: [] });
          map.get(t.assignee_id)!.tickets.push(t);
        }
        setTeamGroups([...map.values()].sort((a, b) => a.name.localeCompare(b.name)));
      })
      .catch(() => setError("Não foi possível carregar os tickets."))
      .finally(() => setLoading(false));
  }, [user, activePeriod]);

  const tooltipStyle = {
    backgroundColor: theme === "dark" ? "#132238" : "#ffffff",
    border: `1px solid ${theme === "dark" ? "#1E3A5F" : "#e2e8f0"}`,
    borderRadius: "8px",
    color: theme === "dark" ? "#f1f5f9" : "#0f172a",
    fontSize: "12px",
  };

  if (loading) return <div className="flex h-64 items-center justify-center"><Spinner size="lg" /></div>;
  if (error)   return <Alert variant="danger">{error}</Alert>;
  if (!detail) return <Alert variant="danger">Erro ao carregar dados.</Alert>;

  const myActiveCount = myTickets.filter((t) => t.status === "open" || t.status === "in_progress").length;
  const myBreachCount = myTickets.filter((t) => t.sla_response_breach || t.sla_resolve_breach).length;
  const axisColor     = theme === "dark" ? "#475569" : "#94a3b8";
  const teamAllTickets = teamGroups.flatMap((g) => g.tickets);

  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Olá, <span className="font-medium text-slate-700 dark:text-slate-300">{user?.name?.split(" ")[0]}</span>! Aqui está sua fila de hoje.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Period dropdown */}
          <div className="relative" ref={periodRef}>
            <button
              onClick={() => setPeriodOpen((o) => !o)}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-elevated text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-background-surface transition-colors"
            >
              <svg className="w-4 h-4 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span>{periodLabel}</span>
              <svg className={cn("w-3.5 h-3.5 shrink-0 text-slate-400 transition-transform", periodOpen && "rotate-180")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {periodOpen && (
              <div className="absolute right-0 top-full mt-1 z-50 w-48 rounded-xl border border-slate-200 dark:border-border bg-white dark:bg-background-surface shadow-xl overflow-hidden">
                {PERIOD_OPTIONS.map((p) => (
                  <button
                    key={p.key}
                    onClick={() => { setPeriodKey(p.key); setPeriodOpen(false); }}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-left transition-colors",
                      periodKey === p.key
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-background-elevated",
                    )}
                  >
                    {periodKey === p.key && (
                      <svg className="w-3.5 h-3.5 text-primary shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                    <span className={periodKey !== p.key ? "ml-6" : ""}>{p.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Custom date inputs — inline */}
          {periodKey === "custom" && (
            <div className="flex items-center gap-2 flex-wrap">
              <input
                type="date"
                value={customDates.start}
                max={customDates.end}
                onChange={(e) => setCustomDates((d) => ({ ...d, start: e.target.value }))}
                className="text-sm rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-elevated text-slate-700 dark:text-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <span className="text-xs text-slate-400">até</span>
              <input
                type="date"
                value={customDates.end}
                min={customDates.start}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setCustomDates((d) => ({ ...d, end: e.target.value }))}
                className="text-sm rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-elevated text-slate-700 dark:text-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          )}
        </div>
      </div>

      {/* ── KPI Row ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Meus tickets ativos"
          value={myActiveCount}
          sub="Abertos + em andamento"
          accent={myActiveCount > 0 ? "border-l-sky-500" : "border-l-slate-300 dark:border-l-slate-600"}
          iconBg={myActiveCount > 0 ? "bg-sky-500/10" : "bg-slate-100 dark:bg-background-elevated"}
          valueCls={myActiveCount > 0 ? "text-sky-600 dark:text-sky-400" : "text-slate-900 dark:text-slate-100"}
          icon={<svg className={cn("w-5 h-5", myActiveCount > 0 ? "text-sky-500" : "text-slate-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>}
        />
        <KpiCard
          label="Fila geral aberta"
          value={openCount}
          sub="Aguardando atendimento"
          accent="border-l-slate-300 dark:border-l-slate-600"
          iconBg="bg-slate-100 dark:bg-background-elevated"
          icon={<svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>}
        />
        <KpiCard
          label="SLA em risco"
          value={myBreachCount}
          sub="Nos meus tickets"
          accent={myBreachCount > 0 ? "border-l-red-500" : "border-l-slate-300 dark:border-l-slate-600"}
          iconBg={myBreachCount > 0 ? "bg-red-500/10" : "bg-slate-100 dark:bg-background-elevated"}
          valueCls={myBreachCount > 0 ? "text-red-600 dark:text-red-400" : "text-slate-900 dark:text-slate-100"}
          icon={<svg className={cn("w-5 h-5", myBreachCount > 0 ? "text-red-500" : "text-slate-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
        />
        <KpiCard
          label="Meu CSAT"
          value={detail.csat_average != null ? `${detail.csat_average.toFixed(1)} / 5` : "—"}
          sub={`${detail.csat_count} avaliações · ${periodLabel}`}
          accent="border-l-amber-400"
          iconBg="bg-amber-500/10"
          valueCls="text-amber-600 dark:text-amber-400"
          icon={<svg className="w-5 h-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>}
        />
      </div>

      {/* ── Charts + stats ───────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Area chart */}
        <div className="lg:col-span-2 rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-border/60">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              Meus atendimentos por dia — {periodLabel}
            </p>
          </div>
          <div className="p-5">
            {detail.tickets_by_day.length === 0 ? (
              <p className="text-slate-500 text-sm py-8 text-center">Sem dados para o período</p>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={detail.tickets_by_day} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="techGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#0ea5e9" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0}   />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: axisColor, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: axisColor, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => fmtDate(String(v))} formatter={(v: number) => [v, "Tickets"]} />
                  <Area type="monotone" dataKey="count" stroke="#0ea5e9" strokeWidth={2} fill="url(#techGradient)" dot={false} activeDot={{ r: 4, fill: "#0ea5e9" }} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Personal stats summary */}
        <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-border/60">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              Meu desempenho — {periodLabel}
            </p>
          </div>
          <div className="p-5 space-y-4">
            {[
              { label: "Atribuídos",        value: detail.total_assigned },
              { label: "Resolvidos",         value: detail.resolved },
              { label: "Em andamento",       value: detail.in_progress },
              { label: "SLA violados",       value: detail.sla_breached,                             danger: detail.sla_breached > 0 },
              { label: "Tempo médio",        value: formatHours(detail.avg_resolution_hours),        raw: true },
              { label: "Conformidade SLA",   value: `${detail.sla_compliance_rate.toFixed(0)}%`,     raw: true },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between">
                <span className="text-sm text-slate-500">{item.label}</span>
                <span className={cn(
                  "text-sm font-semibold tabular-nums",
                  item.danger ? "text-danger" : "text-slate-700 dark:text-slate-200",
                )}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Ticket lists ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TicketListCard
          title="Meus tickets"
          count={myTickets.length}
          tickets={myTickets}
          emptyMsg="Nenhum ticket atribuído"
        />
        <TicketListCard
          title="Tickets da equipe"
          count={teamAllTickets.length}
          tickets={teamAllTickets}
          emptyMsg="Nenhum ticket ativo na equipe"
          showTech
        />
        <TicketListCard
          title="Fila — Tickets abertos"
          count={queue.length}
          tickets={queue}
          emptyMsg="Fila limpa"
        />
      </div>
    </div>
  );
}
