import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "../ui";
import { cn } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";
import {
  getNotifications,
  markAllRead,
  markRead,
  type Notification,
} from "../../services/notificationService";

const roleLabel: Record<string, string> = {
  admin: "Administrador",
  technician: "Técnico",
  client: "Cliente",
};

const NOTIF_TYPE_LABEL: Record<string, string> = {
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

interface TopbarProps {
  onMenuClick: () => void;
}

// ── NotificationDropdown ──────────────────────────────────────

interface NotificationDropdownProps {
  onClose: () => void;
}

function NotificationDropdown({ onClose }: NotificationDropdownProps) {
  const navigate = useNavigate();
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [markingAll, setMarkingAll] = useState(false);

  useEffect(() => {
    getNotifications({ limit: 10 })
      .then((res) => {
        setItems(res.items);
        setUnread(res.unread);
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleMarkRead(notif: Notification) {
    if (!notif.read) {
      await markRead(notif.id);
      setItems((prev) =>
        prev.map((n) => (n.id === notif.id ? { ...n, read: true } : n)),
      );
      setUnread((u) => Math.max(0, u - 1));
    }
    if (notif.data?.ticket_id) {
      onClose();
      navigate(`/tickets/${notif.data.ticket_id}`);
    }
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

  function timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "agora";
    if (mins < 60) return `${mins}min`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    return `${Math.floor(hrs / 24)}d`;
  }

  return (
    <div className="absolute right-0 top-full mt-1 w-80 max-w-[calc(100vw-1rem)] rounded-xl border border-border bg-background-surface shadow-xl z-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-100">
            Notificações
          </span>
          {unread > 0 && (
            <span className="text-xs bg-danger text-white rounded-full px-1.5 py-0.5 font-medium">
              {unread}
            </span>
          )}
        </div>
        {unread > 0 && (
          <button
            className="text-xs text-primary hover:text-primary/80 disabled:opacity-50"
            onClick={handleMarkAllRead}
            disabled={markingAll}
          >
            {markingAll ? "..." : "Marcar todas"}
          </button>
        )}
      </div>

      {/* List */}
      <div className="max-h-80 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
            Carregando…
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-slate-500 text-sm">
            Nenhuma notificação
          </div>
        ) : (
          items.map((n) => (
            <button
              key={n.id}
              className={cn(
                "w-full text-left px-4 py-3 border-b border-border/50 hover:bg-background-elevated transition-colors",
                !n.read && "bg-background-elevated/40",
              )}
              onClick={() => handleMarkRead(n)}
            >
              <div className="flex items-start gap-2">
                {!n.read && (
                  <span className="mt-1.5 w-2 h-2 rounded-full bg-primary shrink-0" />
                )}
                <div className={cn("flex-1 min-w-0", n.read && "pl-4")}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-slate-500 truncate">
                      {NOTIF_TYPE_LABEL[n.type] ?? n.type}
                    </p>
                    <span className="text-xs text-slate-600 shrink-0">
                      {timeAgo(n.created_at)}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-slate-200 truncate">
                    {n.title}
                  </p>
                  <p className="text-xs text-slate-400 line-clamp-2">
                    {n.message}
                  </p>
                </div>
              </div>
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-border">
        <button
          className="w-full text-center text-xs text-primary hover:text-primary/80 transition-colors"
          onClick={() => {
            onClose();
            navigate("/notifications");
          }}
        >
          Ver todas as notificações
        </button>
      </div>
    </div>
  );
}

// ── Topbar ────────────────────────────────────────────────────

export function Topbar({ onMenuClick }: TopbarProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const userMenuRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  // Fetch unread count on mount + every 30s
  const fetchUnread = useCallback(() => {
    getNotifications({ limit: 1 })
      .then((res) => setUnreadCount(res.unread))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchUnread();
    const interval = setInterval(fetchUnread, 30_000);
    return () => clearInterval(interval);
  }, [fetchUnread]);

  // Close dropdowns on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        userMenuRef.current &&
        !userMenuRef.current.contains(e.target as Node)
      ) {
        setUserMenuOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background-surface px-4 md:px-6">
      {/* Left: hamburger (mobile) */}
      <button
        className="rounded-lg p-2 text-slate-400 hover:bg-background-elevated hover:text-slate-100 transition-colors md:hidden"
        onClick={onMenuClick}
        aria-label="Abrir menu"
      >
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 6h16M4 12h16M4 18h16"
          />
        </svg>
      </button>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right: notifications + user menu */}
      <div className="flex items-center gap-2">
        {/* Notification bell */}
        <div className="relative" ref={notifRef}>
          <button
            className={cn(
              "relative rounded-lg p-2 text-slate-400 hover:bg-background-elevated hover:text-slate-100 transition-colors",
              notifOpen && "bg-background-elevated text-slate-100",
            )}
            aria-label="Notificações"
            onClick={() => setNotifOpen((v) => !v)}
          >
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
              />
            </svg>
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 min-w-[1rem] h-4 rounded-full bg-danger text-white text-[10px] font-bold flex items-center justify-center px-0.5">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </button>

          {notifOpen && (
            <NotificationDropdown onClose={() => setNotifOpen(false)} />
          )}
        </div>

        {/* User dropdown */}
        <div className="relative" ref={userMenuRef}>
          <button
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors",
              "hover:bg-background-elevated",
              userMenuOpen && "bg-background-elevated",
            )}
            onClick={() => setUserMenuOpen((v) => !v)}
          >
            <Avatar name={user?.name ?? "?"} size="sm" />
            <div className="hidden md:block text-left">
              <p className="text-sm font-medium text-slate-100 leading-tight">
                {user?.name}
              </p>
              <p className="text-xs text-slate-500 leading-tight">
                {roleLabel[user?.role ?? "client"]}
              </p>
            </div>
            <svg
              className="w-4 h-4 text-slate-500 hidden md:block"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>

          {/* Dropdown menu */}
          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 rounded-xl border border-border bg-background-surface shadow-xl z-50 py-1">
              <div className="px-3 py-2 border-b border-border">
                <p className="text-sm font-medium text-slate-100 truncate">
                  {user?.name}
                </p>
                <p className="text-xs text-slate-500 truncate">{user?.email}</p>
              </div>
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-background-elevated hover:text-slate-100 transition-colors"
                onClick={() => {
                  setUserMenuOpen(false);
                  navigate("/profile");
                }}
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
                    d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                  />
                </svg>
                Meu perfil
              </button>
              <button
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-danger hover:bg-background-elevated transition-colors"
                onClick={handleLogout}
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
                    d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                  />
                </svg>
                Sair
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
