import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Modal,
  ModalFooter,
  Pagination,
  PriorityBadge,
  Select,
  Spinner,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeaderCell,
  TableRow,
  TicketFilters,
  type TicketFilterState,
  EMPTY_FILTERS,
} from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import {
  assignTicket,
  getTickets,
  updateTicketStatus,
  type SortBy,
  type SortDir,
  type Ticket,
} from "../../services/ticketService";
import { getTechnicians, type UserSummary } from "../../services/userService";
import { TICKET_TRANSITIONS } from "../../lib/ticketConstants";

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<string, string> = {
  open: "Aberto",
  in_progress: "Em andamento",
  awaiting_client: "Ag. cliente",
  awaiting_technical: "Ag. técnico",
  resolved: "Resolvido",
  closed: "Fechado",
  cancelled: "Cancelado",
};

// ── SLA cell ──────────────────────────────────────────────────

function SlaCell({ ticket }: { ticket: Ticket }) {
  if (ticket.sla_resolve_breach) {
    return <span className="text-xs font-medium text-danger">Vencido</span>;
  }
  if (!ticket.sla_resolve_due_at) {
    return <span className="text-xs text-slate-600">—</span>;
  }
  const diff = new Date(ticket.sla_resolve_due_at).getTime() - Date.now();
  if (diff <= 0) {
    return <span className="text-xs font-medium text-danger">Vencido</span>;
  }
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const display = h > 0 ? `${h}h ${m}m` : `${m}m`;
  const color = h < 4 ? "text-warning-400" : "text-slate-400";
  return <span className={`text-xs ${color}`}>{display}</span>;
}

// ── TicketListPage ────────────────────────────────────────────

