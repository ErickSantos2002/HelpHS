import { marked } from "marked";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Alert, Button, Input, Spinner, Textarea } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import {
  createKBArticle,
  getKBArticle,
  updateKBArticle,
  type KBArticleStatus,
} from "../../services/kbService";

marked.setOptions({ breaks: true });

// ── Constants ─────────────────────────────────────────────────

const CATEGORIES = [
  { value: "hardware", label: "Hardware" }, { value: "software", label: "Software" },
  { value: "network",  label: "Rede"      }, { value: "access",   label: "Acesso"    },
  { value: "email",    label: "E-mail"    }, { value: "security", label: "Segurança" },
  { value: "general",  label: "Geral"     }, { value: "other",    label: "Outro"     },
];

const STATUS_OPTIONS: { value: KBArticleStatus; label: string; dot: string }[] = [
  { value: "draft",     label: "Rascunho",  dot: "#f59e0b" },
  { value: "published", label: "Publicado", dot: "#10b981" },
  { value: "archived",  label: "Arquivado", dot: "#64748b" },
];

const STATUS_CONFIG: Record<KBArticleStatus, { cls: string }> = {
  published: { cls: "bg-success/10 text-success-700 dark:text-success-400 border-success/30" },
  draft:     { cls: "bg-warning/10 text-warning-700 dark:text-warning-400 border-warning/30" },
  archived:  { cls: "bg-background-elevated text-slate-500 border-border/50"                  },
};

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  ArrowLeft: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>,
  Eye: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>,
  Edit: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>,
  Info: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>,
};

// ── Content editor ────────────────────────────────────────────

