import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Badge,
  Button,
  Icon,
  Modal,
  ModalFooter,
  Pagination,
  Select,
  Selector,
  Spinner,
} from "../../components/ui";
import type { BadgeProps } from "../../components/ui";
import { CATEGORIAS, rotuloDeCategoria } from "../../lib/categoria";
import { toastApiError } from "../../lib/toastError";
import { useAuth } from "../../contexts/AuthContext";
import {
  deleteKBArticle,
  getKBArticles,
  type KBArticle,
  type KBArticleStatus,
} from "../../services/kbService";
import { getProducts, type Product } from "../../services/productService";

// ── Constants ─────────────────────────────────────────────────

/**
 * O status do ARTIGO, que não é o status do chamado.
 *
 * `lib/status.ts` é a fonte única dos **sete status de chamado** — aberto, em
 * andamento, resolvido, cancelado. Estes três são outro domínio: o ciclo
 * editorial de um artigo. Emprestar aquele módulo aqui faria dois vocabulários
 * caberem numa tabela só, que é o começo exato da divergência que esta fase
 * está desfazendo.
 *
 * Fica local, mas com a disciplina dos módulos de `lib/`: rótulo, variante do
 * `Badge` e amostra de cor saem **daqui**, e as opções do filtro são
 * DERIVADAS da tabela em vez de escritas ao lado dela. Antes eram duas listas
 * paralelas mantidas à mão — o mesmo modo de falha que deu três cópias do mapa
 * de papel dentro do `UsersPage`.
 *
 * ⚠️ **Ela já tem um segundo consumidor**: `pages/kb/KBFormPage.tsx` repete os
 * três rótulos e os três hexadecimais. Pela regra registrada no `lib/papel.ts`
 * — tabela com **um** consumidor fica local, tabela com **vários** sobe —, esta
 * devia virar `src/lib/kbStatus.ts`. `src/lib/**` está fora do escopo desta
 * tela; relatado ao operador.
 */
interface StatusDoArtigo {
  /** O nome por extenso. É o que o selo e o filtro mostram. */
  rotulo: string;
  /** Variante do `Badge` — o mesmo vocabulário de `lib/status.ts`. */
  variante: BadgeProps["variant"];
  /**
   * A amostra de cor do seletor, que é `style` e não classe.
   *
   * O `Selector` pinta o ponto com `backgroundColor` embutido, então aqui entra
   * **valor CSS**, não utilitário do Tailwind. Os três eram hexadecimal cravado
   * (`#10b981`, `#f59e0b`, `#64748b`): decisão de desenho escrita à mão, que
   * não acompanha o tema nem a rampa e não tem como ser conferida por nenhuma
   * varredura.
   *
   * Passam a apontar para os tokens de PREENCHIMENTO, que é o caminho que o
   * `graficoDePrioridade()` de `lib/prioridade.ts` já fazia — inclusive o
   * neutro, que lá também é `--border-control`, porque `--fill-muted` não
   * existe: o pacote resolve o neutro com o contorno de controle.
   */
  amostra: string;
}

const STATUS_DO_ARTIGO: Record<KBArticleStatus, StatusDoArtigo> = {
  published: {
    rotulo: "Publicado",
    variante: "success",
    amostra: "var(--fill-success)",
  },
  draft: {
    rotulo: "Rascunho",
    variante: "warning",
    amostra: "var(--fill-warning)",
  },
  archived: {
    rotulo: "Arquivado",
    variante: "muted",
    amostra: "var(--border-control)",
  },
};

/**
 * As opções do filtro de status, derivadas da tabela.
 *
 * A ordem é a de publicação — publicado, rascunho, arquivado —, que é a que o
 * filtro sempre teve. Trocá-la é decisão de desenho e não se decide aqui.
 */
const OPCOES_DE_STATUS = (
  Object.keys(STATUS_DO_ARTIGO) as KBArticleStatus[]
).map((s) => ({
  value: s,
  label: STATUS_DO_ARTIGO[s].rotulo,
  dot: STATUS_DO_ARTIGO[s].amostra,
}));

