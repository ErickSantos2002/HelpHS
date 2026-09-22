import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";
import { Button } from "./Button";
import { Input } from "./Input";
import { SelectMenu } from "./SelectMenu";

// ── Filter state type ─────────────────────────────────────────

export interface TicketFilterState {
  search: string;
  status: string;
  priority: string;
  category: string;
  assignee_id: string;
  tag_id: string;
}

// eslint-disable-next-line react-refresh/only-export-components
export const EMPTY_FILTERS: TicketFilterState = {
  search: "",
  status: "",
  priority: "",
  category: "",
  assignee_id: "",
  tag_id: "",
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
  technicians?: { id: string; name: string }[];
  tags?: { id: string; name: string; color: string }[];
  className?: string;
}

export function TicketFilters({
  value,
  onChange,
  technicians,
  tags,
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
    value.search ||
    value.status ||
    value.priority ||
    value.category ||
    value.assignee_id ||
    value.tag_id;

  return (
    <div className={cn("flex flex-wrap items-end gap-3", className)}>
      {/* Search */}
      <div className="flex-1 min-w-48">
        <Input
          ref={searchRef}
          placeholder="Buscar por título, protocolo ou nº de série…"
          defaultValue={value.search}
          onChange={(e) => handleSearch(e.target.value)}
        />
      </div>

      {/* Status */}
      <div className="w-44">
        <SelectMenu
          placeholder="Status"
          options={STATUS_OPTIONS}
          value={value.status}
          onChange={(v) => onChange({ ...value, status: v })}
        />
      </div>

      {/* Priority */}
      <div className="w-36">
        <SelectMenu
          placeholder="Prioridade"
          options={PRIORITY_OPTIONS}
          value={value.priority}
          onChange={(v) => onChange({ ...value, priority: v })}
        />
      </div>

      {/* Category */}
      <div className="w-40">
        <SelectMenu
          placeholder="Categoria"
          options={CATEGORY_OPTIONS}
          value={value.category}
          onChange={(v) => onChange({ ...value, category: v })}
        />
      </div>

      {/* Responsável (staff only) */}
      {technicians && technicians.length > 0 && (
        <div className="w-44">
          <SelectMenu
            placeholder="Responsável"
            options={technicians.map((t) => ({ value: t.id, label: t.name }))}
            value={value.assignee_id}
            onChange={(v) => onChange({ ...value, assignee_id: v })}
          />
        </div>
      )}

      {/* Etiqueta */}
      {tags && tags.length > 0 && (
        <div className="w-40">
          <SelectMenu
            placeholder="Etiqueta"
            options={tags.map((t) => ({ value: t.id, label: t.name }))}
            value={value.tag_id}
            onChange={(v) => onChange({ ...value, tag_id: v })}
          />
        </div>
      )}

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