function ContentEditor({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) {
  const [tab, setTab] = useState<"write" | "preview">("write");
  const html = marked.parse(value) as string;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-slate-300">Conteúdo <span className="text-danger">*</span></label>
        <div className="flex rounded-lg border border-border/50 overflow-hidden text-xs">
          <button
            type="button"
            onClick={() => setTab("write")}
            className={`flex items-center gap-1.5 px-3 py-1.5 transition-colors cursor-pointer ${tab === "write" ? "bg-background-elevated text-slate-200" : "text-slate-500 hover:text-slate-300"}`}
          >
            {IC.Edit} Editar
          </button>
          <button
            type="button"
            onClick={() => setTab("preview")}
            className={`flex items-center gap-1.5 px-3 py-1.5 border-l border-border/50 transition-colors cursor-pointer ${tab === "preview" ? "bg-background-elevated text-slate-200" : "text-slate-500 hover:text-slate-300"}`}
          >
            {IC.Eye} Preview
          </button>
        </div>
      </div>

      {tab === "write" ? (
        <>
          <Textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={"## Título\n\nDescrição do problema...\n\n### Solução\n\n1. Passo um\n2. Passo dois\n\n**Nota:** informação importante"}
            rows={18}
            error={error}
          />
          <p className="text-xs text-slate-600">Suporta Markdown: **negrito**, *itálico*, ## títulos, listas, `código`, links</p>
        </>
      ) : (
        <div className="min-h-[460px] rounded-xl border border-border/40 bg-background-elevated/60 px-5 py-4">
          {value.trim() ? (
            <div
              className="prose prose-invert prose-sm max-w-none
                prose-headings:text-slate-100 prose-headings:font-semibold
                prose-p:text-slate-300 prose-p:leading-relaxed
                prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                prose-strong:text-slate-100
                prose-code:text-primary prose-code:bg-background prose-code:px-1 prose-code:rounded
                prose-pre:bg-background prose-pre:border prose-pre:border-border
                prose-ul:text-slate-300 prose-ol:text-slate-300
                prose-blockquote:border-l-primary prose-blockquote:text-slate-400
                prose-hr:border-border"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          ) : (
            <p className="text-sm italic text-slate-500">Nada para pré-visualizar ainda…</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── FormSection ───────────────────────────────────────────────

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border/40 bg-background-surface">
      <div className="border-b border-border/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────

export default function KBFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isEdit = Boolean(id);

  const isStaff = user?.role === "admin" || user?.role === "technician";
  if (!isStaff) { navigate("/403", { replace: true }); return null; }

  const [title, setTitle]           = useState("");
  const [content, setContent]       = useState("");
  const [category, setCategory]     = useState("general");
  const [status, setStatus]         = useState<KBArticleStatus>("draft");
  const [tagsInput, setTagsInput]   = useState("");
  const [loading, setLoading]       = useState(false);
  const [loadingArticle, setLoadingArticle] = useState(isEdit);
  const [errors, setErrors]         = useState<Record<string, string>>({});

  useEffect(() => {
    if (!id) return;
    getKBArticle(id)
      .then((a) => { setTitle(a.title); setContent(a.content); setCategory(a.category); setStatus(a.status); setTagsInput(a.tags.join(", ")); })
      .catch(() => navigate("/kb"))
      .finally(() => setLoadingArticle(false));
  }, [id, navigate]);

  function validate() {
    const errs: Record<string, string> = {};
    if (!title.trim()) errs.title = "Título é obrigatório";
    if (!content.trim()) errs.content = "Conteúdo é obrigatório";
    return errs;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length > 0) { setErrors(errs); return; }

    const tags = tagsInput.split(",").map((t) => t.trim()).filter(Boolean);
    setLoading(true);
    try {
      if (isEdit && id) {
        await updateKBArticle(id, { title, content, category, tags, status });
        navigate(`/kb/${id}`);
      } else {
        const article = await createKBArticle({ title, content, category, tags, status });
        navigate(`/kb/${article.id}`);
      }
    } catch {
      setErrors({ form: "Erro ao salvar artigo. Tente novamente." });
    } finally {
      setLoading(false);
    }
  }

  if (loadingArticle) {
    return <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>;
  }

  const stCfg = STATUS_CONFIG[status];
  const catLabel = CATEGORIES.find((c) => c.value === category)?.label ?? category;

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="min-w-0">
          <button
            onClick={() => navigate(id ? `/kb/${id}` : "/kb")}
            className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-primary transition-colors cursor-pointer"
          >
            {IC.ArrowLeft}
            <span>Base de Conhecimento</span>
            {id && <><span className="text-slate-600">/</span><span className="text-slate-500 truncate max-w-xs">{title || "Artigo"}</span></>}
          </button>
          <h1 className="text-xl font-extrabold text-white">{isEdit ? "Editar artigo" : "Novo artigo"}</h1>
          <p className="mt-1 text-sm text-slate-500">{isEdit ? "Atualize o conteúdo do artigo." : "Preencha as informações para criar um novo artigo."}</p>
        </div>
      </div>

      {errors.form && <Alert variant="danger" onDismiss={() => setErrors((p) => ({ ...p, form: "" }))}>{errors.form}</Alert>}

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

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-300">Categoria</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full rounded-lg border border-border/60 bg-background-elevated px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors hover:border-border cursor-pointer"
                  >
                    {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium text-slate-300">Status</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value as KBArticleStatus)}
                    className="w-full rounded-lg border border-border/60 bg-background-elevated px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors hover:border-border cursor-pointer"
                  >
                    {STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-sm font-medium text-slate-300">
                  Tags <span className="font-normal text-slate-500">(separadas por vírgula)</span>
                </label>
                <Input
                  value={tagsInput}
                  onChange={(e) => setTagsInput(e.target.value)}
                  placeholder="ex: acesso, vpn, senha"
                />
                <p className="text-xs text-slate-500">Tags ajudam os usuários a encontrar o artigo nas buscas.</p>
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
              <Button type="button" variant="secondary" onClick={() => navigate(id ? `/kb/${id}` : "/kb")}>Cancelar</Button>
              <Button type="submit" loading={loading}>{isEdit ? "Salvar alterações" : "Criar artigo"}</Button>
            </div>
          </div>

          {/* ── Sidebar ─────────────────────────────────────── */}
          <div className="space-y-4">
            <div className="rounded-xl border border-border/40 bg-background-surface p-4">
              <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-slate-500">Resumo</p>
              <div className="space-y-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-0.5">Título</p>
                  <p className="text-sm text-slate-200 line-clamp-2">{title || <span className="italic text-slate-600">Não preenchido</span>}</p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-0.5">Categoria</p>
                  <p className="text-sm text-slate-200">{catLabel}</p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-1">Status</p>
                  <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${stCfg.cls}`}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: STATUS_OPTIONS.find((s) => s.value === status)?.dot }} />
                    {STATUS_OPTIONS.find((s) => s.value === status)?.label}
                  </span>
                </div>
                {tagsInput.trim() && (
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 mb-1">Tags</p>
                    <div className="flex flex-wrap gap-1">
                      {tagsInput.split(",").map((t) => t.trim()).filter(Boolean).map((tag) => (
                        <span key={tag} className="rounded-md bg-background-elevated px-2 py-0.5 text-[11px] text-slate-400">{tag}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-border/40 bg-background-surface p-4">
              <p className="mb-3 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                {IC.Info} Dicas
              </p>
              <ul className="space-y-2 text-xs text-slate-500">
                <li className="flex gap-2"><span className="text-primary shrink-0 mt-0.5">•</span>Use títulos claros e objetivos.</li>
                <li className="flex gap-2"><span className="text-primary shrink-0 mt-0.5">•</span>Estruture o conteúdo com títulos (##) e listas para facilitar a leitura.</li>
                <li className="flex gap-2"><span className="text-primary shrink-0 mt-0.5">•</span>Salve como Rascunho para revisar antes de publicar.</li>
                <li className="flex gap-2"><span className="text-primary shrink-0 mt-0.5">•</span>Tags ajudam os usuários a encontrar o artigo.</li>
              </ul>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
