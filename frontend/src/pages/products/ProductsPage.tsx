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
  Textarea,
} from "../../components/ui";
import {
  createEquipment,
  createProduct,
  getEquipments,
  getProducts,
  setEquipmentActive,
  setProductActive,
  updateEquipment,
  updateProduct,
  type Equipment,
  type Product,
} from "../../services/productService";

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  Box: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
  ),
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
  Plus: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
    </svg>
  ),
  Search: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  ),
  ChevronRight: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  ),
  User: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  ),
  Building: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  ),
};

// ── Constants ─────────────────────────────────────────────────

const PROD_PAGE = 10;
const EQUIP_PAGE = 10;

// ── Schemas ───────────────────────────────────────────────────

const productSchema = z.object({
  name: z.string().min(1, "Nome obrigatório"),
  description: z.string().optional(),
  version: z.string().optional(),
});

const equipmentSchema = z.object({
  name: z.string().min(1, "Nome obrigatório"),
  serial_number: z.string().optional(),
  model: z.string().optional(),
  description: z.string().optional(),
});

type ProductValues = z.infer<typeof productSchema>;
type EquipmentValues = z.infer<typeof equipmentSchema>;

// ── FilterTabs ────────────────────────────────────────────────

type FilterTab = "all" | "active" | "inactive";

function FilterTabs({ value, onChange }: { value: FilterTab; onChange: (v: FilterTab) => void }) {
  const tabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "Todos" },
    { key: "active", label: "Ativos" },
    { key: "inactive", label: "Inativos" },
  ];
  return (
    <div className="flex items-center gap-0.5 bg-background-elevated border border-border/60 rounded-lg p-0.5">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            value === t.key
              ? "bg-primary/20 text-primary"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ── ActivePill ────────────────────────────────────────────────

function ActivePill({
  active,
  loading,
  onToggle,
}: {
  active: boolean;
  loading?: boolean;
  onToggle?: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      disabled={!onToggle || loading}
      title={active ? "Clique para desativar" : "Clique para ativar"}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors shrink-0 ${
        active
          ? "border-emerald-700/50 bg-emerald-900/20 text-emerald-300 hover:bg-emerald-900/40 cursor-pointer"
          : "border-slate-600/50 bg-slate-800/40 text-slate-400 hover:bg-slate-700/40 cursor-pointer"
      } disabled:cursor-default`}
    >
      {loading ? (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      ) : (
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${active ? "bg-emerald-400" : "bg-slate-500"}`} />
      )}
      {active ? "Ativo" : "Inativo"}
    </button>
  );
}

// ── ProductFormModal ──────────────────────────────────────────

