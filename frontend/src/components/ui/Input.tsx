import { forwardRef, useId } from "react";
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
 * **O foco é desvio com prazo.** O `ring` do Tailwind é `box-shadow` por fora;
 * o pacote desenha `outline` por dentro. Sai tela a tela nas Fases 11–16 e é
 * conferido no **Checkpoint 4** (`VERSION.md`, desvio F1).
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
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
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={descrito}
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

Input.displayName = "Input";
