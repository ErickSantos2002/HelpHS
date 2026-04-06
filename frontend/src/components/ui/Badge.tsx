import { cn } from "../../lib/utils";

type BadgeVariant =
  | "primary"
  | "secondary"
  | "danger"
  | "warning"
  | "info"
  | "success"
  | "muted";

export interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  primary: "bg-primary/20 text-primary border-primary/30",
  secondary: "bg-background-elevated text-slate-300 border-border",
  danger: "bg-danger/20 text-danger-400 border-danger/30",
  warning: "bg-warning/20 text-warning-400 border-warning/30",
  info: "bg-info/20 text-info-400 border-info/30",
  success: "bg-primary/20 text-primary border-primary/30",
  muted: "bg-background-elevated text-slate-500 border-border",
};

export function Badge({
  variant = "secondary",
  children,
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className,
      )}
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
