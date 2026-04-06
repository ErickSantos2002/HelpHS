import { cn } from "../../lib/utils";

type Size = "sm" | "md" | "lg";

const sizeClasses: Record<Size, string> = {
  sm: "w-4 h-4 border-2",
  md: "w-6 h-6 border-2",
  lg: "w-8 h-8 border-[3px]",
};

interface SpinnerProps {
  size?: Size;
  className?: string;
}

export function Spinner({ size = "md", className }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Carregando..."
      className={cn(
        "inline-block rounded-full border-current border-t-transparent animate-spin text-primary",
        sizeClasses[size],
        className,
      )}
    />
  );
}
