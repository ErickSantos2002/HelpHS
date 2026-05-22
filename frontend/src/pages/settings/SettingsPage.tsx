import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  Spinner,
} from "../../components/ui";
import { TagBadge } from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import {
  createTag,
  deleteTag,
  getTags,
  updateTag,
  type Tag,
} from "../../services/tagService";

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

// ── Color picker ──────────────────────────────────────────────

const PRESET_COLORS = [
  { hex: "#6366f1", label: "Índigo"   },
  { hex: "#8b5cf6", label: "Violeta"  },
  { hex: "#ec4899", label: "Rosa"     },
  { hex: "#ef4444", label: "Vermelho" },
  { hex: "#f97316", label: "Laranja"  },
  { hex: "#eab308", label: "Amarelo"  },
  { hex: "#22c55e", label: "Verde"    },
  { hex: "#10b981", label: "Esmeralda"},
  { hex: "#06b6d4", label: "Ciano"    },
  { hex: "#3b82f6", label: "Azul"     },
  { hex: "#64748b", label: "Ardósia"  },
  { hex: "#a16207", label: "Âmbar"    },
  { hex: "#be185d", label: "Fucsia"   },
  { hex: "#0f766e", label: "Teal"     },
  { hex: "#1d4ed8", label: "Royal"    },
  { hex: "#7c3aed", label: "Púrpura"  },
];

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cor da etiqueta</p>
      <div className="grid grid-cols-8 gap-2">
        {PRESET_COLORS.map((c) => (
          <button
            key={c.hex}
            type="button"
            onClick={() => onChange(c.hex)}
            title={c.label}
            className="relative w-8 h-8 rounded-lg transition-all duration-150 hover:scale-110 focus:outline-none"
            style={{ backgroundColor: c.hex }}
          >
            {value === c.hex && (
              <span className="absolute inset-0 flex items-center justify-center">
                <svg className="w-4 h-4 text-white drop-shadow" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </span>
            )}
          </button>
        ))}
        <label
          title="Cor personalizada"
          className="w-8 h-8 rounded-lg border-2 border-dashed border-slate-600 hover:border-primary flex items-center justify-center cursor-pointer transition-colors overflow-hidden"
        >
          <input
            type="color"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="opacity-0 absolute w-0 h-0"
          />
          <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </label>
      </div>
    </div>
  );
}

// ── Tags section ──────────────────────────────────────────────

const PAGE_SIZE = 10;

