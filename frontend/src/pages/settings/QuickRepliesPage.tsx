import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Alert,
  Button,
  Checkbox,
  Card,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  Spinner,
  Textarea,
} from "../../components/ui";
import { toastApiError } from "../../lib/toastError";
import { cn } from "../../lib/utils";
import {
  createQuickReply,
  deleteQuickReply,
  listQuickReplies,
  updateQuickReply,
  type QuickReply,
} from "../../services/quickReplyService";

// ── Icons ─────────────────────────────────────────────────────

function IconEdit() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  );
}
function IconTrash() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}

const PAGE_SIZE = 10;

/** O backend aceita só minúsculas, números, hífen e underline. */
function sanitizeShortcut(value: string): string {
  return value
    .replace(/^\//, "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "");
}

// ── Form modal ────────────────────────────────────────────────

interface FormState {
  shortcut: string;
  title: string;
  content: string;
  isActive: boolean;
}

const EMPTY_FORM: FormState = { shortcut: "", title: "", content: "", isActive: true };

function QuickReplyModal({
  editing,
  onClose,
  onSaved,
}: {
  editing: QuickReply | null;
  onClose: () => void;
  onSaved: (reply: QuickReply, isNew: boolean) => void;
}) {
  const [form, setForm] = useState<FormState>(
    editing
      ? {
          shortcut: editing.shortcut,
          title: editing.title,
          content: editing.content,
          isActive: editing.is_active,
        }
      : EMPTY_FORM,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (form.shortcut.length < 2) {
      setError("O atalho precisa de pelo menos 2 caracteres.");
      return;
    }
    if (!form.title.trim()) {
      setError("Informe um título para identificar a resposta.");
      return;
    }
    if (!form.content.trim()) {
      setError("Escreva o texto que será inserido no chat.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload = {
        shortcut: form.shortcut,
        title: form.title.trim(),
        content: form.content.trim(),
        is_active: form.isActive,
      };
      const saved = editing
        ? await updateQuickReply(editing.id, payload)
        : await createQuickReply(payload);
      onSaved(saved, !editing);
      toast.success(editing ? "Resposta rápida atualizada." : "Resposta rápida criada.");
      onClose();
    } catch (err) {
      toastApiError(err, "Não foi possível salvar a resposta rápida.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? "Editar resposta rápida" : "Nova resposta rápida"}
      size="md"
    >
      <div className="space-y-4">
        {error && <Alert variant="warning">{error}</Alert>}

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-400">
            Atalho <span className="text-danger-400">*</span>
          </label>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-500">/</span>
            <input
              value={form.shortcut}
              onChange={(e) =>
                setForm((f) => ({ ...f, shortcut: sanitizeShortcut(e.target.value) }))
              }
              placeholder="bomdia"
              maxLength={50}
              autoFocus
              className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            />
          </div>
          <p className="text-xs text-slate-500">
            É o que o técnico digita depois da barra no chat. Sem espaços nem acentos.
          </p>
        </div>

        <Input
          label="Título *"
          value={form.title}
          onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
          placeholder="Ex: Saudação inicial"
          maxLength={120}
        />

        <Textarea
          label="Mensagem *"
          value={form.content}
          onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
          placeholder="Bom dia! Sou da equipe de suporte da H&S. Como posso ajudar?"
          rows={5}
          maxLength={4000}
        />

        <Checkbox
          checked={form.isActive}
          onChange={(ativo) => setForm((f) => ({ ...f, isActive: ativo }))}
          label="Disponível no chat"
          className="items-center"
        />
      </div>

      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>
          Cancelar
        </Button>
        <Button variant="primary" onClick={handleSave} loading={saving}>
          {editing ? "Salvar" : "Criar"}
        </Button>
      </ModalFooter>
    </Modal>
  );
}

// ── Page ──────────────────────────────────────────────────────

export default function QuickRepliesPage() {
  const [replies, setReplies] = useState<QuickReply[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<QuickReply | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<QuickReply | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    listQuickReplies()
      .then(setReplies)
      .catch(() => setLoadError("Não foi possível carregar as respostas rápidas."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return replies;
    return replies.filter(
      (r) =>
        r.shortcut.toLowerCase().includes(term) ||
        r.title.toLowerCase().includes(term) ||
        r.content.toLowerCase().includes(term),
    );
  }, [replies, search]);

  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function handleSaved(saved: QuickReply, isNew: boolean) {
    setReplies((prev) =>
      (isNew ? [...prev, saved] : prev.map((r) => (r.id === saved.id ? saved : r))).sort((a, b) =>
        a.shortcut.localeCompare(b.shortcut),
      ),
    );
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteQuickReply(deleteTarget.id);
      setReplies((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      toast.success("Resposta rápida excluída.");
      setDeleteTarget(null);
    } catch (err) {
      toastApiError(err, "Não foi possível excluir a resposta rápida.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-5 pb-10">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-extrabold text-slate-900 dark:text-slate-100">
            Respostas Rápidas
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Mensagens prontas que a equipe insere no chat digitando <code>/atalho</code>
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            setEditing(null);
            setModalOpen(true);
          }}
        >
          Nova resposta
        </Button>
      </div>

      {loadError && <Alert variant="danger">{loadError}</Alert>}

      <Card padding="none">
        {/* Busca */}
        <div className="border-b border-border p-3">
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Buscar por atalho, título ou conteúdo…"
            className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
          />
        </div>

        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <Spinner />
          </div>
        ) : paged.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-slate-500">
            {replies.length === 0
              ? "Nenhuma resposta rápida cadastrada ainda."
              : "Nenhuma resposta encontrada para esta busca."}
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {paged.map((reply) => (
              <li
                key={reply.id}
                className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-background-elevated"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-xs font-semibold text-primary">
                      /{reply.shortcut}
                    </span>
                    <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-200">
                      {reply.title}
                    </span>
                    <span
                      className={cn(
                        "rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                        reply.is_active
                          ? "bg-success/10 text-success-700 dark:text-success-400"
                          : "bg-slate-200 text-slate-600 dark:bg-background-elevated dark:text-slate-500",
                      )}
                    >
                      {reply.is_active ? "Ativa" : "Inativa"}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">{reply.content}</p>
                </div>

                <div className="flex shrink-0 gap-1">
                  <button
                    onClick={() => {
                      setEditing(reply);
                      setModalOpen(true);
                    }}
                    aria-label={`Editar ${reply.shortcut}`}
                    className="cursor-pointer rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-primary/10 hover:text-primary"
                  >
                    <IconEdit />
                  </button>
                  <button
                    onClick={() => setDeleteTarget(reply)}
                    aria-label={`Excluir ${reply.shortcut}`}
                    className="cursor-pointer rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                  >
                    <IconTrash />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {filtered.length > PAGE_SIZE && (
          <div className="px-4 pb-3">
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={filtered.length}
              onPageChange={setPage}
              itemLabel="respostas"
            />
          </div>
        )}
      </Card>

      {modalOpen && (
        <QuickReplyModal
          editing={editing}
          onClose={() => setModalOpen(false)}
          onSaved={handleSaved}
        />
      )}

      {deleteTarget && (
        <Modal open onClose={() => setDeleteTarget(null)} title="Excluir resposta rápida" size="sm">
          <p className="text-sm text-slate-300">
            A resposta <span className="font-semibold">/{deleteTarget.shortcut}</span> será removida
            e deixará de aparecer no chat.
          </p>
          <p className="mt-2 text-xs text-slate-500">Ação irreversível.</p>
          <ModalFooter>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
              Cancelar
            </Button>
            <Button variant="danger" onClick={handleDelete} loading={deleting}>
              Excluir
            </Button>
          </ModalFooter>
        </Modal>
      )}
    </div>
  );
}
