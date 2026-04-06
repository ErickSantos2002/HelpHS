import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, hint, className, id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-slate-300"
          >
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={inputId}
          rows={4}
          className={cn(
            "w-full rounded-lg border bg-background-surface px-3 py-2 text-sm text-slate-100",
            "placeholder:text-slate-500 resize-y min-h-[80px]",
            "focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-colors",
            error
              ? "border-danger focus:ring-danger"
              : "border-border hover:border-slate-500",
            className,
          )}
          {...props}
        />
        {error && <p className="text-xs text-danger">{error}</p>}
        {hint && !error && <p className="text-xs text-slate-500">{hint}</p>}
      </div>
    );
  },
);

Textarea.displayName = "Textarea";
