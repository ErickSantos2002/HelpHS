import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Icon,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  Spinner,
} from "../../components/ui";
import { TagBadge } from "../../components/ui";
import { readableTextColor } from "../../lib/colors";
import { useAuth } from "../../contexts/AuthContext";
import {
  createTag,
  deleteTag,
  getTags,
  updateTag,
  type Tag,
} from "../../services/tagService";

// ── Color picker ──────────────────────────────────────────────

/**
 * Os dezesseis hexadecimais desta tela **não são dívida de sistema de design**,
 * e é por isso que continuam escritos aqui.
 *
 * Cor de etiqueta é DADO: quem escolhe é o usuário, o valor viaja para o
 * backend em `tags.color` e volta para pintar o selo em toda a lista de
 * tickets. Um token semântico não cabe — `--tint-danger` não é uma opção que
 * alguém possa escolher para chamar de "Vermelho", e trocar estes valores por
 * tokens mudaria a cor das etiquetas que já existem no banco.
 *
 * O que a tabela é, então: a **paleta padrão oferecida**, o atalho para não
 * obrigar ninguém a abrir o seletor do sistema operacional. Qual paleta
 * oferecer é decisão de desenho de quem cuida do produto, não desta migração —
 * fica como está, e o relatório da fase a aponta.
 *
 * O que a migração resolveu foi o outro lado: o "certo" que marca a escolhida
 * era `text-white` cravado sobre uma cor arbitrária. Sobre o `#eab308` isso é
 * texto claro sobre fundo claro. O `readableTextColor` decide por luminância
 * (WCAG) e é o mesmo que o `TagBadge` e a agenda já usam.
 */
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
      <p className="text-xs font-semibold text-conteudo-muted uppercase tracking-wider">Cor da etiqueta</p>
      <div className="grid grid-cols-8 gap-2">
        {PRESET_COLORS.map((c) => (
          <button
            key={c.hex}
            type="button"
            onClick={() => onChange(c.hex)}
            title={c.label}
            // `aria-pressed` porque o único sinal de "esta é a escolhida" era
            // o desenho do certo. Quem não vê a tela ouvia dezesseis botões
            // idênticos e nenhum jeito de saber em qual a etiqueta está.
            aria-pressed={value === c.hex}
            // O `focus:outline-none` de antes tirava o anel do sistema e não
            // punha nada no lugar: dava para chegar ao botão pelo teclado e
            // não dava para ver onde se estava.
            className="relative w-8 h-8 rounded-lg transition-all duration-150 hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
            style={{ backgroundColor: c.hex }}
          >
            {value === c.hex && (
              <span className="absolute inset-0 flex items-center justify-center">
                <Icon
                  name="check"
                  size={16}
                  strokeWidth={2}
                  className="drop-shadow"
                  // A cor do certo depende da cor escolhida, e por isso sai de
                  // função e não de token: é o par de um fundo que o sistema
                  // não conhece.
                  style={{ color: readableTextColor(c.hex) }}
                />
              </span>
            )}
          </button>
        ))}
        <label
          title="Cor personalizada"
          className="w-8 h-8 rounded-lg border-2 border-dashed border-borda-control hover:border-action flex items-center justify-center cursor-pointer transition-colors overflow-hidden"
        >
          <input
            type="color"
            // O rótulo visível deste campo é um desenho: sem `aria-label` o
            // campo não tem nome nenhum na árvore de acessibilidade.
            aria-label="Cor personalizada"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="opacity-0 absolute w-0 h-0"
          />
          <Icon name="plus" size={16} strokeWidth={2} className="text-conteudo-muted" />
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
          <p className="text-conteudo-muted text-sm text-center py-8">
            Nenhuma etiqueta cadastrada.{" "}
            {canCreate && (
              <button
                type="button"
                onClick={onOpenCreate}
                // `text-primary` é o degrau de MARCA e dá 3,66:1 sobre a
                // superfície; `--text-link` existe para texto que se clica.
                className="text-conteudo-link hover:text-conteudo-link-hover hover:underline"
              >
                Criar a primeira
              </button>
            )}
          </p>
        ) : (
          <div>
            <div className="divide-y divide-borda" style={{ minHeight: 520 }}>
              {tags.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((tag) => (
                <div
                  key={tag.id}
                  className="flex items-center justify-between px-4 py-3"
                >
                  <TagBadge name={tag.name} color={tag.color} />
                  {canCreate && (
                    <div className="flex items-center gap-1">
                      {/* O nome acessível diz QUAL etiqueta: dez linhas na
                          página davam dez botões chamados "Editar", e o
                          `title` sozinho não separa um do outro para quem
                          navega pela lista de controles. */}
                      <button
                        type="button"
                        onClick={() => openEdit(tag)}
                        title="Editar"
                        aria-label={`Editar ${tag.name}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-surface-elevated transition-colors cursor-pointer"
                      >
                        <Icon name="edit" size={16} strokeWidth={2} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(tag)}
                        title="Excluir"
                        aria-label={`Excluir ${tag.name}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-colors cursor-pointer"
                      >
                        <Icon name="trash" size={16} strokeWidth={2} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="px-4 py-2 border-t border-borda">
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
          <div className="rounded-xl border border-borda bg-surface-elevated p-4">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-conteudo-muted mb-3">Prévia</p>
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl shrink-0 shadow-lg"
                style={{ backgroundColor: newColor }}
              />
              <div>
                <TagBadge name={newName || "Nome da etiqueta"} color={newColor} />
                <p className="text-xs text-conteudo-muted mt-1">Assim aparecerá nos tickets</p>
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
          <div className="rounded-xl border border-borda bg-surface-elevated p-4">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-conteudo-muted mb-3">Prévia</p>
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl shrink-0 shadow-lg"
                style={{ backgroundColor: editColor }}
              />
              <div>
                <TagBadge name={editName || "Nome da etiqueta"} color={editColor} />
                <p className="text-xs text-conteudo-muted mt-1">Assim aparecerá nos tickets</p>
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
        size="sm"
        title="Excluir etiqueta"
      >
        <div className="space-y-4">
          {/* O aviso de "não volta" era um banner à mão em `red-900/20`, virou
              `Alert variant="danger" live={false}`, e pela D9.3 virou PROSA: a
              forma de exclusão da frota é modal `sm` com a frase que nomeia o
              que some, sem bloco com casca em volta. */}

          {/* Tag being deleted */}
          {deleteTarget && (
            <div className="flex items-center gap-3 rounded-xl border border-borda bg-surface-elevated px-4 py-3">
              {/* Quadrado da cor da etiqueta: dado do registro, como no resto
                  da tela. */}
              <div className="w-8 h-8 rounded-lg shrink-0" style={{ backgroundColor: deleteTarget.color }} />
              <div className="min-w-0">
                <p className="text-sm font-medium text-conteudo-heading truncate">{deleteTarget.name}</p>
                <p className="text-xs text-conteudo-muted">Etiqueta selecionada</p>
              </div>
            </div>
          )}

          <p className="text-sm text-conteudo-muted">
            Tem certeza que deseja excluir{" "}
            <span className="text-conteudo font-medium">"{deleteTarget?.name}"</span>? A
            etiqueta será removida de todos os tickets que a utilizam, e esta
            ação não pode ser desfeita.
          </p>
        </div>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)} disabled={deleteLoading}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={handleDelete} loading={deleteLoading}>
            Excluir
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
          {/* Era `text-slate-800 dark:text-slate-100`: dois degraus da paleta
              crua, um por tema, escritos à mão. `--text-heading` já inverte. */}
          <h1 className="text-2xl font-bold text-conteudo-heading">Etiquetas</h1>
          <p className="text-conteudo-muted text-sm mt-0.5">
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
