import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
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
import { api } from "../../services/api";
import {
  createMyEquipment,
  deleteMyEquipment,
  getMyEquipment,
  updateMyEquipment,
  type Equipment,
} from "../../services/equipmentService";

// ── Types ─────────────────────────────────────────────────────

interface Product {
  id: string;
  name: string;
  version: string | null;
  is_active: boolean;
}

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  Cpu: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <rect x="4" y="4" width="16" height="16" rx="2" /><path strokeLinecap="round" strokeLinejoin="round" d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" />
    </svg>
  ),
  Edit: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  ),
  Trash: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  ),
  Plus: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
    </svg>
  ),
  MapPin: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
};

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 10;

// ── Schema ────────────────────────────────────────────────────

const equipSchema = z.object({
  product_id: z.string().min(1, "Selecione um produto"),
  name: z.string().min(1, "Nome obrigatório"),
  serial_number: z.string().optional(),
  location: z.string().optional(),
});

const editSchema = z.object({
  name: z.string().min(1, "Nome obrigatório"),
  serial_number: z.string().optional(),
  location: z.string().optional(),
});

type EquipValues = z.infer<typeof equipSchema>;
type EditValues = z.infer<typeof editSchema>;

// ── ActivePill ────────────────────────────────────────────────

function ActivePill({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium shrink-0 ${
        active
          ? "border-emerald-300 bg-emerald-50 text-emerald-600 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300"
          : "border-slate-300 bg-slate-100 text-slate-500 dark:border-slate-600/50 dark:bg-slate-800/40 dark:text-slate-400"
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${active ? "bg-emerald-500 dark:bg-emerald-400" : "bg-slate-400 dark:bg-slate-500"}`} />
      {active ? "Ativo" : "Inativo"}
    </span>
  );
}

// ── KpiCard ───────────────────────────────────────────────────

function KpiCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="rounded-xl bg-background-surface border border-border p-4 flex flex-col gap-1">
      <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold ${accent ?? "text-slate-700 dark:text-slate-100"}`}>{value}</p>
    </div>
  );
}

// ── AddModal ──────────────────────────────────────────────────

function AddModal({ products, onClose, onAdded }: {
  products: Product[];
  onClose: () => void;
  onAdded: (eq: Equipment) => void;
}) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<EquipValues>({
    resolver: zodResolver(equipSchema),
    defaultValues: { product_id: products[0]?.id ?? "" },
  });

  async function handleSubmit(values: EquipValues) {
    setSubmitError(null);
    try {
      const eq = await createMyEquipment(values.product_id, {
        name: values.name,
        serial_number: values.serial_number || null,
        location: values.location || null,
      });
      onAdded(eq);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSubmitError(detail ?? "Erro ao adicionar equipamento.");
    }
  }

  return (
    <Modal open onClose={onClose} title="Novo equipamento">
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {submitError && <Alert variant="danger">{submitError}</Alert>}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-600 dark:text-slate-400">Produto *</label>
          <select
            className="w-full rounded-xl border border-border/60 bg-background-elevated px-3 py-2 text-sm text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            {...form.register("product_id")}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}{p.version ? ` (${p.version})` : ""}
              </option>
            ))}
          </select>
          {form.formState.errors.product_id && (
            <p className="text-xs text-danger">{form.formState.errors.product_id.message}</p>
          )}
        </div>
        <Input
          label="Nome do equipamento *"
          placeholder="ex: Notebook Welton"
          autoFocus
          error={form.formState.errors.name?.message}
          {...form.register("name")}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Número de série" placeholder="ex: SN-001234" {...form.register("serial_number")} />
          <Input label="Localização" placeholder="ex: Sala 201" {...form.register("location")} />
        </div>
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>Cancelar</Button>
          <Button type="submit" loading={form.formState.isSubmitting}>Adicionar equipamento</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── EditModal ─────────────────────────────────────────────────

