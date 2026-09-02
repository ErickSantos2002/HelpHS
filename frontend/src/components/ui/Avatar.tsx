import type { HTMLAttributes, ImgHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

type Size = "xs" | "sm" | "md" | "lg";

/** 24 / 32 / 40 / 48px, de `DS/components/core/Avatar.jsx` (SIZES e FONT). */
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

/**
 * Os seis pares de `Avatar.jsx` (COLORS): fundo no degrau claro da rampa e
 * texto no 700, mais o par neutro de superfície.
 *
 * Os pares translúcidos de antes (`bg-primary/30 text-primary`) reprovavam AA
 * nos dois temas — 6 de 6 no claro, 5 de 6 no escuro, o pior deles em 1,33:1.
 * Estes passam em 6 de 6 nos dois temas. O neutro era o único que faltava,
 * em 4,34:1 no claro; a emenda E4 do pacote troca `--text-muted` por
 * `--on-tint-neutral` no sexto par e leva os mesmos pixels a 6,92:1, sem
 * mexer no fundo. No escuro nada muda: lá `--on-tint-neutral` é o próprio
 * `--text-muted`, e os 5,29:1 seguem iguais.
 *
 * Dois dos pares antigos vinham de `purple` e `pink`, da paleta padrão do
 * Tailwind: não existe `--color-purple-*` nem `--color-pink-*` no pacote.
 */
const COLORS = [
  "bg-primary-100 text-primary-700",
  "bg-info-50 text-info-700",
  "bg-warning-50 text-warning-700",
  "bg-danger-50 text-danger-700",
  "bg-success-50 text-success-700",
  "bg-surface-elevated text-on-tint-neutral",
];

function colorFromName(name: string): string {
  const sum = name.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return COLORS[sum % COLORS.length];
}

export interface AvatarProps
  extends Omit<HTMLAttributes<HTMLElement>, "children"> {
  name: string;
  src?: string;
  size?: Size;
}

export function Avatar({
  name,
  src,
  size = "md",
  className,
  ...props
}: AvatarProps) {
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
        {...(props as ImgHTMLAttributes<HTMLImageElement>)}
      />
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full font-semibold select-none",
        sizeClasses[size],
        colorFromName(name),
        className,
      )}
      title={name}
      {...props}
    >
      {getInitials(name)}
    </span>
  );
}
