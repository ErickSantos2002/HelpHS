import { createContext, useContext, ReactNode } from "react";
import { cn } from "../../lib/utils";

// ── Context ───────────────────────────────────────────────────

interface TabsContextValue {
  active: string;
  onChange: (value: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs subcomponents must be used inside <Tabs>");
  return ctx;
}

// ── Tabs (root) ───────────────────────────────────────────────

export interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  className?: string;
}

export function Tabs({ value, onChange, children, className }: TabsProps) {
  return (
    <TabsContext.Provider value={{ active: value, onChange }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

// ── TabsList ──────────────────────────────────────────────────

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
        "inline-flex rounded-lg bg-background-elevated p-1 gap-1",
        className,
      )}
    >
      {children}
    </div>
  );
}

// ── TabsTrigger ───────────────────────────────────────────────

export interface TabsTriggerProps {
  value: string;
  children: ReactNode;
  className?: string;
}

export function TabsTrigger({ value, children, className }: TabsTriggerProps) {
  const { active, onChange } = useTabsContext();
  const isActive = active === value;

  return (
    <button
      role="tab"
      aria-selected={isActive}
      onClick={() => onChange(value)}
      className={cn(
        "px-4 py-1.5 rounded-md text-sm font-medium transition-colors",
        isActive
          ? "bg-background-surface text-slate-100 shadow-sm"
          : "text-slate-400 hover:text-slate-200",
        className,
      )}
    >
      {children}
    </button>
  );
}

// ── TabsContent ───────────────────────────────────────────────

export interface TabsContentProps {
  value: string;
  children: ReactNode;
  className?: string;
}

export function TabsContent({ value, children, className }: TabsContentProps) {
  const { active } = useTabsContext();
  if (active !== value) return null;
  return <div className={className}>{children}</div>;
}
