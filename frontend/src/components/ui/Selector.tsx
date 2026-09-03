import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/utils";
import { Icon } from "./Icon";

/**
 * Seletor único, de `DS/components/forms/Select.jsx` e `SearchSelect.jsx`.
 *
 * Nasce da unificação de três componentes que faziam a mesma coisa com três
 * desenhos diferentes: `FilterSelect` (17 chamadas), `FormDropdown` (2) e
 * `SearchSelect` (1). Os três nomes continuam existindo como invólucros finos
 * `@deprecated`, com as props de hoje — **nenhuma página muda nesta fase**.
 *
 * ── Os dois eixos, e por que são dois ──────────────────────────────────
 *
 * `variant` decide **onde o painel é ancorado**, e isso não é estética:
 *
 * - `"filter"` monta o painel num **portal** com `position: fixed` e
 *   coordenadas calculadas do gatilho. É carga, não enfeite — os filtros vivem
 *   dentro de contêineres com `overflow`, e um painel `absolute` seria cortado.
 *   Fecha ao rolar e ao redimensionar, porque as coordenadas envelhecem.
 * - `"form"` usa `absolute` sob o campo, com rótulo em cima e erro embaixo.
 *
 * `searchable` decide **de onde vêm as opções**: `options` (lista pronta) ou
 * `onSearch` (busca no servidor, com debounce e guarda de corrida). Um seletor
 * de filtro pode ser buscável e um de formulário pode não ser; por isso são
 * eixos separados, e não um `variant` de três valores.
 *
 * ── O que a unificação conserta ────────────────────────────────────────
 *
 * 1. **Nenhum dos três usava um token do pacote.** Eram 45 cores `slate`
 *    cravadas. E a catraca não as via: ela casa `bg-*` com `text-*` na mesma
 *    string, e nestes componentes o fundo vinha do elemento pai.
 * 2. **O `FormDropdown` e o `SearchSelect` eram escritos só para o tema
 *    escuro** — `text-slate-300` no rótulo, sem um único `dark:`. No tema claro
 *    o rótulo ficava slate-300 sobre fundo claro.
 * 3. **`focus:outline-none` sem nada no lugar**, nos dois. É o mesmo defeito da
 *    emenda **E9**: o foco não estava fraco, estava ausente. Aqui o gatilho tem
 *    anel em `--action`.
 * 4. **Nenhum dos três tinha teclado.** O `SearchSelect` chegava a declarar
 *    `role="listbox"` e `role="option"` — prometendo um contrato de widget que
 *    não honrava, o que é pior que não declarar nada. Aqui as setas andam, o
 *    `Enter` escolhe, o `Escape` fecha, e `Home`/`End` vão às pontas.
 *
 * ── Uma coisa que NÃO foi unificada, de propósito ──────────────────────
 *
 * `dot` e `hint` continuam dois campos. O primeiro é uma amostra de cor, o
 * segundo é uma linha de texto secundária; juntá-los num "campo secundário"
 * seria unificação falsa — a mesma armadilha de "token certo, propósito
 * errado" que a E7 e as barras de SLA já custaram nesta migração.
 */

export interface SelectorOption {
  value: string;
  label: string;
  /** Amostra de cor à esquerda. Vem das telas como hex cru — ver a pendência. */
  dot?: string;
  /** Linha secundária — e-mail, empresa, o que desambigua homônimos. */
  hint?: string;
}

export interface SelectorProps {
  value: string | null;
  /** Recebe o valor e a opção inteira; os invólucros adaptam para as assinaturas de hoje. */
  onChange: (value: string | null, option: SelectorOption | null) => void;
  /** Lista pronta. Ignorada quando `searchable` e `onSearch` estão presentes. */
  options?: SelectorOption[];
  /** Busca no servidor. A tela monta a chamada; `ui/` continua apresentacional. */
  onSearch?: (term: string) => Promise<SelectorOption[]>;
  searchable?: boolean;
  variant?: "filter" | "form";
  label?: string;
  /** Texto do gatilho quando nada está escolhido. */
  placeholder?: string;
  /** Texto dentro do campo de busca. */
  searchPlaceholder?: string;
  /** Rótulo da opção que desfaz a escolha. */
  emptyLabel?: string;
  /** Rótulo do valor atual, quando a lista não o contém (modo busca). */
  selectedLabel?: string | null;
  /**
   * Aviso de busca sem resultado. Tem prop própria porque o texto de hoje
   * nomeia o domínio — "Nenhum cliente encontrado." — e um componente de `ui/`
   * não pode saber que a lista é de clientes. O invólucro preserva o texto.
   */
  emptyResultsLabel?: string;
  disabled?: boolean;
  error?: string;
  className?: string;
  debounceMs?: number;
}

