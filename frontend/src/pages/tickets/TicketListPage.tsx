import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Spinner } from "../../components/ui";
import { cn } from "../../lib/utils";
import { getTickets, type Ticket } from "../../services/ticketService";

// ── Priority ──────────────────────────────────────────────────

const PRIORITY_ORDER: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3,
};

const PRIORITY_CFG: Record<string, {
  label: string; borderCls: string; dotColor: string; badgeCls: string;
}> = {
  critical: {
    label: "Crítico",
    borderCls: "border-l-red-500",
    dotColor: "#ef4444",
    badgeCls: "bg-red-500/10 text-red-600 dark:text-red-400",
  },
  high: {
    label: "Alto",
    borderCls: "border-l-amber-500",
    dotColor: "#f59e0b",
    badgeCls: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  medium: {
    label: "Médio",
    borderCls: "border-l-indigo-400",
    dotColor: "#818cf8",
    badgeCls: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  },
  low: {
    label: "Baixo",
    borderCls: "border-l-slate-300 dark:border-l-slate-600",
    dotColor: "#94a3b8",
    badgeCls: "bg-slate-100 dark:bg-background-elevated text-slate-500",
  },
};

// ── Columns ───────────────────────────────────────────────────

const COLUMNS: {
  status: string; label: string; desc: string;
  color: string; bg: string; text: string; headerBg: string;
}[] = [
  { status: "open",               label: "Aberto",       desc: "Aguardando atendimento",     color: "#0ea5e9", bg: "bg-sky-500/10",     text: "text-sky-600 dark:text-sky-400",       headerBg: "bg-sky-500/5 dark:bg-sky-500/10"      },
  { status: "in_progress",        label: "Em Andamento", desc: "Técnico vinculado",           color: "#6366f1", bg: "bg-indigo-500/10",  text: "text-indigo-600 dark:text-indigo-400", headerBg: "bg-indigo-500/5 dark:bg-indigo-500/10"  },
  { status: "awaiting_technical", label: "Ag. Técnico",  desc: "Aguardando resp. técnica",    color: "#f59e0b", bg: "bg-amber-500/10",   text: "text-amber-600 dark:text-amber-400",   headerBg: "bg-amber-500/5 dark:bg-amber-500/10"    },
  { status: "awaiting_client",    label: "Ag. Cliente",  desc: "Aguardando resp. cliente",    color: "#8b5cf6", bg: "bg-violet-500/10",  text: "text-violet-600 dark:text-violet-400", headerBg: "bg-violet-500/5 dark:bg-violet-500/10"  },
  { status: "resolved",           label: "Resolvido",    desc: "Finalizado com sucesso",      color: "#10b981", bg: "bg-emerald-500/10", text: "text-emerald-600 dark:text-emerald-400",headerBg: "bg-emerald-500/5 dark:bg-emerald-500/10"},
  { status: "closed",             label: "Fechado",      desc: "Encerrado",                   color: "#64748b", bg: "bg-slate-500/10",   text: "text-slate-500 dark:text-slate-400",   headerBg: "bg-slate-500/5 dark:bg-slate-500/10"    },
];

// ── TicketCard ────────────────────────────────────────────────

function TicketCard({ ticket }: { ticket: Ticket }) {
  const navigate = useNavigate();
  const pCfg    = PRIORITY_CFG[ticket.priority] ?? PRIORITY_CFG.low;
  const hasBreach = ticket.sla_response_breach || ticket.sla_resolve_breach;
  const initials  = ticket.assignee_name
    ? ticket.assignee_name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()
    : null;

  return (
    <button
      onClick={() => navigate(`/tickets/${ticket.id}`)}
      className={cn(
        "w-full text-left rounded-lg",
        "bg-white dark:bg-background-surface",
        "border border-slate-200 dark:border-border border-l-4",
        "p-3 shadow-sm hover:shadow-md hover:-translate-y-0.5 active:translate-y-0",
        "transition-all duration-150 cursor-pointer group",
        pCfg.borderCls,
      )}
    >
      {/* Protocol + indicators */}
      <div className="flex items-center justify-between mb-2 gap-1">
        <span className="text-[11px] font-mono text-slate-400 truncate">{ticket.protocol}</span>
        <div className="flex items-center gap-1 shrink-0">
          {hasBreach && (
            <span className="text-[10px] font-bold text-red-600 dark:text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded">
              SLA
            </span>
          )}
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: pCfg.dotColor }}
            title={pCfg.label}
          />
        </div>
      </div>

      {/* Title */}
      <p className="text-sm font-medium text-slate-800 dark:text-slate-100 line-clamp-2 mb-3 leading-snug group-hover:text-primary transition-colors duration-150">
        {ticket.title}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden">
          <span className="text-[11px] text-slate-500 bg-slate-100 dark:bg-background-elevated px-2 py-0.5 rounded truncate max-w-[100px]">
            {ticket.category}
          </span>
          <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0", pCfg.badgeCls)}>
            {pCfg.label}
          </span>
        </div>
        {initials ? (
          <div
            className="w-6 h-6 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0"
            title={ticket.assignee_name ?? ""}
          >
            <span className="text-[9px] font-bold text-primary leading-none">{initials}</span>
          </div>
        ) : (
          <div className="w-6 h-6 rounded-full bg-slate-100 dark:bg-background-elevated border border-slate-200 dark:border-border flex items-center justify-center shrink-0">
            <svg className="w-3 h-3 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
        )}
      </div>
    </button>
  );
}

// ── KanbanColumn ──────────────────────────────────────────────