function ProductFormModal({
  editing,
  onClose,
  onSaved,
}: {
  editing: Product | null;
  onClose: () => void;
  onSaved: (p: Product) => void;
}) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<ProductValues>({
    resolver: zodResolver(productSchema),
    defaultValues: editing
      ? { name: editing.name, description: editing.description ?? "", version: editing.version ?? "" }
      : {},
  });

  async function onSubmit(values: ProductValues) {
    setSubmitError(null);
    try {
      const payload = {
        name: values.name,
        description: values.description || undefined,
        version: values.version || undefined,
      };
      const saved = editing
        ? await updateProduct(editing.id, payload)
        : await createProduct(payload);
      onSaved(saved);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSubmitError(
        detail === "Product name already exists"
          ? "Já existe um produto com esse nome."
          : "Erro ao salvar. Tente novamente.",
      );
    }
  }

  return (
    <Modal open onClose={onClose} title={editing ? "Editar produto" : "Novo produto"}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {submitError && <Alert variant="danger">{submitError}</Alert>}
        <Input label="Nome *" autoFocus error={form.formState.errors.name?.message} {...form.register("name")} />
        <Input label="Versão" placeholder="ex: 2.1.0" {...form.register("version")} />
        <Textarea label="Descrição" rows={3} {...form.register("description")} />
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>Cancelar</Button>
          <Button type="submit" loading={form.formState.isSubmitting}>{editing ? "Salvar" : "Criar produto"}</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── EquipmentFormModal ────────────────────────────────────────

function EquipmentFormModal({
  productId,
  editing,
  onClose,
  onSaved,
}: {
  productId: string;
  editing: Equipment | null;
  onClose: () => void;
  onSaved: (e: Equipment) => void;
}) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<EquipmentValues>({
    resolver: zodResolver(equipmentSchema),
    defaultValues: editing
      ? { name: editing.name, serial_number: editing.serial_number ?? "", model: editing.model ?? "", description: editing.description ?? "" }
      : {},
  });

  async function onSubmit(values: EquipmentValues) {
    setSubmitError(null);
    try {
      const payload = {
        name: values.name,
        serial_number: values.serial_number || undefined,
        model: values.model || undefined,
        description: values.description || undefined,
      };
      const saved = editing
        ? await updateEquipment(editing.id, payload)
        : await createEquipment(productId, payload);
      onSaved(saved);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSubmitError(
        detail === "Serial number already in use"
          ? "Este número de série já está em uso."
          : "Erro ao salvar. Tente novamente.",
      );
    }
  }

  return (
    <Modal open onClose={onClose} title={editing ? "Editar equipamento" : "Novo equipamento"}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {submitError && <Alert variant="danger">{submitError}</Alert>}
        <Input label="Nome *" autoFocus error={form.formState.errors.name?.message} {...form.register("name")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Número de série" placeholder="ex: SN-001234" {...form.register("serial_number")} />
          <Input label="Modelo" placeholder="ex: ThinkPad X1" {...form.register("model")} />
        </div>
        <Textarea label="Descrição" rows={2} {...form.register("description")} />
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>Cancelar</Button>
          <Button type="submit" loading={form.formState.isSubmitting}>{editing ? "Salvar" : "Criar equipamento"}</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── ProductsPage ──────────────────────────────────────────────

export default function ProductsPage() {
  // Products
  const [products, setProducts] = useState<Product[]>([]);
  const [totalProducts, setTotalProducts] = useState(0);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState<string | null>(null);
  const [productSearch, setProductSearch] = useState("");
  const [productFilter, setProductFilter] = useState<FilterTab>("active");
  const [productPage, setProductPage] = useState(1);
  const [togglingProduct, setTogglingProduct] = useState<string | null>(null);

  // Product modals
  const [productFormOpen, setProductFormOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);

  // Selected product + equipments
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [totalEquip, setTotalEquip] = useState(0);
  const [equipLoading, setEquipLoading] = useState(false);
  const [equipError, setEquipError] = useState<string | null>(null);
  const [equipPage, setEquipPage] = useState(1);
  const [equipFilter, setEquipFilter] = useState<FilterTab>("active");
  const [equipSearch, setEquipSearch] = useState("");
  const [togglingEquip, setTogglingEquip] = useState<string | null>(null);

  // Equipment modals
  const [equipFormOpen, setEquipFormOpen] = useState(false);
  const [editingEquip, setEditingEquip] = useState<Equipment | null>(null);

  function loadProducts(p = productPage) {
    setProductsLoading(true);
    setProductsError(null);
    getProducts({
      search: productSearch || undefined,
      is_active: productFilter === "all" ? undefined : productFilter === "active",
      limit: PROD_PAGE,
      offset: (p - 1) * PROD_PAGE,
    })
      .then((res) => { setProducts(res.items); setTotalProducts(res.total); })
      .catch(() => setProductsError("Não foi possível carregar os produtos."))
      .finally(() => setProductsLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadProducts(); }, [productSearch, productFilter, productPage]);

  function loadEquipments(productId: string, p = equipPage) {
    setEquipLoading(true);
    setEquipError(null);
    getEquipments(productId, {
      search: equipSearch || undefined,
      is_active: equipFilter === "all" ? undefined : equipFilter === "active",
      limit: EQUIP_PAGE,
      offset: (p - 1) * EQUIP_PAGE,
    })
      .then((res) => { setEquipments(res.items); setTotalEquip(res.total); })
      .catch(() => setEquipError("Não foi possível carregar os equipamentos."))
      .finally(() => setEquipLoading(false));
  }

  useEffect(() => {
    if (selectedProduct) loadEquipments(selectedProduct.id, equipPage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProduct?.id, equipFilter, equipSearch, equipPage]);

  async function toggleProduct(product: Product) {
    setTogglingProduct(product.id);
    try {
      const updated = await setProductActive(product.id, !product.is_active);
      setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      if (selectedProduct?.id === updated.id) setSelectedProduct(updated);
    } finally {
      setTogglingProduct(null);
    }
  }

  async function toggleEquipment(equip: Equipment) {
    setTogglingEquip(equip.id);
    try {
      const updated = await setEquipmentActive(equip.id, !equip.is_active);
      setEquipments((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    } finally {
      setTogglingEquip(null);
    }
  }

  function handleProductSaved(p: Product) {
    const wasEditing = !!editingProduct;
    setProductFormOpen(false);
    setEditingProduct(null);
    setProducts((prev) => {
      const idx = prev.findIndex((x) => x.id === p.id);
      if (idx >= 0) { const next = [...prev]; next[idx] = p; return next; }
      return [p, ...prev];
    });
    if (!wasEditing) setTotalProducts((t) => t + 1);
  }

  function handleEquipSaved(e: Equipment) {
    setEquipFormOpen(false);
    setEditingEquip(null);
    setEquipments((prev) => {
      const idx = prev.findIndex((x) => x.id === e.id);
      if (idx >= 0) { const next = [...prev]; next[idx] = e; return next; }
      return [e, ...prev];
    });
    if (!editingEquip) setTotalEquip((t) => t + 1);
  }

  function selectProduct(p: Product) {
    if (selectedProduct?.id === p.id) {
      setSelectedProduct(null);
    } else {
      setSelectedProduct(p);
      setEquipPage(1);
      setEquipSearch("");
    }
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Produtos</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {totalProducts} {totalProducts === 1 ? "produto cadastrado" : "produtos cadastrados"}
          </p>
        </div>
      </div>

      {/* Products + Equipment — split layout when product selected */}
      <div className={`grid gap-5 items-start transition-all duration-300 ${selectedProduct ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1"}`}>

      {/* Products card */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-200">Catálogo de produtos</p>
            <p className="text-xs text-slate-500 mt-0.5">Clique num produto para ver seus equipamentos.</p>
          </div>
          <div className="flex items-center gap-3">
            <FilterTabs value={productFilter} onChange={(v) => { setProductFilter(v); setProductPage(1); }} />
            <Button size="sm" onClick={() => { setEditingProduct(null); setProductFormOpen(true); }}>
              {IC.Plus} Novo produto
            </Button>
          </div>
        </div>

        {/* Search */}
        <div className="px-4 py-2.5 border-b border-border">
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none">{IC.Search}</span>
            <input
              className="w-full pl-9 pr-3 py-2 rounded-xl border border-border/60 bg-background-elevated text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
              placeholder="Buscar produto…"
              value={productSearch}
              onChange={(e) => { setProductSearch(e.target.value); setProductPage(1); }}
            />
          </div>
        </div>

        {productsError && <div className="p-4"><Alert variant="danger">{productsError}</Alert></div>}

        {productsLoading ? (
          <div className="flex h-32 items-center justify-center"><Spinner /></div>
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-10 h-10 rounded-full bg-background-elevated border border-border flex items-center justify-center text-slate-600 mb-3">{IC.Box}</div>
            <p className="text-sm text-slate-400">Nenhum produto encontrado.</p>
            <button onClick={() => setProductFormOpen(true)} className="mt-2 text-sm text-primary hover:text-primary/80 transition-colors cursor-pointer">Criar o primeiro produto</button>
          </div>
        ) : (
          <>
            <div className="divide-y divide-border">
              {products.map((p) => (
                <div
                  key={p.id}
                  onClick={() => selectProduct(p)}
                  className={`flex items-center gap-4 px-4 py-3 hover:bg-background-elevated/40 transition-colors cursor-pointer ${
                    selectedProduct?.id === p.id ? "bg-primary/5 border-l-2 border-primary" : ""
                  }`}
                >
                  {/* Icon */}
                  <div className="w-9 h-9 rounded-lg bg-background-elevated border border-border/60 flex items-center justify-center shrink-0 text-slate-400">
                    {IC.Box}
                  </div>

                  {/* Name + description */}
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium truncate ${p.is_active ? "text-slate-200" : "text-slate-500 line-through"}`}>
                      {p.name}
                    </p>
                    {p.description && (
                      <p className="text-xs text-slate-500 truncate">{p.description}</p>
                    )}
                  </div>

                  {/* Version badge */}
                  {p.version && (
                    <span className="hidden sm:inline-flex shrink-0 text-xs font-mono px-2 py-0.5 rounded-full bg-background-elevated border border-border/50 text-slate-400">
                      v{p.version}
                    </span>
                  )}

                  {/* Active pill */}
                  <div onClick={(e) => e.stopPropagation()}>
                    <ActivePill
                      active={p.is_active}
                      loading={togglingProduct === p.id}
                      onToggle={() => toggleProduct(p)}
                    />
                  </div>

                  {/* Edit */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingProduct(p); setProductFormOpen(true); }}
                    title="Editar"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                  >
                    {IC.Edit}
                  </button>

                  {/* Chevron */}
                  <span className={`text-slate-600 transition-transform ${selectedProduct?.id === p.id ? "rotate-90" : ""}`}>
                    {IC.ChevronRight}
                  </span>
                </div>
              ))}
            </div>

            <div className="px-4 py-2 border-t border-border">
              <Pagination page={productPage} pageSize={PROD_PAGE} total={totalProducts} onPageChange={setProductPage} itemLabel="produtos" />
            </div>
          </>
        )}
      </Card>

      {/* Equipments card */}
      {selectedProduct && (
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-200">
                Equipamentos
                <span className="font-normal text-slate-400 ml-2">— {selectedProduct.name}</span>
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                {totalEquip} {totalEquip === 1 ? "equipamento" : "equipamentos"}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <FilterTabs value={equipFilter} onChange={(v) => { setEquipFilter(v); setEquipPage(1); }} />
              <Button size="sm" onClick={() => { setEditingEquip(null); setEquipFormOpen(true); }}>
                {IC.Plus} Novo Equipamento
              </Button>
            </div>
          </div>

          {/* Equipment search */}
          <div className="px-4 py-2.5 border-b border-border">
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none">{IC.Search}</span>
              <input
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-border/60 bg-background-elevated text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
                placeholder="Buscar equipamento…"
                value={equipSearch}
                onChange={(e) => { setEquipSearch(e.target.value); setEquipPage(1); }}
              />
            </div>
          </div>

          {equipError && <div className="p-4"><Alert variant="danger">{equipError}</Alert></div>}

          {equipLoading ? (
            <div className="flex h-32 items-center justify-center"><Spinner /></div>
          ) : equipments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-10 h-10 rounded-full bg-background-elevated border border-border flex items-center justify-center text-slate-600 mb-3">{IC.Cpu}</div>
              <p className="text-sm text-slate-400">Nenhum equipamento para este produto.</p>
              <button onClick={() => setEquipFormOpen(true)} className="mt-2 text-sm text-primary hover:text-primary/80 transition-colors cursor-pointer">
                Adicionar equipamento
              </button>
            </div>
          ) : (
            <>
              <div className="divide-y divide-border">
                {equipments.map((e) => (
                  <div key={e.id} className="flex items-center gap-4 px-4 py-3 hover:bg-background-elevated/40 transition-colors">
                    {/* Icon */}
                    <div className="w-9 h-9 rounded-lg bg-background-elevated border border-border/60 flex items-center justify-center shrink-0 text-slate-400">
                      {IC.Cpu}
                    </div>

                    {/* Name + serial */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium truncate ${e.is_active ? "text-slate-200" : "text-slate-500 line-through"}`}>
                        {e.name}
                      </p>
                      {e.serial_number && (
                        <p className="text-xs font-mono text-slate-500 truncate">{e.serial_number}</p>
                      )}
                    </div>

                    {/* Model */}
                    {e.model && (
                      <span className="hidden md:inline-flex shrink-0 text-xs px-2 py-0.5 rounded-full bg-background-elevated border border-border/50 text-slate-400">
                        {e.model}
                      </span>
                    )}

                    {/* Owner + company — always visible */}
                    <div className="flex flex-col items-end shrink-0 max-w-[180px]">
                      <span className="flex items-center gap-1 text-xs text-slate-300 truncate">
                        {e.owner_name ?? <span className="text-slate-600">—</span>}
                        {IC.User}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-slate-500 truncate mt-0.5">
                        {e.company_name
                          ? <>
                              {e.company_name}
                              {e.company_cnpj && <span className="font-mono text-slate-600 ml-1">· {e.company_cnpj}</span>}
                            </>
                          : <span className="text-slate-600">—</span>
                        }
                        {IC.Building}
                      </span>
                    </div>

                    {/* Status */}
                    <div onClick={(e) => e.stopPropagation()}>
                      <ActivePill
                        active={e.is_active}
                        loading={togglingEquip === e.id}
                        onToggle={() => toggleEquipment(e)}
                      />
                    </div>

                    {/* Edit */}
                    <button
                      onClick={() => { setEditingEquip(e); setEquipFormOpen(true); }}
                      title="Editar"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                    >
                      {IC.Edit}
                    </button>
                  </div>
                ))}
              </div>

              <div className="px-4 py-2 border-t border-border">
                <Pagination page={equipPage} pageSize={EQUIP_PAGE} total={totalEquip} onPageChange={setEquipPage} itemLabel="equipamentos" />
              </div>
            </>
          )}
        </Card>
      )}

      </div> {/* end split grid */}

      {/* Modals */}
      {productFormOpen && (
        <ProductFormModal
          editing={editingProduct}
          onClose={() => { setProductFormOpen(false); setEditingProduct(null); }}
          onSaved={handleProductSaved}
        />
      )}
      {equipFormOpen && selectedProduct && (
        <EquipmentFormModal
          productId={selectedProduct.id}
          editing={editingEquip}
          onClose={() => { setEquipFormOpen(false); setEditingEquip(null); }}
          onSaved={handleEquipSaved}
        />
      )}
    </div>
  );
}