const LARGURA_MIN = 160;

export function Selector({
  value,
  onChange,
  options,
  onSearch,
  searchable = false,
  variant = "form",
  label,
  placeholder,
  searchPlaceholder = "Buscar…",
  emptyLabel,
  selectedLabel,
  emptyResultsLabel = "Nenhum resultado encontrado.",
  disabled = false,
  error,
  className,
  debounceMs = 300,
}: SelectorProps) {
  const filtro = variant === "filter";
  const textoVazio = placeholder ?? (filtro ? "Todos" : "Selecione…");
  const rotuloLimpar = emptyLabel ?? textoVazio;

  const [aberto, setAberto] = useState(false);
  const [termo, setTermo] = useState("");
  const [achados, setAchados] = useState<SelectorOption[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [falhou, setFalhou] = useState(false);
  const [ativo, setAtivo] = useState(0);
  const [pos, setPos] = useState<{ top: number; left?: number; right?: number }>({
    top: 0,
    left: 0,
  });

  const raizRef = useRef<HTMLDivElement>(null);
  const gatilhoRef = useRef<HTMLButtonElement>(null);
  const painelRef = useRef<HTMLDivElement>(null);
  const buscaAtual = useRef(0);

  const idBase = useId();
  const idPainel = idBase + "-painel";
  // O erro era um `<p>` solto ao lado do gatilho: visualmente junto, e sem
  // relação nenhuma com ele para um leitor de tela.
  const idErro = idBase + "-erro";
  const idOpcao = (i: number) => idBase + "-op-" + String(i);

  // `""` e `null` são a mesma coisa aqui: o `FilterSelect` limpava com string
  // vazia e o `SearchSelect` com `null`.
  const vazio = value === null || value === undefined || value === "";
  const lista = searchable ? achados : (options ?? []);
  const escolhida = (options ?? []).find((o) => o.value === value) ?? null;

  // A linha que limpa a escolha ocupa o índice 0; as opções vêm depois.
  const navegaveis = useMemo(
    () => [null as SelectorOption | null, ...lista],
    [lista],
  );

  useEffect(() => {
    function foraDoComponente(e: MouseEvent) {
      const alvo = e.target as Node;
      const naRaiz = raizRef.current?.contains(alvo);
      const noPainel = painelRef.current?.contains(alvo);
      if (!naRaiz && !noPainel) setAberto(false);
    }
    document.addEventListener("mousedown", foraDoComponente);
    return () => document.removeEventListener("mousedown", foraDoComponente);
  }, []);

  // Só a variante de filtro fecha ao rolar: as coordenadas do portal são
  // calculadas no momento da abertura e envelhecem com o scroll. A de
  // formulário é `absolute` e acompanha o campo sozinha.
  useEffect(() => {
    if (!aberto || !filtro) return;
    const fechar = () => setAberto(false);
    window.addEventListener("scroll", fechar, true);
    window.addEventListener("resize", fechar);
    return () => {
      window.removeEventListener("scroll", fechar, true);
      window.removeEventListener("resize", fechar);
    };
  }, [aberto, filtro]);

  useEffect(() => {
    if (!aberto) {
      setTermo("");
      setAtivo(0);
    }
  }, [aberto]);

  useEffect(() => {
    if (!searchable || !onSearch) return;
    if (!aberto || !termo.trim()) {
      setAchados([]);
      setFalhou(false);
      return;
    }

    // Cada busca leva um número; só a mais recente escreve na lista. Sem isso,
    // a resposta lenta de um termo antigo chega depois e sobrescreve o que a
    // pessoa está vendo.
    const minha = ++buscaAtual.current;
    setBuscando(true);
    setFalhou(false);

    const timer = setTimeout(() => {
      onSearch(termo.trim())
        .then((r) => {
          if (minha !== buscaAtual.current) return;
          setAchados(r);
          setAtivo(0);
        })
        .catch(() => {
          if (minha !== buscaAtual.current) return;
          setFalhou(true);
          setAchados([]);
        })
        .finally(() => {
          if (minha === buscaAtual.current) setBuscando(false);
        });
    }, debounceMs);

    return () => clearTimeout(timer);
    // `onSearch` fica de fora de propósito: a tela costuma passar uma função
    // nova a cada render, e incluí-la dispararia uma busca por render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [termo, aberto, debounceMs, searchable]);

  function posicionar() {
    if (!filtro || !gatilhoRef.current) return;
    const r = gatilhoRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    // Se o painel estourasse a borda direita, ancora pela direita do gatilho.
    if (r.left + LARGURA_MIN > vw - 8) {
      setPos({ top: r.bottom + 6, right: vw - r.right });
    } else {
      setPos({ top: r.bottom + 6, left: r.left });
    }
  }

  function alternar() {
    if (disabled) return;
    if (!aberto) posicionar();
    setAberto((v) => !v);
  }

  function escolher(opcao: SelectorOption | null) {
    onChange(opcao?.value ?? null, opcao);
    setAberto(false);
  }

  function aoTeclar(e: React.KeyboardEvent) {
    if (disabled) return;

    if (!aberto) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        posicionar();
        setAberto(true);
      }
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      setAberto(false);
      gatilhoRef.current?.focus();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAtivo((i) => Math.min(i + 1, navegaveis.length - 1));
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setAtivo((i) => Math.max(i - 1, 0));
      return;
    }
    if (e.key === "Home") {
      e.preventDefault();
      setAtivo(0);
      return;
    }
    if (e.key === "End") {
      e.preventDefault();
      setAtivo(navegaveis.length - 1);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      escolher(navegaveis[ativo] ?? null);
    }
  }

  const rotuloGatilho = searchable
    ? (vazio ? rotuloLimpar : (selectedLabel ?? "Selecionado"))
    : (escolhida?.label ?? textoVazio);

  const linhaBase =
    "flex w-full items-center gap-2.5 px-3 py-2.5 text-sm transition-colors cursor-pointer text-left";

  function classeLinha(selecionada: boolean, emFoco: boolean) {
    return cn(
      linhaBase,
      selecionada
        ? "bg-tint-primary text-on-tint-primary font-semibold"
        : "text-conteudo hover:bg-surface-elevated hover:text-conteudo-heading",
      // O realce do teclado é o mesmo do mouse: quem navega com setas vê onde
      // está sem que o cursor precise estar em cima.
      emFoco && !selecionada && "bg-surface-elevated text-conteudo-heading",
    );
  }

  const conteudoPainel = (
    <>
      {searchable && (
        <div className="p-2">
          <input
            autoFocus
            type="text"
            value={termo}
            onChange={(e) => setTermo(e.target.value)}
            onKeyDown={aoTeclar}
            placeholder={searchPlaceholder}
            role="combobox"
            aria-expanded={aberto}
            aria-controls={idPainel}
            aria-activedescendant={idOpcao(ativo)}
            aria-label={label ?? searchPlaceholder}
            className="w-full rounded-lg border border-borda-control bg-surface-elevated px-3 py-2 text-sm text-conteudo placeholder:text-conteudo-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
          />
        </div>
      )}

      <div
        id={idPainel}
        role="listbox"
        aria-label={label ?? textoVazio}
        className={cn(!filtro && "max-h-60 overflow-y-auto")}
      >
        <button
          type="button"
          role="option"
          id={idOpcao(0)}
          aria-selected={vazio}
          onClick={() => escolher(null)}
          className={classeLinha(vazio, ativo === 0)}
        >
          {!searchable && (
            <span className="h-2 w-2 shrink-0 rounded-full border border-borda-control bg-transparent" />
          )}
          <span className="flex-1">{rotuloLimpar}</span>
          {vazio && (
            <Icon name="check" size={14} strokeWidth={2.5} className="shrink-0" />
          )}
        </button>

        <div className="mx-2 h-px bg-borda-muted" />

        {searchable && buscando && (
          <p className="px-3 py-2.5 text-sm text-conteudo-muted">Buscando…</p>
        )}

        {searchable && !buscando && falhou && (
          <p className="px-3 py-2.5 text-sm text-on-tint-danger">
            Não foi possível buscar agora.
          </p>
        )}

        {searchable && !buscando && !falhou && termo.trim() && lista.length === 0 && (
          <p className="px-3 py-2.5 text-sm text-conteudo-muted">{emptyResultsLabel}</p>
        )}

        {(!searchable || !buscando) &&
          lista.map((opcao, i) => {
            const selecionada = !vazio && value === opcao.value;
            return (
              <button
                key={opcao.value}
                type="button"
                role="option"
                id={idOpcao(i + 1)}
                aria-selected={selecionada}
                onClick={() => escolher(opcao)}
                className={cn(
                  classeLinha(selecionada, ativo === i + 1),
                  opcao.hint && "flex-col items-start gap-0",
                )}
              >
                <span className={cn("flex w-full items-center gap-2.5")}>
                  {!searchable &&
                    (opcao.dot ? (
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: opcao.dot }}
                      />
                    ) : (
                      <span className="h-2 w-2 shrink-0 rounded-full bg-transparent" />
                    ))}
                  <span className="flex-1 truncate">{opcao.label}</span>
                  {selecionada && (
                    <Icon name="check" size={14} strokeWidth={2.5} className="shrink-0" />
                  )}
                </span>
                {opcao.hint && (
                  <span className="truncate text-xs text-conteudo-muted">
                    {opcao.hint}
                  </span>
                )}
              </button>
            );
          })}
      </div>
    </>
  );

  const painel = !aberto ? null : filtro ? (
    createPortal(
      <div
        ref={painelRef}
        style={{
          position: "fixed",
          top: pos.top,
          left: pos.left,
          right: pos.right,
          minWidth: LARGURA_MIN,
          zIndex: 9999,
        }}
        className="overflow-hidden rounded-xl border border-borda bg-surface shadow-lg"
      >
        {conteudoPainel}
      </div>,
      document.body,
    )
  ) : (
    <div
      ref={painelRef}
      className="absolute left-0 top-full z-50 mt-1.5 w-full overflow-hidden rounded-xl border border-borda bg-surface shadow-xl"
    >
      {conteudoPainel}
    </div>
  );

  return (
    <div
      ref={raizRef}
      className={cn(filtro ? "relative" : "relative flex flex-col gap-1.5", className)}
    >
      {label && !filtro && (
        <label className="text-sm font-medium text-conteudo">{label}</label>
      )}

      <button
        ref={gatilhoRef}
        type="button"
        disabled={disabled}
        onClick={alternar}
        onKeyDown={aoTeclar}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? idErro : undefined}
        aria-haspopup="listbox"
        aria-expanded={aberto}
        aria-controls={aberto ? idPainel : undefined}
        aria-activedescendant={aberto && !searchable ? idOpcao(ativo) : undefined}
        className={cn(
          "flex items-center border text-sm transition-all select-none",
          // O anel de foco existe porque antes não existia: os dois seletores
          // de formulário traziam `focus:outline-none` e nada no lugar.
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
          filtro
            ? "h-9 gap-2 rounded-lg px-3 font-medium bg-surface dark:bg-surface-elevated"
            : "w-full justify-between gap-2 rounded-lg px-3 py-2 bg-surface-elevated",
          disabled
            ? "cursor-not-allowed opacity-40"
            : "cursor-pointer hover:border-borda-strong",
          aberto
            ? "border-action ring-2 ring-action/20 text-conteudo-heading"
            : error
              ? "border-danger text-conteudo"
              : "border-borda-control text-conteudo",
          vazio && "text-conteudo-muted",
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          {escolhida?.dot && (
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: escolhida.dot }}
            />
          )}
          <span className="truncate">{rotuloGatilho}</span>
        </span>
        <Icon
          name="chevronDown"
          size={filtro ? 14 : 16}
          strokeWidth={2}
          className={cn(
            "shrink-0 text-conteudo-muted transition-transform duration-150",
            filtro ? "" : "ml-2",
            aberto && "rotate-180",
          )}
        />
      </button>

      {error && !filtro && (
        <p id={idErro} className="text-xs text-on-tint-danger">
          {error}
        </p>
      )}

      {painel}
    </div>
  );
}
