import React from "react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { toastApiError } from "../../lib/toastError";
import {
  Avatar,
  Badge,
  Button,
  Card,
  Icon,
  Spinner,
} from "../../components/ui";
import { rotuloDeCategoria } from "../../lib/categoria";
import { rotuloDePapel, varianteDePapel } from "../../lib/papel";
import { plural } from "../../lib/utils";
import { renderMarkdown } from "../../lib/markdown";
import { useAuth } from "../../contexts/AuthContext";
import {
  createKBComment,
  deleteKBComment,
  getKBArticle,
  getKBComments,
  submitKBFeedback,
  type KBArticle,
  type KBComment,
} from "../../services/kbService";

/**
 * Os dois polegares, apontados por nome e não por posição no arquivo.
 *
 * Estas duas constantes nasceram de um defeito real: a **E21** subiu os dois
 * ícones a partir desta tela e **inverteu os nomes** — o traçado guardado em
 * `thumbsUp` era o polegar para baixo. Quem migrou esta tela casou pelo
 * **traçado**, como o contrato manda, e isolou a inversão aqui em vez de
 * espalhá-la por quatro chamadas: ficava absurdo de ler e certo de ver.
 *
 * A **E21-b** consertou o pacote, e o conserto desceu para cá invertendo estas
 * duas linhas. As constantes ficam porque continuam sendo a coisa certa: o
 * ponto de uso diz o que o desenho FAZ, não como o pacote o chamou.
 *
 * O que fez o defeito ser achável: os dois aparecem lado a lado, num "Sim" e
 * num "Não". Foi o único lugar do sistema onde a troca produzia sintoma —
 * contagem, unicidade e hash passaram verdes com ela.
 */
const TRACO_POLEGAR_PARA_CIMA = "thumbsUp" as const;
const TRACO_POLEGAR_PARA_BAIXO = "thumbsDown" as const;

// ── Markdown ──────────────────────────────────────────────────

/**
 * ⚠️ Nenhuma das classes `prose-*` abaixo gera CSS neste projeto.
 *
 * O `@tailwindcss/typography` não está no `package.json` nem em
 * `plugins: []` do `tailwind.config.js`, e não existe regra `.prose` em
 * `index.css` nem no pacote. Ou seja: o corpo do artigo é renderizado **sem
 * estilo nenhum** desde sempre — título com o tamanho padrão do navegador,
 * link azul sublinhado do agente, bloco de código sem fundo.
 *
 * As classes ficam, traduzidas para os tokens, por dois motivos: elas são a
 * única declaração escrita de como o corpo do artigo deveria parecer, e trocar
 * `slate-*` por token aqui é o que fecha a tela em zero paleta crua. Instalar o
 * plugin mexe em `package.json` e em `tailwind.config.js`, os dois fora do
 * escopo desta tela.
 *
 * Dois avisos para quem instalar: `prose-invert` está cravado sem `dark:`, o
 * que inverteria o corpo no tema CLARO, e a altura do bloco é limitada a 15rem
 * com rolagem — as duas coisas precisam de decisão antes de o plugin entrar.
 */
