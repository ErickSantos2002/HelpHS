import { useEffect, useState } from "react";
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
import { Select } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import {
  exportReportsUrl,
  getReports,
  getTechnicianDetailReport,
  getTechnicianListReport,
  type ReportData,
  type TechnicianDetailReport,
  type TechnicianListReport,
  type TechnicianSummary,
} from "../../services/reportService";

// ── Constants ─────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { value: "7", label: "Últimos 7 dias" },
  { value: "14", label: "Últimos 14 dias" },
  { value: "30", label: "Últimos 30 dias" },
  { value: "90", label: "Últimos 90 dias" },
];

const PRIORITY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#22c55e",
};

const PRIORITY_LABELS: Record<string, string> = {
  critical: "Crítica",
  high: "Alta",
  medium: "Média",
  low: "Baixa",
};

const CATEGORY_LABELS: Record<string, string> = {
  hardware: "Hardware",
  software: "Software",
  network: "Rede",
  access: "Acesso",
  email: "E-mail",
  security: "Segurança",
  general: "Geral",
  other: "Outro",
};

const CSAT_COLORS = ["#ef4444", "#f97316", "#eab308", "#84cc16", "#22c55e"];

const tooltipStyle = {
  backgroundColor: "#1e2433",
  border: "1px solid #2d3748",
  borderRadius: "8px",
  fontSize: "12px",
  color: "#e2e8f0",
};

// ── Shared components ─────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="rounded-xl bg-background-surface border border-border p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${color ?? "text-slate-100"}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-background-surface border border-border p-5">
      <h2 className="text-sm font-medium text-slate-300 mb-4">{title}</h2>
      {children}
    </div>
  );
}

function LoadingState() {
  return (
    <p className="text-sm text-slate-500 text-center py-16">Carregando…</p>
  );
}

// ── Global report section (admin) ─────────────────────────────

