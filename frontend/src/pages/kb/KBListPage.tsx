import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, FilterSelect, Modal, ModalFooter, Spinner } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import {
  deleteKBArticle,
  getKBArticles,
  type KBArticle,
  type KBArticleStatus,
} from "../../services/kbService";

// ── Constants ─────────────────────────────────────────────────

const CATEGORY_LABEL: Record<string, string> = {
  hardware: "Hardware", software: "Software", network: "Rede",
  access: "Acesso", email: "E-mail", security: "Segurança",
  general: "Geral", other: "Outro",
};

const STATUS_CONFIG: Record<KBArticleStatus, { label: string; cls: string }> = {
  published: { label: "Publicado", cls: "bg-success/10 text-success-700 dark:text-success-400 border-success/30" },
  draft:     { label: "Rascunho",  cls: "bg-warning/10 text-warning-700 dark:text-warning-400 border-warning/30"  },
  archived:  { label: "Arquivado", cls: "bg-background-elevated text-slate-500 border-border/50"                  },
};

const PAGE_SIZE = 20;

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  Plus:       <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" /></svg>,
  Search:     <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>,
  Book:       <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>,
  Edit:       <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>,
  Trash:      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>,
  TrashSm:    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>,
  Eye:        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>,
  ThumbUp:    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" /></svg>,
  ChevLeft:   <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>,
  ChevRight:  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>,
  X:          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>,
};

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
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<KBArticle | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => { setOffset(0); }, [search, category, statusFilter]);

  useEffect(() => {
    setLoading(true);
    getKBArticles({ search: search || undefined, category: category || undefined, status: (statusFilter as KBArticleStatus) || undefined, offset, limit: PAGE_SIZE })
      .then((res) => { setArticles(res.items); setTotal(res.total); })
      .finally(() => setLoading(false));
  }, [search, category, statusFilter, offset]);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await deleteKBArticle(deleteTarget.id);
      setArticles((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setTotal((t) => t - 1);
      setDeleteTarget(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const hasFilters = !!(search || category || statusFilter);

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-slate-100">Base de Conhecimento</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Artigos e guias de suporte{total > 0 && ` · ${total} artigo${total !== 1 ? "s" : ""}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Search */}
          <div className="relative w-full sm:w-auto">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">{IC.Search}</span>
            <input
              type="text"
              placeholder="Buscar artigos…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-8 py-2 text-sm w-full sm:w-52 rounded-lg border border-border/60 bg-background-elevated text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            />
            {search && (
              <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 cursor-pointer">{IC.X}</button>
            )}
          </div>

          {/* Category */}
          <FilterSelect
            value={category}
            onChange={setCategory}
            placeholder="Todas as categorias"
            options={[
              { value: "hardware", label: "Hardware" },
              { value: "software", label: "Software" },
              { value: "network",  label: "Rede"      },
              { value: "access",   label: "Acesso"    },
              { value: "email",    label: "E-mail"    },
              { value: "security", label: "Segurança" },
              { value: "general",  label: "Geral"     },
              { value: "other",    label: "Outro"     },
            ]}
          />

          {/* Status (staff only) */}
          {isStaff && (
            <FilterSelect
              value={statusFilter}
              onChange={setStatusFilter}
              placeholder="Todos os status"
              options={[
                { value: "published", label: "Publicado", dot: "#10b981" },
                { value: "draft",     label: "Rascunho",  dot: "#f59e0b" },
                { value: "archived",  label: "Arquivado", dot: "#64748b" },
              ]}
            />
          )}

          {hasFilters && (
            <button
              onClick={() => { setSearch(""); setCategory(""); setStatusFilter(""); }}
              className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-danger transition-colors cursor-pointer px-2 py-2 rounded-lg border border-border/40 hover:border-danger/30"
            >
              {IC.X}
              Limpar
            </button>
          )}

          {isStaff && (
            <button
              onClick={() => navigate("/kb/new")}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-primary text-white hover:bg-primary/90 transition-all cursor-pointer"
            >
              {IC.Plus}
              Novo artigo
            </button>
          )}
        </div>
      </div>

      {/* ── List ─────────────────────────────────────────────── */}
      {loading ? (
        <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
      ) : articles.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-border/40 bg-background-surface py-20">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-background-elevated text-slate-600">{IC.Book}</div>
          <p className="text-sm font-medium text-slate-400">Nenhum artigo encontrado.</p>
          {hasFilters && <button onClick={() => { setSearch(""); setCategory(""); setStatusFilter(""); }} className="mt-2 text-xs text-primary hover:text-primary/80 cursor-pointer transition-colors">Limpar filtros</button>}
          {isStaff && !hasFilters && <button onClick={() => navigate("/kb/new")} className="mt-3 text-xs font-medium text-primary hover:text-primary/80 cursor-pointer transition-colors">+ Criar primeiro artigo</button>}
        </div>
      ) : (
        <div className="space-y-2">
          {articles.map((article) => {
            const stCfg = STATUS_CONFIG[article.status];
            const catLabel = CATEGORY_LABEL[article.category] ?? article.category;
            const preview = article.content.replace(/#+\s/g, "").replace(/\*\*/g, "").slice(0, 160);

            return (
              <div
                key={article.id}
                className="flex items-start gap-4 rounded-xl border border-border/40 bg-background-surface px-5 py-4 hover:border-primary/30 hover:bg-primary/[0.02] transition-all cursor-pointer"
                onClick={() => navigate(`/kb/${article.id}`)}
              >
                {/* Icon */}
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  {IC.Book}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-slate-100 hover:text-primary transition-colors truncate">
                      {article.title}
                    </span>
                    {isStaff && (
                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${stCfg.cls}`}>
                        {stCfg.label}
                      </span>
                    )}
                    <span className="ml-0.5 rounded-md border border-border/40 bg-background-elevated px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                      {catLabel}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-1">{preview}…</p>
                  {article.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {[...new Set(article.tags)].map((tag) => (
                        <span key={tag} className="rounded-md bg-background-elevated px-1.5 py-0.5 text-[10px] text-slate-500">{tag}</span>
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
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1 text-[11px] text-slate-500">{IC.Eye}{article.view_count}</span>
                    <span className="flex items-center gap-1 text-[11px] text-success-700 dark:text-success-400">{IC.ThumbUp}{article.helpful}</span>
                  </div>

                  {/* Action buttons — sempre visíveis */}
                  {isStaff && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => navigate(`/kb/${article.id}/edit`)}
                        title="Editar"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                      >
                        {IC.Edit}
                      </button>
                      {user?.role === "admin" && (
                        <button
                          onClick={() => setDeleteTarget(article)}
                          title="Excluir"
                          className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-900/20 transition-colors cursor-pointer"
                        >
                          {IC.Trash}
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
      {totalPages > 1 && (
        <div className="flex items-center justify-between rounded-xl border border-border/40 bg-background-surface px-5 py-3">
          <span className="text-sm text-slate-500">{total} artigo{total !== 1 ? "s" : ""}</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
              disabled={currentPage === 1}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border/40 text-sm text-slate-400 hover:bg-background-elevated hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {IC.ChevLeft} Anterior
            </button>
            <span className="text-sm text-slate-500 px-2">{currentPage} / {totalPages}</span>
            <button
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
              disabled={currentPage === totalPages}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border/40 text-sm text-slate-400 hover:bg-background-elevated hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              Próxima {IC.ChevRight}
            </button>
          </div>
        </div>
      )}

      {/* ── Delete modal ─────────────────────────────────────── */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Excluir artigo"
      >
        <div className="space-y-4">
          {/* Warning banner */}
          <div className="flex gap-3 rounded-xl bg-red-900/20 border border-red-800/40 p-4">
            <div className="shrink-0 w-9 h-9 rounded-full bg-red-900/40 flex items-center justify-center text-red-400">
              {IC.TrashSm}
            </div>
            <div>
              <p className="text-sm font-semibold text-red-300">Ação irreversível</p>
              <p className="text-xs text-red-400/80 mt-0.5">
                Este artigo será removido permanentemente da base de conhecimento.
              </p>
            </div>
          </div>

          {/* Article preview */}
          {deleteTarget && (
            <div className="flex items-center gap-3 rounded-xl border border-border bg-background-elevated px-4 py-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                {IC.Book}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-100 truncate">{deleteTarget.title}</p>
                <p className="text-xs text-slate-500">
                  {CATEGORY_LABEL[deleteTarget.category] ?? deleteTarget.category}
                  {" · "}
                  {STATUS_CONFIG[deleteTarget.status].label}
                </p>
              </div>
            </div>
          )}

          <p className="text-sm text-slate-400">
            Tem certeza que deseja excluir{" "}
            <span className="text-slate-200 font-medium">"{deleteTarget?.title}"</span>?
          </p>
        </div>
        <ModalFooter>
          <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleteLoading}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={handleDelete} loading={deleteLoading}>
            Sim, excluir
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
