import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
}

/**
 * Área de texto, de `DS/components/forms/Textarea.jsx`.
 *
 * Segue o `Input` linha a linha, pelas mesmas razões — inclusive as duas
 * **não-mudanças**: a borda de erro fica no degrau cheio `danger` (trocar por
 * `action-danger` regride o escuro de 4,25:1 para 3,31:1, porque o token só
 * existe no `:root`), e o `forwardRef` fica.
 *
 * O hover da borda saiu pelo mesmo motivo: a **E7** levou a borda de repouso a
 * `--border-control`, que é slate-500 — exatamente onde o `hover:border-slate-500`
 * chegava. O campo está sempre na força que antes dependia do ponteiro.
 *
 * **Uma diferença de forma que fica como está.** O pacote desenha o foco com a
 * borda pintada de `--action` mais um `outline` de 2px com `outlineOffset: -1`,
 * ou seja, indicador **por dentro** da caixa. Aqui é `ring` do Tailwind, que é
 * `box-shadow` por **fora**. Alinhar mudaria a geometria do foco em 18 usos sem
 * ganho de contraste — o anel de fora já dá 5,29:1 contra a superfície.
 */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
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
        <textarea
          ref={ref}
          id={inputId}
          rows={4}
          className={cn(
            "w-full rounded-lg border bg-surface px-3 py-2 text-sm text-conteudo",
            "placeholder:text-conteudo-muted resize-y min-h-[80px]",
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

Textarea.displayName = "Textarea";
