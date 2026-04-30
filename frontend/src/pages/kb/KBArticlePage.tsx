import { marked } from "marked";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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

// ── Markdown renderer ─────────────────────────────────────────

marked.setOptions({ breaks: true });

function MarkdownContent({ content }: { content: string }) {
  const html = marked.parse(content) as string;
  return (
    <div
      className="prose prose-invert prose-sm max-w-none
        prose-headings:text-slate-100 prose-headings:font-semibold
        prose-p:text-slate-300 prose-p:leading-relaxed
        prose-a:text-primary prose-a:no-underline hover:prose-a:underline
        prose-strong:text-slate-100
        prose-code:text-primary prose-code:bg-background-elevated prose-code:px-1 prose-code:rounded
        prose-pre:bg-background-elevated prose-pre:border prose-pre:border-border
        prose-ul:text-slate-300 prose-ol:text-slate-300
        prose-li:marker:text-slate-500
        prose-blockquote:border-l-primary prose-blockquote:text-slate-400
        prose-hr:border-border"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ── Role label ────────────────────────────────────────────────

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  technician: "Técnico",
  client: "Cliente",
};

const ROLE_COLOR: Record<string, string> = {
  admin: "text-primary",
  technician: "text-info",
  client: "text-slate-400",
};

// ── Comment form ──────────────────────────────────────────────

interface CommentFormProps {
  onSubmit: (content: string) => Promise<void>;
  placeholder?: string;
  autoFocus?: boolean;
  onCancel?: () => void;
  submitLabel?: string;
}

function CommentForm({
  onSubmit,
  placeholder = "Deixe um comentário…",
  autoFocus = false,
  onCancel,
  submitLabel = "Comentar",
}: CommentFormProps) {
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = content.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await onSubmit(trimmed);
      setContent("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <textarea
        ref={textareaRef}
        rows={3}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder={placeholder}
        className="w-full resize-none rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
      />
      <div className="flex gap-2 justify-end">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="text-xs px-3 py-1.5 rounded-lg border border-border text-slate-400 hover:text-slate-200 transition-colors"
          >
            Cancelar
          </button>
        )}
        <button
          type="submit"
          disabled={!content.trim() || submitting}
          className="text-xs px-3 py-1.5 rounded-lg bg-primary text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? "Enviando…" : submitLabel}
        </button>
      </div>
    </form>
  );
}

// ── Single comment ────────────────────────────────────────────

interface CommentItemProps {
  comment: KBComment;
  currentUserId?: string;
  currentUserRole?: string;
  isStaff: boolean;
  onReply: (parentId: string, content: string) => Promise<void>;
  onDelete: (commentId: string) => Promise<void>;
}

