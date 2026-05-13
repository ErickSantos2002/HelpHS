import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardTitle,
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
  "#6366f1",
  "#8b5cf6",
  "#ec4899",
  "#ef4444",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#10b981",
  "#06b6d4",
  "#3b82f6",
  "#64748b",
  "#a16207",
];

function ColorPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (c: string) => void;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-400 mb-2">Cor</p>
      <div className="flex flex-wrap gap-2">
        {PRESET_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            className="w-7 h-7 rounded-full border-2 transition-transform hover:scale-110"
            style={{
              backgroundColor: c,
              borderColor: value === c ? "white" : "transparent",
            }}
            aria-label={c}
          />
        ))}
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-7 h-7 rounded-full cursor-pointer border-0 bg-transparent"
          title="Cor personalizada"
        />
      </div>
    </div>
  );
}

// ── Tags section ──────────────────────────────────────────────

const PAGE_SIZE = 10;

function TagsSection() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canCreate = isAdmin || user?.role === "technician";

  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const [createModal, setCreateModal] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(PRESET_COLORS[0]);
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
      setCreateModal(false);
      setNewName("");
      setNewColor(PRESET_COLORS[0]);
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
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div>
            <CardTitle>Etiquetas</CardTitle>
            <p className="text-xs text-slate-500 mt-0.5">
              Classifique tickets com etiquetas coloridas para facilitar a
              organização.
            </p>
          </div>
          {canCreate && (
            <Button size="sm" onClick={() => setCreateModal(true)}>
              + Nova etiqueta
            </Button>
          )}
        </div>

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
                onClick={() => setCreateModal(true)}
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
        open={createModal}
        onClose={() => {
          setCreateModal(false);
          setCreateError(null);
        }}
        title="Nova etiqueta"
      >
        <div className="space-y-4">
          {createError && <Alert variant="danger">{createError}</Alert>}
          <Input
            label="Nome"
            placeholder="ex.: Urgente, Bug, Solicitação…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            autoFocus
          />
          <ColorPicker value={newColor} onChange={setNewColor} />
          <div className="pt-1">
            <p className="text-xs text-slate-500 mb-2">Prévia</p>
            <TagBadge name={newName || "Etiqueta"} color={newColor} />
          </div>
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setCreateModal(false)}
            disabled={createLoading}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleCreate}
            loading={createLoading}
            disabled={!newName.trim()}
          >
            Criar
          </Button>
        </ModalFooter>
      </Modal>

      {/* Edit modal */}
      <Modal
        open={!!editTag}
        onClose={() => setEditTag(null)}
        title="Editar etiqueta"
      >
        <div className="space-y-4">
          {editError && <Alert variant="danger">{editError}</Alert>}
          <Input
            label="Nome"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleEdit()}
            autoFocus
          />
          <ColorPicker value={editColor} onChange={setEditColor} />
          <div className="pt-1">
            <p className="text-xs text-slate-500 mb-2">Prévia</p>
            <TagBadge name={editName || "Etiqueta"} color={editColor} />
          </div>
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setEditTag(null)}
            disabled={editLoading}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleEdit}
            loading={editLoading}
            disabled={!editName.trim()}
          >
            Salvar
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete confirm */}
      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Excluir etiqueta"
      >
        <p className="text-sm text-slate-300">
          Tem certeza que deseja excluir a etiqueta{" "}
          <span className="font-medium text-slate-100">
            "{deleteTarget?.name}"
          </span>
          ? Ela será removida de todos os tickets.
        </p>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setDeleteTarget(null)}
            disabled={deleteLoading}
          >
            Cancelar
          </Button>
          <Button
            variant="danger"
            onClick={handleDelete}
            loading={deleteLoading}
          >
            Excluir
          </Button>
        </ModalFooter>
      </Modal>
    </>
  );
}

// ── SettingsPage ──────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Etiquetas</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          Classifique tickets com etiquetas coloridas para facilitar a organização.
        </p>
      </div>

      <TagsSection />
    </div>
  );
}
