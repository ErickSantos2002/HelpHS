import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Card,
  CardTitle,
  PriorityBadge,
  Spinner,
  StatusBadge,
} from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import {
  getDashboardStats,
  type DashboardStats,
} from "../../services/dashboardService";
import { getTickets, type Ticket } from "../../services/ticketService";

const ACTIVE_STATUSES = new Set([
  "open",
  "in_progress",
  "awaiting_client",
  "awaiting_technical",
]);

interface TechGroup {
  name: string;
  tickets: Ticket[];
}

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

// ── Ticket Row ────────────────────────────────────────────────

function TicketRow({
  ticket,
  showTech,
}: {
  ticket: Ticket;
  showTech?: boolean;
}) {
  const navigate = useNavigate();
  const hasBreach = ticket.sla_response_breach || ticket.sla_resolve_breach;

  return (
    <button
      className="w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-background-elevated transition-colors"
      onClick={() => navigate(`/tickets/${ticket.id}`)}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="text-xs text-slate-500 font-mono shrink-0">
            {ticket.protocol}
          </span>
          {hasBreach && (
            <span className="text-xs text-danger font-medium shrink-0">
              ⚠ SLA
            </span>
          )}
          {showTech && ticket.assignee_name && (
            <span className="text-xs text-slate-400 shrink-0">
              · {ticket.assignee_name}
            </span>
          )}
        </div>
        <p className="text-sm text-slate-200 truncate">{ticket.title}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <PriorityBadge priority={ticket.priority} />
        <StatusBadge status={ticket.status} />
      </div>
    </button>
  );
}

// ── Technician Dashboard ──────────────────────────────────────

export default function TechnicianDashboard() {
  const { user } = useAuth();

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [myTickets, setMyTickets] = useState<Ticket[]>([]);
  const [queue, setQueue] = useState<Ticket[]>([]);
  const [teamGroups, setTeamGroups] = useState<TechGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    Promise.all([
      getDashboardStats(),
      getTickets({ assignee_id: user.id, limit: 6 }),
      getTickets({ status: "open", limit: 6 }),
      getTickets({ limit: 100 }),
    ])
      .then(([statsData, myData, queueData, allData]) => {
        setStats(statsData);
        setMyTickets(myData.items);
        setQueue(queueData.items);

        // Group active tickets from other technicians
        const map = new Map<string, TechGroup>();
        for (const t of allData.items) {
          if (!t.assignee_id || t.assignee_id === user.id) continue;
          if (!ACTIVE_STATUSES.has(t.status)) continue;
          const key = t.assignee_id;
          if (!map.has(key)) {
            map.set(key, { name: t.assignee_name ?? "Técnico", tickets: [] });
          }
          map.get(key)!.tickets.push(t);
        }
        setTeamGroups(
          [...map.values()].sort((a, b) => a.name.localeCompare(b.name)),
        );
      })
      .catch(() => setError("Não foi possível carregar os dados."))
      .finally(() => setLoading(false));
  }, [user]);

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

  const { tickets } = stats;
  const myActiveCount = myTickets.filter(
    (t) => t.status === "open" || t.status === "in_progress",
  ).length;
  const myBreachCount = myTickets.filter(
    (t) => t.sla_response_breach || t.sla_resolve_breach,
  ).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Dashboard</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          Olá, {user?.name?.split(" ")[0]}! Aqui está sua fila de hoje.
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Meus tickets ativos"
          value={myActiveCount}
          sub="Abertos + em andamento"
          color={myActiveCount > 0 ? "text-info" : "text-slate-100"}
        />
        <KpiCard
          label="Fila geral aberta"
          value={tickets.open}
          sub="Aguardando atendimento"
        />
        <KpiCard
          label="SLA em risco"
          value={myBreachCount}
          sub="Nos meus tickets"
          color={myBreachCount > 0 ? "text-danger" : "text-slate-100"}
        />
        <KpiCard
          label="Total no sistema"
          value={tickets.total}
          sub="Todos os status"
        />
      </div>

      {/* Tickets lists */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* My assigned tickets */}
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <CardTitle>Meus tickets</CardTitle>
            <span className="text-xs text-slate-500">{myTickets.length}</span>
          </div>
          {myTickets.length === 0 ? (
            <p className="text-slate-500 text-sm px-4 py-8 text-center">
              Nenhum ticket atribuído a você
            </p>
          ) : (
            <div className="p-2 space-y-0.5">
              {myTickets.map((t) => (
                <TicketRow key={t.id} ticket={t} />
              ))}
            </div>
          )}
        </Card>

        {/* Team tickets */}
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <CardTitle>Tickets da equipe</CardTitle>
            <span className="text-xs text-slate-500">
              {teamGroups.reduce((acc, g) => acc + g.tickets.length, 0)}
            </span>
          </div>
          {teamGroups.length === 0 ? (
            <p className="text-slate-500 text-sm px-4 py-8 text-center">
              Nenhum ticket ativo na equipe
            </p>
          ) : (
            <div className="p-2 space-y-0.5">
              {teamGroups
                .flatMap((g) => g.tickets)
                .slice(0, 8)
                .map((t) => (
                  <TicketRow key={t.id} ticket={t} showTech />
                ))}
            </div>
          )}
        </Card>

        {/* Open queue */}
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <CardTitle>Fila — Tickets abertos</CardTitle>
            <span className="text-xs text-slate-500">{queue.length}</span>
          </div>
          {queue.length === 0 ? (
            <p className="text-slate-500 text-sm px-4 py-8 text-center">
              Nenhum ticket aberto na fila
            </p>
          ) : (
            <div className="p-2 space-y-0.5">
              {queue.map((t) => (
                <TicketRow key={t.id} ticket={t} />
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
