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
import {
  exportReportsUrl,
  getReports,
  type ReportData,
} from "../../services/reportService";

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

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="rounded-xl bg-background-surface border border-border p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-semibold text-slate-100">{value}</p>
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

const tooltipStyle = {
  backgroundColor: "#1e2433",
  border: "1px solid #2d3748",
  borderRadius: "8px",
  fontSize: "12px",
  color: "#e2e8f0",
};

export default function ReportsPage() {
  const [period, setPeriod] = useState("30");
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getReports(Number(period))
      .then(setData)
      .finally(() => setLoading(false));
  }, [period]);

  const totalCsat =
    data?.csat_distribution.reduce((s, d) => s + d.count, 0) ?? 0;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Relatórios</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Visão geral de desempenho e SLA
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            options={PERIOD_OPTIONS}
            className="w-44"
          />
          <a
            href={exportReportsUrl("csv", Number(period))}
            download
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm text-slate-300 hover:bg-background-elevated transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            CSV
          </a>
          <a
            href={exportReportsUrl("pdf", Number(period))}
            download
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm text-slate-300 hover:bg-background-elevated transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            PDF
          </a>
        </div>
      </div>

      {loading && (
        <p className="text-sm text-slate-500 text-center py-16">Carregando…</p>
      )}

      {!loading && data && (
        <>
          {/* Summary cards */}
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
              sub="conformidade de resolução"
            />
            <StatCard
              label="SLA alto"
              value={`${data.sla_compliance.find((s) => s.priority === "high")?.compliance_rate ?? 100}%`}
              sub="conformidade de resolução"
            />
          </div>

          {/* Tickets por dia */}
          <ChartCard title="Tickets criados por dia">
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart
                data={data.tickets_by_day}
                margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
              >
                <defs>
                  <linearGradient
                    id="ticketGradient"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: "#94a3b8" }}
                  tickFormatter={(v: string) => v.slice(5)}
                  interval={Math.floor(data.tickets_by_day.length / 6)}
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

          {/* Bottom row: category + SLA + CSAT */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Tickets por categoria */}
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

            {/* Conformidade SLA */}
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

            {/* CSAT distribuição */}
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
        </>
      )}
    </div>
  );
}
