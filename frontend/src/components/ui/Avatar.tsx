import { cn } from "../../lib/utils";

type Size = "xs" | "sm" | "md" | "lg";

const sizeClasses: Record<Size, string> = {
  xs: "w-6 h-6 text-xs",
  sm: "w-8 h-8 text-xs",
  md: "w-10 h-10 text-sm",
  lg: "w-12 h-12 text-base",
};

function getInitials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0].toUpperCase())
    .join("");
}

// Deterministic color based on name
const COLORS = [
  "bg-primary/30 text-primary",
  "bg-info/30 text-info-400",
  "bg-warning/30 text-warning-400",
  "bg-danger/30 text-danger-400",
  "bg-purple-500/30 text-purple-400",
  "bg-pink-500/30 text-pink-400",
];

function colorFromName(name: string): string {
  const sum = name.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return COLORS[sum % COLORS.length];
}

export interface AvatarProps {
  name: string;
  src?: string;
  size?: Size;
  className?: string;
}

export function Avatar({ name, src, size = "md", className }: AvatarProps) {
  if (src) {
    return (
      <img
        src={src}
        alt={name}
        className={cn(
          "rounded-full object-cover",
          sizeClasses[size],
          className,
        )}
      />
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full font-medium select-none",
        sizeClasses[size],
        colorFromName(name),
        className,
      )}
      title={name}
    >
      {getInitials(name)}
    </span>
  );
}