function GlobalReport({ data, period }: { data: ReportData; period: number }) {
  const totalCsat = data.csat_distribution.reduce((s, d) => s + d.count, 0);

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Tickets no período"
          value={data.total_tickets}
          sub={`últimos ${data.period_days} dias`}
        />
        <StatCard
          label="Média CSAT"
          value={data.csat_average ? `${data.csat_average} / 5` : "—"}
          sub={`${totalCsat} avaliação${totalCsat !== 1 ? "ões" : ""}`}
        />
        <StatCard
          label="SLA crítico"
          value={`${data.sla_compliance.find((s) => s.priority === "critical")?.compliance_rate ?? 100}%`}
          sub="conformidade resolução"
        />
        <StatCard
          label="SLA alto"
          value={`${data.sla_compliance.find((s) => s.priority === "high")?.compliance_rate ?? 100}%`}
          sub="conformidade resolução"
        />
      </div>

      <ChartCard title="Tickets criados por dia">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart
            data={data.tickets_by_day}
            margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient id="ticketGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              tickFormatter={(v: string) => v.slice(5)}
              interval={Math.max(1, Math.floor(data.tickets_by_day.length / 6))}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(v) => `Data: ${v}`}
              formatter={(v) => [v ?? 0, "Tickets"]}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#6366f1"
              strokeWidth={2}
              fill="url(#ticketGradient)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ChartCard title="Tickets por categoria">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={data.tickets_by_category.filter((c) => c.count > 0)}
              layout="vertical"
              margin={{ top: 0, right: 8, left: 4, bottom: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#2d3748"
                horizontal={false}
              />
              <XAxis
                type="number"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                allowDecimals={false}
              />
              <YAxis
                dataKey="category"
                type="category"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v: string) => CATEGORY_LABELS[v] ?? v}
                width={60}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v) => [v ?? 0, "Tickets"]}
                labelFormatter={(v) => CATEGORY_LABELS[String(v)] ?? v}
              />
              <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Conformidade SLA por prioridade">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={data.sla_compliance}
              margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis
                dataKey="priority"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v: string) => PRIORITY_LABELS[v] ?? v}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v) => [`${v ?? 0}%`, "Conformidade"]}
                labelFormatter={(v) => PRIORITY_LABELS[String(v)] ?? v}
              />
              <Bar dataKey="compliance_rate" radius={[4, 4, 0, 0]}>
                {data.sla_compliance.map((entry) => (
                  <Cell
                    key={entry.priority}
                    fill={PRIORITY_COLORS[entry.priority] ?? "#6366f1"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Distribuição CSAT (1–5)">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={data.csat_distribution}
              margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis
                dataKey="rating"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                tickFormatter={(v: number) => `★ ${v}`}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v) => [v ?? 0, "Avaliações"]}
                labelFormatter={(v) => {
                  const n = Number(v ?? 0);
                  return `${n} estrela${n !== 1 ? "s" : ""}`;
                }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {data.csat_distribution.map((entry) => (
                  <Cell
                    key={entry.rating}
                    fill={CSAT_COLORS[entry.rating - 1]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Export */}
      <div className="flex justify-end gap-2">
        <a
          href={exportReportsUrl("csv", period)}
          download
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm text-slate-300 hover:bg-background-elevated transition-colors"
        >
          Exportar CSV
        </a>
        <a
          href={exportReportsUrl("pdf", period)}
          download
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm text-slate-300 hover:bg-background-elevated transition-colors"
        >
          Exportar PDF
        </a>
      </div>
    </>
  );
}

// ── Technician detail section ─────────────────────────────────

function TechnicianDetail({ data }: { data: TechnicianDetailReport }) {
  const slaColor =
    data.sla_compliance_rate >= 90
      ? "text-green-400"
      : data.sla_compliance_rate >= 70
        ? "text-yellow-400"
        : "text-red-400";

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Atribuídos no período"
          value={data.total_assigned}
          sub={`últimos ${data.period_days} dias`}
        />
        <StatCard
          label="Resolvidos / Fechados"
          value={data.resolved}
          sub={
            data.total_assigned > 0
              ? `${Math.round((data.resolved / data.total_assigned) * 100)}% do total`
              : "—"
          }
          color="text-green-400"
        />
        <StatCard
          label="Conformidade SLA"
          value={`${data.sla_compliance_rate}%`}
          sub={`${data.sla_breached} violação${data.sla_breached !== 1 ? "ões" : ""}`}
          color={slaColor}
        />
        <StatCard
          label="CSAT médio"
          value={data.csat_average ? `${data.csat_average} / 5` : "—"}
          sub={
            data.csat_count > 0
              ? `${data.csat_count} avaliação${data.csat_count !== 1 ? "ões" : ""}`
              : "sem avaliações"
          }
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Em andamento" value={data.in_progress} />
        <StatCard label="Em aberto" value={data.open_count} />
        <StatCard
          label="Tempo médio resolução"
          value={
            data.avg_resolution_hours != null
              ? data.avg_resolution_hours >= 24
                ? `${(data.avg_resolution_hours / 24).toFixed(1)}d`
                : `${data.avg_resolution_hours.toFixed(1)}h`
              : "—"
          }
          sub="tickets fechados"
        />
        <StatCard
          label="Taxa de resolução"
          value={
            data.total_assigned > 0
              ? `${Math.round((data.resolved / data.total_assigned) * 100)}%`
              : "—"
          }
        />
      </div>

      <ChartCard title="Tickets atribuídos por dia">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart
            data={data.tickets_by_day}
            margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
          >
            <defs>
              <linearGradient id="techGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              tickFormatter={(v: string) => v.slice(5)}
              interval={Math.max(1, Math.floor(data.tickets_by_day.length / 6))}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(v) => `Data: ${v}`}
              formatter={(v) => [v ?? 0, "Tickets"]}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#22c55e"
              strokeWidth={2}
              fill="url(#techGradient)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>
    </>
  );
}

// ── Technician ranking table (admin only) ─────────────────────

function TechnicianRanking({
  data,
  onSelect,
}: {
  data: TechnicianListReport;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="rounded-xl bg-background-surface border border-border overflow-hidden">
      <div className="px-5 py-3 border-b border-border">
        <h2 className="text-sm font-medium text-slate-300">
          Desempenho por técnico
        </h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              {[
                "Técnico",
                "Atribuídos",
                "Resolvidos",
                "Em aberto",
                "SLA",
                "Tempo médio",
                "CSAT",
                "",
              ].map((h) => (
                <th
                  key={h}
                  className="px-4 py-2.5 text-left text-xs text-slate-500 font-medium"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.technicians.map((t) => {
              const slaColor =
                t.sla_compliance_rate >= 90
                  ? "text-green-400"
                  : t.sla_compliance_rate >= 70
                    ? "text-yellow-400"
                    : "text-red-400";
              return (
                <tr
                  key={t.technician_id}
                  className="hover:bg-background-elevated/50 transition-colors"
                >
                  <td className="px-4 py-3 font-medium text-slate-200">
                    {t.technician_name}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {t.total_assigned}
                  </td>
                  <td className="px-4 py-3 text-green-400">{t.resolved}</td>
                  <td className="px-4 py-3 text-slate-400">{t.open_count}</td>
                  <td className={`px-4 py-3 font-medium ${slaColor}`}>
                    {t.sla_compliance_rate}%
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {t.avg_resolution_hours != null
                      ? t.avg_resolution_hours >= 24
                        ? `${(t.avg_resolution_hours / 24).toFixed(1)}d`
                        : `${t.avg_resolution_hours.toFixed(1)}h`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {t.csat_average != null ? `${t.csat_average} ★` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => onSelect(t.technician_id)}
                      className="text-xs text-primary hover:text-primary/80 transition-colors"
                    >
                      Detalhes
                    </button>
                  </td>
                </tr>
              );
            })}
            {data.technicians.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  className="px-4 py-8 text-center text-slate-500 text-sm"
                >
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

// ── Main page ─────────────────────────────────────────────────

type Tab = "global" | "technicians";

export default function ReportsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isTechnician = user?.role === "technician";

  const [period, setPeriod] = useState("30");
  const [tab, setTab] = useState<Tab>(isAdmin ? "global" : "technicians");

  // Global report state (admin only)
  const [globalData, setGlobalData] = useState<ReportData | null>(null);
  const [globalLoading, setGlobalLoading] = useState(false);

  // Technician list state (admin only)
  const [techList, setTechList] = useState<TechnicianListReport | null>(null);
  const [techListLoading, setTechListLoading] = useState(false);

  // Selected technician detail
  const [selectedTechId, setSelectedTechId] = useState<string | undefined>(
    isTechnician ? user?.id : undefined,
  );
  const [techDetail, setTechDetail] = useState<TechnicianDetailReport | null>(
    null,
  );
  const [techDetailLoading, setTechDetailLoading] = useState(false);

  const p = Number(period);

  // Load global report when on global tab (admin)
  useEffect(() => {
    if (tab !== "global" || !isAdmin) return;
    setGlobalLoading(true);
    getReports(p)
      .then(setGlobalData)
      .catch(() => {})
      .finally(() => setGlobalLoading(false));
  }, [tab, p, isAdmin]);

  // Load technician list when on technicians tab (admin)
  useEffect(() => {
    if (tab !== "technicians" || !isAdmin) return;
    setTechListLoading(true);
    getTechnicianListReport(p)
      .then(setTechList)
      .catch(() => {})
      .finally(() => setTechListLoading(false));
  }, [tab, p, isAdmin]);

  // Load technician detail — for technician role: always own; for admin: when selected
  useEffect(() => {
    if (isTechnician) {
      setTechDetailLoading(true);
      getTechnicianDetailReport(p)
        .then(setTechDetail)
        .catch(() => {})
        .finally(() => setTechDetailLoading(false));
      return;
    }
    if (!selectedTechId) return;
    setTechDetailLoading(true);
    getTechnicianDetailReport(p, selectedTechId)
      .then(setTechDetail)
      .catch(() => {})
      .finally(() => setTechDetailLoading(false));
  }, [p, selectedTechId, isTechnician]);

  function handleSelectTechnician(id: string) {
    setSelectedTechId(id);
    setTechDetail(null);
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Relatórios</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isTechnician
              ? "Suas métricas de desempenho"
              : "Visão geral e desempenho da equipe"}
          </p>
        </div>
        <Select
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          options={PERIOD_OPTIONS}
          className="w-44"
        />
      </div>

      {/* Tabs — admin only */}
      {isAdmin && (
        <div className="flex rounded-lg border border-border overflow-hidden w-fit text-sm">
          <button
            onClick={() => setTab("global")}
            className={`px-4 py-2 transition-colors ${
              tab === "global"
                ? "bg-background-elevated text-slate-200"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            Visão geral
          </button>
          <button
            onClick={() => setTab("technicians")}
            className={`px-4 py-2 border-l border-border transition-colors ${
              tab === "technicians"
                ? "bg-background-elevated text-slate-200"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            Por técnico
          </button>
        </div>
      )}

      {/* ── Global tab (admin) ── */}
      {isAdmin && tab === "global" && (
        <>
          {globalLoading && <LoadingState />}
          {!globalLoading && globalData && (
            <GlobalReport data={globalData} period={p} />
          )}
        </>
      )}

      {/* ── Technicians tab (admin) ── */}
      {isAdmin && tab === "technicians" && (
        <div className="space-y-6">
          {techListLoading && <LoadingState />}
          {!techListLoading && techList && (
            <TechnicianRanking
              data={techList}
              onSelect={handleSelectTechnician}
            />
          )}

          {/* Detail panel — appears when admin clicks "Detalhes" */}
          {selectedTechId && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-slate-300">
                  {techDetail
                    ? `Detalhes — ${techDetail.technician_name}`
                    : "Carregando detalhes…"}
                </h2>
                <button
                  onClick={() => {
                    setSelectedTechId(undefined);
                    setTechDetail(null);
                  }}
                  className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
                >
                  Fechar
                </button>
              </div>
              {techDetailLoading && <LoadingState />}
              {!techDetailLoading && techDetail && (
                <TechnicianDetail data={techDetail} />
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Technician view (own metrics) ── */}
      {isTechnician && (
        <>
          {techDetailLoading && <LoadingState />}
          {!techDetailLoading && techDetail && (
            <TechnicianDetail data={techDetail} />
          )}
        </>
      )}
    </div>
  );
}