function TagsSection({
  createOpen,
  onOpenCreate,
  onCreateClose,
}: {
  createOpen: boolean;
  onOpenCreate: () => void;
  onCreateClose: () => void;
}) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canCreate = isAdmin || user?.role === "technician";

  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(PRESET_COLORS[0].hex);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editTag, setEditTag] = useState<Tag | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<Tag | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    getTags()
      .then(setTags)
      .catch(() => setError("Não foi possível carregar as etiquetas."))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreateLoading(true);
    setCreateError(null);
    try {
      const tag = await createTag({ name: newName.trim(), color: newColor });
      setTags((prev) =>
        [...prev, tag].sort((a, b) => a.name.localeCompare(b.name)),
      );
      onCreateClose();
      setNewName("");
      setNewColor(PRESET_COLORS[0].hex);
    } catch (err: unknown) {
      setCreateError(
        (err as { response?: { status?: number } })?.response?.status === 409
          ? "Já existe uma etiqueta com esse nome."
          : "Erro ao criar etiqueta.",
      );
    } finally {
      setCreateLoading(false);
    }
  }

  function openEdit(tag: Tag) {
    setEditTag(tag);
    setEditName(tag.name);
    setEditColor(tag.color);
    setEditError(null);
  }

  async function handleEdit() {
    if (!editTag || !editName.trim()) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const updated = await updateTag(editTag.id, {
        name: editName.trim(),
        color: editColor,
      });
      setTags((prev) =>
        prev
          .map((t) => (t.id === updated.id ? updated : t))
          .sort((a, b) => a.name.localeCompare(b.name)),
      );
      setEditTag(null);
    } catch (err: unknown) {
      setEditError(
        (err as { response?: { status?: number } })?.response?.status === 409
          ? "Já existe uma etiqueta com esse nome."
          : "Erro ao salvar etiqueta.",
      );
    } finally {
      setEditLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await deleteTag(deleteTarget.id);
      setTags((prev) => prev.filter((t) => t.id !== deleteTarget.id));
      setDeleteTarget(null);
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <>
      <Card padding="none">

        {loading ? (
          <div className="flex h-24 items-center justify-center">
            <Spinner />
          </div>
        ) : error ? (
          <div className="p-4">
            <Alert variant="danger">{error}</Alert>
          </div>
        ) : tags.length === 0 ? (
          <p className="text-slate-500 text-sm text-center py-8">
            Nenhuma etiqueta cadastrada.{" "}
            {canCreate && (
              <button
                onClick={onOpenCreate}
                className="text-primary hover:underline"
              >
                Criar a primeira
              </button>
            )}
          </p>
        ) : (
          <div>
            <div className="divide-y divide-border" style={{ minHeight: 520 }}>
              {tags.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((tag) => (
                <div
                  key={tag.id}
                  className="flex items-center justify-between px-4 py-3"
                >
                  <TagBadge name={tag.name} color={tag.color} />
                  {canCreate && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => openEdit(tag)}
                        title="Editar"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                      >
                        <IconEdit />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(tag)}
                        title="Excluir"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-900/20 transition-colors cursor-pointer"
                      >
                        <IconTrash />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="px-4 py-2 border-t border-border">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={tags.length}
                onPageChange={setPage}
                itemLabel="etiquetas"
              />
            </div>
          </div>
        )}
      </Card>

      {/* Create modal */}
      <Modal
        open={createOpen}
        onClose={() => { onCreateClose(); setCreateError(null); }}
        title="Nova etiqueta"
        size="lg"
      >
        <div className="space-y-5">
          {createError && <Alert variant="danger">{createError}</Alert>}

          <Input
            label="Nome da etiqueta"
            placeholder="ex.: Urgente, Bug, Solicitação…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            autoFocus
          />

          <ColorPicker value={newColor} onChange={setNewColor} />

          {/* Preview */}
          <div className="rounded-xl border border-border bg-background-elevated p-4">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500 mb-3">Prévia</p>
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl shrink-0 shadow-lg"
                style={{ backgroundColor: newColor }}
              />
              <div>
                <TagBadge name={newName || "Nome da etiqueta"} color={newColor} />
                <p className="text-xs text-slate-500 mt-1">Assim aparecerá nos tickets</p>
              </div>
            </div>
          </div>
        </div>
        <ModalFooter>
          <Button variant="ghost" onClick={onCreateClose} disabled={createLoading}>
            Cancelar
          </Button>
          <Button onClick={handleCreate} loading={createLoading} disabled={!newName.trim()}>
            Criar etiqueta
          </Button>
        </ModalFooter>
      </Modal>

      {/* Edit modal */}
      <Modal
        open={!!editTag}
        onClose={() => setEditTag(null)}
        title="Editar etiqueta"
        size="lg"
      >
        <div className="space-y-5">
          {editError && <Alert variant="danger">{editError}</Alert>}

          <Input
            label="Nome da etiqueta"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleEdit()}
            autoFocus
          />

          <ColorPicker value={editColor} onChange={setEditColor} />

          {/* Preview */}
          <div className="rounded-xl border border-border bg-background-elevated p-4">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500 mb-3">Prévia</p>
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl shrink-0 shadow-lg"
                style={{ backgroundColor: editColor }}
              />
              <div>
                <TagBadge name={editName || "Nome da etiqueta"} color={editColor} />
                <p className="text-xs text-slate-500 mt-1">Assim aparecerá nos tickets</p>
              </div>
            </div>
          </div>
        </div>
        <ModalFooter>
          <Button variant="ghost" onClick={() => setEditTag(null)} disabled={editLoading}>
            Cancelar
          </Button>
          <Button onClick={handleEdit} loading={editLoading} disabled={!editName.trim()}>
            Salvar alterações
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete confirm */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Excluir etiqueta"
      >
        <div className="space-y-4">
          {/* Warning banner */}
          <div className="flex gap-3 rounded-xl bg-red-900/20 border border-red-800/40 p-4">
            <div className="shrink-0 w-9 h-9 rounded-full bg-red-900/40 flex items-center justify-center">
              <IconTrash />
            </div>
            <div>
              <p className="text-sm font-semibold text-red-300">Ação irreversível</p>
              <p className="text-xs text-red-400/80 mt-0.5">
                Esta etiqueta será removida de todos os tickets que a utilizam.
              </p>
            </div>
          </div>

          {/* Tag being deleted */}
          {deleteTarget && (
            <div className="flex items-center gap-3 rounded-xl border border-border bg-background-elevated px-4 py-3">
              <div className="w-8 h-8 rounded-lg shrink-0" style={{ backgroundColor: deleteTarget.color }} />
              <div>
                <p className="text-sm font-medium text-slate-100">{deleteTarget.name}</p>
                <p className="text-xs text-slate-500">Etiqueta selecionada</p>
              </div>
            </div>
          )}

          <p className="text-sm text-slate-400">
            Tem certeza que deseja excluir <span className="text-slate-200 font-medium">"{deleteTarget?.name}"</span>?
          </p>
        </div>
        <ModalFooter>
          <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleteLoading}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={handleDelete} loading={deleteLoading}>
            Sim, excluir
          </Button>
        </ModalFooter>
      </Modal>
    </>
  );
}

// ── SettingsPage ──────────────────────────────────────────────

export default function SettingsPage() {
  const { user } = useAuth();
  const canCreate = user?.role === "admin" || user?.role === "technician";
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="text-center sm:text-left">
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Etiquetas</h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-0.5">
            Classifique tickets com etiquetas coloridas para facilitar a organização.
          </p>
        </div>
        {canCreate && (
          <Button className="w-full sm:w-auto" onClick={() => setCreateOpen(true)}>
            + Nova etiqueta
          </Button>
        )}
      </div>

      <TagsSection
        createOpen={createOpen}
        onOpenCreate={() => setCreateOpen(true)}
        onCreateClose={() => setCreateOpen(false)}
      />
    </div>
  );
}
