import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/utils";

export interface FormDropdownOption {
  value: string;
  label: string;
  dot?: string;
}

export interface FormDropdownProps {
  value: string;
  onChange: (value: string) => void;
  options: FormDropdownOption[];
  placeholder?: string;
  disabled?: boolean;
  label?: string;
  error?: string;
  className?: string;
}

const ChevronDown = (
  <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
  </svg>
);

const CheckIcon = (
  <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
);

export function FormDropdown({
  value, onChange, options, placeholder = "Selecione…",
  disabled, label, error, className,
}: FormDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  function choose(val: string) {
    onChange(val);
    setOpen(false);
  }

  return (
    <div ref={ref} className={cn("relative flex flex-col gap-1.5", className)}>
      {label && (
        <label className="text-sm font-medium text-slate-300">{label}</label>
      )}

      {/* Trigger */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-all select-none",
          "bg-background-elevated focus:outline-none",
          disabled
            ? "opacity-40 cursor-not-allowed"
            : "cursor-pointer hover:border-border",
          open
            ? "border-primary ring-2 ring-primary/20 text-slate-100"
            : error
              ? "border-danger text-slate-300"
              : "border-border/60 text-slate-300",
          !selected && "text-slate-500",
        )}
      >
        <span className="flex items-center gap-2 min-w-0">
          {selected?.dot && (
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: selected.dot }} />
          )}
          <span className="truncate">{selected?.label ?? placeholder}</span>
        </span>
        <span className={cn("ml-2 text-slate-400 transition-transform duration-150", open && "rotate-180")}>
          {ChevronDown}
        </span>
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-full rounded-xl border border-border/60 bg-background-surface shadow-xl shadow-black/20 overflow-hidden">
          {/* Placeholder row */}
          <button
            type="button"
            onClick={() => choose("")}
            className={cn(
              "flex w-full items-center gap-2.5 px-3 py-2.5 text-sm transition-colors cursor-pointer",
              !value
                ? "bg-primary/10 text-primary font-semibold"
                : "text-slate-400 hover:bg-background-elevated hover:text-slate-200",
            )}
          >
            <span className="w-2 h-2 rounded-full shrink-0 border border-slate-600 bg-transparent" />
            <span className="flex-1 text-left">{placeholder}</span>
            {!value && <span className="text-primary">{CheckIcon}</span>}
          </button>

          <div className="h-px bg-border/40 mx-2" />

          {/* Options */}
          <div className="max-h-60 overflow-y-auto">
            {options.map((opt) => {
              const active = value === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => choose(opt.value)}
                  className={cn(
                    "flex w-full items-center gap-2.5 px-3 py-2.5 text-sm transition-colors cursor-pointer",
                    active
                      ? "bg-primary/10 text-primary font-semibold"
                      : "text-slate-300 hover:bg-background-elevated hover:text-slate-100",
                  )}
                >
                  {opt.dot ? (
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: opt.dot }} />
                  ) : (
                    <span className="w-2 h-2 rounded-full shrink-0 bg-transparent" />
                  )}
                  <span className="flex-1 text-left">{opt.label}</span>
                  {active && <span className="text-primary">{CheckIcon}</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
