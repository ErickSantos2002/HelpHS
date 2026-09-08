import { zodResolver } from "@hookform/resolvers/zod";
import { formatCnpj } from "../../lib/documents";
import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Button,
  Card,
  FilterSelect,
  FormDropdown,
  Icon,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  SearchSelect,
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
import { getUsers } from "../../services/userService";
import { getApiError } from "../../lib/apiError";

// ── Constants ─────────────────────────────────────────────────
//
// A tabela `IC` que morava aqui tinha nove `<svg>` desenhados à mão. Oito
// batiam caractere a caractere com um traçado do pacote (`box`, `edit`,
// `plus`, `search`, `chevronRight`, `eye`, `user`, `building`); o nono era um
// segundo desenho de chip — retângulo com pinos — que **significa** o mesmo
// que `cpu` e por isso se unificou com ele, em vez de virar ícone novo.
// Desenho local é o defeito que esta migração existe para tirar: dois chips
// diferentes na mesma família são dois sistemas de desenho, não um.

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
  owner_id: z.string().nullable().optional(),
});

type ProductValues = z.infer<typeof productSchema>;
type EquipmentValues = z.infer<typeof equipmentSchema>;

// ── FilterTabs ────────────────────────────────────────────────

type FilterTab = "all" | "active" | "inactive";

/**
 * As três opções, escritas **uma vez**.
 *
 * Estavam duas: aqui, como `{ key, label }`, e vinte linhas abaixo no
 * `FilterSelect` dos produtos, como `{ value, label }`. Diziam o mesmo hoje —
 * e é exatamente assim que prioridade começou antes de virar dez mapas
 * divergentes. Renomear "Inativos" num lugar só é o modo de falhar que isto
 * fecha.
 */
const FILTROS: { value: FilterTab; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "active", label: "Ativos" },
  { value: "inactive", label: "Inativos" },
];

