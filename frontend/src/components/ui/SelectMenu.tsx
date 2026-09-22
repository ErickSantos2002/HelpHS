import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/utils";
import { Icon } from "./Icon";

/**
 * Seletor de lista fechada, no desenho do `SelectMenu` do HS Growth
 * (`frontend/src/pages/Products.tsx`, filtros de Status e Categoria).
 *
 * Substitui o `<select>` nativo. O nativo abria uma lista desenhada pelo
 * sistema operacional — fora do tema, sem os tokens do pacote, e diferente em
 * cada navegador. Aqui o painel é nosso.
 *
 * ── O que veio do Growth, e o que mudou ao chegar ─────────────────────
 *
 * A geometria e o comportamento vieram inteiros: gatilho `flex` entre as
 * pontas, `rounded-lg`, `px-4 py-2`, texto pequeno, seta que gira 180° quando
 * abre; painel `rounded-lg` com borda e `shadow-lg`, opções `px-4 py-2` com
 * hover e destaque da escolhida; fecha ao escolher e ao clicar fora
 * (`mousedown` no `document`).
 *
 * Mudaram três coisas, e nenhuma é gosto:
 *
 * 1. **As cores são tokens, não `slate`/`gray`/`emerald`.** O HelpHS pinta com o
 *    pacote de design (claro e escuro pelo mesmo token), e o foco é do degrau
 *    de ação (`ring-action`), não verde. A borda de repouso é
 *    `border-borda-control` — a da E7: o `gray-300` do Growth sobre branco dá
 *    1,5:1, abaixo do 3:1 que a WCAG 1.4.11 pede para o limite de um campo.
 * 2. **O painel vai para o `body`, com `position: fixed`.** O `absolute` do
 *    Growth é cortado por qualquer ancestral com `overflow` — e aqui os campos
 *    moram em modais (`max-h-[92vh]`, com rolagem própria), cartões e barras de
 *    filtro. Mesmo motivo da variante `filter` do `Selector`. Tem a largura do
 *    campo, nasce 8px abaixo dele (o `mt-2` do Growth) e abre para cima quando
 *    não cabe embaixo — o caso do celular com o campo perto do fim da tela.
 * 3. **Teclado e papéis de campo.** O Growth não tem teclado. O nativo tinha,
 *    de graça, e trocar o nativo por um painel sem teclado seria trocar
 *    aparência por acesso. O gatilho é `role="combobox"` — o mesmo papel
 *    implícito do `<select>` —, as setas andam, `Enter`/Espaço escolhem,
 *    `Escape` fecha, `Home`/`End` vão às pontas e uma letra leva à opção que
 *    começa com ela.
 *
 * ── O `placeholder` é uma opção, como no `Select` nativo ──────────────
 *
 * No Growth ele é só o texto do gatilho vazio. Aqui ele também é a primeira
 * linha da lista, de valor `""` — que é o que o `Select` nativo fazia com
 * `<option value="">`. As barras de filtro dependem disso para LIMPAR o filtro
 * ("Todos os status"); tirar a linha mudaria a regra do filtro.
 *
 * ── O `Selector` continua existindo ───────────────────────────────────
 *
 * Os dois dividem o trabalho pela regra da D9.2 — quem escreve a lista. Lista
 * fechada, escrita no código: este. Lista que vem da rede e cresce com o
 * cadastro, com busca, marcador de cor ou linha secundária: o `Selector`.
 */

export interface SelectMenuOption {
  value: string;
  label: string;
}

export interface SelectMenuProps {
  value: string;
  options: SelectMenuOption[];
  onChange: (value: string) => void;
  /** Texto do gatilho vazio, e a linha de valor `""` no topo da lista. */
  placeholder?: string;
  disabled?: boolean;
  label?: string;
  hint?: string;
  error?: string;
  /** Vai para o gatilho. Sem ele, sai do `useId`. */
  id?: string;
  /** Chamado quando o gatilho perde o foco — o `onBlur` do react-hook-form. */
  onBlur?: () => void;
  /** Vai para o gatilho, como no `Select` nativo ia para o `<select>`. */
  className?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
}

/** 8px entre o campo e o painel — o `mt-2` do Growth. */
const ESPACO = 8;
/** Folga mínima entre o painel e a borda da tela. */
const MARGEM = 8;
/** `max-h-60`: a partir daqui a lista rola dentro do painel. */
const ALTURA_MAX = 240;
/** `py-2` + `text-sm`: altura de uma linha, para estimar o painel antes de desenhá-lo. */
const ALTURA_LINHA = 36;
/** Acima do `z-[200]` do `Modal`, como o painel do `Selector`. */
const CAMADA = 9999;
/** Janela da busca por letra: teclas dentro dela somam ao termo. */
const JANELA_BUSCA_MS = 500;
/**
 * Folga, em `ch`, do que o gatilho tem além do texto: `px-4` dos dois lados,
 * o `gap-3` e a seta de 16px. A 14px (`text-sm`) isso dá ~62px, e o `ch` do
 * Inter mede ~8,4px.
 */
