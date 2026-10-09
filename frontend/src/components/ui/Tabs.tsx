import { createContext, useContext, useId } from "react";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

/**
 * Abas, de `DS/components/navigation/Tabs.jsx`.
 *
 * ── O que a Fase 10 encontrou ─────────────────────────────────────────
 *
 * O componente declarava `role="tablist"` e `role="tab"` e **não entregava nada
 * do que esses papéis prometem**. É o mesmo defeito do `SearchSelect` antes da
 * Fase 8, e o pior da família: declarar o papel faz um leitor de tela anunciar
 * "aba 2 de 4" e esperar as setas; sem elas, a pessoa fica presa esperando um
 * comportamento que nunca vem.
 *
 * Faltavam três coisas, e as três são o mesmo contrato:
 *
 * 1. **Setas.** O padrão WAI-ARIA de abas navega com ←/→, e o `Tab` sai da
 *    lista para o painel. Aqui o `Tab` percorria aba por aba, que é o
 *    comportamento de um grupo de botões — não de abas.
 * 2. **Tabulação móvel.** Só a aba ativa é tabulável; as outras ficam em
 *    `tabIndex={-1}` e são alcançadas pelas setas. Sem isso, uma tela com cinco
 *    abas gasta cinco paradas de teclado antes de chegar ao conteúdo.
 * 3. **O painel.** Não havia `role="tabpanel"`, nem `aria-controls` na aba, nem
 *    `aria-labelledby` no painel. A aba dizia existir e não dizia o que
 *    controlava.
 *
 * ── E o resto ─────────────────────────────────────────────────────────
 *
 * As cores eram escritas **só para o tema escuro** — `text-slate-100`,
 * `text-slate-400`, sem um único `dark:`. É o quinto componente de `ui/` com
 * esse vício nesta migração.
 *
 * O gatilho também não tinha `type="button"`: dentro de `<form>` o padrão do
 * HTML é `submit`, e trocar de aba enviaria o formulário. Aqui não há portal
 * para salvar, ao contrário do `Modal`.
 */

interface TabsContextValue {
  active: string;
  onChange: (value: string) => void;
  idBase: string;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs subcomponents must be used inside <Tabs>");
  return ctx;
}

/** Os dois lados do par precisam gerar o mesmo id a partir do mesmo valor. */
const idDaAba = (base: string, valor: string) => base + "-aba-" + valor;
const idDoPainel = (base: string, valor: string) => base + "-painel-" + valor;

export interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  className?: string;
}

export function Tabs({ value, onChange, children, className }: TabsProps) {
  const idBase = useId();

  return (
    <TabsContext.Provider value={{ active: value, onChange, idBase }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex gap-1 rounded-lg bg-surface-elevated p-1",
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface TabsTriggerProps {
  value: string;
  children: ReactNode;
  className?: string;
}

export function TabsTrigger({ value, children, className }: TabsTriggerProps) {
  const { active, onChange, idBase } = useTabsContext();
  const isActive = active === value;

  function aoTeclar(e: React.KeyboardEvent<HTMLButtonElement>) {
    const teclas = ["ArrowRight", "ArrowLeft", "Home", "End"];
    if (!teclas.includes(e.key)) return;

    // As irmãs vêm do DOM, e não de um registro no contexto: a lista é montada
    // por quem chama, em qualquer ordem, e o DOM é a única fonte que já sabe
    // qual é essa ordem.
    const lista = e.currentTarget.closest('[role="tablist"]');
    const abas = Array.from(
      lista?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? [],
    );
    if (abas.length === 0) return;

    const atual = abas.indexOf(e.currentTarget);
    let proxima = atual;
    if (e.key === "ArrowRight") proxima = (atual + 1) % abas.length;
    if (e.key === "ArrowLeft") proxima = (atual - 1 + abas.length) % abas.length;
    if (e.key === "Home") proxima = 0;
    if (e.key === "End") proxima = abas.length - 1;

    e.preventDefault();
    abas[proxima].focus();
    abas[proxima].click();
  }

  return (
    <button
      type="button"
      role="tab"
      id={idDaAba(idBase, value)}
      aria-selected={isActive}
      aria-controls={idDoPainel(idBase, value)}
      // Tabulação móvel: só a ativa recebe o foco pelo `Tab`; as outras são
      // alcançadas pelas setas, como o padrão WAI-ARIA de abas define.
      tabIndex={isActive ? 0 : -1}
      onClick={() => onChange(value)}
      onKeyDown={aoTeclar}
      className={cn(
        "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
        isActive
          ? "bg-surface text-conteudo-heading shadow-sm"
          : "text-conteudo-muted hover:text-conteudo",
        className,
      )}
    >
      {children}
    </button>
  );
}

export interface TabsContentProps {
  value: string;
  children: ReactNode;
  className?: string;
}

export function TabsContent({ value, children, className }: TabsContentProps) {
  const { active, idBase } = useTabsContext();
  if (active !== value) return null;

  return (
    <div
      role="tabpanel"
      id={idDoPainel(idBase, value)}
      aria-labelledby={idDaAba(idBase, value)}
      // O painel entra na tabulação: é para onde o `Tab` leva depois da lista, e
      // sem isso um painel sem elemento focável fica inalcançável por teclado.
      tabIndex={0}
      className={cn("focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action", className)}
    >
      {children}
    </div>
  );
}
