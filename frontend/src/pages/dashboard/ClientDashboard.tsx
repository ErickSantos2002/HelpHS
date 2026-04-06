import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  CardHeader,
  CardTitle,
  PriorityBadge,
  Spinner,
  StatusBadge,
} from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { getTickets, type Ticket } from "../../services/ticketService";

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

function TicketRow({ ticket }: { ticket: Ticket }) {
  const navigate = useNavigate();

  return (
    <button
      className="w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-left hover:bg-background-elevated transition-colors"
      onClick={() => navigate(`/tickets/${ticket.id}`)}
    >
      <div className="flex-1 min-w-0">
        <span className="text-xs text-slate-500 font-mono block mb-0.5">
          {ticket.protocol}
        </span>
        <p className="text-sm text-slate-200 truncate">{ticket.title}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <PriorityBadge priority={ticket.priority} />
        <StatusBadge status={ticket.status} />
      </div>
    </button>
  );
}

// ── Client Dashboard ──────────────────────────────────────────

export default function ClientDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    getTickets({ creator_id: user.id, limit: 10 })
      .then((data) => {
        setTickets(data.items);
        setTotal(data.total);
      })
      .catch(() => setError("Não foi possível carregar seus tickets."))
      .finally(() => setLoading(false));
  }, [user]);

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return <Alert variant="danger">{error}</Alert>;
  }

  const openCount = tickets.filter(
    (t) => t.status === "open" || t.status === "in_progress",
  ).length;
  const resolvedCount = tickets.filter(
    (t) => t.status === "resolved" || t.status === "closed",
  ).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Meus Tickets</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Olá, {user?.name?.split(" ")[0]}! Acompanhe seus chamados abaixo.
          </p>
        </div>
        <Button onClick={() => navigate("/tickets/new")}>Abrir chamado</Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <KpiCard
          label="Total de chamados"
          value={total}
          sub="Todos os status"
        />
        <KpiCard
          label="Em andamento"
          value={openCount}
          sub="Abertos + em progresso"
          color={openCount > 0 ? "text-info" : "text-slate-100"}
        />
        <KpiCard
          label="Resolvidos"
          value={resolvedCount}
          sub="Resolvidos + fechados"
          color={resolvedCount > 0 ? "text-primary" : "text-slate-100"}
        />
      </div>

      {/* Ticket list */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border">
          <CardTitle>Chamados recentes</CardTitle>
        </div>
        {tickets.length === 0 ? (
          <div className="px-4 py-12 text-center space-y-3">
            <p className="text-slate-500 text-sm">
              Você ainda não abriu nenhum chamado.
            </p>
            <Button
              variant="secondary"
              onClick={() => navigate("/tickets/new")}
            >
              Abrir primeiro chamado
            </Button>
          </div>
        ) : (
          <div className="p-2 space-y-0.5">
            {tickets.map((t) => (
              <TicketRow key={t.id} ticket={t} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