function MarkdownContent({ content }: { content: string }) {
  const html = renderMarkdown(content);
  return (
    <div
      className="prose prose-invert prose-sm max-w-none [overflow-wrap:anywhere] [word-break:break-word]
        prose-headings:text-conteudo-heading prose-headings:font-semibold
        prose-p:text-conteudo prose-p:leading-relaxed
        prose-a:text-conteudo-link prose-a:no-underline hover:prose-a:underline
        prose-strong:text-conteudo-heading
        prose-code:text-conteudo-link prose-code:bg-surface-elevated prose-code:px-1 prose-code:rounded
        prose-pre:bg-surface-elevated prose-pre:border prose-pre:border-borda prose-pre:overflow-x-auto
        prose-ul:text-conteudo prose-ol:text-conteudo
        prose-li:marker:text-conteudo-muted
        prose-blockquote:border-l-action prose-blockquote:text-conteudo-muted
        prose-hr:border-borda"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ── Comment form ──────────────────────────────────────────────

function CommentForm({
  onSubmit,
  placeholder = "Deixe um comentário…",
  rotulo = "Comentário",
  autoFocus = false,
  onCancel,
}: {
  onSubmit: (content: string) => Promise<void>;
  placeholder?: string;
  /**
   * O nome acessível do campo.
   *
   * O campo se identificava só pelo `placeholder` — o texto que some
   * exatamente quando a pessoa começa a digitar, e que em leitor de tela vale
   * como dica, não como nome. Item fixo do CHECKLIST-29.
   */
  rotulo?: string;
  autoFocus?: boolean;
  onCancel?: () => void;
  submitLabel?: string;
}) {
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { if (autoFocus) textareaRef.current?.focus(); }, [autoFocus]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = content.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try { await onSubmit(trimmed); setContent(""); }
    finally { setSubmitting(false); }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex items-center gap-2">
        {/*
          Não é o primitivo `Textarea`: ele embrulha o campo num `div` de
          coluna e crava `resize-y min-h-[80px]`, e o `cn` do projeto é
          concatenação simples — sem `tailwind-merge`, `resize-none` e
          `resize-y` sairiam os dois no atributo e quem decide vira a ordem do
          CSS gerado. Este campo é de uma linha que cresce até 6rem dentro de
          uma linha de flex, e a geometria não sobreviveria à troca.

          A borda vem de `--border-control` (E7) e não do `borda/60` de antes:
          o contorno de um CONTROLE pede 3:1 pela 1.4.11, e o separador de
          superfície a 60% dava perto de 1,2:1.
        */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={placeholder}
          aria-label={rotulo}
          className="flex-1 resize-none rounded-lg border border-borda-control bg-surface-elevated px-3 py-2 text-sm text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-action focus:border-transparent transition-colors max-h-24 overflow-y-auto leading-relaxed break-words"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e as unknown as React.FormEvent);
            }
          }}
        />
        {/*
          O botão não tinha nome acessível nenhum: dentro dele só havia um
          `<svg>`, e o `Icon` é `aria-hidden`. Quem navega por leitor de tela
          ouvia "botão" e mais nada.
        */}
        <Button
          type="submit"
          aria-label={`Enviar ${rotulo.toLowerCase()}`}
          disabled={!content.trim() || submitting}
          className="shrink-0"
        >
          <Icon name="send" size={16} strokeWidth={2} />
        </Button>
      </div>
      {onCancel && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="text-xs text-conteudo-muted hover:text-conteudo transition-colors cursor-pointer"
          >
            Cancelar
          </button>
        </div>
      )}
      <p className="text-xs text-conteudo-muted">
        Enter para enviar · Shift+Enter para nova linha
      </p>
    </form>
  );
}

// ── Comment item ──────────────────────────────────────────────

