import { cn } from "../../lib/utils";

type BadgeVariant =
  | "primary"
  | "secondary"
  | "danger"
  | "warning"
  | "info"
  | "success"
  | "muted";

export interface BadgeProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> {
  variant?: BadgeVariant;
  children: React.ReactNode;
}

/**
 * As sete variantes, como o `Badge.jsx` do pacote as define: fundo na **tinta**,
 * texto no **par da tinta**, borda de 1px na cor semântica a 30%.
 *
 * ── O que estava errado, e não era pouco ──────────────────────────────
 *
 * Seis das sete pintavam `bg-<cor>/20` — a cor cheia da rampa com opacidade — e
 * quatro escreviam o degrau de texto à mão, com `dark:` para inverter. Medido
 * nas três superfícies e nos dois temas, **7 das 42 combinações reprovavam**, e
 * a pior era o `primary` no escuro: `dark:text-primary` é o degrau 500 sobre a
 * própria tinta, **2,77:1** sobre `--surface-elevated`.
 *
 * O `warning` era o único correto de ponta a ponta — e por isso foi o único que
 * a emenda **E8** alcançou. Ela levou `--on-tint-success` ao 800 e
 * `--on-tint-danger`/`--on-tint-info` ao 300 no escuro; nenhum desses tokens era
 * lido aqui, então a emenda passou por cima do componente sem tocá-lo.
 *
 * **Corrigir o token não alcança quem não o usa.** É a quarta aparição da mesma
 * regra nesta migração, e a primeira em que ela quase virou um relatório errado:
 * a medição dos **tokens** dava zero reprovações e a do **componente** dava
 * sete. O número estava certo e respondia outra pergunta.
 *
 * ── Sem modificador de opacidade nas tintas ───────────────────────────
 *
 * Regra (a) do D8-a: os cinco `--tint-*` já carregam alfa de 15% no token.
 * `bg-tint-danger/20` multiplicaria 0,15 × 0,20 e daria fundo quase invisível —
 * e o conserto intuitivo (subir para /30, /50) continua multiplicando e nunca
 * chega nos 15% do pacote.
 *
 * A borda continua com o modificador porque ela **não** é token com alfa: é a
 * cor cheia da rampa a 30%, exatamente como o pacote a escreve.
 */
const variantClasses: Record<BadgeVariant, string> = {
  primary: "bg-tint-primary text-on-tint-primary border-primary/30",
  secondary: "bg-tint-neutral text-on-tint-neutral border-borda",
  danger: "bg-tint-danger text-on-tint-danger border-danger/30",
  warning: "bg-tint-warning text-on-tint-warning border-warning/30",
  info: "bg-tint-info text-on-tint-info border-info/30",
  success: "bg-tint-success text-on-tint-success border-success/30",
  muted: "bg-tint-neutral text-on-tint-neutral border-borda",
};

export function Badge({
  variant = "secondary",
  children,
  className,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

// ── Ticket status badge ───────────────────────────────────────

type TicketStatus =
  | "open"
  | "in_progress"
  | "awaiting_client"
  | "awaiting_technical"
  | "resolved"
  | "closed"
  | "cancelled";

const statusVariant: Record<TicketStatus, BadgeVariant> = {
  open: "info",
  in_progress: "primary",
  awaiting_client: "warning",
  awaiting_technical: "warning",
  resolved: "success",
  closed: "muted",
  cancelled: "danger",
};

const statusLabel: Record<TicketStatus, string> = {
  open: "Aberto",
  in_progress: "Em andamento",
  awaiting_client: "Aguardando cliente",
  awaiting_technical: "Aguardando técnico",
  resolved: "Resolvido",
  closed: "Fechado",
  cancelled: "Cancelado",
};

export function StatusBadge({ status }: { status: TicketStatus }) {
  return <Badge variant={statusVariant[status]}>{statusLabel[status]}</Badge>;
}

// ── Ticket priority badge ─────────────────────────────────────

type TicketPriority = "critical" | "high" | "medium" | "low";

const priorityVariant: Record<TicketPriority, BadgeVariant> = {
  critical: "danger",
  high: "warning",
  medium: "info",
  low: "muted",
};

const priorityLabel: Record<TicketPriority, string> = {
  critical: "Crítico",
  high: "Alto",
  medium: "Médio",
  low: "Baixo",
};

export function PriorityBadge({ priority }: { priority: TicketPriority }) {
  return (
    <Badge variant={priorityVariant[priority]}>{priorityLabel[priority]}</Badge>
  );
}

// ── Tag badge ─────────────────────────────────────────────────

export function TagBadge({
  name,
  color,
  onRemove,
}: {
  name: string;
  color: string;
  onRemove?: () => void;
}) {
  return (
    <span
      title={name}
      className="inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{
        backgroundColor: `${color}22`,
        borderColor: `${color}55`,
        color,
      }}
    >
      {/* truncate evita que um nome longo empurre a largura do container */}
      <span className="truncate">{name}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="ml-0.5 shrink-0 hover:opacity-70 transition-opacity leading-none"
          aria-label={`Remover etiqueta ${name}`}
        >
          ×
        </button>
      )}
    </span>
  );
}
