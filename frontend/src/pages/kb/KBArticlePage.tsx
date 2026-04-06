import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import {
  getKBArticle,
  submitKBFeedback,
  type KBArticle,
} from "../../services/kbService";

export default function KBArticlePage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isStaff = user?.role === "admin" || user?.role === "technician";

  const [article, setArticle] = useState<KBArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<boolean | null>(null);

  useEffect(() => {
    if (!id) return;
    getKBArticle(id)
      .then(setArticle)
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
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

        {/* Content */}
        <div className="prose prose-invert prose-sm max-w-none text-slate-300 leading-relaxed whitespace-pre-wrap">
          {article.content}
        </div>

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
