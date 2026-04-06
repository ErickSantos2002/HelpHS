import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../lib/utils";
import {
  getKBArticles,
  suggestArticlesForTicket,
  type KBArticle,
} from "../../services/kbService";
import { api } from "../../services/api";

interface KBSuggestionsPanelProps {
  ticketId: string;
}

export function KBSuggestionsPanel({ ticketId }: KBSuggestionsPanelProps) {
  const [articles, setArticles] = useState<KBArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [searching, setSearching] = useState(false);
  const [sending, setSending] = useState<string | null>(null);
  const [sentIds, setSentIds] = useState<Set<string>>(new Set());
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load suggestions on mount
  useEffect(() => {
    suggestArticlesForTicket(ticketId)
      .then(setArticles)
      .catch(() => setArticles([]))
      .finally(() => setLoading(false));
  }, [ticketId]);

  // Debounced search
  useEffect(() => {
    if (!search.trim()) {
      // Restore suggestions when search is cleared
      setSearching(true);
      suggestArticlesForTicket(ticketId)
        .then(setArticles)
        .catch(() => setArticles([]))
        .finally(() => setSearching(false));
      return;
    }

    searchTimer.current && clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setSearching(true);
      getKBArticles({ search: search.trim(), limit: 5 })
        .then((res) => setArticles(res.items))
        .catch(() => setArticles([]))
        .finally(() => setSearching(false));
    }, 400);

    return () => {
      searchTimer.current && clearTimeout(searchTimer.current);
    };
  }, [search, ticketId]);

  async function handleSend(article: KBArticle) {
    setSending(article.id);
    try {
      const message = `📄 Artigo recomendado: **${article.title}**\n\nAcesse: ${window.location.origin}/kb/${article.id}`;
      await api.post(`/tickets/${ticketId}/messages`, { content: message });
      setSentIds((prev) => new Set([...prev, article.id]));
    } catch {
      // silently ignore
    } finally {
      setSending(null);
    }
  }

  return (
    <div className="rounded-xl bg-background-surface border border-border p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.75}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
            />
          </svg>
          <h2 className="text-sm font-semibold text-slate-300">
            Base de Conhecimento
          </h2>
        </div>
        <Link
          to="/kb"
          className="text-xs text-slate-500 hover:text-primary transition-colors"
        >
          Ver todos →
        </Link>
      </div>

      {/* Search */}
      <div className="relative">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar artigos…"
          className={cn(
            "w-full rounded-lg border bg-background-elevated px-3 py-1.5 text-sm text-slate-100",
            "placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent",
            "border-border hover:border-slate-500 transition-colors",
          )}
        />
        {searching && (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 inline-block w-3.5 h-3.5 border border-slate-400 border-t-transparent rounded-full animate-spin" />
        )}
      </div>

      {/* Results */}
      <div className="space-y-2">
        {loading && (
          <p className="text-xs text-slate-500 text-center py-3">
            Carregando sugestões…
          </p>
        )}
        {!loading && articles.length === 0 && (
          <p className="text-xs text-slate-500 text-center py-3">
            {search
              ? "Nenhum artigo encontrado."
              : "Sem sugestões para este ticket."}
          </p>
        )}
        {!loading &&
          articles.map((article) => (
            <div
              key={article.id}
              className="flex items-start gap-2 p-2.5 rounded-lg bg-background-elevated border border-border hover:border-slate-600 transition-colors"
            >
              <div className="flex-1 min-w-0">
                <Link
                  to={`/kb/${article.id}`}
                  target="_blank"
                  className="text-xs font-medium text-slate-200 hover:text-primary transition-colors line-clamp-1"
                >
                  {article.title}
                </Link>
                <p className="text-xs text-slate-500 mt-0.5 line-clamp-1 capitalize">
                  {article.category}
                  {article.tags.length > 0 &&
                    ` · ${article.tags.slice(0, 2).join(", ")}`}
                </p>
              </div>
              <button
                onClick={() => handleSend(article)}
                disabled={sending === article.id || sentIds.has(article.id)}
                className={cn(
                  "shrink-0 flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors",
                  sentIds.has(article.id)
                    ? "border border-green-700 text-green-500 cursor-default"
                    : "border border-border text-slate-400 hover:border-primary hover:text-primary disabled:opacity-40",
                )}
                title={
                  sentIds.has(article.id)
                    ? "Enviado"
                    : "Enviar ao cliente via chat"
                }
              >
                {sending === article.id ? (
                  <span className="inline-block w-3 h-3 border border-slate-400 border-t-transparent rounded-full animate-spin" />
                ) : sentIds.has(article.id) ? (
                  <>
                    <svg
                      className="w-3 h-3"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    Enviado
                  </>
                ) : (
                  <>
                    <svg
                      className="w-3 h-3"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                      />
                    </svg>
                    Enviar
                  </>
                )}
              </button>
            </div>
          ))}
      </div>
    </div>
  );
}
