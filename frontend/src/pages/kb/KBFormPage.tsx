import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Input, Select, Textarea } from "../../components/ui";
import {
  createKBArticle,
  getKBArticle,
  updateKBArticle,
  type KBArticleStatus,
} from "../../services/kbService";

const CATEGORIES = [
  { value: "hardware", label: "Hardware" },
  { value: "software", label: "Software" },
  { value: "network", label: "Rede" },
  { value: "access", label: "Acesso" },
  { value: "email", label: "E-mail" },
  { value: "security", label: "Segurança" },
  { value: "general", label: "Geral" },
  { value: "other", label: "Outro" },
];

const STATUS_OPTIONS: { value: KBArticleStatus; label: string }[] = [
  { value: "draft", label: "Rascunho" },
  { value: "published", label: "Publicado" },
  { value: "archived", label: "Arquivado" },
];

export default function KBFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("general");
  const [status, setStatus] = useState<KBArticleStatus>("draft");
  const [tagsInput, setTagsInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingArticle, setLoadingArticle] = useState(isEdit);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!id) return;
    getKBArticle(id)
      .then((a) => {
        setTitle(a.title);
        setContent(a.content);
        setCategory(a.category);
        setStatus(a.status);
        setTagsInput(a.tags.join(", "));
      })
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
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }

    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    setLoading(true);
    try {
      if (isEdit && id) {
        await updateKBArticle(id, { title, content, category, tags, status });
        navigate(`/kb/${id}`);
      } else {
        const article = await createKBArticle({
          title,
          content,
          category,
          tags,
          status,
        });
        navigate(`/kb/${article.id}`);
      }
    } catch {
      setErrors({ form: "Erro ao salvar artigo. Tente novamente." });
    } finally {
      setLoading(false);
    }
  }

  if (loadingArticle) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-10 text-center text-slate-500">
        Carregando…
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">
          {isEdit ? "Editar artigo" : "Novo artigo"}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">Base de Conhecimento</p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="rounded-xl bg-background-surface border border-border p-6 space-y-5"
      >
        {errors.form && (
          <p className="text-sm text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
            {errors.form}
          </p>
        )}

        {/* Title */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-300">Título</label>
          <Input
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              setErrors((prev) => ({ ...prev, title: "" }));
            }}
            placeholder="Título do artigo"
            error={errors.title}
          />
        </div>

        {/* Category + Status */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-300">
              Categoria
            </label>
            <Select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              options={CATEGORIES}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-300">Status</label>
            <Select
              value={status}
              onChange={(e) => setStatus(e.target.value as KBArticleStatus)}
              options={STATUS_OPTIONS}
            />
          </div>
        </div>

        {/* Tags */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-300">
            Tags{" "}
            <span className="text-slate-500 font-normal">
              (separadas por vírgula)
            </span>
          </label>
          <Input
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="ex: acesso, vpn, senha"
          />
        </div>

        {/* Content */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-slate-300">Conteúdo</label>
          <Textarea
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setErrors((prev) => ({ ...prev, content: "" }));
            }}
            placeholder="Escreva o conteúdo do artigo… (suporta texto simples ou Markdown)"
            rows={16}
            error={errors.content}
          />
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => navigate(id ? `/kb/${id}` : "/kb")}
            className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
          >
            Cancelar
          </button>
          <Button type="submit" loading={loading}>
            {isEdit ? "Salvar alterações" : "Criar artigo"}
          </Button>
        </div>
      </form>
    </div>
  );
}
