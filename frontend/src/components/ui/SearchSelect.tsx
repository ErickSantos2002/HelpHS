import { Selector } from "./Selector";

export interface SearchSelectOption {
  value: string;
  label: string;
  /** Linha secundária — e-mail, empresa, o que ajude a desambiguar homônimos. */
  hint?: string;
}

export interface SearchSelectProps {
  value: string | null;
  /** Rótulo do valor atual. Evita uma busca só para mostrar o que já se sabe. */
  selectedLabel?: string | null;
  onChange: (value: string | null, label: string | null) => void;
  onSearch: (term: string) => Promise<SearchSelectOption[]>;
  label?: string;
  placeholder?: string;
  /** Texto da opção que desfaz a escolha. */
  emptyLabel?: string;
  disabled?: boolean;
  error?: string;
  className?: string;
  debounceMs?: number;
}

/**
 * @deprecated Invólucro fino sobre o {@link Selector} com `searchable`.
 *
 * Mantido com as props de hoje para que a chamada do `ProductsPage` não mude
 * na Fase 8.
 *
 * **Este é o único dos três que adapta de verdade, e não só repassa.** O
 * `Selector` emite `(value, option)` — a opção inteira — e este invólucro
 * devolve `(value, label)`, que é a assinatura de duas aridades que a tela
 * espera. Era a única divergência dos três que um repasse não resolvia.
 *
 * O `placeholder` daqui é o texto do **campo de busca**, não o do gatilho: no
 * componente original ele ia para o `input`, e quem rotula o gatilho vazio é o
 * `emptyLabel`. O `Selector` mantém a distinção com dois nomes.
 */
export function SearchSelect({
  value,
  selectedLabel,
  onChange,
  onSearch,
  label,
  placeholder = "Buscar…",
  emptyLabel = "— Nenhum —",
  disabled,
  error,
  className,
  debounceMs = 300,
}: SearchSelectProps) {
  return (
    <Selector
      variant="form"
      searchable
      value={value}
      selectedLabel={selectedLabel}
      onSearch={onSearch}
      label={label}
      searchPlaceholder={placeholder}
      emptyLabel={emptyLabel}
      // O texto de hoje nomeia o domínio, e o `Selector` não pode saber que a
      // lista é de clientes. Fica aqui para o contrato não mudar.
      emptyResultsLabel="Nenhum cliente encontrado."
      disabled={disabled}
      error={error}
      className={className}
      debounceMs={debounceMs}
      onChange={(v, opcao) => onChange(v, opcao?.label ?? null)}
    />
  );
}