export default function TicketListPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isStaff = user?.role === "admin" || user?.role === "technician";

  // Data
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters + pagination + sort — T84: technician defaults to their own queue
  const [filters, setFilters] = useState<TicketFilterState>(() =>
    user?.role === "technician" && user.id
      ? { ...EMPTY_FILTERS, assignee_id: user.id }
      : EMPTY_FILTERS,
  );
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<SortBy>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Bulk selection
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Bulk action modals
  const [bulkStatusModal, setBulkStatusModal] = useState(false);
  const [bulkAssignModal, setBulkAssignModal] = useState(false);
  const [bulkStatus, setBulkStatus] = useState("");
  const [bulkAssignee, setBulkAssignee] = useState("");
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [technicians, setTechnicians] = useState<UserSummary[]>([]);

  // Load technicians for filter dropdown (staff) and bulk assign (admin)
  useEffect(() => {
    if (isStaff) {
      getTechnicians()
        .then(setTechnicians)
        .catch(() => {});
    }
  }, [isStaff]);

  // Fetch tickets whenever deps change
  useEffect(() => {
    setLoading(true);
    setError(null);
    setSelected(new Set());

    getTickets({
      status: filters.status || undefined,
      priority: filters.priority || undefined,
      category: filters.category || undefined,
      assignee_id: filters.assignee_id || undefined,
      search: filters.search || undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      sort_by: sortBy,
      sort_dir: sortDir,
    })
      .then((res) => {
        setTickets(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Não foi possível carregar os tickets."))
      .finally(() => setLoading(false));
  }, [filters, page, sortBy, sortDir]);

  // Reset to page 1 when filters change
  function handleFiltersChange(f: TicketFilterState) {
    setFilters(f);
    setPage(1);
  }

  // Sort toggle
  function handleSort(col: SortBy) {
    if (sortBy === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      setSortDir("desc");
    }
    setPage(1);
  }

  function sortedState(col: SortBy): "asc" | "desc" | null {
    return sortBy === col ? sortDir : null;
  }

  // Row selection
  function toggleAll() {
    if (selected.size === tickets.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(tickets.map((t) => t.id)));
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // Bulk status change
  async function handleBulkStatus() {
    if (!bulkStatus) return;
    setBulkLoading(true);
    setBulkError(null);
    try {
      await Promise.all(
        [...selected].map((id) => updateTicketStatus(id, bulkStatus)),
      );
      setBulkStatusModal(false);
      setBulkStatus("");
      setSelected(new Set());
      // Refresh
      const res = await getTickets({
        status: filters.status || undefined,
        priority: filters.priority || undefined,
        category: filters.category || undefined,
        assignee_id: filters.assignee_id || undefined,
        search: filters.search || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      setTickets(res.items);
      setTotal(res.total);
    } catch {
      setBulkError("Falha ao alterar status de alguns tickets.");
    } finally {
      setBulkLoading(false);
    }
  }

  // Bulk assign
  async function handleBulkAssign() {
    if (!bulkAssignee) return;
    setBulkLoading(true);
    setBulkError(null);
    try {
      await Promise.all(
        [...selected].map((id) => assignTicket(id, bulkAssignee)),
      );
      setBulkAssignModal(false);
      setBulkAssignee("");
      setSelected(new Set());
      const res = await getTickets({
        status: filters.status || undefined,
        priority: filters.priority || undefined,
        category: filters.category || undefined,
        assignee_id: filters.assignee_id || undefined,
        search: filters.search || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      setTickets(res.items);
      setTotal(res.total);
    } catch {
      setBulkError("Falha ao atribuir alguns tickets.");
    } finally {
      setBulkLoading(false);
    }
  }

  const createdAt = (t: Ticket) =>
    new Date(t.created_at).toLocaleDateString("pt-BR");

  const techName = (id: string | null) =>
    id ? (technicians.find((t) => t.id === id)?.name ?? "—") : "—";

  // Compute the common valid transitions for all selected tickets
  const selectedTickets = tickets.filter((t) => selected.has(t.id));
  const commonTransitions =
    selectedTickets.length > 0
      ? Object.keys(STATUS_LABEL).filter((s) =>
          selectedTickets.every((t) =>
            TICKET_TRANSITIONS[t.status]?.includes(s),
          ),
        )
      : [];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Tickets</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {total} {total === 1 ? "chamado" : "chamados"} encontrados
          </p>
        </div>
        <Button onClick={() => navigate("/tickets/new")}>Abrir chamado</Button>
      </div>

      {/* Filters */}
      <TicketFilters
        value={filters}
        onChange={handleFiltersChange}
        technicians={isStaff ? technicians : undefined}
      />

      {/* Bulk action bar */}
      {isStaff && selected.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg bg-background-elevated border border-border px-4 py-2.5">
          <span className="text-sm text-slate-300 font-medium">
            {selected.size} selecionado{selected.size > 1 ? "s" : ""}
          </span>
          <div className="flex gap-2 ml-auto">
            {commonTransitions.length > 0 && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setBulkStatusModal(true)}
              >
                Alterar status
              </Button>
            )}
            {user?.role === "admin" && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setBulkAssignModal(true)}
              >
                Atribuir técnico
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelected(new Set())}
            >
              Limpar seleção
            </Button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && <Alert variant="danger">{error}</Alert>}

      {/* Table */}
      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-background-surface overflow-hidden">
          <div className="overflow-x-auto">
            <Table>
              <TableHead>
                <TableRow>
                  {isStaff && (
                    <TableHeaderCell className="w-10">
                      <input
                        type="checkbox"
                        checked={
                          tickets.length > 0 && selected.size === tickets.length
                        }
                        onChange={toggleAll}
                        className="accent-primary"
                        aria-label="Selecionar todos"
                      />
                    </TableHeaderCell>
                  )}
                  <TableHeaderCell className="w-36">Protocolo</TableHeaderCell>
                  <TableHeaderCell>Título</TableHeaderCell>
                  <TableHeaderCell className="w-36">Status</TableHeaderCell>
                  <TableHeaderCell
                    className="w-28"
                    sortable
                    sorted={sortedState("priority")}
                    onSort={() => handleSort("priority")}
                  >
                    Prioridade
                  </TableHeaderCell>
                  <TableHeaderCell className="w-28">Categoria</TableHeaderCell>
                  {isStaff && (
                    <TableHeaderCell className="w-36">
                      Responsável
                    </TableHeaderCell>
                  )}
                  <TableHeaderCell
                    className="w-28"
                    sortable
                    sorted={sortedState("sla_resolve_due_at")}
                    onSort={() => handleSort("sla_resolve_due_at")}
                  >
                    SLA
                  </TableHeaderCell>
                  <TableHeaderCell
                    className="w-28"
                    sortable
                    sorted={sortedState("created_at")}
                    onSort={() => handleSort("created_at")}
                  >
                    Criado em
                  </TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.length === 0 ? (
                  <TableEmpty
                    colSpan={isStaff ? 9 : 7}
                    message="Nenhum ticket encontrado para os filtros aplicados."
                  />
                ) : (
                  tickets.map((t) => (
                    <TableRow
                      key={t.id}
                      clickable
                      onClick={() => navigate(`/tickets/${t.id}`)}
                      className={selected.has(t.id) ? "bg-primary/5" : ""}
                    >
                      {isStaff && (
                        <TableCell
                          onClick={(e) => e.stopPropagation()}
                          className="w-10"
                        >
                          <input
                            type="checkbox"
                            checked={selected.has(t.id)}
                            onChange={() => toggleOne(t.id)}
                            className="accent-primary"
                            aria-label={`Selecionar ${t.protocol}`}
                          />
                        </TableCell>
                      )}
                      <TableCell muted>
                        <span className="font-mono text-xs">{t.protocol}</span>
                        {(t.sla_response_breach || t.sla_resolve_breach) && (
                          <span className="ml-1 text-danger text-xs">⚠</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className="line-clamp-1">{t.title}</span>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={t.status} />
                      </TableCell>
                      <TableCell>
                        <PriorityBadge priority={t.priority} />
                      </TableCell>
                      <TableCell muted className="text-xs capitalize">
                        {{
                          hardware: "Hardware",
                          software: "Software",
                          network: "Rede",
                          access: "Acesso",
                          email: "E-mail",
                          security: "Segurança",
                          general: "Geral",
                          other: "Outro",
                        }[t.category] ?? t.category}
                      </TableCell>
                      {isStaff && (
                        <TableCell muted className="text-xs">
                          {techName(t.assignee_id)}
                        </TableCell>
                      )}
                      <TableCell>
                        <SlaCell ticket={t} />
                      </TableCell>
                      <TableCell muted className="text-xs">
                        {createdAt(t)}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Pagination */}
      {!loading && total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={setPage}
        />
      )}

      {/* ── Bulk status modal ─────────────────────────── */}
      <Modal
        open={bulkStatusModal}
        onClose={() => {
          setBulkStatusModal(false);
          setBulkError(null);
          setBulkStatus("");
        }}
        title={`Alterar status — ${selected.size} ticket${selected.size > 1 ? "s" : ""}`}
      >
        <div className="space-y-4">
          {bulkError && <Alert variant="danger">{bulkError}</Alert>}
          <Select
            label="Novo status"
            options={commonTransitions.map((s) => ({
              value: s,
              label: STATUS_LABEL[s] ?? s,
            }))}
            placeholder="Selecione"
            value={bulkStatus}
            onChange={(e) => setBulkStatus(e.target.value)}
          />
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setBulkStatusModal(false)}
            disabled={bulkLoading}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleBulkStatus}
            loading={bulkLoading}
            disabled={!bulkStatus}
          >
            Confirmar
          </Button>
        </ModalFooter>
      </Modal>

      {/* ── Bulk assign modal ─────────────────────────── */}
      <Modal
        open={bulkAssignModal}
        onClose={() => {
          setBulkAssignModal(false);
          setBulkError(null);
          setBulkAssignee("");
        }}
        title={`Atribuir técnico — ${selected.size} ticket${selected.size > 1 ? "s" : ""}`}
      >
        <div className="space-y-4">
          {bulkError && <Alert variant="danger">{bulkError}</Alert>}
          <Select
            label="Técnico"
            options={technicians.map((t) => ({
              value: t.id,
              label: t.name,
            }))}
            placeholder="Selecione um técnico"
            value={bulkAssignee}
            onChange={(e) => setBulkAssignee(e.target.value)}
          />
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setBulkAssignModal(false)}
            disabled={bulkLoading}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleBulkAssign}
            loading={bulkLoading}
            disabled={!bulkAssignee}
          >
            Atribuir
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