/**
 * As opções do filtro de categoria, de `lib/categoria.ts`.
 *
 * A lista estava escrita à mão dentro do JSX, com os oito pares repetidos —
 * era a quinta cópia das categorias no projeto, e a segunda **dentro desta
 * tela** (a outra era o `CATEGORY_LABEL`, que traduzia o valor cru de volta
 * para o rótulo). As duas saem, e o `ReportsPage` e o `TicketFormPage` já
 * derivam a lista do mesmo módulo.
 */
const OPCOES_DE_CATEGORIA = CATEGORIAS.map((c) => ({
  value: c.value,
  label: c.label,
}));

const PAGE_SIZE = 20;

// ── Main ──────────────────────────────────────────────────────

export default function KBListPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isStaff = user?.role === "admin" || user?.role === "technician";

  const [articles, setArticles] = useState<KBArticle[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<KBArticle | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => { setOffset(0); }, [search, category, productFilter, statusFilter]);

  useEffect(() => {
    getProducts({ limit: 100 }).then((res) => setProducts(res.items)).catch(() => setProducts([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    getKBArticles({ search: search || undefined, category: category || undefined, product_id: productFilter || undefined, status: (statusFilter as KBArticleStatus) || undefined, offset, limit: PAGE_SIZE })
      .then((res) => { setArticles(res.items); setTotal(res.total); })
      .finally(() => setLoading(false));
  }, [search, category, productFilter, statusFilter, offset]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await deleteKBArticle(deleteTarget.id);
      setArticles((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setTotal((t) => t - 1);
      setDeleteTarget(null);
    } catch (err) {
      // Sem este `catch` a exclusão que falha só fazia o botão parar de
      // girar: o modal seguia aberto, o artigo seguia na lista e NADA
      // dizia por quê. A tela sabia mostrar erro — o import de `Alert`
      // ficou órfão quando o aviso virou prosa, e essa órfã é a prova de
      // que o caminho de falha nunca teve dono. `toastApiError` mostra o
      // título da ação e a razão que o servidor devolveu.
      toastApiError(err, "Não foi possível excluir o artigo.");
    } finally {
      setDeleteLoading(false);
    }
  }

  // Estava escrito duas vezes, idêntico, no botão "Limpar" e no estado vazio.
  // Duas cópias de uma limpeza de quatro campos é onde um quinto filtro futuro
  // entra em uma delas e não na outra.
  function limparFiltros() {
    setSearch("");
    setCategory("");
    setProductFilter("");
    setStatusFilter("");
  }

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const hasFilters = !!(search || category || productFilter || statusFilter);

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      {/*
        A casca fica desenhada à mão, e não vira `Card`: o cabeçalho é
        `rounded-2xl` e o `Card` é `rounded-xl`. O `cn()` deste projeto é
        concatenação simples, **não** `tailwind-merge` — mandar `rounded-2xl`
        por `className` deixaria as duas classes no atributo e quem vence
        sairia da ordem do CSS gerado. Raio diferente é decisão de desenho.
        Os tokens são os mesmos do `Card`.
      */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-conteudo-heading">Base de Conhecimento</h1>
          <p className="mt-0.5 text-sm text-conteudo-muted">
            Artigos e guias de suporte{total > 0 && ` · ${total} artigo${total !== 1 ? "s" : ""}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Search */}
          <div className="relative w-full sm:w-auto">
            {/*
              `pointer-events-none` no ícone: ele fica por cima do campo, e sem
              isso o clique em cima da lupa não põe o cursor no campo.
            */}
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-conteudo-muted">
              <Icon name="search" size={16} strokeWidth={2} />
            </span>
            {/*
              O campo se identificava só pelo `placeholder` — o texto que some
              exatamente quando a pessoa começa a digitar, e que em leitor de
              tela vale como dica, não como nome. Item fixo do CHECKLIST-29, e
              o mesmo conserto que a `KBArticlePage` fez no campo de comentário.

              A borda vem de `--border-control` (E7) e não do `borda/60` de
              antes: o contorno de um CONTROLE pede 3:1 pela 1.4.11, e o
              separador de superfície a 60% dava perto de 1,2:1.
            */}
            <input
              type="text"
              aria-label="Buscar artigos"
              placeholder="Buscar artigos…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-8 py-2 text-sm w-full sm:w-52 rounded-lg border border-borda-control bg-surface-elevated text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent transition-colors"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                aria-label="Limpar busca"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-conteudo-muted hover:text-conteudo cursor-pointer"
              >
                <Icon name="close" size={14} strokeWidth={2.5} />
              </button>
            )}
          </div>

          {/* Category — D9.2: oito categorias, de `lib/categoria.ts`, nenhuma
              vinda da rede. Lista curta e conhecida, logo `<select>` nativo.

              O rótulo é `sr-only` porque a barra não tem espaço para ele: sem
              rótulo, os três filtros desta barra se anunciavam pelo valor
              escolhido — "Hardware", "Publicado" — sem dizer de que filtro
              eram. */}
          <span id="rotulo-filtro-categoria" className="sr-only">
            Categoria
          </span>
          <Select
            id="filtro-categoria"
            aria-labelledby="rotulo-filtro-categoria"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Todas as categorias"
            options={OPCOES_DE_CATEGORIA}
          />

          {/* Produto — D9.2: lista LONGA. As opções vêm de `getProducts` e
              crescem com o cadastro, então o controle é o
              `Selector variant="filter"`, que também traz o rótulo. */}
          {products.length > 0 && (
            <Selector
              variant="filter"
              label="Produto"
              value={productFilter}
              onChange={(v) => setProductFilter(v ?? "")}
              placeholder="Todos os produtos"
              options={products.map((p) => ({ value: p.id, label: p.name }))}
            />
          )}

          {/* Status (staff only) — D9.2: três estados de publicação, de
              `STATUS_DO_ARTIGO`. Lista curta e conhecida, logo `<select>`
              nativo — e o ponto de cor sai com ele, porque o `<option>` não
              aceita marcador. O selo de cada linha da lista continua pintando
              pela mesma fonte, então a cor não some da tela. */}
          {isStaff && (
            <>
              <span id="rotulo-filtro-status" className="sr-only">
                Status do artigo
              </span>
              <Select
                id="filtro-status"
                aria-labelledby="rotulo-filtro-status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                placeholder="Todos os status"
                options={OPCOES_DE_STATUS}
              />
            </>
          )}

          {hasFilters && (
            /*
              `hover:text-on-tint-danger` e não `hover:text-danger`: a cor cheia
              da rampa como cor de TEXTO reprova o piso — 16 das 24 combinações
              medidas. A borda continua na cor cheia a 30%, que é forma e não
              texto, e é como o `Badge` a escreve desde a E8.
            */
            <button
              onClick={limparFiltros}
              className="flex items-center gap-1.5 text-xs font-medium text-conteudo-muted hover:text-on-tint-danger transition-colors cursor-pointer px-2 py-2 rounded-lg border border-borda/40 hover:border-danger/30"
            >
              <Icon name="close" size={14} strokeWidth={2.5} />
              Limpar
            </button>
          )}

          {/*
            Era `bg-primary` com `text-white`: **3,83:1 nos dois temas**, porque
            o degrau 500 é absoluto e não inverte. E era um `<button>` que
            chamava `navigate()` — navegação é link. O `Button to=` resolve os
            dois: par `--action` / `--text-on-primary` da E2, e um `<a>` de
            verdade.
          */}
          {isStaff && (
            <Button
              to="/kb/new"
              icon={<Icon name="plus" size={16} strokeWidth={2.5} />}
            >
              Novo artigo
            </Button>
          )}
        </div>
      </div>

      {/* ── List ─────────────────────────────────────────────── */}
      {loading ? (
        <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
      ) : articles.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-borda/40 bg-surface py-20">
          {/*
            `conteudo-muted` e não `faint`: o círculo é `bg-surface-elevated` e
            o texto está no MESMO elemento — o par que a varredura media em
            2,34:1 no claro e 1,79:1 no escuro. A E5 levou `--text-muted` a
            `slate-600` no claro justamente para dar 6,92:1 sobre a superfície
            elevada.
          */}
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-elevated text-conteudo-muted">
            <Icon name="book" size={20} strokeWidth={1.5} />
          </div>
          <p className="text-sm font-medium text-conteudo-muted">Nenhum artigo encontrado.</p>
          {hasFilters && (
            <button
              onClick={limparFiltros}
              className="mt-2 text-xs text-conteudo-link hover:text-conteudo-link-hover cursor-pointer transition-colors"
            >
              Limpar filtros
            </button>
          )}
          {/*
            Este NÃO é botão: ele leva para outra página. `text-conteudo-link` e
            não `text-primary` — o degrau de marca sobre `--bg-base` dá 3,66:1,
            e link é texto.
          */}
          {isStaff && !hasFilters && (
            <Link
              to="/kb/new"
              className="mt-3 text-xs font-medium text-conteudo-link hover:text-conteudo-link-hover cursor-pointer transition-colors"
            >
              + Criar primeiro artigo
            </Link>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {articles.map((article) => {
            const st = STATUS_DO_ARTIGO[article.status];
            const catLabel = rotuloDeCategoria(article.category);
            const preview = article.content.replace(/#+\s/g, "").replace(/\*\*/g, "").slice(0, 160);

            return (
              /*
                O `onClick` da linha inteira continua, como conveniência de
                mouse — mas ele nunca foi alcançável por teclado nem anunciado
                como controle: um `<div>` com `cursor-pointer` não entra na
                ordem de tabulação e um leitor de tela não diz que ele leva a
                lugar nenhum. Quem navega sem mouse não tinha como abrir artigo
                nenhum a partir desta lista.

                O título passa a ser um `Link` de verdade — o mesmo conserto da
                trilha da `KBArticlePage`. Ele é o alvo acessível; a linha
                continua clicável para quem usa mouse, e o `stopPropagation`
                impede que o clique no título navegue duas vezes.
              */
              <div
                key={article.id}
                className="flex items-start gap-4 rounded-xl border border-borda/40 bg-surface px-5 py-4 hover:border-primary/30 hover:bg-primary/[0.02] transition-all cursor-pointer"
                onClick={() => navigate(`/kb/${article.id}`)}
              >
                {/* Icon */}
                {/*
                  `bg-tint-primary` com `text-on-tint-primary`: o par medido da
                  E8, o mesmo que o `Badge` usa. O `bg-primary/10` com
                  `text-primary` de antes era a rampa a 10% com o degrau de
                  marca por cima — 2,77:1 sobre a superfície elevada no escuro.
                */}
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-tint-primary text-on-tint-primary">
                  <Icon name="book" size={20} strokeWidth={1.5} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <Link
                      to={`/kb/${article.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-sm font-semibold text-conteudo-heading hover:text-conteudo-link transition-colors truncate"
                    >
                      {article.title}
                    </Link>
                    {isStaff && (
                      <Badge variant={st.variante}>{st.rotulo}</Badge>
                    )}
                    <Badge variant="secondary">{catLabel}</Badge>
                    {article.products.length === 0 ? (
                      <Badge variant="secondary">Todos os produtos</Badge>
                    ) : (
                      article.products.map((p) => (
                        <Badge
                          key={p.id}
                          variant="primary"
                          className="max-w-[10rem] truncate"
                        >
                          {p.name}
                        </Badge>
                      ))
                    )}
                  </div>
                  <p className="text-xs text-conteudo-muted line-clamp-1">{preview}…</p>
                  {article.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {[...new Set(article.tags)].map((tag) => (
                        <Badge key={tag} variant="secondary">{tag}</Badge>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right: stats + actions */}
                <div
                  className="flex flex-col items-end gap-2.5 shrink-0 self-center"
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Stats */}
                  {/*
                    Os dois números eram só número: o `Icon` é `aria-hidden`, e
                    quem usa leitor de tela ouvia "12" e "3", sem saber do quê.
                    O texto invisível diz a unidade — e é texto, não `title`,
                    porque `title` em `<span>` não vira nome de nada.
                  */}
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1 text-[11px] text-conteudo-muted">
                      <Icon name="eye" size={14} strokeWidth={2} />
                      {article.view_count}
                      <span className="sr-only">visualizações</span>
                    </span>
                    <span className="flex items-center gap-1 text-[11px] text-on-tint-success">
                      <Icon name="thumbsUp" size={14} strokeWidth={2} />
                      {article.helpful}
                      <span className="sr-only">votos de útil</span>
                    </span>
                  </div>

                  {/* Action buttons — sempre visíveis */}
                  {isStaff && (
                    <div className="flex items-center gap-1">
                      {/*
                        Editar navega, então é link. E o nome acessível carrega
                        o TÍTULO do artigo: numa lista de vinte linhas, vinte
                        controles chamados "Editar" não dizem qual dos vinte.
                      */}
                      <Link
                        to={`/kb/${article.id}/edit`}
                        title="Editar"
                        aria-label={`Editar ${article.title}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-primary/10 transition-colors cursor-pointer"
                      >
                        <Icon name="edit" size={16} strokeWidth={2} />
                      </Link>
                      {user?.role === "admin" && (
                        <button
                          onClick={() => setDeleteTarget(article)}
                          title="Excluir"
                          aria-label={`Excluir ${article.title}`}
                          className="p-1.5 rounded-lg text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-colors cursor-pointer"
                        >
                          <Icon name="trash" size={16} strokeWidth={2} />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Pagination ────────────────────────────────────────── */}
      {/*
        Era um par "Anterior / Próxima" desenhado à mão, sem `nav`, sem nome de
        região e sem como pular para uma página distante — numa base com 200
        artigos, chegar à página 9 custava oito cliques. O `Pagination` do
        pacote traz o `nav aria-label="Paginação"`, os números da janela e o
        `aria-current="page"` na atual.

        Ele conta a partir de 1 e este estado guarda `offset`; a conversão fica
        num lugar só, aqui.
      */}
      {total > PAGE_SIZE && (
        <Pagination
          page={currentPage}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={(p) => setOffset((p - 1) * PAGE_SIZE)}
          itemLabel="artigos"
        />
      )}

      {/* ── Delete modal ─────────────────────────────────────── */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        size="sm"
        title="Excluir artigo"
      >
        <div className="space-y-4">
          {/*
            O aviso era um bloco à mão em `red-900/20` sobre `red-800/40` com
            texto `red-300`, virou `Alert variant="danger" live={false}`, e pela
            D9.3 virou PROSA: a forma de exclusão da frota é modal `sm` com a
            frase que nomeia o que some, sem bloco com casca em volta.
          */}

          {/* Article preview */}
          {deleteTarget && (
            <div className="flex items-center gap-3 rounded-xl border border-borda bg-surface-elevated px-4 py-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-tint-primary text-on-tint-primary">
                <Icon name="book" size={20} strokeWidth={1.5} />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-conteudo-heading truncate">{deleteTarget.title}</p>
                <p className="text-xs text-conteudo-muted">
                  {rotuloDeCategoria(deleteTarget.category)}
                  {" · "}
                  {STATUS_DO_ARTIGO[deleteTarget.status].rotulo}
                </p>
              </div>
            </div>
          )}

          <p className="text-sm text-conteudo-muted">
            Tem certeza que deseja excluir{" "}
            <span className="text-conteudo-heading font-medium">"{deleteTarget?.title}"</span>? O
            artigo será removido permanentemente da base de conhecimento, e esta
            ação não pode ser desfeita.
          </p>
        </div>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleteLoading}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={handleDelete} loading={deleteLoading}>
            Excluir
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
