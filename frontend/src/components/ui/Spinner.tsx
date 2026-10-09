import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

type Size = "sm" | "md" | "lg";

/** Diâmetro e espessura do traço, de `DS/components/core/Spinner.jsx` (SIZES). */
const sizeClasses: Record<Size, string> = {
  sm: "w-4 h-4 border-2",
  md: "w-6 h-6 border-2",
  lg: "w-8 h-8 border-[3px]",
};

export interface SpinnerProps extends HTMLAttributes<HTMLSpanElement> {
  size?: Size;
}

export function Spinner({ size = "md", className, ...props }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Carregando..."
      className={cn(
        // `text-action`, não `text-primary`: o anel sai do degrau interativo,
        // que inverte no tema escuro. O degrau de marca (`--color-primary-500`)
        // é o mesmo nos dois temas e o próprio `colors.css` o marca como
        // "nunca texto".
        "inline-block rounded-full border-current border-t-transparent text-action",
        "animate-[hs-spin_0.7s_linear_infinite]",
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  );
}
