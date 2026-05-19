import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  CardTitle,
  Pagination,
  PriorityBadge,
  Spinner,
  StatusBadge,
} from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { getTickets, type Ticket } from "../../services/ticketService";

const PAGE_SIZE = 10;

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
      className="w-full grid grid-cols-[1fr_auto_auto] sm:grid-cols-[7rem_1fr_auto_auto] items-center gap-3 px-4 py-3 text-left hover:bg-background-elevated transition-colors"
      onClick={() => navigate(`/tickets/${ticket.id}`)}
    >
      {/* Protocol — hidden on mobile, shown sm+ */}
      <span className="hidden sm:block text-xs font-mono text-slate-500 truncate">
        {ticket.protocol}
      </span>

      {/* Title + protocol (mobile only) */}
      <div className="min-w-0">
        <span className="sm:hidden text-xs font-mono text-slate-500 block mb-0.5">
          {ticket.protocol}
        </span>
        <p className="text-sm text-slate-200 truncate">{ticket.title}</p>
      </div>

      <PriorityBadge priority={ticket.priority} />
      <StatusBadge status={ticket.status} />
    </button>
  );
}

// ── Client Dashboard ──────────────────────────────────────────

export default function ClientDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [listLoading, setListLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initial load — also computes KPI totals
  const [kpiOpen, setKpiOpen]     = useState(0);
  const [kpiResolved, setKpiResolved] = useState(0);
  const [kpiTotal, setKpiTotal]   = useState(0);

  // Load KPIs once (all tickets, no pagination)
  useEffect(() => {
    if (!user) return;
    getTickets({ creator_id: user.id, limit: 500 })
      .then((data) => {
        setKpiTotal(data.total);
        setKpiOpen(data.items.filter((t) => t.status === "open" || t.status === "in_progress").length);
        setKpiResolved(data.items.filter((t) => t.status === "resolved" || t.status === "closed").length);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user]);

  // Load paginated list
  useEffect(() => {
    if (!user) return;
    setListLoading(true);
    getTickets({ creator_id: user.id, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
      .then((data) => {
        setTickets(data.items);
        setTotal(data.total);
      })
      .catch(() => setError("Não foi possível carregar seus tickets."))
      .finally(() => setListLoading(false));
  }, [user, page]);

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

  return (
    <div className="space-y-5 pb-10">

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-slate-100">Meus Tickets</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Olá, <span className="font-semibold text-slate-300">{user?.name?.split(" ")[0]}</span>! Acompanhe seus chamados abaixo.
          </p>
        </div>
        <div className="flex justify-center sm:justify-end">
          <button
            onClick={() => navigate("/tickets/new")}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-primary text-white hover:bg-primary/90 transition-all cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            Abrir chamado
          </button>
        </div>
      </div>

      {/* ── KPIs ────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Total de chamados" value={kpiTotal} sub="Todos os status" />
        <KpiCard
          label="Em andamento"
          value={kpiOpen}
          sub="Abertos + em progresso"
          color={kpiOpen > 0 ? "text-info" : "text-slate-100"}
        />
        <KpiCard
          label="Resolvidos"
          value={kpiResolved}
          sub="Resolvidos + fechados"
          color={kpiResolved > 0 ? "text-primary" : "text-slate-100"}
        />
      </div>

      {/* ── Ticket table ────────────────────────────────────── */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border">
          <CardTitle>Chamados recentes</CardTitle>
        </div>

        {listLoading ? (
          <div className="flex items-center justify-center py-10">
            <Spinner size="md" />
          </div>
        ) : tickets.length === 0 ? (
          <div className="px-4 py-12 text-center space-y-3">
            <p className="text-slate-500 text-sm">Você ainda não abriu nenhum chamado.</p>
            <Button variant="secondary" onClick={() => navigate("/tickets/new")}>
              Abrir primeiro chamado
            </Button>
          </div>
        ) : (
          <>
            {/* Table header */}
            <div className="hidden sm:grid grid-cols-[7rem_1fr_auto_auto] gap-3 px-4 py-2 border-b border-border/60 bg-background-elevated/40">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Protocolo</span>
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Título</span>
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Prioridade</span>
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</span>
            </div>

            {/* Rows */}
            <div className="divide-y divide-border/60">
              {tickets.map((t) => <TicketRow key={t.id} ticket={t} />)}
            </div>

            {/* Pagination */}
            <div className="px-4 pb-4">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={total}
                onPageChange={setPage}
                itemLabel="chamados"
              />
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
