import { cn } from "../../lib/utils";

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  itemLabel?: string;
  className?: string;
}

const WINDOW_SIZE = 5;

function getVisiblePages(current: number, total: number): number[] {
  const half = Math.floor(WINDOW_SIZE / 2);
  let start = Math.max(1, current - half);
  let end = start + WINDOW_SIZE - 1;
  if (end > total) {
    end = total;
    start = Math.max(1, end - WINDOW_SIZE + 1);
  }
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  itemLabel = "registros",
  className,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const hasPrev = page > 1;
  const hasNext = page < totalPages;
  const visiblePages = getVisiblePages(page, totalPages);

  return (
    <div className={cn("border-t border-border pt-3", className)}>
      {/* Desktop */}
      <div className="hidden md:flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
        <span>
          {total === 0
            ? `Nenhum ${itemLabel}`
            : `Mostrando ${from} a ${to} de ${total} ${itemLabel}`}
        </span>

        <div className="flex items-center gap-1.5">
          <NavBtn onClick={() => onPageChange(page - 1)} disabled={!hasPrev}>
            Anterior
          </NavBtn>

          <div className="flex items-center gap-1">
            {visiblePages.map((p) => (
              <PageBtn key={p} active={p === page} onClick={() => onPageChange(p)}>
                {p}
              </PageBtn>
            ))}
          </div>

          <NavBtn onClick={() => onPageChange(page + 1)} disabled={!hasNext}>
            Próxima
          </NavBtn>
        </div>
      </div>

      {/* Mobile */}
      <div className="flex flex-col items-center gap-2 text-sm text-slate-500 dark:text-slate-400 md:hidden">
        <span>
          {total === 0
            ? `Nenhum ${itemLabel}`
            : `${from}–${to} de ${total} ${itemLabel}`}
        </span>
        <div className="flex items-center gap-2">
          <NavBtn onClick={() => onPageChange(page - 1)} disabled={!hasPrev}>‹</NavBtn>
          <PageBtn active>{page}</PageBtn>
          <NavBtn onClick={() => onPageChange(page + 1)} disabled={!hasNext}>›</NavBtn>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────

function NavBtn({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-lg border border-border bg-background-surface px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer",
        "text-slate-300 hover:bg-background-elevated hover:text-slate-100",
        "disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      {children}
    </button>
  );
}

function PageBtn({
  children,
  active,
  onClick,
}: {
  children?: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={active}
      className={cn(
        "min-w-9 h-8 rounded-lg px-2.5 text-sm font-medium transition-colors cursor-pointer",
        active
          ? "bg-primary text-white cursor-default"
          : "border border-border bg-background-surface text-slate-300 hover:bg-background-elevated hover:text-slate-100",
      )}
    >
      {children}
    </button>
  );
}