function CommentItem({ comment, currentUserId, isStaff, onReply, onDelete }: {
  comment: KBComment; currentUserId?: string; currentUserRole?: string;
  isStaff: boolean; onReply: (parentId: string, content: string) => Promise<void>;
  onDelete: (commentId: string) => Promise<void>;
}) {
  const [showReplyForm, setShowReplyForm] = useState(false);
  const [showReplies, setShowReplies] = useState(false);
  const canDelete = isStaff || (comment.replies.length === 0 && comment.author_id === currentUserId);
  const date = new Date(comment.created_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const replyCount = comment.replies.length;

  return (
    <div className="space-y-3">
      <div className="flex gap-3">
        <Avatar name={comment.author_name} size="sm" />
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-conteudo">
              {comment.author_name}
            </span>
            {/*
              O papel sai de `lib/papel.ts`. A cópia local desta tela era a
              sexta, e era a que divergia no TEXTO: dizia "Admin" onde as
              outras cinco dizem "Administrador".
            */}
            {comment.author_role && (
              <Badge variant={varianteDePapel(comment.author_role)}>
                {rotuloDePapel(comment.author_role)}
              </Badge>
            )}
            <span className="text-xs text-conteudo-muted">{date}</span>
          </div>
          <p className="text-sm text-conteudo leading-relaxed whitespace-pre-wrap break-words">
            {comment.content}
          </p>
          <div className="flex items-center gap-3 mt-2">
            {!comment.parent_id && (
              <button
                onClick={() => setShowReplyForm((v) => !v)}
                aria-expanded={showReplyForm}
                className="text-xs text-conteudo-muted hover:text-conteudo-link transition-colors cursor-pointer"
              >
                Responder
              </button>
            )}
            {replyCount > 0 && (
              <button
                onClick={() => setShowReplies((v) => !v)}
                aria-expanded={showReplies}
                className="flex items-center gap-1 text-xs text-conteudo-muted hover:text-conteudo transition-colors cursor-pointer"
              >
                <Icon
                  name="chevronDown"
                  size={12}
                  strokeWidth={2.5}
                  className={`transition-transform duration-150 ${showReplies ? "rotate-180" : ""}`}
                />
                {showReplies ? "Ocultar" : "Ver"} {replyCount} resposta
                {replyCount !== 1 ? "s" : ""}
              </button>
            )}
            {canDelete && (
              <button
                onClick={() => onDelete(comment.id)}
                className="text-xs text-conteudo-muted hover:text-on-tint-danger transition-colors cursor-pointer"
              >
                Excluir
              </button>
            )}
          </div>
        </div>
      </div>

      {showReplyForm && (
        <div className="ml-11">
          <CommentForm
            placeholder="Escreva uma resposta…"
            rotulo="Resposta"
            autoFocus
            submitLabel="Responder"
            onCancel={() => setShowReplyForm(false)}
            onSubmit={async (content) => {
              await onReply(comment.id, content);
              setShowReplyForm(false);
            }}
          />
        </div>
      )}

      {showReplies && replyCount > 0 && (
        <div className="ml-11 space-y-4 border-l-2 border-borda/40 pl-4">
          {comment.replies.map((reply) => (
            <CommentItem
              key={reply.id}
              comment={reply}
              currentUserId={currentUserId}
              isStaff={isStaff}
              onReply={onReply}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Sidebar prop row ──────────────────────────────────────────

function PropRow({ icon, label, children }: { icon: React.JSX.Element; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-borda/30 last:border-0">
      <span className="mt-0.5 shrink-0 text-conteudo-muted">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-widest text-conteudo-muted">
          {label}
        </p>
        <div className="text-sm font-medium text-conteudo">{children}</div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────

export default function KBArticlePage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const isStaff = user?.role === "admin" || user?.role === "technician";

  const [article, setArticle] = useState<KBArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<boolean | null>(null);
  const [comments, setComments] = useState<KBComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    getKBArticle(id).then(setArticle).catch(() => setNotFound(true)).finally(() => setLoading(false));
    getKBComments(id).then(setComments).catch(() => toast.error("Erro ao carregar comentários.")).finally(() => setCommentsLoading(false));
  }, [id]);

  async function handleFeedback(helpful: boolean) {
    if (!id || feedbackGiven !== null) return;
    await submitKBFeedback(id, helpful);
    setFeedbackGiven(helpful);
    setArticle((prev) => prev ? { ...prev, helpful: helpful ? prev.helpful + 1 : prev.helpful, not_helpful: !helpful ? prev.not_helpful + 1 : prev.not_helpful } : prev);
  }

  async function handleAddComment(content: string) {
    if (!id) return;
    try {
      const comment = await createKBComment(id, content);
      setComments((prev) => [comment, ...prev]);
    } catch (err) {
      toastApiError(err, "Não foi possível salvar o comentário.");
      throw new Error("comment_failed");
    }
  }

  async function handleReply(parentId: string, content: string) {
    if (!id) return;
    try {
      const reply = await createKBComment(id, content, parentId);
      setComments((prev) => prev.map((c) => c.id === parentId ? { ...c, replies: [...c.replies, reply] } : c));
    } catch (err) {
      toastApiError(err, "Não foi possível salvar a resposta.");
      throw new Error("reply_failed");
    }
  }

  /**
   * Exclui o comentario, e so entao o tira da lista.
   *
   * O `await` estava SOLTO aqui, e a ordem era a inversa da segura: a lista era
   * filtrada logo depois da chamada, sem saber se ela tinha dado certo. Uma
   * falha de rede rejeitava a promessa sem tratamento, o comentario continuava
   * no servidor, **e a tela mostrava removido o que continuava la** — o usuario
   * so descobria ao recarregar.
   *
   * A forma e a das irmas deste mesmo arquivo (`handleAddComment`,
   * `handleReply`): o estado local muda DENTRO do `try`, depois do `await`.
   *
   * Nao relanca, ao contrario das irmas: elas relancam para o formulario saber
   * que nao deve limpar o campo. Aqui nao ha campo — o que a lixeira precisa e
   * que a lista NAO mude, e isso o `catch` ja garante.
   */
  async function handleDeleteComment(commentId: string) {
    try {
      await deleteKBComment(commentId);
      setComments((prev) => prev.filter((c) => c.id !== commentId).map((c) => ({ ...c, replies: c.replies.filter((r) => r.id !== commentId) })));
    } catch (err) {
      toastApiError(err, "Não foi possível excluir o comentário.");
    }
  }

  const totalComments = comments.reduce((acc, c) => acc + 1 + c.replies.length, 0);

  if (loading) return <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>;

  if (notFound || !article) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <p className="text-conteudo-muted mb-2">Artigo não encontrado.</p>
        {/* Navegação é link: o `onClick={navigate("/kb")}` tirava daqui abrir
            em aba nova, menu de contexto e o destino na barra de status. */}
        <Link
          to="/kb"
          className="text-conteudo-link text-sm hover:text-conteudo-link-hover cursor-pointer transition-colors"
        >
          Voltar à Base de Conhecimento
        </Link>
      </div>
    );
  }

  const formattedDate = new Date(article.updated_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
  const catLabel = rotuloDeCategoria(article.category);

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="min-w-0 text-center sm:text-left">
          {/*
            A trilha era UM botão com a linha inteira dentro, então o nome
            acessível do controle era "Base de Conhecimento / <título do
            artigo>" — a página de onde se vem e a página onde se está, num
            controle só. Mesmo defeito, mesma correção do `TicketDetailPage`:
            o que navega é link e leva só o nome do destino; o título do artigo
            é texto, porque a página já está nele.
          */}
          <nav
            aria-label="Trilha"
            className="mb-2 flex items-center justify-center gap-1.5 text-xs font-medium sm:justify-start"
          >
            <Link
              to="/kb"
              className="inline-flex items-center gap-1.5 text-conteudo-muted hover:text-conteudo-link transition-colors"
            >
              <Icon name="arrowLeft" size={14} strokeWidth={2.5} />
              <span>Base de Conhecimento</span>
            </Link>
            <span aria-hidden="true" className="text-conteudo-faint">
              /
            </span>
            <span className="text-conteudo-muted truncate max-w-[160px] sm:max-w-xs">
              {article.title}
            </span>
          </nav>
          <h1 className="text-xl font-extrabold leading-tight text-conteudo-heading break-words [overflow-wrap:anywhere]">
            {article.title}
          </h1>
        </div>
        {isStaff && (
          <div className="flex justify-center sm:justify-end">
            <Button
              to={`/kb/${article.id}/edit`}
              variant="secondary"
              icon={<Icon name="edit" size={14} strokeWidth={2} />}
            >
              Editar artigo
            </Button>
          </div>
        )}
      </div>

      {/* ── Body ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_260px]">
        {/* ── Main column ───────────────────────────────────── */}
        <div className="flex flex-col gap-5 min-w-0">
          {/* Article content */}
          <Card padding="none" className="overflow-hidden">
            <div className="px-6 pt-5 pb-0">
              <div className="max-h-[15rem] overflow-y-auto pb-5 pr-1">
                <MarkdownContent content={article.content} />
              </div>
            </div>

            {/*
              Feedback. Os dois botões são de escolha única e irreversível: o
              primeiro clique desabilita os dois, e por isso `aria-pressed`
              conta o estado — sem ele, quem não vê a tinta não sabe qual dos
              dois foi o voto.

              A tinta é o par medido (`--tint-*` com `--on-tint-*`) e não a
              rampa a 10% com o degrau 700/400 por cima: são os mesmos valores
              que o `Badge` usa desde a E8, e o `text-success-700
              dark:text-success-400` de antes escrevia à mão a inversão que o
              token já faz sozinho.
            */}
            <div className="border-t border-borda/40 px-6 py-5 flex flex-col items-center gap-3 text-center">
              <span className="text-sm text-conteudo-muted">
                Este artigo foi útil?
              </span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleFeedback(true)}
                  disabled={feedbackGiven !== null}
                  aria-pressed={feedbackGiven === true}
                  className={`flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg border transition-colors cursor-pointer disabled:cursor-not-allowed ${
                    feedbackGiven === true
                      ? "border-success/30 bg-tint-success text-on-tint-success"
                      : "border-borda text-conteudo-muted hover:border-success/30 hover:text-on-tint-success disabled:opacity-50"
                  }`}
                >
                  <Icon
                    name={TRACO_POLEGAR_PARA_CIMA}
                    size={16}
                    strokeWidth={2}
                  />{" "}
                  Sim ({article.helpful})
                </button>
                <button
                  onClick={() => handleFeedback(false)}
                  disabled={feedbackGiven !== null}
                  aria-pressed={feedbackGiven === false}
                  className={`flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg border transition-colors cursor-pointer disabled:cursor-not-allowed ${
                    feedbackGiven === false
                      ? "border-danger/30 bg-tint-danger text-on-tint-danger"
                      : "border-borda text-conteudo-muted hover:border-danger/30 hover:text-on-tint-danger disabled:opacity-50"
                  }`}
                >
                  <Icon
                    name={TRACO_POLEGAR_PARA_BAIXO}
                    size={16}
                    strokeWidth={2}
                  />{" "}
                  Não ({article.not_helpful})
                </button>
              </div>
              {feedbackGiven !== null && (
                <span role="status" className="text-xs text-conteudo-muted">
                  Obrigado pelo feedback!
                </span>
              )}
            </div>
          </Card>

          {/* Comments */}
          <Card padding="none">
            <div className="flex items-center gap-2 border-b border-borda/40 px-5 py-3.5">
              <span className="text-conteudo-muted">
                <Icon name="chat" size={16} strokeWidth={2} />
              </span>
              <h2 className="text-sm font-semibold text-conteudo">
                Comentários ({totalComments})
              </h2>
            </div>
            <div className="p-5 space-y-4">
              <CommentForm onSubmit={handleAddComment} />

              {commentsLoading ? (
                <div className="flex justify-center py-4">
                  <Spinner size="sm" />
                </div>
              ) : comments.length === 0 ? (
                <div className="py-10 text-center">
                  {/* `conteudo-muted` e não `faint`: o par com
                      `bg-surface-elevated` no mesmo elemento é o que a
                      varredura media em 2,34:1 no claro. */}
                  <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-surface-elevated text-conteudo-muted">
                    <Icon name="chat" size={16} strokeWidth={2} />
                  </div>
                  <p className="text-sm text-conteudo-muted">
                    Nenhum comentário ainda. Seja o primeiro!
                  </p>
                </div>
              ) : (
                <div className="overflow-y-auto max-h-[280px] pr-1 space-y-5 divide-y divide-borda/40">
                  {comments.map((comment) => (
                    <div key={comment.id} className="pt-5 first:pt-0">
                      <CommentItem
                        comment={comment}
                        currentUserId={user?.id}
                        currentUserRole={user?.role}
                        isStaff={isStaff}
                        onReply={handleReply}
                        onDelete={handleDeleteComment}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* ── Sidebar ───────────────────────────────────────── */}
        <div className="space-y-4">
          <Card>
            <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">
              Sobre o artigo
            </p>
            <div>
              <PropRow
                icon={<Icon name="user" size={14} strokeWidth={2} />}
                label="Autor"
              >
                {article.author_name}
              </PropRow>
              <PropRow
                icon={<Icon name="calendar" size={14} strokeWidth={2} />}
                label="Atualizado em"
              >
                {formattedDate}
              </PropRow>
              <PropRow
                icon={<Icon name="tag" size={14} strokeWidth={2} />}
                label="Categoria"
              >
                {catLabel}
              </PropRow>
              <PropRow
                icon={<Icon name="eye" size={14} strokeWidth={2} />}
                label="Visualizações"
              >
                {article.view_count}{" "}
                {plural(article.view_count, "visualização", "visualizações")}
              </PropRow>
            </div>
          </Card>

          <Card>
            <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">
              Produtos
            </p>
            {article.products.length === 0 ? (
              <p className="text-xs text-conteudo-muted">
                Vale para todos os produtos.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {article.products.map((p) => (
                  <Badge
                    key={p.id}
                    variant="primary"
                    className="max-w-full truncate"
                  >
                    {p.name}
                  </Badge>
                ))}
              </div>
            )}
          </Card>

          {article.tags.length > 0 && (
            <Card>
              <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">
                Tags
              </p>
              <div className="flex flex-wrap gap-1.5">
                {[...new Set(article.tags)].map((tag) => (
                  <Badge key={tag} variant="secondary">
                    {tag}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          <Card>
            <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-conteudo-muted">
              Feedback
            </p>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5 text-on-tint-success">
                <Icon name={TRACO_POLEGAR_PARA_CIMA} size={16} strokeWidth={2} />
                <span className="text-sm font-semibold">{article.helpful}</span>
                <span className="text-xs text-conteudo-muted">útil</span>
              </div>
              <div className="flex items-center gap-1.5 text-on-tint-danger">
                <Icon
                  name={TRACO_POLEGAR_PARA_BAIXO}
                  size={16}
                  strokeWidth={2}
                />
                <span className="text-sm font-semibold">
                  {article.not_helpful}
                </span>
                <span className="text-xs text-conteudo-muted">não útil</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
