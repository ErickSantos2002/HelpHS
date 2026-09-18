import { forwardRef, useId } from "react";
import type { SelectHTMLAttributes } from "react";
import { cn } from "../../lib/utils";
import { Icon } from "./Icon";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  hint?: string;
  options: SelectOption[];
  placeholder?: string;
}

/**
 * Seletor nativo, de `DS/components/forms/Select.jsx`.
 *
 * ── O `id` deixou de sair do rótulo (E11) ─────────────────────────────
 *
 * Ele era `label.toLowerCase()`. **Dois seletores com o mesmo rótulo na mesma
 * tela geravam o mesmo `id`** — e aí o `<label htmlFor>` do segundo apontava
 * para o campo do PRIMEIRO: clicar no rótulo de baixo focava o de cima, e o
 * leitor de tela lia o nome errado. HTML com `id` repetido não é erro, então
 * nada acusava — nem `tsc`, nem `eslint`, nem teste de componente.
 *
 * E sem rótulo o `id` ficava `undefined`, que é o `htmlFor` quebrado do outro
 * lado — o caso dos cinco filtros do `TicketFilters`, que só têm placeholder.
 *
 * Agora vem do `useId`, como no `Input`: um por instância, estável entre
 * renderizações e igual no servidor e no cliente. **O `id` passado por quem
 * chama continua ganhando** — as quatorze telas que passaram a filtrar por
 * este primitivo depois da D9.2 mandam o seu (`filtro-periodo`,
 * `filtro-status`, `kb-categoria`…), e elas não mudam.
 *
 * ── E o erro também não chegava a quem não o vê (E11) ─────────────────
 *
 * O erro e a dica eram `<p>` soltos ao lado do campo. Visualmente ficam
 * juntos; na árvore de acessibilidade **não havia relação nenhuma** entre eles
 * e o `select`. A pessoa ouvia o nome do campo, escolhia, o formulário
 * recusava — e ela nunca ouvia por quê.
 *
 * `aria-describedby` cria a relação, e `aria-invalid` marca o campo como
 * recusado. **Aponta para o erro OU para a dica, nunca para os dois**: quando
 * há erro a dica nem é renderizada, e apontar para ela seria apontar para um
 * `id` que não existe. É o mesmo desenho do `Input`.
 *
 * `aria-required` NÃO entra: o `required` nativo chega aqui pelo espalhamento
 * das props e já informa a árvore de acessibilidade — repetir declararia duas
 * vezes a mesma coisa, e as duas podem divergir.
 *
 * O `Select` era o consumidor que ficou para trás: o contrato da E11 já
 * existia e a tabela de `campos-aria.test.tsx` cobria `Input`, `Textarea` e
 * `Selector` — só este primitivo nunca entrou nela. Tabela de contrato que não
 * cobre todos os implementadores dá a impressão de contrato e não é.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    { label, error, hint, options, placeholder, className, id, ...props },
    ref,
  ) => {
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
        {/* O `relative` existe por causa da seta: ela era um data URI com
            `stroke='%2394a3b8'` cravado — slate-400 — e data URI **não aceita
            `var()`**, então a seta nunca seguiu o tema. Sobre o campo branco
            isso dava **2,56:1**, abaixo do piso de 3:1 que a WCAG 1.4.11 pede
            para gráfico. O `Select.jsx` do pacote tem exatamente o mesmo data
            URI, com o mesmo hexadecimal.

            Trocada pelo primitivo `Icon`, que herda `currentColor`: a seta passa
            a valer `--text-muted` e a seguir o tema — 7,58:1 no claro e 6,23:1
            no escuro. */}
        <div className="relative">
        <select
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={descrito}
          className={cn(
            "w-full rounded-lg border bg-surface px-3 py-2 pr-9 text-sm text-conteudo",
            "focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-colors appearance-none cursor-pointer",
            error
              ? "border-danger focus:ring-danger"
              : "border-borda-control",
            className,
          )}
          {...props}
        >
          {placeholder && (
            <option value="" className="bg-surface text-conteudo-muted">
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option
              key={opt.value}
              value={opt.value}
              className="bg-surface text-conteudo"
            >
              {opt.label}
            </option>
          ))}
        </select>
        <Icon
          name="chevronDown"
          size={16}
          strokeWidth={2}
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-conteudo-muted"
        />
        </div>
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

Select.displayName = "Select";
