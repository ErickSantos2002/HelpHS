import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/utils";

/**
 * Seletor com busca no servidor, para listas que não cabem num dropdown.
 *
 * O `FormDropdown` recebe todas as opções prontas, o que só funciona enquanto
 * a lista é pequena e estável (produtos, status). Para clientes não serve:
 * `GET /users` tem `limit` máximo de 100 e ordena por data de criação, então
 * pré-carregar quebraria em silêncio ao passar de 100 — mostrando os 100 mais
 * recentes, ordem que não ajuda ninguém a procurar um nome.
 *
 * O componente não conhece a API: quem monta a chamada é a tela, via
 * `onSearch`. Assim `ui/` continua apresentacional e o teste não precisa
 * mockar serviço nenhum.
 */

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

const ChevronDown = (
  <svg
    className="w-4 h-4 shrink-0"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
  </svg>
);

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
  const [open, setOpen] = useState(false);
  const [termo, setTermo] = useState("");
  const [opcoes, setOpcoes] = useState<SearchSelectOption[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [falhou, setFalhou] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Cada busca leva um número; só a mais recente pode escrever na lista. Sem
  // isso, uma resposta lenta de um termo antigo chega depois e sobrescreve o
  // resultado do termo que a pessoa está vendo.
  const buscaAtual = useRef(0);

  useEffect(() => {
    function fecharForaDoComponente(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", fecharForaDoComponente);
    return () => document.removeEventListener("mousedown", fecharForaDoComponente);
  }, []);

  useEffect(() => {
    if (!open || !termo.trim()) {
      setOpcoes([]);
      setFalhou(false);
      return;
    }

    const minhaBusca = ++buscaAtual.current;
    setBuscando(true);
    setFalhou(false);

    const timer = setTimeout(() => {
      onSearch(termo.trim())
        .then((resultado) => {
          if (minhaBusca !== buscaAtual.current) return;
          setOpcoes(resultado);
        })
        .catch(() => {
          if (minhaBusca !== buscaAtual.current) return;
          setFalhou(true);
          setOpcoes([]);
        })
        .finally(() => {
          if (minhaBusca === buscaAtual.current) setBuscando(false);
        });
    }, debounceMs);

    return () => clearTimeout(timer);
    // `onSearch` fica de fora de propósito: a tela costuma passar uma função
    // nova a cada render, e incluí-la dispararia uma busca por render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [termo, open, debounceMs]);

  function escolher(opcao: SearchSelectOption | null) {
    onChange(opcao?.value ?? null, opcao?.label ?? null);
    setOpen(false);
    setTermo("");
  }

  const rotuloVisivel = value ? (selectedLabel ?? "Selecionado") : emptyLabel;

  return (
    <div ref={ref} className={cn("relative flex flex-col gap-1.5", className)}>
      {label && <label className="text-sm font-medium text-slate-300">{label}</label>}

      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-all select-none",
          "bg-background-elevated focus:outline-none",
          disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:border-border",
          open
            ? "border-primary ring-2 ring-primary/20 text-slate-100"
            : error
              ? "border-danger text-slate-300"
              : "border-border/60 text-slate-300",
          !value && "text-slate-500",
        )}
      >
        <span className="truncate">{rotuloVisivel}</span>
        <span
          className={cn(
            "ml-2 text-slate-400 transition-transform duration-150",
            open && "rotate-180",
          )}
        >
          {ChevronDown}
        </span>
      </button>

      {error && <span className="text-xs text-danger">{error}</span>}

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-full rounded-xl border border-border/60 bg-background-surface shadow-xl shadow-black/20 overflow-hidden">
          <div className="p-2">
            <input
              autoFocus
              type="text"
              value={termo}
              onChange={(e) => setTermo(e.target.value)}
              placeholder={placeholder}
              className="w-full rounded-lg border border-border/60 bg-background-elevated px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:border-primary focus:outline-none"
            />
          </div>

          <div className="h-px bg-border/40 mx-2" />

          <div role="listbox" className="max-h-60 overflow-y-auto">
            <button
              type="button"
              role="option"
              aria-selected={!value}
              onClick={() => escolher(null)}
              className={cn(
                "flex w-full items-center px-3 py-2.5 text-sm transition-colors cursor-pointer",
                !value
                  ? "bg-primary/10 text-primary font-semibold"
                  : "text-slate-400 hover:bg-background-elevated hover:text-slate-200",
              )}
            >
              {emptyLabel}
            </button>

            {buscando && (
              <p className="px-3 py-2.5 text-sm text-slate-500">Buscando…</p>
            )}

            {!buscando && falhou && (
              <p className="px-3 py-2.5 text-sm text-danger">Não foi possível buscar agora.</p>
            )}

            {!buscando && !falhou && termo.trim() && opcoes.length === 0 && (
              <p className="px-3 py-2.5 text-sm text-slate-500">Nenhum cliente encontrado.</p>
            )}

            {!buscando &&
              opcoes.map((opcao) => (
                <button
                  key={opcao.value}
                  type="button"
                  role="option"
                  aria-selected={value === opcao.value}
                  onClick={() => escolher(opcao)}
                  className={cn(
                    "flex w-full flex-col items-start px-3 py-2.5 text-sm transition-colors cursor-pointer",
                    value === opcao.value
                      ? "bg-primary/10 text-primary font-semibold"
                      : "text-slate-300 hover:bg-background-elevated hover:text-slate-100",
                  )}
                >
                  <span className="truncate">{opcao.label}</span>
                  {opcao.hint && (
                    <span className="text-xs text-slate-500 truncate">{opcao.hint}</span>
                  )}
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
