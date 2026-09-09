import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar, Icon, Switch } from "../ui";
import { cn } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";
import { useTheme } from "../../contexts/ThemeContext";
import { rotuloDePapel } from "../../lib/papel";
import {
  getNotifications,
  markAllRead,
  markRead,
  type Notification,
} from "../../services/notificationService";

/* O rótulo do papel vem de `lib/papel.ts`. Esta era uma das cinco cópias. */

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
  onMobileMenuClick: () => void;
  onToggleCollapsed: () => void;
  sidebarCollapsed: boolean;
  /**
   * Titulo da pagina, no lugar que o design system reserva para ele: o
   * template oficial de listagem tem um unico <h1>, e ele fica aqui, nao
   * dentro do <main>.
   *
   * Nasce opcional de proposito. Hoje 27 paginas do HelpHS desenham o
   * proprio <h1>; passar o titulo aqui antes de tira-lo de la duplicaria o
   * titulo — e dois <h1> na mesma pagina. Cada tela passa a preencher esta
   * prop quando for migrada (Fases 11-16), soltando o <h1> que tem hoje.
   */
  pageTitle?: React.ReactNode;
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
    <div className="absolute right-0 top-[calc(100%+0.5rem)] w-80 max-w-[calc(100vw-1rem)] rounded-xl border border-borda bg-surface shadow-xl z-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-borda">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-conteudo-heading">
            Notificações
          </span>
          {unread > 0 && (
            /* `bg-danger` é a cor CHEIA da rampa; com `text-white` por cima dá
               3,76:1, e era um dos dois pares que a catraca cobrava desta
               tela. O degrau de AÇÃO (`--action-danger`) e o par dele
               (`--text-on-danger`) existem para isto. */
            <span className="text-xs bg-action-danger text-on-danger rounded-full px-1.5 py-0.5 font-medium">
              {unread}
            </span>
          )}
        </div>
        {unread > 0 && (
          <button
            className="text-xs text-conteudo-link hover:text-conteudo-link-hover disabled:opacity-50"
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
          <div className="flex items-center justify-center py-8 text-conteudo-muted text-sm">
            Carregando…
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-conteudo-muted text-sm">
            Nenhuma notificação
          </div>
        ) : (
          items.map((n) => (
            <button
              key={n.id}
              className={cn(
                "w-full text-left px-4 py-3 border-b border-borda hover:bg-surface-elevated transition-colors",
                // O realce de "não lida" era `bg-slate-50` no claro e
                // `bg-surface-elevated/40` no escuro — dois valores à mão, um
                // por tema, e no escuro ele empatava com o hover. O
                // `--action-tint` resolve por tema sozinho, e é o mesmo realce
                // que a `NotificationsPage` usa para a mesma linha.
                !n.read && "bg-action-tint",
              )}
              onClick={() => handleMarkRead(n)}
            >
              <div className="flex items-start gap-2">
                {!n.read && (
                  <span className="mt-1.5 w-2 h-2 rounded-full bg-action shrink-0" />
                )}
                <div className={cn("flex-1 min-w-0", n.read && "pl-4")}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-conteudo-muted truncate">
                      {NOTIF_TYPE_LABEL[n.type] ?? n.type}
                    </p>
                    <span className="text-xs text-conteudo-muted shrink-0">
                      {timeAgo(n.created_at)}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-conteudo truncate">
                    {n.title}
                  </p>
                  <p className="text-xs text-conteudo-muted line-clamp-2">
                    {n.message}
                  </p>
                </div>
              </div>
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t border-borda">
        <button
          className="w-full text-center text-xs text-conteudo-link hover:text-conteudo-link-hover transition-colors"
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

export function Topbar({ onMobileMenuClick, onToggleCollapsed, sidebarCollapsed, pageTitle }: TopbarProps) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
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
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-borda bg-surface px-4 md:px-6">
      {/* Left: hamburger desktop (colapsa sidebar) + mobile (abre drawer) */}
      <div className="flex items-center gap-1">
        {/* Desktop toggle */}
        <button
          className="hidden md:flex rounded-lg p-2 text-conteudo-muted hover:bg-surface-elevated hover:text-conteudo-heading transition-colors"
          onClick={onToggleCollapsed}
          aria-label={sidebarCollapsed ? "Expandir menu" : "Recolher menu"}
          aria-expanded={!sidebarCollapsed}
          aria-controls="sidebar-nav"
        >
          <Icon name="menu" size={20} strokeWidth={2} />
        </button>

        {/* Mobile toggle */}
        <button
          className="md:hidden rounded-lg p-2 text-conteudo-muted hover:bg-surface-elevated hover:text-conteudo-heading transition-colors"
          onClick={onMobileMenuClick}
          aria-label="Abrir menu de navegação"
          aria-controls="sidebar-nav"
          aria-expanded={false}
        >
          <Icon name="menu" size={20} strokeWidth={2} />
        </button>
      </div>

      {/* Titulo da pagina — --text-base semibold --text-heading, medidas do
          AppShell.jsx. Corta com reticencias em vez de empurrar as acoes. */}
      {pageTitle && (
        <h1 className="ml-2 min-w-0 truncate text-base font-semibold text-conteudo-heading">
          {pageTitle}
        </h1>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right: notifications + user menu */}
      <div className="relative flex items-center gap-2">
        {/* Notification bell */}
        <div ref={notifRef}>
          <button
            className={cn(
              "relative rounded-lg p-2 text-conteudo-muted transition-colors",
              "hover:bg-surface-elevated hover:text-conteudo-heading",
              notifOpen && "bg-surface-elevated text-conteudo-heading",
            )}
            aria-label={
              unreadCount > 0
                ? `Notificações — ${unreadCount} não lida${unreadCount > 1 ? "s" : ""}`
                : "Notificações"
            }
            aria-expanded={notifOpen}
            aria-haspopup="dialog"
            onClick={() => setNotifOpen((v) => !v)}
          >
            <Icon name="bell" size={20} strokeWidth={2} />
            {unreadCount > 0 && (
              /* O segundo par que a catraca cobrava: mesmo `bg-danger` +
                 `text-white` de 3,76:1 do contador de dentro do painel. */
              <span className="absolute top-1 right-1 min-w-[1rem] h-4 rounded-full bg-action-danger text-on-danger text-[10px] font-bold flex items-center justify-center px-0.5">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </button>

          {notifOpen && (
            <NotificationDropdown onClose={() => setNotifOpen(false)} />
          )}
        </div>

        {/* User dropdown */}
        <div ref={userMenuRef}>
          <button
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors",
              "hover:bg-surface-elevated",
              userMenuOpen && "bg-surface-elevated",
            )}
            onClick={() => setUserMenuOpen((v) => !v)}
            aria-label={`Menu do usuário — ${user?.name ?? ""}`}
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
          >
            <Avatar name={user?.name ?? "?"} src={user?.avatar_url ?? undefined} size="sm" />
            <div className="hidden md:block text-left">
              <p className="text-sm font-medium text-conteudo leading-tight">
                {user?.name}
              </p>
              <p className="text-xs text-conteudo-muted leading-tight">
                {rotuloDePapel(user?.role ?? "client")}
              </p>
            </div>
            <Icon
              name="chevronDown"
              size={16}
              strokeWidth={2}
              className="text-conteudo-muted hidden md:block"
            />
          </button>

          {/* Dropdown menu */}
          {userMenuOpen && (
            <div className="absolute right-0 top-[calc(100%+0.5rem)] w-56 rounded-xl border border-borda bg-surface shadow-xl z-50 py-1">
              {/* User info */}
              <div className="px-3 py-2.5 border-b border-borda">
                <p className="text-sm font-semibold text-conteudo-heading truncate">
                  {user?.name}
                </p>
                <p className="text-xs text-conteudo-muted truncate">{user?.email}</p>
              </div>

              {/* Meu perfil */}
              <button
                className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-conteudo hover:bg-surface-elevated hover:text-conteudo-heading transition-colors"
                onClick={() => { setUserMenuOpen(false); navigate("/profile"); }}
              >
                <Icon name="user" size={16} strokeWidth={2} />
                Meu perfil
              </button>

              {/* Tema — o interruptor e o primitivo `Switch`, e nao um botao
                  com um trilho desenhado dentro: o estado agora e anunciado.
                  O `theme === "dark"` que sobra aqui é o ESTADO do controle,
                  não escolha de cor: ele não seleciona hexadecimal nenhum, e
                  por isso fica. */}
              <Switch
                checked={theme === "dark"}
                onChange={() => toggleTheme()}
                size="sm"
                className="w-full flex-row-reverse justify-between px-3 py-2 text-conteudo-muted transition-colors hover:bg-surface-elevated hover:text-conteudo"
                label={
                  <span className="flex flex-1 items-center gap-2.5">
                    <Icon name="moon" size={16} strokeWidth={2} />
                    <span className="flex-1 text-left">Modo escuro</span>
                  </span>
                }
              />

              <div className="border-t border-borda mt-1 pt-1">
              <button
                className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-on-tint-danger hover:bg-surface-elevated transition-colors"
                onClick={handleLogout}
              >
                <Icon name="logout" size={16} strokeWidth={2} />
                Sair
              </button>
            </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
