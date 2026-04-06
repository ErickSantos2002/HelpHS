import { ReactNode } from "react";
import { cn } from "../../lib/utils";

// ── Table ─────────────────────────────────────────────────────

export interface TableProps {
  children: ReactNode;
  className?: string;
}

export function Table({ children, className }: TableProps) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full text-sm text-left", className)}>
        {children}
      </table>
    </div>
  );
}

// ── TableHead ─────────────────────────────────────────────────

export function TableHead({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <thead
      className={cn("border-b border-border text-xs text-slate-400", className)}
    >
      {children}
    </thead>
  );
}

// ── TableBody ─────────────────────────────────────────────────

export function TableBody({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <tbody className={cn("divide-y divide-border", className)}>
      {children}
    </tbody>
  );
}

// ── TableRow ──────────────────────────────────────────────────

export interface TableRowProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  clickable?: boolean;
}

export function TableRow({
  children,
  className,
  onClick,
  clickable,
}: TableRowProps) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        "transition-colors",
        clickable && "cursor-pointer hover:bg-background-elevated",
        className,
      )}
    >
      {children}
    </tr>
  );
}

// ── TableHeaderCell ───────────────────────────────────────────

export interface TableHeaderCellProps {
  children?: ReactNode;
  className?: string;
  sortable?: boolean;
  sorted?: "asc" | "desc" | null;
  onSort?: () => void;
}

export function TableHeaderCell({
  children,
  className,
  sortable,
  sorted,
  onSort,
}: TableHeaderCellProps) {
  return (
    <th
      className={cn(
        "px-4 py-3 font-medium uppercase tracking-wider",
        sortable && "cursor-pointer select-none hover:text-slate-200",
        className,
      )}
      onClick={sortable ? onSort : undefined}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {sortable && (
          <span className="text-slate-600">
            {sorted === "asc" ? "↑" : sorted === "desc" ? "↓" : "↕"}
          </span>
        )}
      </span>
    </th>
  );
}

// ── TableCell ─────────────────────────────────────────────────

export interface TableCellProps {
  children?: ReactNode;
  className?: string;
  muted?: boolean;
}

export function TableCell({ children, className, muted }: TableCellProps) {
  return (
    <td
      className={cn(
        "px-4 py-3",
        muted ? "text-slate-500" : "text-slate-200",
        className,
      )}
    >
      {children}
    </td>
  );
}

// ── TableEmpty ────────────────────────────────────────────────

export function TableEmpty({
  colSpan,
  message = "Nenhum resultado encontrado.",
}: {
  colSpan: number;
  message?: string;
}) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className="px-4 py-12 text-center text-sm text-slate-500"
      >
        {message}
      </td>
    </tr>
  );
}
