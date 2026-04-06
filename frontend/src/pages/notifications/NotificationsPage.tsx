import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Button,
  Pagination,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui";
import { cn } from "../../lib/utils";
import {
  deleteNotification,
  getNotifications,
  markAllRead,
  markRead,
  type Notification,
} from "../../services/notificationService";

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 20;

const TYPE_LABEL: Record<string, string> = {
  ticket_created: "Chamado criado",
  ticket_assigned: "Chamado atribuído",
  ticket_updated: "Chamado atualizado",
  ticket_resolved: "Chamado resolvido",
  ticket_closed: "Chamado encerrado",
  sla_warning: "Aviso SLA",
  sla_breached: "SLA violado",
  chat_message: "Nova mensagem",
  satisfaction_survey: "Pesquisa de satisfação",
  system: "Sistema",
};

const TYPE_COLOR: Record<string, string> = {
  sla_warning: "text-warning",
  sla_breached: "text-danger",
  ticket_resolved: "text-primary",
  ticket_closed: "text-slate-500",
  system: "text-slate-500",
};

// ── NotificationsPage ─────────────────────────────────────────

export default function NotificationsPage() {
  const navigate = useNavigate();

  const [items, setItems] = useState<Notification[]>([]);
  const [total, setTotal] = useState(0);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);

  function load(p = page, unreadOnlyFilter = unreadOnly) {
    setLoading(true);
    setError(null);
    getNotifications({
      limit: PAGE_SIZE,
      offset: (p - 1) * PAGE_SIZE,
      unread_only: unreadOnlyFilter,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
        setUnread(res.unread);
      })
      .catch(() => setError("Não foi possível carregar as notificações."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, unreadOnly]);

  async function handleMarkRead(notif: Notification) {
    if (!notif.read) {
      await markRead(notif.id);
      setItems((prev) =>
        prev.map((n) => (n.id === notif.id ? { ...n, read: true } : n)),
      );
      setUnread((u) => Math.max(0, u - 1));
    }
    if (notif.data?.ticket_id) {
      navigate(`/tickets/${notif.data.ticket_id}`);
    }
  }

  async function handleDelete(id: string) {
    await deleteNotification(id);
    setItems((prev) => prev.filter((n) => n.id !== id));
    setTotal((t) => t - 1);
  }

  async function handleMarkAllRead() {
    setMarkingAll(true);
    try {
      await markAllRead();
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnread(0);
    } finally {
      setMarkingAll(false);
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Notificações</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {unread > 0 ? (
              <span>
                <span className="text-primary font-medium">{unread}</span> não
                lidas
              </span>
            ) : (
              "Todas lidas"
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => {
                setUnreadOnly(e.target.checked);
                setPage(1);
              }}
              className="accent-primary"
            />
            Apenas não lidas
          </label>
          {unread > 0 && (
            <Button
              variant="secondary"
              size="sm"
              loading={markingAll}
              onClick={handleMarkAllRead}
            >
              Marcar todas como lidas
            </Button>
          )}
        </div>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

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
                  <TableHeaderCell className="w-8" />
                  <TableHeaderCell>Título</TableHeaderCell>
                  <TableHeaderCell className="w-40">Tipo</TableHeaderCell>
                  <TableHeaderCell className="w-40">Data</TableHeaderCell>
                  <TableHeaderCell className="w-20 text-right">
                    Ações
                  </TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.length === 0 ? (
                  <TableEmpty
                    colSpan={5}
                    message="Nenhuma notificação encontrada."
                  />
                ) : (
                  items.map((n) => (
                    <TableRow
                      key={n.id}
                      className={cn(
                        "cursor-pointer",
                        !n.read && "bg-background-elevated/30",
                      )}
                      onClick={() => handleMarkRead(n)}
                    >
                      <TableCell>
                        {!n.read && (
                          <span className="block w-2 h-2 rounded-full bg-primary mx-auto" />
                        )}
                      </TableCell>
                      <TableCell>
                        <div>
                          <p
                            className={cn(
                              "text-sm",
                              n.read
                                ? "text-slate-400"
                                : "font-medium text-slate-200",
                            )}
                          >
                            {n.title}
                          </p>
                          <p className="text-xs text-slate-500 line-clamp-1">
                            {n.message}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span
                          className={cn(
                            "text-xs",
                            TYPE_COLOR[n.type] ?? "text-slate-400",
                          )}
                        >
                          {TYPE_LABEL[n.type] ?? n.type}
                        </span>
                      </TableCell>
                      <TableCell muted className="text-xs">
                        {formatDate(n.created_at)}
                      </TableCell>
                      <TableCell
                        className="text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(n.id)}
                        >
                          Remover
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {!loading && total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={setPage}
        />
      )}
    </div>
  );
}
