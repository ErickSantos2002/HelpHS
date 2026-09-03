import { Selector } from "./Selector";
import type { SelectorOption } from "./Selector";

export interface FilterSelectOption {
  value: string;
  label: string;
  dot?: string;
}

export interface FilterSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: FilterSelectOption[];
  placeholder?: string;
  className?: string;
}

/**
 * @deprecated Invólucro fino sobre o {@link Selector} com `variant="filter"`.
 *
 * Mantido com as props de hoje para que **nenhuma das 17 chamadas mude** na
 * Fase 8. As telas migram uma a uma nas Fases 11–16, e o nome sai quando a
 * última sair.
 *
 * A única adaptação é a assinatura: o `Selector` emite
 * `(value: string | null, option)` e este invólucro devolve `string`, com
 * `null` virando `""` — que é como o filtro sempre representou "nada
 * escolhido".
 */
export function FilterSelect({
  value,
  onChange,
  options,
  placeholder = "Todos",
  className,
}: FilterSelectProps) {
  return (
    <Selector
      variant="filter"
      value={value}
      options={options as SelectorOption[]}
      placeholder={placeholder}
      className={className}
      onChange={(v) => onChange(v ?? "")}
    />
  );
}
