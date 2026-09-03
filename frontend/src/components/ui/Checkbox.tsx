import type { InputHTMLAttributes, ReactNode } from "react";
import { useEffect, useId, useRef } from "react";
import { cn } from "../../lib/utils";

/**
 * Caixa de seleção, de `DS/components/forms/Checkbox.jsx`.
 *
 * **Vale depois do Salvar**, e aceita várias por grupo — é o que a separa do
 * `Switch`, cujo efeito é imediato.
 *
 * Extraída de três usos inline: o aceite de LGPD do registro
 * (`RegisterPage.tsx`), o "todos os produtos" do formulário da base de
 * conhecimento (`KBFormPage.tsx`) e o "disponível no chat" das respostas
 * rápidas (`QuickRepliesPage.tsx`). Os três pintavam `accent-primary`, que é o
 * degrau de **marca** e não o de **ação** — o pacote é explícito sobre isso:
 * foco e item ativo saem de `--action`, nunca de `--color-primary-500`.
 *
 * ── Duas coisas que a extração conserta ────────────────────────────────
 *
 * 1. **`accent-primary` não é estilizável nem tokenizável.** O `accent-color`
 *    nativo aceita uma cor e nada mais: não há contorno, não há estado
 *    indeterminado desenhável, e o visto é o do sistema operacional. Trocando
 *    por caixa própria, o contorno vazio ganha `--border-control` (emenda E7) e
 *    o visto ganha um token que inverte por tema.
 * 2. **Indeterminado era só desenho.** O `Checkbox.jsx` do pacote pinta o traço
 *    e **não** marca a propriedade `indeterminate` do input — quem usa leitor de
 *    tela ouve "não marcado", que é a informação errada. Aqui a propriedade do
 *    DOM é marcada e o estado vira `mixed` na árvore de acessibilidade.
 *
 * ── Um desvio que durou uma tarde ─────────────────────────────────────
 *
 * O `Checkbox.jsx` pinta o visto e o traço com `--color-white` cravado. Sobre o
 * `--action` do tema escuro isso dá **2,69:1**, abaixo do piso de **3:1** que a
 * WCAG 1.4.11 pede para limite gráfico. Aqui os dois usam
 * `--text-on-primary`: 5,29:1 no claro e **5,11:1** no escuro.
 *
 * A emenda **E7** corrigiu a bolinha do `Switch` e não alcançou estes dois,
 * porque o escopo dela nomeou o interruptor; a **E7-b** os corrigiu na origem no
 * mesmo dia, e com ela a família fechou em **seis** — E1, link de pular, `ghost`
 * do `Button`, botão de sair do `Topbar`, bolinha do `Switch`, e estes. Está
 * exaurida, e isso foi conferido: não há mais nenhum `--color-white` em
 * `components/forms/`. Este arquivo e a referência voltaram a dizer o mesmo.
 */
export interface CheckboxProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "onChange" | "type" | "checked"
  > {
  checked: boolean;
  /** Traço no lugar do visto — grupo parcialmente marcado. */
  indeterminate?: boolean;
  /** Recebe o valor novo, não o evento — como o `.d.ts` do pacote define. */
  onChange: (checked: boolean) => void;
  /** Conteúdo à direita. É o nome acessível do controle. */
  label?: ReactNode;
  /** Segunda linha, menor, explicando a consequência de marcar. */
  hint?: ReactNode;
  disabled?: boolean;
}

export function Checkbox({
  checked,
  indeterminate = false,
  onChange,
  label,
  hint,
  disabled = false,
  className,
  id,
  ...props
}: CheckboxProps) {
  const gerado = useId();
  const inputId = id ?? gerado;
  const ref = useRef<HTMLInputElement>(null);

  // A propriedade `indeterminate` não existe como atributo HTML: só se marca
  // pelo DOM. Sem isto o traço apareceria e o estado anunciado seria "não
  // marcado" — desenho certo, informação errada.
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <label
      htmlFor={inputId}
      className={cn(
        "inline-flex items-start gap-2 text-sm leading-4 text-conteudo",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        className,
      )}
    >
      <input
        ref={ref}
        id={inputId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-checked={indeterminate ? "mixed" : checked}
        onChange={(e) => onChange(e.target.checked)}
        className="peer absolute h-px w-px opacity-0"
        {...props}
      />

      <span
        aria-hidden="true"
        className={cn(
          "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border transition-colors",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-action peer-focus-visible:ring-offset-2",
          checked || indeterminate
            ? "border-action bg-action"
            : "border-borda-control bg-surface",
        )}
      >
        {indeterminate ? (
          // O traço do estado misto. `--text-on-primary` e não branco: sobre o
          // `--action` do escuro o branco cai a 2,69:1.
          <span className="h-0.5 w-2 rounded-sm bg-on-primary" />
        ) : checked ? (
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-on-primary"
          >
            <path d="M5 13l4 4L19 7" />
          </svg>
        ) : null}
      </span>

      {label ? (
        <span>
          {label}
          {hint ? (
            <span className="mt-0.5 block text-xs text-conteudo-muted">{hint}</span>
          ) : null}
        </span>
      ) : null}
    </label>
  );
}
