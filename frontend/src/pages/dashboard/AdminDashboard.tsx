import { useEffect, useState } from "react";
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  Bar,
  BarChart,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Card,
  CardHeader,
  CardTitle,
  Spinner,
  Alert,
} from "../../components/ui";
import {
  getDashboardStats,
  type DashboardStats,
} from "../../services/dashboardService";

// ── KPI Card ──────────────────────────────────────────────────

interface KpiCardProps {
  label: string;
  value: number | string;
  sub?: string;
  color?: string;
}

function KpiCard({
  label,
  value,
  sub,
  color = "text-slate-100",
}: KpiCardProps) {
  return (
    <Card>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">
        {label}
      </p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </Card>
  );
}

// ── Chart colours ─────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  Abertos: "#3B82F6",
  "Em andamento": "#10B981",
  Aguardando: "#F59E0B",
  Resolvidos: "#6ee7b7",
  Fechados: "#475569",
  Cancelados: "#EF4444",
};

const PRIORITY_COLORS: Record<string, string> = {
  Crítico: "#EF4444",
  Alto: "#F59E0B",
  Médio: "#3B82F6",
  Baixo: "#475569",
};

// ── Admin Dashboard ───────────────────────────────────────────

export default function AdminDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboardStats()
      .then(setStats)
      .catch(() => setError("Não foi possível carregar as estatísticas."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !stats) {
    return <Alert variant="danger">{error ?? "Erro desconhecido."}</Alert>;
  }

  const { tickets, surveys, sla } = stats;

  const statusData = [
    { name: "Abertos", value: tickets.open },
    { name: "Em andamento", value: tickets.in_progress },
    { name: "Aguardando", value: tickets.awaiting },
    { name: "Resolvidos", value: tickets.resolved },
    { name: "Fechados", value: tickets.closed },
    { name: "Cancelados", value: tickets.cancelled },
  ].filter((d) => d.value > 0);

  const priorityData = [
    { name: "Crítico", value: tickets.by_priority_critical },
    { name: "Alto", value: tickets.by_priority_high },
    { name: "Médio", value: tickets.by_priority_medium },
    { name: "Baixo", value: tickets.by_priority_low },
  ];

  const avgRating = surveys.average_rating
    ? `${surveys.average_rating.toFixed(1)} / 5`
    : "—";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
        <p className="text-slate-400 text-sm mt-0.5">Visão geral do sistema</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Total de tickets"
          value={tickets.total}
          sub="Todos os status"
        />
        <KpiCard
          label="Abertos"
          value={tickets.open}
          color="text-info"
          sub="Aguardando atendimento"
        />
        <KpiCard
          label="SLA violado"
          value={sla.resolve_breached}
          color={sla.resolve_breached > 0 ? "text-danger" : "text-slate-100"}
          sub="Prazo de resolução"
        />
        <KpiCard
          label="Avaliação média"
          value={avgRating}
          color="text-primary"
          sub={`${surveys.total} avaliações`}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Status donut */}
        <Card>
          <CardHeader>
            <CardTitle>Tickets por Status</CardTitle>
          </CardHeader>
          {statusData.length === 0 ? (
            <p className="text-slate-500 text-sm py-8 text-center">
              Nenhum ticket encontrado
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {statusData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={STATUS_COLORS[entry.name] ?? "#475569"}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#1E293B",
                    border: "1px solid #334155",
                    borderRadius: "8px",
                    color: "#f1f5f9",
                  }}
                />
                <Legend
                  iconType="circle"
                  iconSize={8}
                  formatter={(value) => (
                    <span className="text-slate-400 text-xs">{value}</span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        {/* Priority bar */}
        <Card>
          <CardHeader>
            <CardTitle>Tickets por Prioridade</CardTitle>
          </CardHeader>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={priorityData}
              margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
            >
              <XAxis
                dataKey="name"
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1E293B",
                  border: "1px solid #334155",
                  borderRadius: "8px",
                  color: "#f1f5f9",
                }}
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]} name="Tickets">
                {priorityData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={PRIORITY_COLORS[entry.name] ?? "#475569"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* SLA detail */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <KpiCard
          label="SLA Resposta violado"
          value={sla.response_breached}
          color={sla.response_breached > 0 ? "text-warning" : "text-slate-100"}
          sub="Primeiro atendimento fora do prazo"
        />
        <KpiCard
          label="SLA Resolução violado"
          value={sla.resolve_breached}
          color={sla.resolve_breached > 0 ? "text-danger" : "text-slate-100"}
          sub="Resolução fora do prazo"
        />
      </div>
    </div>
  );
}
