import { forwardRef, useId } from "react";
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
 * ── O erro precisava chegar a quem não o vê ───────────────────────────
 *
 * O erro e a dica eram `<p>` soltos ao lado do campo. Visualmente ficam
 * juntos; para um leitor de tela **não existe relação nenhuma** entre eles e
 * o `input`. A pessoa ouvia o nome do campo, digitava, e nunca ouvia por que
 * o formulário recusou.
 *
 * `aria-describedby` cria a relação, e `aria-invalid` marca o campo como
 * recusado. `aria-required` NÃO entra: o atributo `required` nativo já diz
 * isso, e chega aqui pelo espalhamento das props — repetir seria declarar
 * duas vezes a mesma coisa.
 *
 * O `id` também mudou. Ele saía do rótulo (`label.toLowerCase()`), então
 * dois campos com o mesmo rótulo na mesma tela geravam o **mesmo id** — e
 * sem rótulo ficava `undefined`, quebrando o `htmlFor`. Agora vem do
 * `useId`, e o `id` passado por quem chama continua ganhando.
 *
 * O hover da borda saiu pelo mesmo motivo: a **E7** levou a borda de repouso a
 * `--border-control`, que é slate-500 — exatamente onde o `hover:border-slate-500`
 * chegava. O campo está sempre na força que antes dependia do ponteiro.
 *
 * **Uma diferença de forma que EXPIRA no Checkpoint 4.** O pacote desenha o foco
 * com a borda pintada de `--action` mais um `outline` de 2px com
 * `outlineOffset: -1` — indicador por **dentro** da caixa. Aqui é `ring` do
 * Tailwind, que é `box-shadow` por **fora**.
 *
 * Não é exceção, é **dívida com prazo** (`VERSION.md`, desvio F1): cada uma das
 * sete telas que usam este componente alinha ao `outline` interno **quando for
 * migrada** nas Fases 11–16, junto da captura antes e depois. Não foi alinhado
 * agora porque mudaria a geometria do foco em todas de uma vez, numa fase de
 * componente, sem ganho de contraste — o anel de fora já dá 5,29:1 e o piso da
 * 1.4.11 é 3:1.
 */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, hint, className, id, ...props }, ref) => {
    const gerado = useId();
    const inputId = id ?? gerado;
    const idErro = inputId + "-erro";
    const idDica = inputId + "-dica";
    const descrito = error ? idErro : hint ? idDica : undefined;

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
          aria-invalid={error ? true : undefined}
          aria-describedby={descrito}
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
        {error && (
          <p id={idErro} className="text-xs text-on-tint-danger">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={idDica} className="text-xs text-conteudo-muted">
            {hint}
          </p>
        )}
      </div>
    );
  },
);

Textarea.displayName = "Textarea";