function CommentItem({
  comment,
  currentUserId,
  isStaff,
  onReply,
  onDelete,
}: CommentItemProps) {
  const [showReplyForm, setShowReplyForm] = useState(false);
  const canDelete = isStaff || comment.author_id === currentUserId;

  const date = new Date(comment.created_at).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="space-y-3">
      {/* Comment bubble */}
      <div className="flex gap-3">
        <div className="w-8 h-8 rounded-full bg-background-elevated border border-border flex items-center justify-center shrink-0 text-xs font-medium text-slate-300">
          {comment.author_name.charAt(0).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium text-slate-200">
              {comment.author_name}
            </span>
            {comment.author_role && (
              <span
                className={`text-xs ${ROLE_COLOR[comment.author_role] ?? "text-slate-500"}`}
              >
                {ROLE_LABEL[comment.author_role] ?? comment.author_role}
              </span>
            )}
            <span className="text-xs text-slate-600">{date}</span>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
            {comment.content}
          </p>
          <div className="flex items-center gap-3 mt-2">
            {/* Reply only allowed on top-level comments */}
            {!comment.parent_id && (
              <button
                onClick={() => setShowReplyForm((v) => !v)}
                className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                Responder
              </button>
            )}
            {canDelete && (
              <button
                onClick={() => onDelete(comment.id)}
                className="text-xs text-slate-600 hover:text-danger transition-colors"
              >
                Excluir
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Reply form */}
      {showReplyForm && (
        <div className="ml-11">
          <CommentForm
            placeholder="Escreva uma resposta…"
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

      {/* Replies */}
      {comment.replies.length > 0 && (
        <div className="ml-11 space-y-3 border-l-2 border-border pl-4">
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

// ── KBArticlePage ─────────────────────────────────────────────

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
    getKBArticle(id)
      .then(setArticle)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));

    getKBComments(id)
      .then(setComments)
      .catch(() => {})
      .finally(() => setCommentsLoading(false));
  }, [id]);

  async function handleFeedback(helpful: boolean) {
    if (!id || feedbackGiven !== null) return;
    await submitKBFeedback(id, helpful);
    setFeedbackGiven(helpful);
    setArticle((prev) =>
      prev
        ? {
            ...prev,
            helpful: helpful ? prev.helpful + 1 : prev.helpful,
            not_helpful: !helpful ? prev.not_helpful + 1 : prev.not_helpful,
          }
        : prev,
    );
  }

  async function handleAddComment(content: string) {
    if (!id) return;
    const comment = await createKBComment(id, content);
    setComments((prev) => [...prev, comment]);
  }

  async function handleReply(parentId: string, content: string) {
    if (!id) return;
    const reply = await createKBComment(id, content, parentId);
    setComments((prev) =>
      prev.map((c) =>
        c.id === parentId ? { ...c, replies: [...c.replies, reply] } : c,
      ),
    );
  }

  async function handleDeleteComment(commentId: string) {
    await deleteKBComment(commentId);
    setComments((prev) => {
      // Remove top-level comment
      const withoutTop = prev.filter((c) => c.id !== commentId);
      // Remove reply
      return withoutTop.map((c) => ({
        ...c,
        replies: c.replies.filter((r) => r.id !== commentId),
      }));
    });
  }

  const totalComments = comments.reduce(
    (acc, c) => acc + 1 + c.replies.length,
    0,
  );

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10 text-center text-slate-500">
        Carregando…
      </div>
    );
  }

  if (notFound || !article) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10 text-center">
        <p className="text-slate-400">Artigo não encontrado.</p>
        <Link to="/kb" className="text-primary text-sm mt-2 inline-block">
          Voltar à Base de Conhecimento
        </Link>
      </div>
    );
  }

  const formattedDate = new Date(article.updated_at).toLocaleDateString(
    "pt-BR",
    { day: "2-digit", month: "long", year: "numeric" },
  );

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Link to="/kb" className="hover:text-slate-300 transition-colors">
          Base de Conhecimento
        </Link>
        <span>/</span>
        <span className="text-slate-400 truncate">{article.title}</span>
      </div>

      {/* Article */}
      <div className="rounded-xl bg-background-surface border border-border p-6 space-y-5">
        {/* Title + actions */}
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-xl font-semibold text-slate-100 leading-snug">
            {article.title}
          </h1>
          {isStaff && (
            <button
              onClick={() => navigate(`/kb/${article.id}/edit`)}
              className="shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border text-slate-400 hover:text-slate-200 hover:bg-background-elevated transition-colors"
            >
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
              Editar
            </button>
          )}
        </div>

        {/* Meta */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 border-b border-border pb-4">
          <span>Por {article.author_name}</span>
          <span>·</span>
          <span>Atualizado em {formattedDate}</span>
          <span>·</span>
          <span className="capitalize">{article.category}</span>
          <span>·</span>
          <span>
            {article.view_count} visualização
            {article.view_count !== 1 ? "ões" : ""}
          </span>
          {article.tags.length > 0 && (
            <>
              <span>·</span>
              <div className="flex gap-1.5 flex-wrap">
                {article.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-1.5 py-0.5 rounded bg-background-elevated text-slate-400"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Content — markdown rendered */}
        <MarkdownContent content={article.content} />

        {/* Feedback */}
        <div className="border-t border-border pt-4 flex items-center gap-4">
          <span className="text-sm text-slate-400">Este artigo foi útil?</span>
          <button
            onClick={() => handleFeedback(true)}
            disabled={feedbackGiven !== null}
            className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border transition-colors disabled:cursor-not-allowed ${
              feedbackGiven === true
                ? "border-green-600 text-green-400 bg-green-900/20"
                : "border-border text-slate-400 hover:border-green-700 hover:text-green-400 disabled:opacity-50"
            }`}
          >
            👍 Sim ({article.helpful})
          </button>
          <button
            onClick={() => handleFeedback(false)}
            disabled={feedbackGiven !== null}
            className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border transition-colors disabled:cursor-not-allowed ${
              feedbackGiven === false
                ? "border-red-700 text-red-400 bg-red-900/20"
                : "border-border text-slate-400 hover:border-red-700 hover:text-red-400 disabled:opacity-50"
            }`}
          >
            👎 Não ({article.not_helpful})
          </button>
          {feedbackGiven !== null && (
            <span className="text-xs text-slate-500">
              Obrigado pelo feedback!
            </span>
          )}
        </div>
      </div>

      {/* Comments section */}
      <div className="rounded-xl bg-background-surface border border-border p-6 space-y-5">
        <h2 className="text-sm font-semibold text-slate-300">
          Comentários ({totalComments})
        </h2>

        {/* New comment form */}
        <CommentForm onSubmit={handleAddComment} />

        {/* Comment list */}
        {commentsLoading ? (
          <p className="text-sm text-slate-500 text-center py-4">
            Carregando comentários…
          </p>
        ) : comments.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-4">
            Nenhum comentário ainda. Seja o primeiro a comentar!
          </p>
        ) : (
          <div className="space-y-5 divide-y divide-border">
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

      {/* Back link */}
      <Link
        to="/kb"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-300 transition-colors"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M10 19l-7-7m0 0l7-7m-7 7h18"
          />
        </svg>
        Voltar à lista
      </Link>
    </div>
  );
}
