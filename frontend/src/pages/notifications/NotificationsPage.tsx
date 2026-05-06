import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Pagination, Spinner } from "../../components/ui";
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
  ticket_created:      "Chamado criado",
  ticket_assigned:     "Chamado atribuído",
  ticket_updated:      "Chamado atualizado",
  ticket_resolved:     "Chamado resolvido",
  ticket_closed:       "Chamado encerrado",
  sla_warning:         "Aviso SLA",
  sla_breached:        "SLA violado",
  chat_message:        "Nova mensagem",
  satisfaction_survey: "Pesquisa de satisfação",
  system:              "Sistema",
};

interface TypeMeta { icon: React.ReactNode; pill: string }

const TYPE_META: Record<string, TypeMeta> = {
  ticket_created: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
      </svg>
    ),
    pill: "bg-primary/10 text-primary",
  },
  ticket_assigned: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
    pill: "bg-info/10 text-info",
  },
  ticket_updated: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
    pill: "bg-primary/10 text-primary",
  },
  ticket_resolved: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    pill: "bg-green-500/10 text-green-600 dark:text-green-400",
  },
  ticket_closed: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
    ),
    pill: "bg-slate-100 dark:bg-slate-700/50 text-slate-500",
  },
  sla_warning: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    pill: "bg-warning/10 text-warning",
  },
  sla_breached: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    pill: "bg-danger/10 text-danger",
  },
  chat_message: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
    pill: "bg-primary/10 text-primary",
  },
  satisfaction_survey: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
      </svg>
    ),
    pill: "bg-warning/10 text-warning",
  },
  system: {
    icon: (
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    pill: "bg-slate-100 dark:bg-slate-700/50 text-slate-500",
  },
};

const DEFAULT_META: TypeMeta = {
  icon: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
    </svg>
  ),
  pill: "bg-slate-100 dark:bg-slate-700/50 text-slate-500",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "agora";
  if (mins < 60) return `há ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `há ${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "ontem";
  if (days < 7) return `há ${days} dias`;
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

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
    getNotifications({ limit: PAGE_SIZE, offset: (p - 1) * PAGE_SIZE, unread_only: unreadOnlyFilter })
      .then((res) => { setItems(res.items); setTotal(res.total); setUnread(res.unread); })
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
      setItems((prev) => prev.map((n) => (n.id === notif.id ? { ...n, read: true } : n)));
      setUnread((u) => Math.max(0, u - 1));
    }
    if (notif.data?.ticket_id) navigate(`/tickets/${notif.data.ticket_id}`);
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

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Notificações</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {unread > 0 ? (
              <span><span className="text-primary font-medium">{unread}</span> não {unread === 1 ? "lida" : "lidas"}</span>
            ) : (
              "Todas lidas"
            )}
          </p>
        </div>

        {unread > 0 && (
          <Button variant="secondary" size="sm" loading={markingAll} onClick={handleMarkAllRead}>
            Marcar todas como lidas
          </Button>
        )}
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1">
        {[
          { label: "Todas", value: false },
          { label: "Não lidas", value: true },
        ].map((tab) => (
          <button
            key={String(tab.value)}
            onClick={() => { setUnreadOnly(tab.value); setPage(1); }}
            className={cn(
              "px-3 py-1.5 text-sm rounded-lg font-medium transition-colors",
              unreadOnly === tab.value
                ? "bg-primary text-white"
                : "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-background-elevated hover:text-slate-900 dark:hover:text-slate-100",
            )}
          >
            {tab.label}
            {tab.value && unread > 0 && (
              <span className="ml-1.5 bg-white/20 text-white text-xs rounded-full px-1.5 py-0.5 font-medium">
                {unread}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Feed */}
      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border py-16 flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-background-elevated flex items-center justify-center">
            <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
              {unreadOnly ? "Nenhuma notificação não lida" : "Nenhuma notificação"}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              {unreadOnly ? "Você está em dia com tudo!" : "As notificações aparecerão aqui"}
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-xl bg-white dark:bg-background-surface border border-slate-200 dark:border-border overflow-hidden divide-y divide-slate-100 dark:divide-border/60">
          {items.map((n) => {
            const meta = TYPE_META[n.type] ?? DEFAULT_META;
            return (
              <div
                key={n.id}
                role="button"
                tabIndex={0}
                onClick={() => handleMarkRead(n)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleMarkRead(n); }}
                className={cn(
                  "group relative flex items-start gap-4 px-5 py-4 cursor-pointer transition-colors",
                  "hover:bg-slate-50 dark:hover:bg-background-elevated",
                  !n.read && "bg-primary/[0.03] dark:bg-primary/[0.05]",
                )}
              >
                {/* Unread left border */}
                {!n.read && (
                  <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-primary rounded-r" />
                )}

                {/* Type icon */}
                <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5", meta.pill)}>
                  {meta.icon}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-3">
                    <p className={cn(
                      "text-sm leading-snug",
                      n.read ? "text-slate-600 dark:text-slate-400" : "font-semibold text-slate-900 dark:text-slate-100",
                    )}>
                      {n.title}
                    </p>
                    <span className="text-xs text-slate-400 shrink-0 mt-0.5">{timeAgo(n.created_at)}</span>
                  </div>
                  {n.message && (
                    <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{n.message}</p>
                  )}
                  <span className={cn("inline-block text-xs px-2 py-0.5 rounded-full mt-2 font-medium", meta.pill)}>
                    {TYPE_LABEL[n.type] ?? n.type}
                  </span>
                </div>

                {/* Delete button */}
                <button
                  type="button"
                  aria-label="Remover notificação"
                  onClick={(e) => { e.stopPropagation(); handleDelete(n.id); }}
                  className="opacity-0 group-hover:opacity-100 shrink-0 mt-0.5 w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-danger hover:bg-danger/10 transition-all"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            );
          })}
        </div>
      )}

      {!loading && total > PAGE_SIZE && (
        <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
      )}
    </div>
  );
}
