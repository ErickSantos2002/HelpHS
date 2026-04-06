import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";
import { Button } from "./Button";
import { Input } from "./Input";
import { Select } from "./Select";

// ── Filter state type ─────────────────────────────────────────

export interface TicketFilterState {
  search: string;
  status: string;
  priority: string;
  category: string;
}

export const EMPTY_FILTERS: TicketFilterState = {
  search: "",
  status: "",
  priority: "",
  category: "",
};

// ── Options ───────────────────────────────────────────────────

const STATUS_OPTIONS = [
  { value: "open", label: "Aberto" },
  { value: "in_progress", label: "Em andamento" },
  { value: "awaiting_client", label: "Aguardando cliente" },
  { value: "awaiting_technical", label: "Aguardando técnico" },
  { value: "resolved", label: "Resolvido" },
  { value: "closed", label: "Fechado" },
  { value: "cancelled", label: "Cancelado" },
];

const PRIORITY_OPTIONS = [
  { value: "critical", label: "Crítico" },
  { value: "high", label: "Alto" },
  { value: "medium", label: "Médio" },
  { value: "low", label: "Baixo" },
];

const CATEGORY_OPTIONS = [
  { value: "hardware", label: "Hardware" },
  { value: "software", label: "Software" },
  { value: "network", label: "Rede" },
  { value: "access", label: "Acesso" },
  { value: "email", label: "E-mail" },
  { value: "security", label: "Segurança" },
  { value: "general", label: "Geral" },
  { value: "other", label: "Outro" },
];

// ── TicketFilters ─────────────────────────────────────────────

export interface TicketFiltersProps {
  value: TicketFilterState;
  onChange: (filters: TicketFilterState) => void;
  className?: string;
}

export function TicketFilters({
  value,
  onChange,
  className,
}: TicketFiltersProps) {
  const searchRef = useRef<HTMLInputElement>(null);

  // Debounce search input
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleSearch(raw: string) {
    if (searchTimeout.current) clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => {
      onChange({ ...value, search: raw });
    }, 350);
  }

  useEffect(() => {
    return () => {
      if (searchTimeout.current) clearTimeout(searchTimeout.current);
    };
  }, []);

  const hasActiveFilters =
    value.search || value.status || value.priority || value.category;

  return (
    <div className={cn("flex flex-wrap items-end gap-3", className)}>
      {/* Search */}
      <div className="flex-1 min-w-48">
        <Input
          ref={searchRef}
          placeholder="Buscar por título ou protocolo…"
          defaultValue={value.search}
          onChange={(e) => handleSearch(e.target.value)}
        />
      </div>

      {/* Status */}
      <div className="w-44">
        <Select
          placeholder="Status"
          options={STATUS_OPTIONS}
          value={value.status}
          onChange={(e) => onChange({ ...value, status: e.target.value })}
        />
      </div>

      {/* Priority */}
      <div className="w-36">
        <Select
          placeholder="Prioridade"
          options={PRIORITY_OPTIONS}
          value={value.priority}
          onChange={(e) => onChange({ ...value, priority: e.target.value })}
        />
      </div>

      {/* Category */}
      <div className="w-40">
        <Select
          placeholder="Categoria"
          options={CATEGORY_OPTIONS}
          value={value.category}
          onChange={(e) => onChange({ ...value, category: e.target.value })}
        />
      </div>

      {/* Clear */}
      {hasActiveFilters && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            if (searchRef.current) searchRef.current.value = "";
            onChange(EMPTY_FILTERS);
          }}
        >
          Limpar
        </Button>
      )}
    </div>
  );
}
