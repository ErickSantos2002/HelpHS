import { useState } from "react";
import { NavLink } from "react-router-dom";
import { cn } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";
import type { UserRole } from "../../types/auth";
import logoFull from "../../assets/Logo HelpHS.png";
import { APP_VERSION } from "../../data/changelog";
import { ChangelogModal } from "./ChangelogModal";
import { Icon } from "../ui";
import type { IconName } from "../ui";

/**
 * Os treze desenhos que moravam aqui voltaram de onde vieram.
 *
 * O `Icon.tsx` do pacote diz, no cabeçalho, que os traçados dele saíram deste
 * arquivo. Conferidos um a um antes da troca, os treze batem **caractere a
 * caractere** com o mapa do pacote, e as treze tags tinham exatamente o mesmo
 * envelope do primitivo — `viewBox="0 0 24 24"`, `fill="none"`,
 * `stroke="currentColor"`, `strokeWidth={1.75}` e 20px de lado. Não é ícone
 * parecido: é o mesmo, copiado. Manter a cópia local significaria que trocar um
 * traçado no pacote deixaria a barra lateral — que aparece em toda tela — com o
 * desenho antigo, e nada acusaria.
 */

// ── Nav structure ─────────────────────────────────────────────

interface NavItem {
  label: string;
  path: string;
  /**
   * Nome do traçado no pacote, não o elemento pronto.
   *
   * Guardar `React.ReactNode` aqui obrigava a existir um componente local por
   * ícone — foi o que segurou os treze `<svg>` neste arquivo. Com `IconName` o
   * TypeScript recusa nome que o pacote não tem, e o mapa continua sendo a
   * estrutura da tela: um item de menu é rótulo, rota, desenho e quem vê.
   */
  icon: IconName;
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
      { label: "Dashboard",            path: "/",          icon: "dashboard", roles: ["admin", "technician", "client"] },
      { label: "Tickets",              path: "/tickets",   icon: "ticket",    roles: ["admin", "technician", "client"] },
      { label: "Meus Equipamentos",    path: "/equipment", icon: "cpu",       roles: ["client"] },
      { label: "Base de Conhecimento", path: "/kb",        icon: "book",      roles: ["admin", "technician", "client"] },
    ],
  },
  {
    label: "Gestão",
    items: [
      { label: "Relatórios", path: "/reports", icon: "chart",    roles: ["admin", "technician"] },
      { label: "Agenda",     path: "/agenda",  icon: "calendar", roles: ["admin", "technician"] },
      { label: "Grupos",     path: "/grupos",  icon: "groups",   roles: ["admin", "technician"] },
      { label: "Respostas Rápidas", path: "/respostas-rapidas", icon: "chat", roles: ["admin", "technician"] },
    ],
  },
  {
    label: "Administração",
    items: [
      { label: "Usuários",    path: "/users",      icon: "users",  roles: ["admin", "technician"] },
      { label: "Produtos",    path: "/products",   icon: "box",    roles: ["admin", "technician"] },
      { label: "Etiquetas",   path: "/etiquetas",  icon: "tag",    roles: ["admin", "technician"] },
      { label: "Configuração SLA", path: "/sla-config", icon: "clock",  roles: ["admin"] },
      { label: "Audit Logs",  path: "/audit-logs", icon: "shield", roles: ["admin"] },
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
          className="fixed inset-0 z-[35] bg-[color:var(--overlay)] md:hidden"
          onClick={onMobileClose}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onMobileClose(); }}
        />
      )}

      {/* Sidebar panel */}
      <aside
        id="sidebar-nav"
        className={cn(
          "fixed inset-y-0 left-0 z-[40] flex flex-col",
          "bg-surface",
          "border-r border-borda",
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
            <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-action-tint">
              <span className="text-sm font-bold text-action">H</span>
            </div>
          ) : (
            <img src={logoFull} alt="HelpHS" className="h-7 w-auto object-contain" />
          )}
        </div>

        {/*
          Nav. O marco de navegação precisa de nome próprio: é o único `<nav>` do
          sistema, e sem rótulo o leitor de tela anuncia só "navegação".
        */}
        <nav
          aria-label="Navegação principal"
          className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-3 space-y-4"
        >
          {visibleGroups.map((group) => (
            /*
              `role="group"` com nome porque o rótulo da seção some no modo
              recolhido — lá sobra um traço decorativo, e "Administração"
              deixava de existir para quem não vê. Com o nome no grupo, os três
              agrupamentos são anunciados nos dois modos.
            */
            <div key={group.label} role="group" aria-label={group.label}>
              {/* Section label — só no modo expandido */}
              {!collapsed && (
                /*
                  `aria-hidden` porque este texto agora é a versão visível do
                  nome que o grupo já declara: sem isso o leitor lê duas vezes.
                */
                <p
                  aria-hidden="true"
                  className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-conteudo-muted"
                >
                  {group.label}
                </p>
              )}
              {/* Separador no modo colapsado */}
              {collapsed && (
                <div className="mx-auto w-6 border-t border-borda mb-1" />
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
                        "relative group flex items-center rounded-lg text-sm font-medium transition-colors duration-150",
                        collapsed ? "justify-center px-0 py-2.5 mx-1" : "gap-3 px-3 py-2",
                        isActive
                          ? [
                              "bg-action-tint text-action",
                              !collapsed && "border-l-2 border-action pl-[calc(0.75rem-2px)]",
                            ]
                          : [
                              !collapsed && "border-l-2 border-transparent pl-[calc(0.75rem-2px)]",
                              // `text-slate-500 dark:text-slate-400` era o
                              // degrau de texto secundário escrito à mão. No
                              // escuro ele já é, valor por valor, o
                              // `--text-muted`; no claro fica um degrau acima
                              // dele — 4,76:1 sobre `--surface`, contra os
                              // 7,58:1 do token. O token vale nos dois temas de
                              // uma vez, e no claro o item em repouso ganha.
                              "text-conteudo-muted",
                              "hover:bg-surface-elevated",
                              // `hover:text-slate-900 dark:hover:text-slate-100`
                              // é, valor por valor, `--text-heading` nos dois
                              // temas. Aqui a troca não muda um pixel.
                              "hover:text-conteudo-heading",
                            ],
                      )
                    }
                  >
                    <Icon name={item.icon} />

                    {/* Label — só no modo expandido */}
                    {!collapsed && <span className="truncate">{item.label}</span>}

                    {/*
                      Dica — só no modo recolhido. O texto fica na árvore
                      mesmo com `opacity-0`, e é ele que dá nome acessível ao
                      link quando o rótulo visível não é desenhado.

                      A pastilha escura invertida (`bg-slate-900
                      dark:bg-slate-700` com branco) virou o cromo de dica que o
                      próprio sistema já define em `CROMO` — superfície, borda e
                      texto de título. É mudança visível, e está relatada.
                    */}
                    {collapsed && (
                      <span className="pointer-events-none absolute left-full ml-3 z-50 whitespace-nowrap rounded-lg border border-borda bg-surface-elevated px-2.5 py-1.5 text-xs font-medium text-conteudo-heading shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-150">
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
          <div className="shrink-0 border-t border-borda px-5 py-4 space-y-0.5 flex flex-col items-center">
            <div className="relative group">
              <button
                onClick={() => setChangelogOpen(true)}
                className="text-xs font-medium text-conteudo-muted hover:text-action transition-colors cursor-pointer"
              >
                HelpHS {APP_VERSION}
              </button>
              {/* Mesma dica do menu recolhido, mesmo cromo. */}
              <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 whitespace-nowrap rounded-lg border border-borda bg-surface-elevated px-2.5 py-1.5 text-xs font-medium text-conteudo-heading shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-150">
                Ver o que há de novo nessa versão
              </span>
            </div>
            {/*
              O crédito era `text-slate-400 dark:text-slate-600`: sobre
              `--surface` dá **2,56:1** no claro e **2,11:1** no escuro. Texto
              de verdade, muito abaixo do piso de 4,5:1 nos dois temas — e
              invisível para a varredura, porque o fundo é declarado no
              `<aside>`, e fundo em ancestral é limitação que ela assume.

              `--text-faint`, que seria o degrau de mesmo nome, também não
              serve: 2,56 e 3,36. Quem aprova é `--text-muted` — 7,58 e 6,23.
              O crédito escurece, e é conserto de defeito medido, não gosto.
            */}
            <p className="text-[11px] text-conteudo-muted">
              © 2026 Health &amp; Safety Tech
            </p>
          </div>
        )}
      </aside>

      <ChangelogModal open={changelogOpen} onClose={() => setChangelogOpen(false)} />
    </>
  );
}
