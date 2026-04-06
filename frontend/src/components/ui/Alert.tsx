import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

type AlertVariant = "info" | "success" | "warning" | "danger";

const variantClasses: Record<AlertVariant, string> = {
  info: "bg-info/10 border-info/30 text-info-400",
  success: "bg-primary/10 border-primary/30 text-primary",
  warning: "bg-warning/10 border-warning/30 text-warning-400",
  danger: "bg-danger/10 border-danger/30 text-danger-400",
};

const icons: Record<AlertVariant, ReactNode> = {
  info: (
    <svg
      className="w-5 h-5 shrink-0"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20A10 10 0 0012 2z"
      />
    </svg>
  ),
  success: (
    <svg
      className="w-5 h-5 shrink-0"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
  warning: (
    <svg
      className="w-5 h-5 shrink-0"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
      />
    </svg>
  ),
  danger: (
    <svg
      className="w-5 h-5 shrink-0"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
};

export interface AlertProps {
  variant?: AlertVariant;
  title?: string;
  children: ReactNode;
  className?: string;
  onDismiss?: () => void;
}

export function Alert({
  variant = "info",
  title,
  children,
  className,
  onDismiss,
}: AlertProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex gap-3 rounded-lg border p-4 text-sm",
        variantClasses[variant],
        className,
      )}
    >
      {icons[variant]}
      <div className="flex-1 min-w-0">
        {title && <p className="font-medium mb-0.5">{title}</p>}
        <div className="text-current/80">{children}</div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="shrink-0 rounded p-0.5 hover:bg-white/10 transition-colors"
          aria-label="Fechar"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      )}
    </div>
  );
}
