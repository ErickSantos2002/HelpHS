import { Selector } from "./Selector";
import type { SelectorOption } from "./Selector";

export interface FormDropdownOption {
  value: string;
  label: string;
  dot?: string;
}

export interface FormDropdownProps {
  value: string;
  onChange: (value: string) => void;
  options: FormDropdownOption[];
  placeholder?: string;
  disabled?: boolean;
  label?: string;
  error?: string;
  className?: string;
}

/**
 * @deprecated Invólucro fino sobre o {@link Selector} com `variant="form"`.
 *
 * Mantido com as props de hoje para que as duas chamadas não mudem na Fase 8.
 *
 * Três props deste invólucro **nunca foram passadas** por nenhuma chamada —
 * `disabled`, `error` e `className`. Ficam aqui porque o contrato é o de hoje,
 * não o que se usa de hoje; quem migrar a tela decide se as quer.
 */
export function FormDropdown({
  value,
  onChange,
  options,
  placeholder = "Selecione…",
  disabled,
  label,
  error,
  className,
}: FormDropdownProps) {
  return (
    <Selector
      variant="form"
      value={value}
      options={options as SelectorOption[]}
      placeholder={placeholder}
      disabled={disabled}
      label={label}
      error={error}
      className={className}
      onChange={(v) => onChange(v ?? "")}
    />
  );
}
