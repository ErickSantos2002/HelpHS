import { cn } from "../../lib/utils";

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  className,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  const pages = buildPageList(page, totalPages);

  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 text-sm",
        className,
      )}
    >
      {/* Count */}
      <p className="text-slate-500 shrink-0">
        {total === 0 ? "Nenhum resultado" : `${from}–${to} de ${total}`}
      </p>

      {/* Page buttons */}
      <div className="flex items-center gap-1">
        <PageButton
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Página anterior"
        >
          ‹
        </PageButton>

        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`ellipsis-${i}`} className="px-2 text-slate-500">
              …
            </span>
          ) : (
            <PageButton
              key={p}
              onClick={() => onPageChange(p as number)}
              active={p === page}
            >
              {p}
            </PageButton>
          ),
        )}

        <PageButton
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Próxima página"
        >
          ›
        </PageButton>
      </div>
    </div>
  );
}

// ── PageButton ────────────────────────────────────────────────

interface PageButtonProps {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  "aria-label"?: string;
}

function PageButton({
  children,
  onClick,
  disabled,
  active,
  "aria-label": ariaLabel,
}: PageButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={cn(
        "min-w-[2rem] h-8 px-2 rounded-md text-sm font-medium transition-colors",
        "disabled:opacity-40 disabled:cursor-not-allowed",
        active
          ? "bg-primary text-white"
          : "text-slate-400 hover:bg-background-elevated hover:text-slate-200",
      )}
    >
      {children}
    </button>
  );
}

// ── buildPageList ─────────────────────────────────────────────
// Returns page numbers + "..." ellipsis markers

function buildPageList(current: number, total: number): (number | "...")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | "...")[] = [1];

  if (current > 3) pages.push("...");

  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) pages.push(i);

  if (current < total - 2) pages.push("...");

  pages.push(total);
  return pages;
}
