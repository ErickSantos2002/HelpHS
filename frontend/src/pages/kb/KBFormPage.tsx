import { useEffect, useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toastApiError } from "../../lib/toastError";
import { renderMarkdown } from "../../lib/markdown";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Icon,
  Input,
  Select,
  Spinner,
  Textarea,
  type BadgeProps,
} from "../../components/ui";
import { CATEGORIAS, rotuloDeCategoria } from "../../lib/categoria";
import { useAuth } from "../../contexts/AuthContext";
import {
  createKBArticle,
  getKBArticle,
  updateKBArticle,
  type KBArticleStatus,
} from "../../services/kbService";
import { getProducts, type Product } from "../../services/productService";

// ── Constants ─────────────────────────────────────────────────

/**
 * As categorias saem de `lib/categoria.ts`, e não da quinta cópia.
 *
 * O mapa local desta tela repetia, valor a valor, o que a `TicketFormPage`, a
 * `TicketDetailPage`, a `ReportsPage` e a `KBArticlePage` já liam do módulo.
 * As cinco diziam a mesma coisa hoje — e é exatamente por isso que valia
 * unificar antes de divergirem, que foi o que aconteceu com prioridade em dez
 * mapas e com status em três.
 *
 * A lista de opções nasce no módulo e é derivada uma vez, fora do componente:
 * derivá-la a cada render criaria um array novo por render sem nenhum ganho.
 */
const OPCOES_DE_CATEGORIA = CATEGORIAS.map((c) => ({
  value: c.value,
  label: c.label,
}));

/**
 * Os três estados de um artigo da base — e este mapa continua LOCAL de
 * propósito.
 *
 * `lib/status.ts` é a fonte única do status de CHAMADO: sete valores, outro
 * vocabulário, outro ciclo de vida. Estado de ARTIGO
 * (rascunho/publicado/arquivado) não tem módulo nenhum, e criar um significa
 * escrever em `src/lib/`, que está fora do escopo desta tela. Fica aqui, e o
 * operador foi avisado — a `KBListPage` tem a segunda cópia, com os mesmos
 * três hexadecimais que saíram daqui.
 *
 * ── O que os três hexadecimais eram ───────────────────────────────────
 *
 * `#f59e0b`, `#10b981` e `#64748b` são amber-500, emerald-500 e slate-500: os
 * três eram **decisão de desenho** cravada em `style`, nenhum era dado vindo
 * da rede. Viraram token, na força de PREENCHIMENTO da E19 — o degrau 500 cheio
 * reprova o piso de 3:1 da WCAG 1.4.11 no tema claro (warning 1,96; success
 * 2,54) e degrau fixo não inverte por tema. O neutro do "Arquivado" virou
 * `--border-control`, que **é** slate-500 desde a E7: mesmo valor, agora com
 * nome.
 *
 * ── As classes vão por EXTENSO, e isso não é estilo ───────────────────
 *
 * O Tailwind gera utilitário varrendo o texto do arquivo. `"bg-fill-" + tom`
 * some da varredura, a regra não nasce, o ponto fica sem cor — e não há erro
 * nem aviso.
 */
interface EstadoDoArtigo {
  value: KBArticleStatus;
  label: string;
  /** A variante do `Badge`: o vocabulário do primitivo, não um segundo. */
  variante: NonNullable<BadgeProps["variant"]>;
  /** Classe de fundo do ponto, escrita por extenso. */
  ponto: string;
}

const ESTADOS_DO_ARTIGO: readonly EstadoDoArtigo[] = [
  { value: "draft", label: "Rascunho", variante: "warning", ponto: "bg-fill-warning" },
  { value: "published", label: "Publicado", variante: "success", ponto: "bg-fill-success" },
  { value: "archived", label: "Arquivado", variante: "secondary", ponto: "bg-borda-control" },
];

const OPCOES_DE_ESTADO = ESTADOS_DO_ARTIGO.map((e) => ({
  value: e.value,
  label: e.label,
}));

