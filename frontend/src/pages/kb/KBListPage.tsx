import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Badge, Input, Select } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import {
  deleteKBArticle,
  getKBArticles,
  type KBArticle,
  type KBArticleStatus,
} from "../../services/kbService";
import { cn } from "../../lib/utils";

const CATEGORIES = [
  { value: "", label: "Todas as categorias" },
  { value: "hardware", label: "Hardware" },
  { value: "software", label: "Software" },
  { value: "network", label: "Rede" },
  { value: "access", label: "Acesso" },
  { value: "email", label: "E-mail" },
  { value: "security", label: "Segurança" },
  { value: "general", label: "Geral" },
  { value: "other", label: "Outro" },
];

const STATUS_OPTIONS = [
  { value: "", label: "Todos os status" },
  { value: "published", label: "Publicado" },
  { value: "draft", label: "Rascunho" },
  { value: "archived", label: "Arquivado" },
];

const STATUS_BADGE: Record<KBArticleStatus, "success" | "warning" | "muted"> = {
  published: "success",
  draft: "warning",
  archived: "muted",
};

const STATUS_LABEL: Record<KBArticleStatus, string> = {
  published: "Publicado",
  draft: "Rascunho",
  archived: "Arquivado",
};

const PAGE_SIZE = 20;

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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setOffset(0);
  }, [search, category, statusFilter]);

  useEffect(() => {
    setLoading(true);
    getKBArticles({
      search: search || undefined,
      category: category || undefined,
      status: (statusFilter as KBArticleStatus) || undefined,
      offset,
      limit: PAGE_SIZE,
    })
      .then((res) => {
        setArticles(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [search, category, statusFilter, offset]);

  async function handleDelete(id: string) {
    if (!confirm("Arquivar este artigo?")) return;
    await deleteKBArticle(id);
    setArticles((prev) => prev.filter((a) => a.id !== id));
    setTotal((t) => t - 1);
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">
            Base de Conhecimento
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Artigos e guias de suporte
          </p>
        </div>
        {isStaff && (
          <Link
            to="/kb/new"
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors"
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
                d="M12 4v16m8-8H4"
              />
            </svg>
            Novo artigo
          </Link>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="flex-1 min-w-[200px]">
          <Input
            placeholder="Buscar artigos…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="w-48"
          options={CATEGORIES}
        />
        {isStaff && (
          <Select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-44"
            options={STATUS_OPTIONS}
          />
        )}
      </div>

      {/* List */}
      <div className="space-y-3">
        {loading && (
          <p className="text-sm text-slate-500 text-center py-8">Carregando…</p>
        )}
        {!loading && articles.length === 0 && (
          <p className="text-sm text-slate-500 text-center py-8">
            Nenhum artigo encontrado.
          </p>
        )}
        {!loading &&
          articles.map((article) => (
            <div
              key={article.id}
              className="rounded-xl bg-background-surface border border-border p-4 hover:border-slate-600 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <Link
                      to={`/kb/${article.id}`}
                      className="text-sm font-medium text-slate-100 hover:text-primary transition-colors truncate"
                    >
                      {article.title}
                    </Link>
                    {isStaff && (
                      <Badge variant={STATUS_BADGE[article.status]}>
                        {STATUS_LABEL[article.status]}
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-2">
                    {article.content.replace(/#+\s/g, "").slice(0, 150)}…
                  </p>
                  <div className="flex items-center gap-3 mt-2 flex-wrap">
                    <span className="text-xs text-slate-600 capitalize">
                      {article.category}
                    </span>
                    {article.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-xs px-1.5 py-0.5 rounded bg-background-elevated text-slate-400"
                      >
                        {tag}
                      </span>
                    ))}
                    <span className="text-xs text-slate-600 ml-auto">
                      {article.view_count} visualização
                      {article.view_count !== 1 ? "ões" : ""}
                    </span>
                    <span className="text-xs text-green-600">
                      👍 {article.helpful}
                    </span>
                    <span className="text-xs text-slate-500">
                      👎 {article.not_helpful}
                    </span>
                  </div>
                </div>

                {isStaff && (
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => navigate(`/kb/${article.id}/edit`)}
                      className="p-1.5 rounded-md text-slate-500 hover:text-slate-300 hover:bg-background-elevated transition-colors"
                      title="Editar"
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
                    </button>
                    {user?.role === "admin" && (
                      <button
                        onClick={() => handleDelete(article.id)}
                        className={cn(
                          "p-1.5 rounded-md transition-colors",
                          "text-slate-500 hover:text-danger hover:bg-danger/10",
                        )}
                        title="Arquivar"
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
                            d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8l1 12a2 2 0 002 2h8a2 2 0 002-2L19 8m-9 4v4m4-4v4"
                          />
                        </svg>
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            {total} artigo{total !== 1 ? "s" : ""}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              disabled={currentPage === 1}
              className="px-3 py-1 rounded-md border border-border hover:bg-background-elevated disabled:opacity-40 transition-colors"
            >
              Anterior
            </button>
            <span>
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              disabled={currentPage === totalPages}
              className="px-3 py-1 rounded-md border border-border hover:bg-background-elevated disabled:opacity-40 transition-colors"
            >
              Próxima
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