const FOLGA_CH = 8;

interface Posicao {
  left: number;
  /**
   * Piso da largura: o campo. O painel cresce daí até caber o maior rótulo.
   *
   * O `<select>` nativo tinha a largura da opção mais longa, e um botão tem a
   * do texto que está exibindo. Com largura cravada no campo, "Administrador"
   * seria truncado dentro de um painel do tamanho da palavra "Perfil".
   */
  minWidth: number;
  /** Teto: a borda direita da tela, para o painel não sair dela no celular. */
  maxWidth: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

interface Linha extends SelectMenuOption {
  /** A linha do placeholder, que limpa a escolha. */
  vazia: boolean;
}

/**
 * Tira acento e caixa para comparar — o mesmo `achatar` do `Selector`. Sem
 * ele, quem digita `t` num campo com `Técnico` não chega lá.
 */
function achatar(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function posicionar(r: DOMRect, linhas: number): Posicao {
  const vh = window.innerHeight;
  const desejada = Math.min(ALTURA_MAX, linhas * ALTURA_LINHA + 2);
  const abaixo = vh - r.bottom - ESPACO - MARGEM;
  const acima = r.top - ESPACO - MARGEM;
  const base = {
    left: r.left,
    minWidth: r.width,
    maxWidth: Math.max(window.innerWidth - r.left - MARGEM, r.width),
  };

  if (abaixo < desejada && acima > abaixo) {
    return { ...base, bottom: vh - r.top + ESPACO, maxHeight: Math.min(ALTURA_MAX, acima) };
  }
  return {
    ...base,
    top: r.bottom + ESPACO,
    maxHeight: Math.min(ALTURA_MAX, Math.max(abaixo, ALTURA_LINHA * 2)),
  };
}

export const SelectMenu = forwardRef<HTMLButtonElement, SelectMenuProps>(
  (
    {
      value,
      options,
      onChange,
      placeholder,
      disabled = false,
      label,
      hint,
      error,
      id,
      onBlur,
      className,
      "aria-label": ariaLabel,
      "aria-labelledby": ariaLabelledby,
    },
    ref,
  ) => {
    const gerado = useId();
    const idGatilho = id ?? gerado + "-gatilho";
    const idRotulo = gerado + "-rotulo";
    const idLista = gerado + "-lista";
    const idErro = idGatilho + "-erro";
    const idDica = idGatilho + "-dica";
    const idOpcao = (i: number) => gerado + "-op-" + String(i);

    const [aberto, setAberto] = useState(false);
    const [ativo, setAtivo] = useState(0);
    const [pos, setPos] = useState<Posicao | null>(null);

    const raizRef = useRef<HTMLDivElement>(null);
    const gatilhoRef = useRef<HTMLButtonElement | null>(null);
    const painelRef = useRef<HTMLUListElement>(null);
    const busca = useRef({ termo: "", ate: 0 });

    // O ref de quem chama (o `field.ref` do react-hook-form, que foca o campo
    // recusado) e o nosso, que mede o gatilho, apontam para o mesmo botão.
    const juntarRef = useCallback(
      (el: HTMLButtonElement | null) => {
        gatilhoRef.current = el;
        if (typeof ref === "function") ref(el);
        else if (ref) ref.current = el;
      },
      [ref],
    );

    const linhas: Linha[] = [
      ...(placeholder !== undefined
        ? [{ value: "", label: placeholder, vazia: true }]
        : []),
      ...options.map((o) => ({ ...o, vazia: false })),
    ];
    const escolhida = linhas.findIndex((l) => l.value === value);
    const opcaoEscolhida = options.find((o) => o.value === value);
    const texto = opcaoEscolhida?.label ?? placeholder ?? "Selecione";

    /**
     * A largura do campo sai da opção MAIS LONGA, não do que está escolhido.
     *
     * É o que o `<select>` nativo fazia, e não é detalhe: um botão mede pelo
     * texto que exibe, então numa barra de filtros a largura pularia a cada
     * escolha ("Perfil" → "Administrador") e empurraria os vizinhos.
     *
     * `min()` com `100%` é o que impede o conserto de virar outro defeito: num
     * formulário estreito ou num celular, um rótulo longo estouraria a largura
     * do pai e criaria rolagem horizontal. O teto é sempre o pai.
     */
    const maiorRotulo = linhas.reduce((n, l) => Math.max(n, l.label.length), 0);
    const larguraMinima = "min(" + String(maiorRotulo + FOLGA_CH) + "ch, 100%)";

    // O nome é o RÓTULO, e só ele — o valor é o conteúdo do combobox, como no
    // `<select>`. Quem chama pode apontar para um rótulo da própria tela.
    const rotulado = ariaLabelledby ?? (label ? idRotulo : undefined);
    const descrito = error ? idErro : hint ? idDica : undefined;

    function abrir(emDestaque = escolhida >= 0 ? escolhida : 0) {
      if (disabled) return;
      setAtivo(emDestaque);
      setAberto(true);
    }

    function fechar() {
      setAberto(false);
    }

    function escolher(i: number) {
      const linha = linhas[i];
      if (!linha) return;
      // Escolher o que já estava escolhido FECHA e não avisa ninguém — é o que
      // o `<select>` nativo faz (sem troca não há evento `change`), e as telas
      // contam com isso: nos dois filtros da `UsersPage` o `onChange` roda
      // `setPage(1)`, então avisar aqui mandaria de volta para a página 1 quem
      // reescolhesse o mesmo filtro estando na 3.
      if (linha.value !== value) onChange(linha.value);
      fechar();
    }

    /** Leva o destaque à próxima linha que começa com o que se digitou. */
    function procurar(tecla: string, de: number): number {
      const agora = Date.now();
      const b = busca.current;
      b.termo = agora > b.ate ? tecla : b.termo + tecla;
      b.ate = agora + JANELA_BUSCA_MS;

      const alvo = achatar(b.termo);
      // Letra repetida anda para a PRÓXIMA com a mesma inicial; termo maior
      // continua procurando a partir de onde já está.
      const inicio = b.termo.length === 1 ? de + 1 : de;
      for (let k = 0; k < linhas.length; k++) {
        const i = (inicio + k) % linhas.length;
        if (achatar(linhas[i].label).startsWith(alvo)) return i;
      }
      return de;
    }

    const letra = (e: KeyboardEvent) =>
      e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey && !e.altKey;

    function aoTeclar(e: KeyboardEvent<HTMLButtonElement>) {
      if (disabled) return;

      if (!aberto) {
        if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
          e.preventDefault();
          abrir();
        } else if (letra(e)) {
          e.preventDefault();
          abrir(procurar(e.key, escolhida >= 0 ? escolhida : -1));
        }
        return;
      }

      const ultima = linhas.length - 1;
      switch (e.key) {
        case "Escape":
          // O `Modal` escuta Escape no `document`. Este Escape foi do menu, e
          // não pode chegar lá: fecharia a modal com o formulário dentro.
          e.preventDefault();
          e.stopPropagation();
          fechar();
          return;
        case "ArrowDown":
          e.preventDefault();
          setAtivo((i) => Math.min(i + 1, ultima));
          return;
        case "ArrowUp":
          e.preventDefault();
          setAtivo((i) => Math.max(i - 1, 0));
          return;
        case "Home":
          e.preventDefault();
          setAtivo(0);
          return;
        case "End":
          e.preventDefault();
          setAtivo(ultima);
          return;
        case "Enter":
        case " ":
          // O `preventDefault` aqui também impede o clique que o botão
          // dispararia sozinho (no keydown do Enter, no keyup do Espaço) — sem
          // ele, escolher reabriria o menu na mesma tecla.
          e.preventDefault();
          escolher(ativo);
          return;
        case "Tab":
          fechar();
          return;
        default:
          if (letra(e)) {
            e.preventDefault();
            setAtivo(procurar(e.key, ativo));
          }
      }
    }

    // Fora do componente é fora do gatilho E fora do painel — o painel mora
    // num portal, e não é descendente da raiz no DOM. O toque entra junto
    // porque, no Safari do iPhone, o `mousedown` não chega ao `document` quando
    // se toca num elemento que não é clicável.
    useEffect(() => {
      if (!aberto) return;
      function foraDoComponente(e: Event) {
        const alvo = e.target as Node;
        if (raizRef.current?.contains(alvo)) return;
        if (painelRef.current?.contains(alvo)) return;
        fechar();
      }
      document.addEventListener("mousedown", foraDoComponente);
      document.addEventListener("touchstart", foraDoComponente, { passive: true });
      return () => {
        document.removeEventListener("mousedown", foraDoComponente);
        document.removeEventListener("touchstart", foraDoComponente);
      };
    }, [aberto]);

    // As coordenadas do portal são tiradas na abertura e envelhecem com a
    // rolagem — então rolar fecha, como no `Selector`. A rolagem da PRÓPRIA
    // lista (a longa rola dentro do painel) não conta.
    useEffect(() => {
      if (!aberto) return;
      function aoRolar(e: Event) {
        if (painelRef.current?.contains(e.target as Node)) return;
        fechar();
      }
      window.addEventListener("scroll", aoRolar, true);
      window.addEventListener("resize", fechar);
      return () => {
        window.removeEventListener("scroll", aoRolar, true);
        window.removeEventListener("resize", fechar);
      };
    }, [aberto]);

    // Mede antes de pintar: o painel nunca aparece no lugar errado por um
    // quadro.
    const quantas = linhas.length;
    useLayoutEffect(() => {
      if (!aberto || !gatilhoRef.current) {
        setPos(null);
        return;
      }
      setPos(posicionar(gatilhoRef.current.getBoundingClientRect(), quantas));
    }, [aberto, quantas]);

    // A linha em destaque pelo teclado fica à vista na lista longa.
    useEffect(() => {
      if (!aberto) return;
      document.getElementById(idOpcao(ativo))?.scrollIntoView?.({ block: "nearest" });
      // `idOpcao` deriva do `useId`, estável por instância.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [aberto, ativo]);

    useEffect(() => {
      if (disabled) setAberto(false);
    }, [disabled]);

    const emDestaque = Math.min(ativo, linhas.length - 1);

    const painel =
      aberto && pos
        ? createPortal(
            <ul
              ref={painelRef}
              id={idLista}
              role="listbox"
              aria-labelledby={rotulado}
              aria-label={rotulado ? undefined : ariaLabel}
              style={{
                position: "fixed",
                zIndex: CAMADA,
                left: pos.left,
                // `max-content` com piso no campo: o painel nunca é mais
                // estreito que o gatilho nem trunca o maior rótulo.
                width: "max-content",
                minWidth: pos.minWidth,
                maxWidth: pos.maxWidth,
                top: pos.top,
                bottom: pos.bottom,
                maxHeight: pos.maxHeight,
              }}
              className="overflow-y-auto rounded-lg border border-borda bg-surface shadow-lg"
            >
              {linhas.map((l, i) => {
                const selecionada = i === escolhida;
                return (
                  <li
                    // O `value` sozinho não serve de chave: a linha do
                    // placeholder e uma opção de valor `""` podem coexistir.
                    key={String(i) + ":" + l.value}
                    id={idOpcao(i)}
                    role="option"
                    aria-selected={selecionada}
                    tabIndex={-1}
                    // O foco fica no gatilho: sem isto, apertar numa opção do
                    // portal tiraria o foco do campo antes do clique.
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setAtivo(i)}
                    onClick={() => escolher(i)}
                    className={cn(
                      "w-full cursor-pointer truncate px-4 py-2 text-left text-sm",
                      "hover:bg-surface-elevated",
                      // O cursor é um só: o mouse move o mesmo destaque que as
                      // setas, e os dois nunca apontam para linhas diferentes.
                      i === emDestaque && "bg-surface-elevated",
                      selecionada
                        ? "bg-surface-elevated font-medium text-conteudo-heading"
                        : l.vazia
                          ? "text-conteudo-muted"
                          : "text-conteudo",
                    )}
                  >
                    {l.label}
                  </li>
                );
              })}
            </ul>,
            document.body,
          )
        : null;

    return (
      <div ref={raizRef} className="flex flex-col gap-1.5">
        {label && (
          <label
            id={idRotulo}
            htmlFor={idGatilho}
            className="text-sm font-medium text-conteudo"
          >
            {label}
          </label>
        )}
        <button
          ref={juntarRef}
          id={idGatilho}
          type="button"
          role="combobox"
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={aberto}
          aria-controls={aberto ? idLista : undefined}
          aria-activedescendant={aberto ? idOpcao(emDestaque) : undefined}
          aria-labelledby={rotulado}
          aria-label={rotulado ? undefined : ariaLabel}
          aria-describedby={descrito}
          aria-invalid={error ? true : undefined}
          onClick={() => {
            // O Safari não dá foco a botão clicado; sem isto, o teclado não
            // funcionaria no menu aberto pelo mouse.
            gatilhoRef.current?.focus();
            if (aberto) fechar();
            else abrir();
          }}
          onKeyDown={aoTeclar}
          onBlur={() => {
            fechar();
            onBlur?.();
          }}
          style={{ minWidth: larguraMinima }}
          className={cn(
            "flex w-full items-center justify-between gap-3 rounded-lg border bg-surface px-4 py-2 text-left text-sm",
            "focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-colors cursor-pointer",
            error ? "border-danger focus:ring-danger" : "border-borda-control",
            className,
          )}
        >
          <span
            className={cn(
              "truncate",
              opcaoEscolhida ? "text-conteudo" : "text-conteudo-muted",
            )}
          >
            {texto}
          </span>
          <Icon
            name="chevronDown"
            size={16}
            strokeWidth={2}
            className={cn(
              "shrink-0 text-conteudo-muted transition-transform duration-150",
              aberto && "rotate-180",
            )}
          />
        </button>
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
        {painel}
      </div>
    );
  },
);

SelectMenu.displayName = "SelectMenu";
