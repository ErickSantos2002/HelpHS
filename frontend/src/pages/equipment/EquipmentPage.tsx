import { useEffect, useState } from "react";
import { Spinner } from "../../components/ui";
import { api } from "../../services/api";
import {
  createMyEquipment,
  getMyEquipment,
  updateMyEquipment,
  type Equipment,
} from "../../services/equipmentService";

// ── Types ──────────────────────────────────────────────────────

interface Product {
  id: string;
  name: string;
  version: string | null;
  is_active: boolean;
}

// ── Shared ─────────────────────────────────────────────────────

const INPUT_CLS =
  "w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors";

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <p className="text-sm text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
      {msg}
    </p>
  );
}

// ── KPI card ───────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <div className="rounded-xl bg-background-surface border border-border p-5 flex flex-col gap-1">
      <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">
        {label}
      </p>
      <p className={`text-3xl font-bold ${accent ?? "text-slate-100"}`}>
        {value}
      </p>
    </div>
  );
}

// ── Edit form (inline) ─────────────────────────────────────────

function EditForm({
  equipment,
  onSaved,
  onCancel,
}: {
  equipment: Equipment;
  onSaved: (updated: Equipment) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(equipment.name);
  const [serial, setSerial] = useState(equipment.serial_number ?? "");
  const [location, setLocation] = useState(equipment.location ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Nome é obrigatório.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const updated = await updateMyEquipment(equipment.id, {
        name: name.trim(),
        serial_number: serial.trim() || null,
        location: location.trim() || null,
      });
      onSaved(updated);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail ?? "Erro ao salvar. Tente novamente.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="p-4 space-y-3 border-t border-border bg-background-elevated/50"
    >
      {error && <ErrorMsg msg={error} />}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="space-y-1">
          <label className="text-xs text-slate-400">Nome</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={INPUT_CLS}
            required
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-slate-400">Número de série</label>
          <input
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            placeholder="Ex: WATFR01-12453"
            className={INPUT_CLS}
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-slate-400">Localização</label>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Ex: Sala 201, Recife"
            className={INPUT_CLS}
          />
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={saving}
          className="px-3 py-1.5 rounded-lg bg-primary text-white text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? "Salvando…" : "Salvar"}
        </button>
      </div>
    </form>
  );
}

// ── Equipment row ──────────────────────────────────────────────

function EquipmentRow({
  equipment,
  productName,
  onUpdated,
}: {
  equipment: Equipment;
  productName: string;
  onUpdated: (updated: Equipment) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [toggling, setToggling] = useState(false);

  async function handleToggle() {
    setToggling(true);
    try {
      const updated = await updateMyEquipment(equipment.id, {
        is_active: !equipment.is_active,
      });
      onUpdated(updated);
    } catch {
      /* ignore */
    } finally {
      setToggling(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-background-surface overflow-hidden">
      <div className="flex items-center gap-4 px-4 py-3">
        {/* Status dot */}
        <div
          className={`w-2.5 h-2.5 rounded-full shrink-0 ${equipment.is_active ? "bg-success" : "bg-slate-600"}`}
        />

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium text-slate-100 truncate">
              {equipment.name}
            </p>
            <span className="text-xs px-2 py-0.5 rounded-full bg-background-elevated text-slate-400 shrink-0">
              {productName}
            </span>
            {!equipment.is_active && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-500 shrink-0">
                Inativo
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            {[equipment.serial_number, equipment.location]
              .filter(Boolean)
              .join(" · ") || "—"}
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setEditing((v) => !v)}
            className="text-xs text-slate-400 hover:text-primary transition-colors"
          >
            {editing ? "Fechar" : "Editar"}
          </button>
          <span className="text-slate-700">|</span>
          <button
            onClick={handleToggle}
            disabled={toggling}
            className={`text-xs transition-colors disabled:opacity-50 ${
              equipment.is_active
                ? "text-slate-400 hover:text-danger"
                : "text-slate-400 hover:text-success"
            }`}
          >
            {toggling ? "…" : equipment.is_active ? "Desativar" : "Ativar"}
          </button>
        </div>
      </div>

      {editing && (
        <EditForm
          equipment={equipment}
          onSaved={(updated) => {
            onUpdated(updated);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      )}
    </div>
  );
}

// ── Add form ───────────────────────────────────────────────────

function AddEquipmentForm({
  products,
  onAdded,
  onCancel,
}: {
  products: Product[];
  onAdded: (eq: Equipment) => void;
  onCancel: () => void;
}) {
  const [productId, setProductId] = useState(
    products.length > 0 ? products[0].id : "",
  );
  const [name, setName] = useState("");
  const [serial, setSerial] = useState("");
  const [location, setLocation] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!productId) {
      setError("Selecione um produto.");
      return;
    }
    if (!name.trim()) {
      setError("Nome é obrigatório.");
      return;
    }
    setAdding(true);
    setError("");
    try {
      const eq = await createMyEquipment(productId, {
        name: name.trim(),
        serial_number: serial.trim() || null,
        location: location.trim() || null,
      });
      onAdded(eq);
      setName("");
      setSerial("");
      setLocation("");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(detail ?? "Erro ao adicionar equipamento.");
    } finally {
      setAdding(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-primary/30 bg-background-surface p-5 space-y-4"
    >
      <h3 className="text-sm font-semibold text-slate-200">Novo equipamento</h3>
      {error && <ErrorMsg msg={error} />}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className="text-xs text-slate-400">Produto</label>
          <select
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            className={INPUT_CLS}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.version ? ` (${p.version})` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-slate-400">Nome do equipamento</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ex: Phoebus-Pernambuco"
            className={INPUT_CLS}
            required
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-slate-400">Número de série</label>
          <input
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            placeholder="Ex: WATFR01-12453"
            className={INPUT_CLS}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-slate-400">Localização</label>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Ex: Sala 201, Recife"
            className={INPUT_CLS}
          />
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={adding}
          className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {adding ? "Adicionando…" : "Adicionar equipamento"}
        </button>
      </div>
    </form>
  );
}

// ── Main page ──────────────────────────────────────────────────

export default function EquipmentPage() {
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [filter, setFilter] = useState<"all" | "active" | "inactive">("all");

  useEffect(() => {
    Promise.all([
      api
        .get<{ items: Product[] }>("/products")
        .then((r) => r.data.items.filter((p) => p.is_active)),
      getMyEquipment(),
    ])
      .then(([prods, equips]) => {
        setProducts(prods);
        setEquipments(equips);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const productMap = Object.fromEntries(products.map((p) => [p.id, p.name]));

  const total = equipments.length;
  const active = equipments.filter((e) => e.is_active).length;
  const inactive = equipments.filter((e) => !e.is_active).length;
  const distinctProducts = new Set(equipments.map((e) => e.product_id)).size;

  const filtered = equipments.filter((e) => {
    if (filter === "active") return e.is_active;
    if (filter === "inactive") return !e.is_active;
    return true;
  });

  function handleUpdated(updated: Equipment) {
    setEquipments((prev) =>
      prev.map((e) => (e.id === updated.id ? updated : e)),
    );
  }

  function handleAdded(eq: Equipment) {
    setEquipments((prev) => [...prev, eq]);
    setShowAdd(false);
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">
            Meus equipamentos
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Gerencie os equipamentos sob sua responsabilidade
          </p>
        </div>
        {!showAdd && products.length > 0 && (
          <button
            onClick={() => setShowAdd(true)}
            className="shrink-0 px-4 py-2 rounded-lg bg-primary text-white text-sm hover:bg-primary/90 transition-colors"
          >
            + Adicionar
          </button>
        )}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiCard label="Total" value={total} />
        <KpiCard label="Ativos" value={active} accent="text-success" />
        <KpiCard label="Inativos" value={inactive} accent="text-slate-500" />
        <KpiCard
          label="Produtos distintos"
          value={distinctProducts}
          accent="text-primary"
        />
      </div>

      {/* Add form */}
      {showAdd && (
        <AddEquipmentForm
          products={products}
          onAdded={handleAdded}
          onCancel={() => setShowAdd(false)}
        />
      )}

      {/* Filter tabs */}
      {total > 0 && (
        <div className="flex gap-1 border-b border-border">
          {(
            [
              { key: "all", label: `Todos (${total})` },
              { key: "active", label: `Ativos (${active})` },
              { key: "inactive", label: `Inativos (${inactive})` },
            ] as { key: typeof filter; label: string }[]
          ).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
                filter === key
                  ? "border-primary text-primary"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* List */}
      {filtered.length === 0 ? (
        <div className="text-center py-12 text-slate-500 text-sm">
          {total === 0
            ? "Nenhum equipamento cadastrado ainda."
            : "Nenhum equipamento neste filtro."}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((eq) => (
            <EquipmentRow
              key={eq.id}
              equipment={eq}
              productName={productMap[eq.product_id] ?? "—"}
              onUpdated={handleUpdated}
            />
          ))}
        </div>
      )}

      {products.length === 0 && total === 0 && (
        <p className="text-xs text-slate-600 text-center">
          Nenhum produto disponível no sistema ainda.
        </p>
      )}
    </div>
  );
}