/**
 * O estado com recuo para neutro, pelo mesmo motivo do `PriorityBadge`: o dado
 * vem da REDE, e um estado novo no backend não pode derrubar a tela nem pintar
 * de verde algo que não se sabe o que é.
 */
function estadoDoArtigo(valor: string): EstadoDoArtigo {
  return (
    ESTADOS_DO_ARTIGO.find((e) => e.value === valor) ?? {
      value: "draft",
      label: valor,
      variante: "secondary",
      ponto: "bg-borda-control",
    }
  );
}

// ── Content editor ────────────────────────────────────────────

function ContentEditor({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  const [tab, setTab] = useState<"write" | "preview">("write");
  // O rótulo era um `<label>` sem `htmlFor` sobre um `Textarea` que gera o
  // próprio `id` internamente: visualmente colados, sem relação nenhuma para
  // um leitor de tela. O `id` nasce aqui e vai para os dois.
  const idConteudo = useId();
  const html = renderMarkdown(value);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        {/*
          Enquanto a aba de pré-visualização está aberta o campo não existe no
          DOM, e o `htmlFor` fica apontando para nada — inerte, sem efeito
          colateral. O rótulo volta a nomear o campo junto com a aba "Editar",
          que é onde se digita.
        */}
        <label htmlFor={idConteudo} className="text-sm font-medium text-conteudo">
          Conteúdo <span className="text-on-tint-danger">*</span>
        </label>
        <div className="flex rounded-lg border border-borda/50 overflow-hidden text-xs">
          {/*
            As duas abas são um alternador de dois estados, e o estado só era
            dito pela tinta. `aria-pressed` diz qual está aberta a quem não vê
            a tinta — mesma correção dos botões de voto da `KBArticlePage`.
          */}
          <button
            type="button"
            onClick={() => setTab("write")}
            aria-pressed={tab === "write"}
            className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors cursor-pointer ${tab === "write" ? "bg-surface-elevated text-conteudo-heading" : "text-conteudo-muted hover:text-conteudo"}`}
          >
            <Icon name="edit" size={14} strokeWidth={2} /> Editar
          </button>
          <button
            type="button"
            onClick={() => setTab("preview")}
            aria-pressed={tab === "preview"}
            className={`flex items-center gap-1.5 px-3 py-1.5 border-l border-borda/50 transition-colors cursor-pointer ${tab === "preview" ? "bg-surface-elevated text-conteudo-heading" : "text-conteudo-muted hover:text-conteudo"}`}
          >
            <Icon name="eye" size={14} strokeWidth={2} /> Preview
          </button>
        </div>
      </div>

      {tab === "write" ? (
        // A ajuda de Markdown era um `<p>` solto ao lado do campo: junto na
        // tela, sem relação nenhuma na árvore de acessibilidade. Como `hint`
        // ela entra no `aria-describedby` do primitivo — e cede a vez ao erro
        // quando há erro, que é a regra do `Input`/`Textarea` do pacote.
        <Textarea
          id={idConteudo}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={"## Título\n\nDescrição do problema...\n\n### Solução\n\n1. Passo um\n2. Passo dois\n\n**Nota:** informação importante"}
          rows={18}
          error={error}
          hint="Suporta Markdown: **negrito**, *itálico*, ## títulos, listas, `código`, links"
        />
      ) : (
        <div className="min-h-[460px] rounded-xl border border-borda/40 bg-surface-elevated/60 px-5 py-4">
          {value.trim() ? (
            /*
              ⚠️ Nenhuma das classes `prose-*` abaixo gera CSS neste projeto.

              O `@tailwindcss/typography` não está no `package.json` nem em
              `plugins: []` do `tailwind.config.js`, e não existe regra `.prose`
              em `index.css` nem no pacote. A pré-visualização é renderizada
              **sem estilo nenhum** desde sempre — e ela mente por isso: mostra
              ao autor uma aparência que não é a que o artigo terá.

              É o mesmo achado da `KBArticlePage`, que exibe o corpo do artigo
              com este mesmo bloco. As classes ficam, traduzidas para os mesmos
              tokens que ela usa, por dois motivos: são a única declaração
              escrita de como o corpo deveria parecer, e é o que fecha a tela em
              zero paleta crua. Instalar o plugin mexe em `package.json` e em
              `tailwind.config.js`, os dois fora do escopo desta tela.

              O aviso de lá vale aqui: `prose-invert` está cravado **sem**
              `dark:`, o que inverteria o corpo no tema CLARO.
            */
            <div
              className="prose prose-invert prose-sm max-w-none
                prose-headings:text-conteudo-heading prose-headings:font-semibold
                prose-p:text-conteudo prose-p:leading-relaxed
                prose-a:text-conteudo-link prose-a:no-underline hover:prose-a:underline
                prose-strong:text-conteudo-heading
                prose-code:text-conteudo-link prose-code:bg-surface-elevated prose-code:px-1 prose-code:rounded
                prose-pre:bg-surface-elevated prose-pre:border prose-pre:border-borda
                prose-ul:text-conteudo prose-ol:text-conteudo
                prose-blockquote:border-l-action prose-blockquote:text-conteudo-muted
                prose-hr:border-borda"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          ) : (
            <p className="text-sm italic text-conteudo-muted">Nada para pré-visualizar ainda…</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── FormSection ───────────────────────────────────────────────

/**
 * A casca é `Card padding="none"`, com o cabeçalho e o corpo por dentro — a
 * mesma composição que a `KBArticlePage` usa nos dois cartões da coluna
 * principal. A borda passa de `borda/40` para `borda` cheia, que é o que o
 * `Card` desenha.
 */
function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card padding="none">
      <div className="border-b border-borda/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-conteudo">{title}</h2>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </Card>
  );
}

// ── Main ──────────────────────────────────────────────────────

export default function KBFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isEdit = Boolean(id);

  const isStaff = user?.role === "admin" || user?.role === "technician";

  const [title, setTitle]           = useState("");
  const [content, setContent]       = useState("");
  const [category, setCategory]     = useState("general");
  const [status, setStatus]         = useState<KBArticleStatus>("draft");
  const [tagsInput, setTagsInput]   = useState("");
  const [loading, setLoading]       = useState(false);
  const [loadingArticle, setLoadingArticle] = useState(isEdit);
  const [errors, setErrors]         = useState<Record<string, string>>({});

  const [products, setProducts] = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [selectedProductIds, setSelectedProductIds] = useState<Set<string>>(new Set());
  // Artigo novo já nasce como "todos os produtos"; ao editar, quem manda é o artigo
  const [allProducts, setAllProducts] = useState(true);

  // O grupo de produtos não é um campo: é um conjunto de controles. Ele se
  // identifica por `<legend>` e se descreve por estes dois ids — o erro e a
  // regra de exibição —, que é o que o `Input`/`Textarea` fazem sozinhos e um
  // `<fieldset>` precisa que alguém faça.
  const idErroProdutos = useId();
  const idAjudaProdutos = useId();
  const idTags = useId();

  useEffect(() => {
    if (!isStaff) return;
    getProducts({ limit: 100 })
      .then((res) => setProducts(res.items))
      .catch(() => setProducts([]))
      .finally(() => setLoadingProducts(false));
  }, [isStaff]);

  // Redireciona quem não é staff — depois dos hooks, para não alterar a ordem
  // deles entre renders (o usuário chega null enquanto a sessão carrega).
  useEffect(() => {
    if (user && !isStaff) navigate("/403", { replace: true });
  }, [user, isStaff, navigate]);

  useEffect(() => {
    if (!id || !isStaff) return;
    getKBArticle(id)
      .then((a) => {
        setTitle(a.title); setContent(a.content); setCategory(a.category);
        setStatus(a.status); setTagsInput(a.tags.join(", "));
        setSelectedProductIds(new Set(a.products.map((p) => p.id)));
        setAllProducts(a.products.length === 0);
      })
      .catch(() => navigate("/kb"))
      .finally(() => setLoadingArticle(false));
  }, [id, isStaff, navigate]);

  if (!isStaff) return null;

  function validate() {
    const errs: Record<string, string> = {};
    if (!title.trim()) errs.title = "Título é obrigatório";
    if (!content.trim()) errs.content = "Conteúdo é obrigatório";
    if (!allProducts && selectedProductIds.size === 0) {
      errs.products = "Selecione ao menos um produto ou marque \"Vale para todos os produtos\".";
    }
    return errs;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    const tags = tagsInput.split(",").map((t) => t.trim()).filter(Boolean);
    // Lista vazia é como o backend representa "vale para todos os produtos"
    const product_ids = allProducts ? [] : [...selectedProductIds];
    setLoading(true);
    try {
      if (isEdit && id) {
        await updateKBArticle(id, { title, content, category, tags, status, product_ids });
        navigate(`/kb/${id}`);
      } else {
        const article = await createKBArticle({ title, content, category, tags, status, product_ids });
        navigate(`/kb/${article.id}`);
      }
    } catch (err) {
      toastApiError(err, "Erro ao salvar artigo. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }

  if (loadingArticle) {
    return <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>;
  }

  const estado = estadoDoArtigo(status);
  const catLabel = rotuloDeCategoria(category);
  const destinoDeSaida = id ? `/kb/${id}` : "/kb";

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="min-w-0">
          {/*
            A trilha era UM botão com a linha inteira dentro: o nome acessível
            do controle era "Base de Conhecimento / <título>", duas páginas num
            controle só, e ele levava as duas para o MESMO destino. Mesma
            correção da `KBArticlePage` e do `TicketDetailPage` — o que navega é
            link, e cada link leva só o nome do seu destino. Aqui os dois
            destinos são páginas de verdade e diferentes: a lista e o artigo. A
            página onde se está ("Editar artigo") é o `h1`, e não entra na
            trilha.
          */}
          <nav
            aria-label="Trilha"
            className="mb-2 flex items-center gap-1.5 text-xs font-medium"
          >
            <Link
              to="/kb"
              className="inline-flex items-center gap-1.5 text-conteudo-muted hover:text-conteudo-link transition-colors"
            >
              <Icon name="arrowLeft" size={14} strokeWidth={2.5} />
              <span>Base de Conhecimento</span>
            </Link>
            {id && (
              <>
                <span aria-hidden="true" className="text-conteudo-faint">/</span>
                <Link
                  to={`/kb/${id}`}
                  className="truncate max-w-xs text-conteudo-muted hover:text-conteudo-link transition-colors"
                >
                  {title || "Artigo"}
                </Link>
              </>
            )}
          </nav>
          <h1 className="text-xl font-extrabold text-conteudo-heading">{isEdit ? "Editar artigo" : "Novo artigo"}</h1>
          <p className="mt-1 text-sm text-conteudo-muted">{isEdit ? "Atualize o conteúdo do artigo." : "Preencha as informações para criar um novo artigo."}</p>
        </div>
      </div>


      {/* ── Body ─────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_300px]">
          {/* ── Main column ─────────────────────────────────── */}
          <div className="space-y-4 min-w-0">
            <FormSection title="Informações">
              <div className="space-y-1">
                <Input
                  label="Título *"
                  value={title}
                  onChange={(e) => { setTitle(e.target.value); setErrors((p) => ({ ...p, title: "" })); }}
                  placeholder="Título do artigo"
                  error={errors.title}
                />
              </div>

              {/*
                Os dois `<select>` à mão viraram o primitivo `Select`. Cada um
                tinha um `<label>` SEM `htmlFor` e um campo SEM `id`: os dois
                rótulos não pertenciam a campo nenhum, e quem navega por leitor
                de tela ouvia "caixa de combinação" sem saber de quê. O
                primitivo amarra os dois, e ainda traz a seta pelo `Icon` — a
                anterior era um data URI com `stroke='%2394a3b8'` cravado, que
                não segue o tema.
              */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Select
                  id="kb-categoria"
                  label="Categoria"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  options={OPCOES_DE_CATEGORIA}
                />
                <Select
                  id="kb-status"
                  label="Status"
                  value={status}
                  onChange={(e) => setStatus(e.target.value as KBArticleStatus)}
                  options={OPCOES_DE_ESTADO}
                />
              </div>

              {/*
                Era um `<label>` sobre um GRUPO de controles — uma caixa de
                seleção mais N botões. `<label>` nomeia UM campo; o que nomeia
                um conjunto é `<legend>` dentro de `<fieldset>`, e é o que o
                navegador anuncia ao entrar no grupo.
              */}
              <fieldset
                className="space-y-1.5"
                aria-describedby={
                  errors.products
                    ? `${idErroProdutos} ${idAjudaProdutos}`
                    : idAjudaProdutos
                }
              >
                <legend className="text-sm font-medium text-conteudo">
                  Produtos <span className="text-on-tint-danger">*</span>
                </legend>

                <Checkbox
                  checked={allProducts}
                  onChange={(todos) => {
                    setAllProducts(todos);
                    if (todos) setSelectedProductIds(new Set());
                    setErrors((p) => ({ ...p, products: "" }));
                  }}
                  label="Vale para todos os produtos"
                  className="w-fit items-center"
                />

                {!allProducts && (
                  loadingProducts ? (
                    <p className="text-xs text-conteudo-muted">Carregando produtos…</p>
                  ) : products.length === 0 ? (
                    <p className="text-xs text-conteudo-muted">Nenhum produto cadastrado.</p>
                  ) : (
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {products.map((p) => {
                        const sel = selectedProductIds.has(p.id);
                        return (
                          <button
                            key={p.id}
                            type="button"
                            aria-pressed={sel}
                            onClick={() => {
                              setSelectedProductIds((prev) => {
                                const n = new Set(prev);
                                if (n.has(p.id)) n.delete(p.id); else n.add(p.id);
                                return n;
                              });
                              setErrors((prev) => ({ ...prev, products: "" }));
                            }}
                            /*
                              Marcado era `bg-primary` com `text-white`: 3,83:1
                              nos DOIS temas, porque o degrau 500 é absoluto e
                              não inverte. É o par que a catraca cobrava nesta
                              tela. Passou para o degrau de AÇÃO com o par dele
                              (`--action` / `--text-on-primary`), que é branco
                              no claro e navy no escuro.

                              Não marcado, a borda saiu de `borda/60` — um
                              separador de superfície, ~1,2:1 — para
                              `--border-control` da E7, que é o contorno de
                              CONTROLE e cumpre os 3:1 da WCAG 1.4.11.
                            */
                            className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold transition-all cursor-pointer ${
                              sel
                                ? "border-action bg-action text-on-primary shadow-sm"
                                : "border-borda-control bg-surface-elevated text-conteudo-muted hover:border-action hover:text-conteudo"
                            }`}
                          >
                            {sel && <Icon name="check" size={12} strokeWidth={2.5} />}
                            <span className="truncate">{p.name}</span>
                          </button>
                        );
                      })}
                    </div>
                  )
                )}

                {errors.products && (
                  <p id={idErroProdutos} className="text-xs text-on-tint-danger">
                    {errors.products}
                  </p>
                )}
                <p id={idAjudaProdutos} className="text-xs text-conteudo-muted">
                  O artigo aparece para o cliente quando o produto do chamado bate com um destes
                  — ou quando a categoria bate.
                </p>
              </fieldset>

              <div className="space-y-1">
                {/*
                  O rótulo fica à mão porque tem marcação por dentro — o
                  "(separadas por vírgula)" em peso normal — e a prop `label`
                  do primitivo é `string`. O que faltava era o `htmlFor`, e ele
                  agora aponta para o `id` que o campo recebe. A segunda linha
                  virou `hint`, que o primitivo liga por `aria-describedby`.
                */}
                <label htmlFor={idTags} className="text-sm font-medium text-conteudo">
                  Tags <span className="font-normal text-conteudo-muted">(separadas por vírgula)</span>
                </label>
                <Input
                  id={idTags}
                  value={tagsInput}
                  onChange={(e) => setTagsInput(e.target.value)}
                  placeholder="ex: acesso, vpn, senha"
                  hint="Tags ajudam os usuários a encontrar o artigo nas buscas."
                />
              </div>
            </FormSection>

            <FormSection title="Conteúdo">
              <ContentEditor
                value={content}
                onChange={(v) => { setContent(v); setErrors((p) => ({ ...p, content: "" })); }}
                error={errors.content}
              />
            </FormSection>

            <div className="flex justify-end gap-3 pt-1">
              {/* Cancelar sai da tela: navegação é link, ação é botão. */}
              <Button to={destinoDeSaida} variant="secondary">Cancelar</Button>
              <Button type="submit" loading={loading}>{isEdit ? "Salvar alterações" : "Criar artigo"}</Button>
            </div>
          </div>

          {/* ── Sidebar ─────────────────────────────────────── */}
          <div className="space-y-4">
            <Card>
              <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">Resumo</p>
              <div className="space-y-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-conteudo-muted mb-0.5">Título</p>
                  <p className="text-sm text-conteudo line-clamp-2">{title || <span className="italic text-conteudo-muted">Não preenchido</span>}</p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-conteudo-muted mb-0.5">Categoria</p>
                  <p className="text-sm text-conteudo">{catLabel}</p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-conteudo-muted mb-1">Status</p>
                  {/*
                    O selo era desenhado à mão com `bg-success/10` mais
                    `text-success-700 dark:text-success-400` — a rampa a 10% com
                    a inversão de tema escrita à mão. O `Badge` já faz isso com
                    o par medido da E8 (`--tint-*` com `--on-tint-*`), e o
                    "Arquivado" era o segundo par da catraca: `text-slate-500`
                    sobre `bg-surface-elevated`, 2,85:1 no escuro.
                  */}
                  <Badge variant={estado.variante} className="gap-1.5">
                    <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${estado.ponto}`} />
                    {estado.label}
                  </Badge>
                </div>
                {tagsInput.trim() && (
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-conteudo-muted mb-1">Tags</p>
                    <div className="flex flex-wrap gap-1">
                      {tagsInput.split(",").map((t) => t.trim()).filter(Boolean).map((tag) => (
                        <Badge key={tag} variant="secondary">{tag}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>

            <Card>
              <p className="mb-3 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">
                <Icon name="info" size={16} strokeWidth={2} /> Dicas
              </p>
              {/*
                O marcador é desenho, não informação — o texto do item já diz
                tudo —, então ele sai da leitura por `aria-hidden`. A cor era
                `text-primary`, o degrau de MARCA, que sobre a superfície dá
                3,66:1 e reprova AA para texto; `--text-link` é o degrau
                legível da mesma família (5,05:1 no claro, 6,47:1 no escuro).
              */}
              <ul className="space-y-2 text-xs text-conteudo-muted">
                <li className="flex gap-2"><span aria-hidden="true" className="text-conteudo-link shrink-0 mt-0.5">•</span>Use títulos claros e objetivos.</li>
                <li className="flex gap-2"><span aria-hidden="true" className="text-conteudo-link shrink-0 mt-0.5">•</span>Estruture o conteúdo com títulos (##) e listas para facilitar a leitura.</li>
                <li className="flex gap-2"><span aria-hidden="true" className="text-conteudo-link shrink-0 mt-0.5">•</span>Salve como Rascunho para revisar antes de publicar.</li>
                <li className="flex gap-2"><span aria-hidden="true" className="text-conteudo-link shrink-0 mt-0.5">•</span>Tags ajudam os usuários a encontrar o artigo.</li>
              </ul>
            </Card>
          </div>
        </div>
      </form>
    </div>
  );
}