function EditModal({ equipment, onClose, onSaved }: {
  equipment: Equipment;
  onClose: () => void;
  onSaved: (eq: Equipment) => void;
}) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      name: equipment.name,
      serial_number: equipment.serial_number ?? "",
      location: equipment.location ?? "",
    },
  });

  async function handleSubmit(values: EditValues) {
    setSubmitError(null);
    try {
      const updated = await updateMyEquipment(equipment.id, {
        name: values.name,
        serial_number: values.serial_number || null,
        location: values.location || null,
      });
      onSaved(updated);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSubmitError(detail ?? "Erro ao salvar.");
    }
  }

  return (
    <Modal open onClose={onClose} title="Editar equipamento">
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {submitError && <Alert variant="danger">{submitError}</Alert>}
        <Input
          label="Nome *"
          autoFocus
          error={form.formState.errors.name?.message}
          {...form.register("name")}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Número de série" placeholder="ex: SN-001234" {...form.register("serial_number")} />
          <Input label="Localização" placeholder="ex: Sala 201" {...form.register("location")} />
        </div>
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>Cancelar</Button>
          <Button type="submit" loading={form.formState.isSubmitting}>Salvar alterações</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── DeleteModal ───────────────────────────────────────────────

function DeleteModal({ equipment, onClose, onDeleted }: {
  equipment: Equipment;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setLoading(true);
    try {
      await deleteMyEquipment(equipment.id);
      onDeleted();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Erro ao excluir equipamento.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Excluir equipamento">
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        <div className="flex gap-3 rounded-xl bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800/40 p-4">
          <div className="shrink-0 w-9 h-9 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center text-red-500 dark:text-red-400">{IC.Trash}</div>
          <div>
            <p className="text-sm font-semibold text-red-600 dark:text-red-300">Ação irreversível</p>
            <p className="text-xs text-red-500/80 dark:text-red-400/80 mt-0.5">Este equipamento será removido permanentemente.</p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-border bg-background-elevated px-4 py-3">
          <div className="w-9 h-9 rounded-lg bg-background-surface border border-border flex items-center justify-center text-slate-500">{IC.Cpu}</div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">{equipment.name}</p>
            {equipment.serial_number && <p className="text-xs font-mono text-slate-500">{equipment.serial_number}</p>}
          </div>
        </div>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Tem certeza que deseja excluir <span className="font-medium text-slate-700 dark:text-slate-200">{equipment.name}</span>?
        </p>
      </div>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose} disabled={loading}>Cancelar</Button>
        <Button variant="danger" onClick={handleDelete} loading={loading}>Excluir permanentemente</Button>
      </ModalFooter>
    </Modal>
  );
}

// ── EquipmentPage ─────────────────────────────────────────────

export default function EquipmentPage() {
  const [allEquipments, setAllEquipments] = useState<Equipment[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<"all" | "active" | "inactive">("all");

  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Equipment | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Equipment | null>(null);

  const productMap = Object.fromEntries(products.map((p) => [p.id, p]));

  useEffect(() => {
    Promise.all([
      api.get<{ items: Product[] }>("/products").then((r) => r.data.items.filter((p) => p.is_active)),
      getMyEquipment(),
    ])
      .then(([prods, equips]) => { setProducts(prods); setAllEquipments(equips); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = allEquipments.filter((e) => {
    if (filter === "active") return e.is_active;
    if (filter === "inactive") return !e.is_active;
    return true;
  });

  const total = allEquipments.length;
  const active = allEquipments.filter((e) => e.is_active).length;
  const inactive = total - active;

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function handleAdded(eq: Equipment) {
    setAllEquipments((prev) => [...prev, eq]);
    setAddOpen(false);
  }

  function handleSaved(updated: Equipment) {
    setAllEquipments((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    setEditTarget(null);
  }

  function handleDeleted() {
    setAllEquipments((prev) => prev.filter((e) => e.id !== deleteTarget?.id));
    setDeleteTarget(null);
  }

  if (loading) {
    return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Meus equipamentos</h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-0.5">
            Gerencie os equipamentos sob sua responsabilidade.
          </p>
        </div>
        {products.length > 0 && (
          <Button onClick={() => setAddOpen(true)}>{IC.Plus} Adicionar equipamento</Button>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="Total" value={total} />
        <KpiCard label="Ativos" value={active} accent="text-emerald-600 dark:text-emerald-400" />
        <KpiCard label="Inativos" value={inactive} accent="text-slate-500" />
      </div>

      {/* Card */}
      <Card padding="none">
        {/* Filter tabs */}
        <div className="flex gap-0 border-b border-border">
          {([ { key: "all", label: `Todos (${total})` }, { key: "active", label: `Ativos (${active})` }, { key: "inactive", label: `Inativos (${inactive})` } ] as { key: typeof filter; label: string }[]).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => { setFilter(key); setPage(1); }}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors cursor-pointer -mb-px ${
                filter === key ? "border-primary text-primary" : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-background-elevated border border-border flex items-center justify-center text-slate-600 mb-3">{IC.Cpu}</div>
            <p className="text-sm text-slate-400">
              {total === 0
                ? "Nenhum equipamento cadastrado ainda."
                : "Nenhum equipamento neste filtro."}
            </p>
            {total === 0 && products.length > 0 && (
              <button onClick={() => setAddOpen(true)} className="mt-2 text-sm text-primary hover:text-primary/80 transition-colors cursor-pointer">
                Adicionar primeiro equipamento
              </button>
            )}
            {total === 0 && products.length === 0 && (
              <p className="mt-1 text-xs text-slate-600">Nenhum produto disponível no sistema ainda.</p>
            )}
          </div>
        ) : (
          <>
            <div className="divide-y divide-border">
              {paginated.map((e) => {
                const prod = productMap[e.product_id];
                return (
                  <div key={e.id} className="flex items-center gap-4 px-4 py-3 hover:bg-background-elevated/40 transition-colors">
                    {/* Icon */}
                    <div className="w-9 h-9 rounded-lg bg-background-elevated border border-border/60 flex items-center justify-center shrink-0 text-slate-400">
                      {IC.Cpu}
                    </div>

                    {/* Name + details */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium truncate ${e.is_active ? "text-slate-800 dark:text-slate-200" : "text-slate-400 line-through"}`}>
                        {e.name}
                      </p>
                      <div className="flex items-center gap-2 flex-wrap mt-0.5">
                        {e.serial_number && (
                          <span className="text-xs font-mono text-slate-500">{e.serial_number}</span>
                        )}
                        {e.location && (
                          <span className="flex items-center gap-0.5 text-xs text-slate-600">
                            {IC.MapPin} {e.location}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Product badge */}
                    {prod && (
                      <span className="hidden sm:inline-flex shrink-0 text-xs px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary/80 truncate max-w-[120px]">
                        {prod.name}
                      </span>
                    )}

                    {/* Status */}
                    <ActivePill active={e.is_active} />

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => setEditTarget(e)}
                        title="Editar"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                      >
                        {IC.Edit}
                      </button>
                      <button
                        onClick={() => setDeleteTarget(e)}
                        title="Excluir"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-900/20 transition-colors cursor-pointer"
                      >
                        {IC.Trash}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="px-4 py-2 border-t border-border">
              <Pagination page={page} pageSize={PAGE_SIZE} total={filtered.length} onPageChange={setPage} itemLabel="equipamentos" />
            </div>
          </>
        )}
      </Card>

      {/* Modals */}
      {addOpen && (
        <AddModal products={products} onClose={() => setAddOpen(false)} onAdded={handleAdded} />
      )}
      {editTarget && (
        <EditModal equipment={editTarget} onClose={() => setEditTarget(null)} onSaved={handleSaved} />
      )}
      {deleteTarget && (
        <DeleteModal equipment={deleteTarget} onClose={() => setDeleteTarget(null)} onDeleted={handleDeleted} />
      )}
    </div>
  );
}
