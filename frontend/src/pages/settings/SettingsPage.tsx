import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardTitle,
  Input,
  Modal,
  ModalFooter,
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

function TagsSection() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canCreate = isAdmin || user?.role === "technician";

  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
          <div className="divide-y divide-border">
            {tags.map((tag) => (
              <div
                key={tag.id}
                className="flex items-center justify-between px-4 py-3"
              >
                <TagBadge name={tag.name} color={tag.color} />
                {canCreate && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openEdit(tag)}
                    >
                      Editar
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteTarget(tag)}
                      className="text-danger hover:text-danger"
                    >
                      Excluir
                    </Button>
                  </div>
                )}
              </div>
            ))}
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
        <h1 className="text-2xl font-bold text-slate-100">Configurações</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          Gerencie as configurações do sistema.
        </p>
      </div>

      <section className="space-y-3">
        <TagsSection />
      </section>
    </div>
  );
}
