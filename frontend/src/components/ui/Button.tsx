import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/utils";

// As cinco variantes do pacote. `success` entrou com a emenda E2, que criou o
// degrau de ação que faltava: enquanto o pacote mandava pintá-la com
// `--color-success-500`, o texto branco dava 2,54:1 e o hover 600 dava 3,77:1.
type Variant = "primary" | "secondary" | "danger" | "success" | "ghost";
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
 *
 * As três variantes preenchidas usam o par `--action-*` / `--text-on-*`, e não
 * a cor cheia da rampa com branco por cima. O primário usa `--text-on-primary`,
 * que vale branco no claro e navy no escuro (`text-white` fixo daria 2,69:1
 * sobre o `--action` do escuro); `danger` e `success` usam `--text-on-danger` e
 * `--text-on-success`, que valem branco nos dois temas porque o fundo delas é
 * degrau absoluto da rampa e não inverte.
 */
const variantClasses: Record<Variant, string> = {
  primary:
    "bg-action text-on-primary border-action hover:bg-action-hover focus-visible:ring-action",
  secondary:
    "bg-surface text-conteudo border-borda hover:bg-surface-elevated focus-visible:ring-action",
  danger:
    "bg-action-danger text-on-danger border-action-danger hover:bg-action-danger-hover focus-visible:ring-danger",
  success:
    "bg-action-success text-on-success border-action-success hover:bg-action-success-hover focus-visible:ring-success",
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