function KanbanColumn({ col, tickets }: { col: typeof COLUMNS[0]; tickets: Ticket[] }) {
  return (
    <div className="flex flex-col w-[268px] min-w-[268px] rounded-xl bg-slate-100 dark:bg-background-elevated border border-slate-200 dark:border-border overflow-hidden">
      {/* Header */}
      <div className={cn("px-3 py-3 shrink-0", col.headerBg)}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: col.color }} />
            <p className={cn("text-sm font-semibold truncate", col.text)}>{col.label}</p>
          </div>
          <span className={cn("text-xs font-bold px-2 py-0.5 rounded-full shrink-0 ml-2", col.bg, col.text)}>
            {tickets.length}
          </span>
        </div>
        <p className="text-[11px] text-slate-400 mt-0.5 pl-4">{col.desc}</p>
      </div>

      {/* Thin color bar */}
      <div className="h-0.5 shrink-0" style={{ backgroundColor: col.color, opacity: 0.4 }} />

      {/* Cards — scrolls independently */}
      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-2">
        {tickets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 mx-1 rounded-lg border-2 border-dashed border-slate-200 dark:border-border/40 mt-1">
            <svg className="w-6 h-6 text-slate-300 dark:text-slate-600 mb-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.25}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-xs text-slate-400">Nenhum ticket</p>
          </div>
        ) : (
          tickets.map((t) => <TicketCard key={t.id} ticket={t} />)
        )}
      </div>
    </div>
  );
}

// ── TicketListPage ────────────────────────────────────────────

export default function TicketListPage() {
  const navigate = useNavigate();

  const [tickets, setTickets]               = useState<Ticket[]>([]);
  const [loading, setLoading]               = useState(true);
  const [error, setError]                   = useState<string | null>(null);
  const [search, setSearch]                 = useState("");
  const [filterPriority, setFilterPriority] = useState("");
  const [filterAssignee, setFilterAssignee] = useState<"all" | "unassigned" | "assigned">("all");

  useEffect(() => {
    setLoading(true);
    getTickets({ limit: 500 })
      .then((r) => setTickets(r.items))
      .catch(() => setError("Não foi possível carregar os tickets."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    let items = tickets;
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter((t) =>
        t.title.toLowerCase().includes(q) || t.protocol.toLowerCase().includes(q),
      );
    }
    if (filterPriority) items = items.filter((t) => t.priority === filterPriority);
    if (filterAssignee === "unassigned") items = items.filter((t) => !t.assignee_id);
    if (filterAssignee === "assigned")   items = items.filter((t) => !!t.assignee_id);
    return items;
  }, [tickets, search, filterPriority, filterAssignee]);

  const grouped = useMemo(() => {
    const map = new Map<string, Ticket[]>();
    COLUMNS.forEach((c) => map.set(c.status, []));
    for (const t of filtered) {
      if (map.has(t.status)) map.get(t.status)!.push(t);
    }
    for (const arr of map.values()) {
      arr.sort((a, b) => (PRIORITY_ORDER[a.priority] ?? 3) - (PRIORITY_ORDER[b.priority] ?? 3));
    }
    return map;
  }, [filtered]);

  const totalShown = filtered.filter((t) => COLUMNS.some((c) => c.status === t.status)).length;
  const hasFilters = !!(search || filterPriority || filterAssignee !== "all");

  if (loading) return <div className="flex h-64 items-center justify-center"><Spinner size="lg" /></div>;
  if (error)   return <Alert variant="danger">{error}</Alert>;

  return (
    // h-full fills the <main> container; flex-col stacks header + board
    <div className="h-full flex flex-col gap-4 min-h-0">

      {/* ── Top bar ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Tickets</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {totalShown} ticket{totalShown !== 1 ? "s" : ""} encontrado{totalShown !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Filters + new */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Buscar…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-3 py-2 text-sm w-52 rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-elevated text-slate-700 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary"
            />
            {search && (
              <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            )}
          </div>

          {/* Priority */}
          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="text-sm rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-elevated text-slate-700 dark:text-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
          >
            <option value="">Todas prioridades</option>
            <option value="critical">Crítico</option>
            <option value="high">Alto</option>
            <option value="medium">Médio</option>
            <option value="low">Baixo</option>
          </select>

          {/* Assignee */}
          <select
            value={filterAssignee}
            onChange={(e) => setFilterAssignee(e.target.value as typeof filterAssignee)}
            className="text-sm rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-elevated text-slate-700 dark:text-slate-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer"
          >
            <option value="all">Todos</option>
            <option value="unassigned">Sem técnico</option>
            <option value="assigned">Com técnico</option>
          </select>

          {/* Clear filters */}
          {hasFilters && (
            <button
              onClick={() => { setSearch(""); setFilterPriority(""); setFilterAssignee("all"); }}
              className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-danger transition-colors cursor-pointer px-2 py-2 rounded-lg border border-slate-200 dark:border-border hover:border-danger/30"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
              Limpar
            </button>
          )}

          {/* New ticket */}
          <button
            onClick={() => navigate("/tickets/new")}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-primary text-white hover:bg-primary/90 active:scale-95 transition-all duration-150 cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>
            Novo Ticket
          </button>
        </div>
      </div>

      {/* ── Kanban Board ─────────────────────────────────────── */}
      {/* flex-1 min-h-0 = preenche o restante sem overflow vertical */}
      <div className="flex-1 min-h-0 rounded-2xl bg-slate-200/60 dark:bg-slate-900/50 border border-slate-200 dark:border-border overflow-hidden">
        {/* overflow-x-auto = scroll horizontal quando colunas não cabem */}
        <div className="h-full overflow-x-auto">
          <div className="flex gap-3 h-full p-3 min-w-max">
            {COLUMNS.map((col) => (
              <KanbanColumn
                key={col.status}
                col={col}
                tickets={grouped.get(col.status) ?? []}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
