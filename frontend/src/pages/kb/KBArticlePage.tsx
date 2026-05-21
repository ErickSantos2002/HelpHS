import { marked } from "marked";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Spinner } from "../../components/ui";
import { getApiError } from "../../lib/apiError";
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

marked.setOptions({ breaks: true });

// ── Constants ─────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = { admin: "Admin", technician: "Técnico", client: "Cliente" };
const ROLE_COLOR: Record<string, string> = { admin: "text-primary", technician: "text-info-700 dark:text-info-400", client: "text-slate-400" };
const CATEGORY_LABEL: Record<string, string> = {
  hardware: "Hardware", software: "Software", network: "Rede",
  access: "Acesso", email: "E-mail", security: "Segurança", general: "Geral", other: "Outro",
};

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  ArrowLeft: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>,
  Edit: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>,
  Eye: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>,
  ThumbUp: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" /></svg>,
  ThumbDown: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.095c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" /></svg>,
  Chat: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>,
  User: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>,
  Calendar: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>,
  Tag: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" /></svg>,
  Send: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>,
};

// ── Markdown ──────────────────────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
  const html = marked.parse(content) as string;
  return (
    <div
      className="prose prose-invert prose-sm max-w-none [overflow-wrap:anywhere] [word-break:break-word]
        prose-headings:text-slate-100 prose-headings:font-semibold
        prose-p:text-slate-300 prose-p:leading-relaxed
        prose-a:text-primary prose-a:no-underline hover:prose-a:underline
        prose-strong:text-slate-100
        prose-code:text-primary prose-code:bg-background-elevated prose-code:px-1 prose-code:rounded
        prose-pre:bg-background-elevated prose-pre:border prose-pre:border-border prose-pre:overflow-x-auto
        prose-ul:text-slate-300 prose-ol:text-slate-300
        prose-li:marker:text-slate-500
        prose-blockquote:border-l-primary prose-blockquote:text-slate-400
        prose-hr:border-border"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ── Comment form ──────────────────────────────────────────────

function CommentForm({ onSubmit, placeholder = "Deixe um comentário…", autoFocus = false, onCancel, submitLabel = "Comentar" }: {
  onSubmit: (content: string) => Promise<void>;
  placeholder?: string; autoFocus?: boolean;
  onCancel?: () => void; submitLabel?: string;
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
        <textarea
          ref={textareaRef}
          rows={1}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={placeholder}
          className="flex-1 resize-none rounded-lg border border-border/60 bg-background-elevated px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors max-h-24 overflow-y-auto leading-relaxed break-words"
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e as unknown as React.FormEvent); } }}
        />
        <button
          type="submit"
          disabled={!content.trim() || submitting}
          className="shrink-0 rounded-lg bg-primary px-3 py-2 text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
        >
          {IC.Send}
        </button>
      </div>
      {onCancel && (
        <div className="flex justify-end">
          <button type="button" onClick={onCancel} className="text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer">Cancelar</button>
        </div>
      )}
      <p className="text-xs text-slate-600">Enter para enviar · Shift+Enter para nova linha</p>
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
        <div className="w-8 h-8 rounded-full bg-background-elevated border border-border/50 flex items-center justify-center shrink-0 text-xs font-semibold text-slate-300">
          {comment.author_name.charAt(0).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-slate-200">{comment.author_name}</span>
            {comment.author_role && (
              <span className={`text-xs ${ROLE_COLOR[comment.author_role] ?? "text-slate-500"}`}>
                {ROLE_LABEL[comment.author_role] ?? comment.author_role}
              </span>
            )}
            <span className="text-xs text-slate-600">{date}</span>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap break-words">{comment.content}</p>
          <div className="flex items-center gap-3 mt-2">
            {!comment.parent_id && (
              <button
                onClick={() => setShowReplyForm((v) => !v)}
                className="text-xs text-slate-500 hover:text-primary transition-colors cursor-pointer"
              >
                Responder
              </button>
            )}
            {replyCount > 0 && (
              <button
                onClick={() => setShowReplies((v) => !v)}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
              >
                <svg
                  className={`w-3 h-3 transition-transform duration-150 ${showReplies ? "rotate-180" : ""}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
                {showReplies ? "Ocultar" : "Ver"} {replyCount} resposta{replyCount !== 1 ? "s" : ""}
              </button>
            )}
            {canDelete && (
              <button onClick={() => onDelete(comment.id)} className="text-xs text-slate-600 hover:text-danger transition-colors cursor-pointer">Excluir</button>
            )}
          </div>
        </div>
      </div>

      {showReplyForm && (
        <div className="ml-11">
          <CommentForm placeholder="Escreva uma resposta…" autoFocus submitLabel="Responder"
            onCancel={() => setShowReplyForm(false)}
            onSubmit={async (content) => { await onReply(comment.id, content); setShowReplyForm(false); }}
          />
        </div>
      )}

      {showReplies && replyCount > 0 && (
        <div className="ml-11 space-y-4 border-l-2 border-border/40 pl-4">
          {comment.replies.map((reply) => (
            <CommentItem key={reply.id} comment={reply} currentUserId={currentUserId} isStaff={isStaff} onReply={onReply} onDelete={onDelete} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Sidebar prop row ──────────────────────────────────────────

function PropRow({ icon, label, children }: { icon: JSX.Element; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border/30 last:border-0">
      <span className="mt-0.5 shrink-0 text-slate-500">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</p>
        <div className="text-sm font-medium text-slate-200">{children}</div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────

export default function KBArticlePage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
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
      toast.error(getApiError(err, "Não foi possível salvar o comentário."));
      throw new Error("comment_failed");
    }
  }

  async function handleReply(parentId: string, content: string) {
    if (!id) return;
    try {
      const reply = await createKBComment(id, content, parentId);
      setComments((prev) => prev.map((c) => c.id === parentId ? { ...c, replies: [...c.replies, reply] } : c));
    } catch (err) {
      toast.error(getApiError(err, "Não foi possível salvar a resposta."));
      throw new Error("reply_failed");
    }
  }

  async function handleDeleteComment(commentId: string) {
    await deleteKBComment(commentId);
    setComments((prev) => prev.filter((c) => c.id !== commentId).map((c) => ({ ...c, replies: c.replies.filter((r) => r.id !== commentId) })));
  }

  const totalComments = comments.reduce((acc, c) => acc + 1 + c.replies.length, 0);

  if (loading) return <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>;

  if (notFound || !article) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <p className="text-slate-400 mb-2">Artigo não encontrado.</p>
        <button onClick={() => navigate("/kb")} className="text-primary text-sm hover:text-primary/80 cursor-pointer transition-colors">Voltar à Base de Conhecimento</button>
      </div>
    );
  }

  const formattedDate = new Date(article.updated_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
  const catLabel = CATEGORY_LABEL[article.category] ?? article.category;

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="min-w-0 text-center sm:text-left">
          <button
            onClick={() => navigate("/kb")}
            className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-primary transition-colors cursor-pointer"
          >
            {IC.ArrowLeft}
            <span>Base de Conhecimento</span>
            <span className="text-slate-600">/</span>
            <span className="text-slate-500 truncate max-w-[160px] sm:max-w-xs">{article.title}</span>
          </button>
          <h1 className="text-xl font-extrabold leading-tight text-slate-100 break-words [overflow-wrap:anywhere]">{article.title}</h1>
        </div>
        {isStaff && (
          <div className="flex justify-center sm:justify-end">
            <button
              onClick={() => navigate(`/kb/${article.id}/edit`)}
              className="flex items-center gap-2 rounded-xl border border-border/50 bg-background-elevated px-4 py-2 text-sm font-semibold text-slate-200 hover:border-border hover:bg-background-elevated/80 transition-colors cursor-pointer"
            >
              {IC.Edit}
              Editar artigo
            </button>
          </div>
        )}
      </div>

      {/* ── Body ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_260px]">
        {/* ── Main column ───────────────────────────────────── */}
        <div className="flex flex-col gap-5 min-w-0">
          {/* Article content */}
          <div className="rounded-xl border border-border/40 bg-background-surface overflow-hidden">
            <div className="px-6 pt-5 pb-0">
              <div className="max-h-[15rem] overflow-y-auto pb-5 pr-1">
                <MarkdownContent content={article.content} />
              </div>
            </div>

            {/* Feedback */}
            <div className="border-t border-border/40 px-6 py-5 flex flex-col items-center gap-3 text-center">
              <span className="text-sm text-slate-400">Este artigo foi útil?</span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleFeedback(true)}
                  disabled={feedbackGiven !== null}
                  className={`flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg border transition-colors cursor-pointer disabled:cursor-not-allowed ${
                    feedbackGiven === true
                      ? "border-success/50 text-success-700 dark:text-success-400 bg-success/10"
                      : "border-border/50 text-slate-400 hover:border-success/50 hover:text-success-700 dark:hover:text-success-400 disabled:opacity-50"
                  }`}
                >
                  {IC.ThumbUp} Sim ({article.helpful})
                </button>
                <button
                  onClick={() => handleFeedback(false)}
                  disabled={feedbackGiven !== null}
                  className={`flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg border transition-colors cursor-pointer disabled:cursor-not-allowed ${
                    feedbackGiven === false
                      ? "border-danger/50 text-danger-700 dark:text-danger-400 bg-danger/10"
                      : "border-border/50 text-slate-400 hover:border-danger/50 hover:text-danger-700 dark:hover:text-danger-400 disabled:opacity-50"
                  }`}
                >
                  {IC.ThumbDown} Não ({article.not_helpful})
                </button>
              </div>
              {feedbackGiven !== null && <span className="text-xs text-slate-500">Obrigado pelo feedback!</span>}
            </div>
          </div>

          {/* Comments */}
          <div className="rounded-xl border border-border/40 bg-background-surface">
            <div className="flex items-center gap-2 border-b border-border/40 px-5 py-3.5">
              <span className="text-slate-500">{IC.Chat}</span>
              <h2 className="text-sm font-semibold text-slate-200">Comentários ({totalComments})</h2>
            </div>
            <div className="p-5 space-y-4">
              <CommentForm onSubmit={handleAddComment} />

              {commentsLoading ? (
                <div className="flex justify-center py-4"><Spinner size="sm" /></div>
              ) : comments.length === 0 ? (
                <div className="py-10 text-center">
                  <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-background-elevated text-slate-600">{IC.Chat}</div>
                  <p className="text-sm text-slate-500">Nenhum comentário ainda. Seja o primeiro!</p>
                </div>
              ) : (
                <div className="overflow-y-auto max-h-[280px] pr-1 space-y-5 divide-y divide-border/40">
                  {comments.map((comment) => (
                    <div key={comment.id} className="pt-5 first:pt-0">
                      <CommentItem comment={comment} currentUserId={user?.id} currentUserRole={user?.role} isStaff={isStaff} onReply={handleReply} onDelete={handleDeleteComment} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Sidebar ───────────────────────────────────────── */}
        <div className="space-y-4">
          <div className="rounded-xl border border-border/40 bg-background-surface p-4">
            <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-slate-500">Sobre o artigo</p>
            <div>
              <PropRow icon={IC.User} label="Autor">{article.author_name}</PropRow>
              <PropRow icon={IC.Calendar} label="Atualizado em">{formattedDate}</PropRow>
              <PropRow icon={IC.Tag} label="Categoria">{catLabel}</PropRow>
              <PropRow icon={IC.Eye} label="Visualizações">
                {article.view_count} visualização{article.view_count !== 1 ? "ões" : ""}
              </PropRow>
            </div>
          </div>

          {article.tags.length > 0 && (
            <div className="rounded-xl border border-border/40 bg-background-surface p-4">
              <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">Tags</p>
              <div className="flex flex-wrap gap-1.5">
                {[...new Set(article.tags)].map((tag) => (
                  <span key={tag} className="rounded-full border border-border/50 bg-background-elevated px-2.5 py-1 text-xs text-slate-400">{tag}</span>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-xl border border-border/40 bg-background-surface p-4">
            <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">Feedback</p>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5 text-success-700 dark:text-success-400">
                {IC.ThumbUp}
                <span className="text-sm font-semibold">{article.helpful}</span>
                <span className="text-xs text-slate-500">útil</span>
              </div>
              <div className="flex items-center gap-1.5 text-danger-700 dark:text-danger-400">
                {IC.ThumbDown}
                <span className="text-sm font-semibold">{article.not_helpful}</span>
                <span className="text-xs text-slate-500">não útil</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
