import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/utils";

// `success` é a quinta variante do pacote e está de fora de propósito: com o
// texto branco que o pacote manda, `--color-success-500` dá 2,54:1 e o hover
// 600 dá 3,77:1 — reprova a §21 nos dois temas. É a mesma classe de lacuna do
// pacote que a emenda E1 corrigiu no `--text-on-primary`, e entra quando a
// decisão for tomada. Hoje `success` não é usada em nenhum botão do HelpHS.
type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary = ação principal (uma por bloco). ghost = ação terciária. */
  variant?: Variant;
  size?: Size;
  /** Mostra o anel de carregando e desabilita o botão junto. */
  loading?: boolean;
  /** Ícone à esquerda do rótulo (16px, stroke 1.75). Cede o lugar ao anel enquanto carrega. */
  icon?: ReactNode;
  fullWidth?: boolean;
}

/**
 * Fundo, texto e borda saem dos tokens do pacote — nunca de cor cravada.
 * O primário usa `--text-on-primary`, que vale branco no tema claro e navy no
 * escuro: `text-white` fixo devolveria 2,69:1 sobre o `--action` do escuro.
 */
const variantClasses: Record<Variant, string> = {
  primary:
    "bg-action text-on-primary border-action hover:bg-action-hover focus-visible:ring-action",
  secondary:
    "bg-surface text-conteudo border-borda hover:bg-surface-elevated focus-visible:ring-action",
  danger:
    "bg-danger text-white border-danger hover:bg-danger-600 focus-visible:ring-danger",
  ghost:
    "bg-transparent text-conteudo-muted border-transparent hover:bg-surface-elevated focus-visible:ring-action",
};

const sizeClasses: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  fullWidth = false,
  className,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg border font-medium leading-tight transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variantClasses[variant],
        sizeClasses[size],
        fullWidth && "w-full",
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        // Decorativo: o rótulo do botão já diz o que está acontecendo, e um
        // aria-label aqui entraria no nome acessível do botão.
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 shrink-0 rounded-full border-2 border-current border-t-transparent animate-[hs-spin_0.7s_linear_infinite]"
        />
      ) : (
        icon
      )}
      {children}
    </button>
  );
}
