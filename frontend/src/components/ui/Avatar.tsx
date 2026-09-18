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
 * Estes passam em 6 de 6 nos dois temas. O neutro era o único que faltava, em
 * 4,34:1 no claro — e o conserto veio na **origem**, não aqui: a emenda **E5**
 * levou `--text-muted` de `slate-500` a `slate-600`, e o par foi a **6,92:1**
 * sem que este arquivo mudasse de token.
 *
 * Chegou a existir uma **E4** que trocaria o par por `--on-tint-neutral`. Ela
 * está registrada no `EMENDAS.md` como **não aplicada**: depois da E5 os dois
 * resolvem para o mesmo `#475569`, e adotá-la seria trocar um token pelo seu
 * próprio alias — zero pixel, um desvio a manter. O par consome o que o pacote
 * consome.
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
  "bg-surface-elevated text-conteudo-muted",
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
