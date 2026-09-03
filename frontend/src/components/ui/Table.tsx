import type { ReactNode } from "react";
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
      className={cn("border-b border-borda text-xs text-conteudo-muted", className)}
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
  children?: ReactNode;
  className?: string;
}) {
  return (
    <tbody className={cn("divide-y divide-borda", className)}>
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
  // Linha clicavel precisava de mouse: `<tr onClick>` nao entra na ordem de
  // tabulacao e nao responde a tecla. `tabIndex` e o `onKeyDown` a tornam
  // alcancavel sem trocar o papel de linha — pôr `role="button"` num `<tr>`
  // quebraria a semantica da tabela, que e o que faz um leitor de tela
  // anunciar "linha 3 de 40".
  //
  // O desenho plenamente correto poe um elemento acionavel DENTRO da linha
  // (o link do registro na primeira celula). Isso muda a marcacao das telas
  // e entra nas Fases 11-16, tela a tela.
  return (
    <tr
      onClick={onClick}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={cn(
        "transition-colors",
        clickable &&
          "cursor-pointer hover:bg-surface-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-action",
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
      // `aria-sort` no `<th>` e o que anuncia a ordem: sem ele, a seta e
      // decoracao que so quem enxerga entende.
      aria-sort={
        !sortable
          ? undefined
          : sorted === "asc"
            ? "ascending"
            : sorted === "desc"
              ? "descending"
              : "none"
      }
      className={cn("px-4 py-3 font-medium uppercase tracking-wider", className)}
    >
      {sortable ? (
        // Botao de verdade, e nao um `<th onClick>`: ordenar era acao so de
        // mouse — fora da ordem de tabulacao e sem tecla.
        <button
          type="button"
          onClick={onSort}
          className="inline-flex cursor-pointer select-none items-center gap-1 uppercase tracking-wider hover:text-conteudo-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
        >
          {children}
          <span aria-hidden="true" className="text-conteudo-muted">
            {sorted === "asc" ? "↑" : sorted === "desc" ? "↓" : "↕"}
          </span>
        </button>
      ) : (
        <span className="inline-flex items-center gap-1">{children}</span>
      )}
    </th>
  );
}

// ── TableCell ─────────────────────────────────────────────────

export interface TableCellProps {
  children?: ReactNode;
  className?: string;
  muted?: boolean;
  onClick?: (e: React.MouseEvent<HTMLTableCellElement>) => void;
}

export function TableCell({
  children,
  className,
  muted,
  onClick,
}: TableCellProps) {
  return (
    <td
      onClick={onClick}
      className={cn(
        "px-4 py-3",
        muted ? "text-conteudo-muted" : "text-conteudo",
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
        className="px-4 py-12 text-center text-sm text-conteudo-muted"
      >
        {message}
      </td>
    </tr>
  );
}