function FilterTabs({ value, onChange }: { value: FilterTab; onChange: (v: FilterTab) => void }) {
  return (
    <div className="flex items-center gap-0.5 bg-surface-elevated border border-borda/60 rounded-lg p-0.5">
      {FILTROS.map((t) => (
        <button
          key={t.value}
          type="button"
          aria-pressed={value === t.value}
          onClick={() => onChange(t.value)}
          // O par da tinta, e não `bg-primary/20 text-primary`: o degrau de
          // marca como cor de TEXTO sobre a própria tinta é o caso que a E8
          // mediu em 2,77:1. `on-tint-primary` é o par medido dessa tinta.
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            value === t.value
              ? "bg-tint-primary text-on-tint-primary"
              : "text-conteudo-muted hover:text-conteudo"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

// ── ActivePill ────────────────────────────────────────────────

/**
 * O selo de ativo/inativo, agora sobre as tintas medidas.
 *
 * Era paleta crua dos dois lados — `emerald-300/50/100/500` no ativo,
 * `slate-100/200/300/400/500` no inativo —, com oito classes `dark:` para
 * inverter à mão o que o token já inverte sozinho. As duas receitas passaram
 * a ser as mesmas do `Badge`: tinta no fundo, o par da tinta no texto, e a
 * cor cheia da rampa a 30% na borda.
 *
 * **O hover mudou de lugar, e é de propósito.** A regra (a) do D8-a proíbe
 * modificador de opacidade sobre as tintas — elas já carregam 15% no token, e
 * `bg-tint-success/20` multiplicaria os dois. Sem `bg-tint-*` mais escuro
 * para onde ir, a resposta ao ponteiro passou para a borda, que é cor cheia e
 * aceita o modificador.
 *
 * O ponto não usa o degrau 500: a E19 mediu `--color-success-500` em 2,54:1
 * como preenchimento no tema claro, abaixo do piso de 3:1 da WCAG 1.4.11. O
 * neutro é `--border-control`, o único que **inverte por tema** — é o mesmo
 * raciocínio que `lib/prioridade.ts` registra para a prioridade baixa.
 *
 * O ponto nunca informa sozinho: o rótulo "Ativo"/"Inativo" vai ao lado, em
 * texto, e é ele que carrega o estado.
 */
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
      type="button"
      onClick={onToggle}
      disabled={!onToggle || loading}
      title={active ? "Clique para desativar" : "Clique para ativar"}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors shrink-0 ${
        active
          ? "border-success/30 bg-tint-success text-on-tint-success hover:border-success/60 cursor-pointer"
          : "border-borda bg-tint-neutral text-on-tint-neutral hover:border-borda-strong cursor-pointer"
      } disabled:cursor-default`}
    >
      {loading ? (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      ) : (
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${active ? "bg-fill-success" : "bg-borda-control"}`} />
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
  productName,
  editing,
  onClose,
  onSaved,
}: {
  productId: string;
  productName: string;
  editing: Equipment | null;
  onClose: () => void;
  onSaved: (e: Equipment) => void;
}) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [allProducts, setAllProducts] = useState<Product[]>([]);

  useEffect(() => {
    getProducts({ is_active: true, limit: 100 }).then((r) => {
      setAllProducts(r.items);
      if (!editing) form.setValue("model", productName);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const form = useForm<EquipmentValues>({
    resolver: zodResolver(equipmentSchema),
    defaultValues: editing
      ? { name: editing.name, serial_number: editing.serial_number ?? "", model: editing.model ?? "", description: editing.description ?? "", owner_id: editing.owner_id ?? null }
      : { model: productName, owner_id: null },
  });

  // O nome do dono já vem na listagem; guardá-lo evita uma busca só para
  // mostrar o que a tela acabou de exibir na tabela.
  const [donoAtual, setDonoAtual] = useState<string | null>(editing?.owner_name ?? null);

  async function buscarClientes(termo: string) {
    const { items } = await getUsers({ role: "client", search: termo, limit: 20 });
    return items.map((u) => ({ value: u.id, label: u.name, hint: u.email }));
  }

  async function onSubmit(values: EquipmentValues) {
    setSubmitError(null);
    try {
      const payload = {
        name: values.name,
        serial_number: values.serial_number || undefined,
        model: values.model || undefined,
        description: values.description || undefined,
        // `null` explícito desvincula; `|| undefined` aqui comeria o null e
        // deixaria o dono antigo no lugar.
        owner_id: values.owner_id ?? null,
      };
      const saved = editing
        ? await updateEquipment(editing.id, payload)
        : await createEquipment(productId, payload);
      onSaved(saved);
    } catch (err: unknown) {
      // O seletor de dono trouxe um erro que a mensagem genérica engoliria: o
      // 400 de "dono precisa ser um cliente cadastrado" já vem pronto e em
      // português do backend. `getApiError` devolve o motivo real quando
      // existe e cai no texto genérico quando não.
      setSubmitError(getApiError(err, "Erro ao salvar. Tente novamente."));
    }
  }

  return (
    <Modal open onClose={onClose} title={editing ? "Editar equipamento" : "Novo equipamento"}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {submitError && <Alert variant="danger">{submitError}</Alert>}
        <Input label="Nome *" autoFocus error={form.formState.errors.name?.message} {...form.register("name")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Número de série" placeholder="ex: SN-001234" {...form.register("serial_number")} />
          <Controller
            control={form.control}
            name="model"
            render={({ field }) => (
              <FormDropdown
                label="Modelo"
                placeholder="— Selecionar —"
                value={field.value ?? ""}
                onChange={field.onChange}
                options={allProducts.map((p) => ({ value: p.name, label: p.name }))}
              />
            )}
          />
        </div>
        <Controller
          control={form.control}
          name="owner_id"
          render={({ field }) => (
            <SearchSelect
              label="Dono"
              value={field.value ?? null}
              selectedLabel={donoAtual}
              onChange={(id, nome) => {
                field.onChange(id);
                setDonoAtual(nome);
              }}
              onSearch={buscarClientes}
              placeholder="Buscar cliente por nome ou e-mail…"
              emptyLabel="— Sem dono —"
            />
          )}
        />
        <Textarea label="Descrição" rows={2} {...form.register("description")} />
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>Cancelar</Button>
          <Button type="submit" loading={form.formState.isSubmitting}>{editing ? "Salvar" : "Criar equipamento"}</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── EquipmentDetailModal ──────────────────────────────────────

function EquipmentDetailModal({ equip, onClose, onEdit }: { equip: Equipment; onClose: () => void; onEdit: () => void }) {
  function row(label: string, value?: string | null) {
    if (!value) return null;
    return (
      <div className="flex flex-col gap-0.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-conteudo-muted">{label}</span>
        <span className="text-sm text-conteudo break-words">{value}</span>
      </div>
    );
  }

  return (
    <Modal open onClose={onClose} title={equip.name}>
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <ActivePill active={equip.is_active} />
          {equip.model && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-surface-elevated border border-borda/50 text-conteudo-muted">
              {equip.model}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-xl border border-borda bg-surface-elevated p-4">
          {row("Número de série", equip.serial_number)}
          {row("Modelo", equip.model)}
          {row("Localização", equip.location)}
          {row("Descrição", equip.description)}
        </div>

        {(equip.owner_name || equip.company_name) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-xl border border-borda bg-surface-elevated p-4">
            {equip.owner_name && (
              <div className="flex flex-col gap-0.5">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-conteudo-muted">Responsável</span>
                <span className="text-sm text-conteudo">{equip.owner_name}</span>
                {equip.owner_email && <span className="text-xs text-conteudo-muted">{equip.owner_email}</span>}
              </div>
            )}
            {equip.company_name && (
              <div className="flex flex-col gap-0.5">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-conteudo-muted">Empresa</span>
                <span className="text-sm text-conteudo">{equip.company_name}</span>
                {equip.company_cnpj && <span className="text-xs text-conteudo-muted">{formatCnpj(equip.company_cnpj)}</span>}
              </div>
            )}
          </div>
        )}

        {(equip.created_at || equip.updated_at) && (
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-conteudo-muted">
            {equip.created_at && <span>Criado em {new Date(equip.created_at).toLocaleDateString("pt-BR")}</span>}
            {equip.updated_at && <span>Atualizado em {new Date(equip.updated_at).toLocaleDateString("pt-BR")}</span>}
          </div>
        )}
      </div>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>Fechar</Button>
        <Button onClick={() => { onClose(); onEdit(); }}><Icon name="edit" size={16} strokeWidth={2} /> Editar</Button>
      </ModalFooter>
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
  // Filtro de órfãos: equipamento cadastrado sem dono. É filtro de servidor
  // (`without_owner`) porque a lista é paginada — peneirar aqui só acharia o
  // órfão que por acaso caiu na página aberta.
  const [equipSemDono, setEquipSemDono] = useState(false);
  const [togglingEquip, setTogglingEquip] = useState<string | null>(null);

  // Equipment modals
  const [equipFormOpen, setEquipFormOpen] = useState(false);
  const [editingEquip, setEditingEquip] = useState<Equipment | null>(null);
  const [viewEquip, setViewEquip] = useState<Equipment | null>(null);

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
      without_owner: equipSemDono || undefined,
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
  }, [selectedProduct?.id, equipFilter, equipSearch, equipSemDono, equipPage]);

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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="text-center sm:text-left">
          <h1 className="text-2xl font-bold text-conteudo-heading">Produtos</h1>
          <p className="text-conteudo-muted text-sm mt-0.5">
            {totalProducts} {totalProducts === 1 ? "produto cadastrado" : "produtos cadastrados"}
          </p>
        </div>
        <Button className="w-full sm:w-auto" onClick={() => { setEditingProduct(null); setProductFormOpen(true); }}>
          <Icon name="plus" size={16} strokeWidth={2} /> Novo produto
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row md:items-center gap-2">
        <div className="relative md:flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-conteudo-muted pointer-events-none"><Icon name="search" size={16} strokeWidth={2} /></span>
          <input
            className="w-full pl-9 pr-3 py-2 rounded-xl border border-borda/60 bg-surface text-sm text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            aria-label="Buscar produto"
            placeholder="Buscar produto…"
            value={productSearch}
            onChange={(e) => { setProductSearch(e.target.value); setProductPage(1); }}
          />
        </div>
        <div className="flex flex-wrap gap-2 items-center justify-center sm:justify-start">
          <FilterSelect
            options={FILTROS}
            placeholder="Status"
            value={productFilter}
            onChange={(v) => { setProductFilter(v as FilterTab); setProductPage(1); }}
          />
          {(productSearch || productFilter !== "active") && (
            <button
              onClick={() => { setProductSearch(""); setProductFilter("active"); setProductPage(1); }}
              className="text-xs text-conteudo-muted hover:text-conteudo transition-colors px-2 py-1.5 rounded-lg hover:bg-surface-elevated cursor-pointer"
            >
              Limpar filtros
            </button>
          )}
        </div>
      </div>

      {/* Products + Equipment — split layout when product selected */}
      <div className={`grid gap-5 items-start transition-all duration-300 ${selectedProduct ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1"}`}>

      {/* Products card */}
      <Card padding="none">
        {productsError && <div className="p-4"><Alert variant="danger">{productsError}</Alert></div>}

        {productsLoading ? (
          <div className="flex h-32 items-center justify-center"><Spinner /></div>
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-10 h-10 rounded-full bg-surface-elevated border border-borda flex items-center justify-center text-conteudo-muted mb-3"><Icon name="box" size={16} strokeWidth={2} /></div>
            <p className="text-sm text-conteudo-muted">Nenhum produto encontrado.</p>
            <button onClick={() => setProductFormOpen(true)} className="mt-2 text-sm text-conteudo-link hover:text-conteudo-link-hover transition-colors cursor-pointer">Criar o primeiro produto</button>
          </div>
        ) : (
          <>
            <div className="divide-y divide-borda">
              {products.map((p) => (
                <div
                  key={p.id}
                  onClick={() => selectProduct(p)}
                  className={`flex items-center gap-4 px-4 py-3 hover:bg-surface-elevated/40 transition-colors cursor-pointer ${
                    selectedProduct?.id === p.id ? "bg-primary/5 border-l-2 border-primary" : ""
                  }`}
                >
                  {/* Icon */}
                  <div className="w-9 h-9 rounded-lg bg-surface-elevated border border-borda/60 flex items-center justify-center shrink-0 text-conteudo-muted">
                    <Icon name="box" size={16} strokeWidth={2} />
                  </div>

                  {/* Name + description */}
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium truncate ${p.is_active ? "text-conteudo" : "text-conteudo-muted line-through"}`}>
                      {p.name}
                    </p>
                    {p.description && (
                      <p className="text-xs text-conteudo-muted truncate">{p.description}</p>
                    )}
                  </div>

                  {/* Version badge */}
                  {p.version && (
                    <span className="hidden sm:inline-flex shrink-0 text-xs font-mono px-2 py-0.5 rounded-full bg-surface-elevated border border-borda/50 text-conteudo-muted">
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
                    className="p-1.5 rounded-lg text-conteudo-muted hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                  >
                    <Icon name="edit" size={16} strokeWidth={2} />
                  </button>

                  {/* Chevron */}
                  <span className={`text-conteudo-muted transition-transform ${selectedProduct?.id === p.id ? "rotate-90" : ""}`}>
                    <Icon name="chevronRight" size={16} strokeWidth={2} />
                  </span>
                </div>
              ))}
            </div>

            <div className="px-4 py-2 border-t border-borda">
              <Pagination page={productPage} pageSize={PROD_PAGE} total={totalProducts} onPageChange={setProductPage} itemLabel="produtos" />
            </div>
          </>
        )}
      </Card>

      {/* Equipments card */}
      {selectedProduct && (
        <Card padding="none">
          <div className="px-4 py-3 border-b border-borda flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-conteudo">
                Equipamentos
                <span className="font-normal text-conteudo-muted ml-2">— {selectedProduct.name}</span>
              </p>
              <p className="text-xs text-conteudo-muted mt-0.5">
                {totalEquip} {totalEquip === 1 ? "equipamento" : "equipamentos"}
              </p>
            </div>
            <div className="flex items-center justify-between sm:justify-end gap-3">
              <FilterTabs value={equipFilter} onChange={(v) => { setEquipFilter(v); setEquipPage(1); }} />
              <Button size="sm" onClick={() => { setEditingEquip(null); setEquipFormOpen(true); }}>
                <Icon name="plus" size={16} strokeWidth={2} /> <span className="hidden xs:inline">Novo </span>Equipamento
              </Button>
            </div>
          </div>

          {/* Equipment search */}
          <div className="px-4 py-2.5 border-b border-borda flex flex-col sm:flex-row sm:items-center gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-conteudo-muted pointer-events-none"><Icon name="search" size={16} strokeWidth={2} /></span>
              <input
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-borda/60 bg-surface-elevated text-sm text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
                aria-label="Buscar equipamento"
                placeholder="Buscar equipamento…"
                value={equipSearch}
                onChange={(e) => { setEquipSearch(e.target.value); setEquipPage(1); }}
              />
            </div>
            <button
              type="button"
              aria-pressed={equipSemDono}
              onClick={() => { setEquipSemDono((v) => !v); setEquipPage(1); }}
              className={`shrink-0 whitespace-nowrap rounded-lg border px-3 py-2 text-sm font-medium transition-colors cursor-pointer ${
                equipSemDono
                  ? "border-primary bg-tint-primary text-on-tint-primary"
                  : "border-borda/60 bg-surface-elevated text-conteudo-muted hover:border-borda hover:text-conteudo"
              }`}
            >
              Sem dono
            </button>
          </div>

          {equipError && <div className="p-4"><Alert variant="danger">{equipError}</Alert></div>}

          {equipLoading ? (
            <div className="flex h-32 items-center justify-center"><Spinner /></div>
          ) : equipments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-10 h-10 rounded-full bg-surface-elevated border border-borda flex items-center justify-center text-conteudo-muted mb-3"><Icon name="cpu" size={16} strokeWidth={2} /></div>
              {equipSemDono ? (
                <>
                  <p className="text-sm text-conteudo-muted">Nenhum equipamento sem dono para este produto.</p>
                  <button onClick={() => { setEquipSemDono(false); setEquipPage(1); }} className="mt-2 text-sm text-conteudo-link hover:text-conteudo-link-hover transition-colors cursor-pointer">
                    Ver todos
                  </button>
                </>
              ) : (
                <>
                  <p className="text-sm text-conteudo-muted">Nenhum equipamento para este produto.</p>
                  <button onClick={() => setEquipFormOpen(true)} className="mt-2 text-sm text-conteudo-link hover:text-conteudo-link-hover transition-colors cursor-pointer">
                    Adicionar equipamento
                  </button>
                </>
              )}
            </div>
          ) : (
            <>
              <div className="divide-y divide-borda">
                {equipments.map((e) => (
                  <div key={e.id} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-elevated/40 transition-colors cursor-pointer" onClick={() => setViewEquip(e)}>
                    {/* Icon */}
                    <div className="w-9 h-9 rounded-lg bg-surface-elevated border border-borda/60 flex items-center justify-center shrink-0 text-conteudo-muted">
                      <Icon name="cpu" size={16} strokeWidth={2} />
                    </div>

                    {/* Name + serial */}
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium truncate ${e.is_active ? "text-conteudo" : "text-conteudo-muted line-through"}`}>
                        {e.name}
                      </p>
                      {e.serial_number && (
                        <p className="text-xs font-mono text-conteudo-muted truncate">{e.serial_number}</p>
                      )}
                    </div>

                    {/* Model */}
                    {e.model && (
                      <span className="hidden md:inline-flex shrink-0 text-xs px-2 py-0.5 rounded-full bg-surface-elevated border border-borda/50 text-conteudo-muted">
                        {e.model}
                      </span>
                    )}

                    {/* Owner + company */}
                    <div className="hidden sm:flex flex-col items-end shrink-0 max-w-[180px]">
                      <span className="flex items-center gap-1 text-xs text-conteudo truncate">
                        {e.owner_name ?? <span className="text-conteudo-muted">—</span>}
                        <Icon name="user" size={14} strokeWidth={2} />
                      </span>
                      <span className="flex items-center gap-1 text-xs text-conteudo-muted truncate mt-0.5">
                        {e.company_name
                          ? <>
                              {e.company_name}
                              {e.company_cnpj && <span className="font-mono text-conteudo-muted ml-1">· {formatCnpj(e.company_cnpj)}</span>}
                            </>
                          : <span className="text-conteudo-muted">—</span>
                        }
                        <Icon name="building" size={14} strokeWidth={2} />
                      </span>
                    </div>

                    {/* Status */}
                    <div onClick={(ev) => ev.stopPropagation()}>
                      <ActivePill
                        active={e.is_active}
                        loading={togglingEquip === e.id}
                        onToggle={() => toggleEquipment(e)}
                      />
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-0.5 shrink-0" onClick={(ev) => ev.stopPropagation()}>
                      <button
                        onClick={() => setViewEquip(e)}
                        title="Visualizar"
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                      >
                        <Icon name="eye" size={16} strokeWidth={2} />
                      </button>
                      <button
                        onClick={() => { setEditingEquip(e); setEquipFormOpen(true); }}
                        title="Editar"
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                      >
                        <Icon name="edit" size={16} strokeWidth={2} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="px-4 py-2 border-t border-borda">
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
          productName={selectedProduct.name}
          editing={editingEquip}
          onClose={() => { setEquipFormOpen(false); setEditingEquip(null); }}
          onSaved={handleEquipSaved}
        />
      )}
      {viewEquip && (
        <EquipmentDetailModal
          equip={viewEquip}
          onClose={() => setViewEquip(null)}
          onEdit={() => { setEditingEquip(viewEquip); setEquipFormOpen(true); }}
        />
      )}
    </div>
  );
}
