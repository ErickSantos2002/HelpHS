import { useState } from "react";
import { NavLink } from "react-router-dom";
import { cn } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";
import type { UserRole } from "../../types/auth";
import logoFull from "../../assets/Logo HelpHS.png";
import { APP_VERSION } from "../../data/changelog";
import { ChangelogModal } from "./ChangelogModal";

// ── Icons ─────────────────────────────────────────────────────

function IconDashboard() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    </svg>
  );
}
function IconTicket() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
    </svg>
  );
}
function IconUsers() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  );
}
function IconBox() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
  );
}
function IconChart() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  );
}

function IconShield() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  );
}
function IconClock() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}
function IconCpu() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H7a2 2 0 00-2 2v2M9 3h6M9 3v2m6-2h2a2 2 0 012 2v2M15 3v2M3 9h2m16 0h-2M3 15h2m16 0h-2M9 21H7a2 2 0 01-2-2v-2m4 4h6m-6 0v-2m6 2h2a2 2 0 002-2v-2m-4 4v-2M9 9h6v6H9V9z" />
    </svg>
  );
}
function IconBook() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  );
}
function IconGroups() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  );
}
function IconTag() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5.586a1 1 0 01.707.293l7.414 7.414a2 2 0 010 2.828l-5.586 5.586a2 2 0 01-2.828 0L4.879 11.707A2 2 0 014.293 11.1L3 5.414A2 2 0 014.414 4L7 3z" />
    </svg>
  );
}
function IconCalendar() {
  return (
    <svg className="w-5 h-5 shrink-0" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}

// ── Nav structure ─────────────────────────────────────────────

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  roles: UserRole[];
}
interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Principal",
    items: [
      { label: "Dashboard",            path: "/",          icon: <IconDashboard />, roles: ["admin", "technician", "client"] },
      { label: "Tickets",              path: "/tickets",   icon: <IconTicket />,   roles: ["admin", "technician", "client"] },
      { label: "Meus Equipamentos",    path: "/equipment", icon: <IconCpu />,      roles: ["client"] },
      { label: "Base de Conhecimento", path: "/kb",        icon: <IconBook />,     roles: ["admin", "technician", "client"] },
    ],
  },
  {
    label: "Gestão",
    items: [
      { label: "Relatórios", path: "/reports", icon: <IconChart />,    roles: ["admin", "technician"] },
      { label: "Agenda",     path: "/agenda",  icon: <IconCalendar />, roles: ["admin", "technician"] },
      { label: "Grupos",     path: "/grupos",  icon: <IconGroups />,   roles: ["admin", "technician"] },
    ],
  },
  {
    label: "Administração",
    items: [
      { label: "Usuários",    path: "/users",      icon: <IconUsers />,  roles: ["admin", "technician"] },
      { label: "Produtos",    path: "/products",   icon: <IconBox />,    roles: ["admin", "technician"] },
      { label: "Etiquetas",   path: "/etiquetas",  icon: <IconTag />,    roles: ["admin", "technician"] },
      { label: "Configuração SLA", path: "/sla-config", icon: <IconClock />,  roles: ["admin"] },
      { label: "Audit Logs",  path: "/audit-logs", icon: <IconShield />, roles: ["admin"] },
    ],
  },
];

// ── Sidebar ───────────────────────────────────────────────────

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ collapsed, mobileOpen, onMobileClose }: SidebarProps) {
  const { user } = useAuth();
  const role = user?.role ?? "client";
  const [changelogOpen, setChangelogOpen] = useState(false);

  const visibleGroups = NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((i) => i.roles.includes(role)),
  })).filter((g) => g.items.length > 0);

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Fechar menu"
          className="fixed inset-0 z-[35] bg-black/50 md:hidden"
          onClick={onMobileClose}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onMobileClose(); }}
        />
      )}

      {/* Sidebar panel */}
      <aside
        id="sidebar-nav"
        className={cn(
          "fixed inset-y-0 left-0 z-[40] flex flex-col",
          "bg-white dark:bg-background-surface",
          "border-r border-slate-200 dark:border-border",
          "transition-[width] duration-300 ease-in-out overflow-hidden",
          // Desktop: width driven by collapsed state
          collapsed ? "md:w-[72px]" : "md:w-64",
          // Mobile: always full width drawer
          "w-64",
          "md:translate-x-0 md:static md:z-auto",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {/* Logo — sem border-b para evitar linha dupla com o Topbar */}
        <div className={cn(
          "flex h-16 shrink-0 items-center",
          collapsed ? "justify-center px-0" : "px-5",
        )}>
          {collapsed ? (
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/10 dark:bg-primary/15">
              <span className="text-sm font-bold text-primary">H</span>
            </div>
          ) : (
            <img src={logoFull} alt="HelpHS" className="h-8 w-auto object-contain" />
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-3 space-y-4">
          {visibleGroups.map((group) => (
            <div key={group.label}>
              {/* Section label — só no modo expandido */}
              {!collapsed && (
                <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-600">
                  {group.label}
                </p>
              )}
              {/* Separador no modo colapsado */}
              {collapsed && (
                <div className="mx-auto w-6 border-t border-slate-200 dark:border-border mb-1" />
              )}

              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/"}
                    onClick={() => onMobileClose()}
                    className={({ isActive }) =>
                      cn(
                        "relative group flex items-center rounded-lg text-sm font-medium transition-all duration-150",
                        collapsed ? "justify-center px-0 py-2.5 mx-1" : "gap-3 px-3 py-2",
                        isActive
                          ? [
                              "bg-primary/10 dark:bg-primary/15 text-primary",
                              !collapsed && "border-l-2 border-primary pl-[calc(0.75rem-2px)]",
                            ]
                          : [
                              !collapsed && "border-l-2 border-transparent pl-[calc(0.75rem-2px)]",
                              "text-slate-500 dark:text-slate-400",
                              "hover:bg-slate-100 dark:hover:bg-background-elevated",
                              "hover:text-slate-900 dark:hover:text-slate-100",
                            ],
                      )
                    }
                  >
                    {item.icon}

                    {/* Label — só no modo expandido */}
                    {!collapsed && <span className="truncate">{item.label}</span>}

                    {/* Tooltip — só no modo colapsado */}
                    {collapsed && (
                      <span className="pointer-events-none absolute left-full ml-3 z-50 whitespace-nowrap rounded-lg bg-slate-900 dark:bg-slate-700 px-2.5 py-1.5 text-xs font-medium text-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                        {item.label}
                      </span>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer */}
        {!collapsed && (
          <div className="shrink-0 border-t border-slate-200 dark:border-border px-5 py-4 space-y-0.5 flex flex-col items-center">
            <div className="relative group">
              <button
                onClick={() => setChangelogOpen(true)}
                className="text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-primary dark:hover:text-primary transition-colors cursor-pointer"
              >
                HelpHS {APP_VERSION}
              </button>
              <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 whitespace-nowrap rounded-lg bg-slate-900 dark:bg-slate-700 px-2.5 py-1.5 text-xs font-medium text-white shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                Ver o que há de novo nessa versão
              </span>
            </div>
            <p className="text-[11px] text-slate-400 dark:text-slate-600">
              © 2026 Health &amp; Safety Tech
            </p>
          </div>
        )}
      </aside>

      <ChangelogModal open={changelogOpen} onClose={() => setChangelogOpen(false)} />
    </>
  );
}
