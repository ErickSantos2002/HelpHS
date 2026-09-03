import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

/**
 * Campo de texto, de `DS/components/forms/Input.jsx`.
 *
 * ── Duas coisas que NÃO mudaram, e é deliberado ───────────────────────
 *
 * **A borda e o anel de erro seguem em `danger`, o degrau cheio.** Trocar por
 * `action-danger` é o movimento óbvio e **regride o tema escuro**: o
 * `--action-danger` só é declarado no `:root`, e o bloco `.dark` não o
 * redefine. Medido — 4,25:1 viraria 3,31:1. O `--color-danger-500` não inverte
 * e dá 3,76:1 no claro e 4,25:1 no escuro, acima do piso de 3:1 que vale para
 * indicador não textual (WCAG 1.4.11).
 *
 * **O `forwardRef` fica.** É melhoria local sobre a referência, que é função
 * simples — e o `TicketFilters` depende dele: `searchRef.current.value = ""`
 * é o que limpa a busca. Alinhar "para baixo" quebraria o botão de limpar
 * filtros em silêncio.
 *
 * ── E o hover da borda saiu, sem perda ────────────────────────────────
 *
 * Era `border-border hover:border-slate-500`: a borda saía de slate-200
 * (**1,23:1** contra a superfície) e só alcançava slate-500 (**4,76:1**) com o
 * mouse em cima. A emenda **E7** levou a borda de repouso a `--border-control`,
 * que é slate-500 — exatamente onde o hover chegava. O campo agora está
 * **sempre** na força que antes dependia do ponteiro, e o hover virou no-op.
 * O `Input.jsx` do pacote também não tem hover nenhum.
 *
 * **O foco é desvio com prazo.** O `ring` do Tailwind é `box-shadow` por fora;
 * o pacote desenha `outline` por dentro. Sai tela a tela nas Fases 11–16 e é
 * conferido no **Checkpoint 4** (`VERSION.md`, desvio F1).
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, className, id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-conteudo"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-conteudo",
            "placeholder:text-conteudo-muted",
            "focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-colors",
            error
              ? "border-danger focus:ring-danger"
              : "border-borda-control",
            className,
          )}
          {...props}
        />
        {error && <p className="text-xs text-on-tint-danger">{error}</p>}
        {hint && !error && <p className="text-xs text-conteudo-muted">{hint}</p>}
      </div>
    );
  },
);

Input.displayName = "Input";
