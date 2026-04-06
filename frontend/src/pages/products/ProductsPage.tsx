import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Button,
  Card,
  CardHeader,
  CardTitle,
  Input,
  Modal,
  ModalFooter,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeaderCell,
  TableRow,
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

// ── Active toggle ─────────────────────────────────────────────

function ActiveToggle({
  active,
  loading,
  onToggle,
}: {
  active: boolean;
  loading: boolean;
  onToggle: () => void;
}) {
  if (loading) return <Spinner size="sm" />;
  return (
    <button
      onClick={onToggle}
      title={active ? "Desativar" : "Ativar"}
      className={`w-10 h-5 rounded-full transition-colors relative shrink-0 ${
        active ? "bg-primary" : "bg-border"
      }`}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
          active ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

// ── Product form schema ───────────────────────────────────────

const productSchema = z.object({
  name: z.string().min(1, "Nome obrigatório").max(255),
  description: z.string().optional(),
  version: z.string().optional(),
});
type ProductValues = z.infer<typeof productSchema>;

// ── Equipment form schema ─────────────────────────────────────

const equipmentSchema = z.object({
  name: z.string().min(1, "Nome obrigatório").max(255),
  serial_number: z.string().optional(),
  model: z.string().optional(),
  description: z.string().optional(),
});
type EquipmentValues = z.infer<typeof equipmentSchema>;

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

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProductValues>({
    resolver: zodResolver(productSchema),
    defaultValues: editing
      ? {
          name: editing.name,
          description: editing.description ?? "",
          version: editing.version ?? "",
        }
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
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setSubmitError(
        detail === "Product name already exists"
          ? "Já existe um produto com esse nome."
          : "Erro ao salvar. Tente novamente.",
      );
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? "Editar produto" : "Novo produto"}
    >
      {submitError && (
        <Alert variant="danger" className="mb-4">
          {submitError}
        </Alert>
      )}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Nome *"
          error={errors.name?.message}
          {...register("name")}
        />
        <Input
          label="Versão"
          placeholder="ex: 2.1.0"
          {...register("version")}
        />
        <Textarea label="Descrição" rows={3} {...register("description")} />
        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {editing ? "Salvar" : "Criar"}
          </Button>
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

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<EquipmentValues>({
    resolver: zodResolver(equipmentSchema),
    defaultValues: editing
      ? {
          name: editing.name,
          serial_number: editing.serial_number ?? "",
          model: editing.model ?? "",
          description: editing.description ?? "",
        }
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
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setSubmitError(
        detail === "Serial number already in use"
          ? "Este número de série já está em uso."
          : "Erro ao salvar. Tente novamente.",
      );
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? "Editar equipamento" : "Novo equipamento"}
    >
      {submitError && (
        <Alert variant="danger" className="mb-4">
          {submitError}
        </Alert>
      )}
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Nome *"
          error={errors.name?.message}
          {...register("name")}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Número de série"
            placeholder="ex: SN-001234"
            {...register("serial_number")}
          />
          <Input
            label="Modelo"
            placeholder="ex: ThinkPad X1"
            {...register("model")}
          />
        </div>
        <Textarea label="Descrição" rows={2} {...register("description")} />
        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {editing ? "Salvar" : "Criar"}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── ProductsPage ──────────────────────────────────────────────

export default function ProductsPage() {
  // Products state
  const [products, setProducts] = useState<Product[]>([]);
  const [totalProducts, setTotalProducts] = useState(0);
  const [productsLoading, setProductsLoading] = useState(true);
  const [productsError, setProductsError] = useState<string | null>(null);
  const [productSearch, setProductSearch] = useState("");
  const [showInactiveProducts, setShowInactiveProducts] = useState(false);
  const [togglingProduct, setTogglingProduct] = useState<string | null>(null);

  // Product modals
  const [productFormOpen, setProductFormOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);

  // Selected product → equipments
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [equipments, setEquipments] = useState<Equipment[]>([]);
  const [equipmentsLoading, setEquipmentsLoading] = useState(false);
  const [equipmentsError, setEquipmentsError] = useState<string | null>(null);
  const [showInactiveEquip, setShowInactiveEquip] = useState(false);
  const [togglingEquip, setTogglingEquip] = useState<string | null>(null);

  // Equipment modals
  const [equipFormOpen, setEquipFormOpen] = useState(false);
  const [editingEquip, setEditingEquip] = useState<Equipment | null>(null);

  // Load products
  function loadProducts() {
    setProductsLoading(true);
    setProductsError(null);
    getProducts({
      search: productSearch || undefined,
      is_active: showInactiveProducts ? undefined : true,
      limit: 100,
    })
      .then((res) => {
        setProducts(res.items);
        setTotalProducts(res.total);
      })
      .catch(() => setProductsError("Não foi possível carregar os produtos."))
      .finally(() => setProductsLoading(false));
  }

  useEffect(() => {
    loadProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productSearch, showInactiveProducts]);

  // Load equipments when product selected
  function loadEquipments(productId: string) {
    setEquipmentsLoading(true);
    setEquipmentsError(null);
    getEquipments(productId, {
      is_active: showInactiveEquip ? undefined : true,
      limit: 100,
    })
      .then((res) => setEquipments(res.items))
      .catch(() =>
        setEquipmentsError("Não foi possível carregar os equipamentos."),
      )
      .finally(() => setEquipmentsLoading(false));
  }

  useEffect(() => {
    if (selectedProduct) loadEquipments(selectedProduct.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProduct?.id, showInactiveEquip]);

  // Toggle product active
  async function toggleProduct(product: Product) {
    setTogglingProduct(product.id);
    try {
      const updated = await setProductActive(product.id, !product.is_active);
      setProducts((prev) =>
        prev.map((p) => (p.id === updated.id ? updated : p)),
      );
      if (selectedProduct?.id === updated.id) setSelectedProduct(updated);
    } finally {
      setTogglingProduct(null);
    }
  }

  // Toggle equipment active
  async function toggleEquipment(equip: Equipment) {
    setTogglingEquip(equip.id);
    try {
      const updated = await setEquipmentActive(equip.id, !equip.is_active);
      setEquipments((prev) =>
        prev.map((e) => (e.id === updated.id ? updated : e)),
      );
    } finally {
      setTogglingEquip(null);
    }
  }

  function handleProductSaved(p: Product) {
    setProductFormOpen(false);
    setEditingProduct(null);
    setProducts((prev) => {
      const idx = prev.findIndex((x) => x.id === p.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = p;
        return next;
      }
      return [p, ...prev];
    });
    if (!editingProduct) setTotalProducts((t) => t + 1);
  }

  function handleEquipSaved(e: Equipment) {
    setEquipFormOpen(false);
    setEditingEquip(null);
    setEquipments((prev) => {
      const idx = prev.findIndex((x) => x.id === e.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = e;
        return next;
      }
      return [e, ...prev];
    });
  }

  return (
    <div className="space-y-6">
      {/* ── Products ─────────────────────────────────────── */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-4">
          <div>
            <CardTitle>Produtos</CardTitle>
            <p className="text-xs text-slate-500 mt-0.5">
              {totalProducts} {totalProducts === 1 ? "produto" : "produtos"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showInactiveProducts}
                onChange={(e) => setShowInactiveProducts(e.target.checked)}
                className="accent-primary"
              />
              Mostrar inativos
            </label>
            <Button
              size="sm"
              onClick={() => {
                setEditingProduct(null);
                setProductFormOpen(true);
              }}
            >
              + Produto
            </Button>
          </div>
        </div>

        {/* Search */}
        <div className="px-4 py-2 border-b border-border">
          <Input
            placeholder="Buscar produto…"
            value={productSearch}
            onChange={(e) => setProductSearch(e.target.value)}
          />
        </div>

        {productsError && (
          <div className="px-4 py-3">
            <Alert variant="danger">{productsError}</Alert>
          </div>
        )}

        {productsLoading ? (
          <div className="flex h-32 items-center justify-center">
            <Spinner />
          </div>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Nome</TableHeaderCell>
                <TableHeaderCell className="w-28">Versão</TableHeaderCell>
                <TableHeaderCell className="w-20">Ativo</TableHeaderCell>
                <TableHeaderCell className="w-24 text-right">
                  Ações
                </TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {products.length === 0 ? (
                <TableEmpty colSpan={4} message="Nenhum produto encontrado." />
              ) : (
                products.map((p) => (
                  <TableRow
                    key={p.id}
                    clickable
                    onClick={() =>
                      setSelectedProduct(
                        selectedProduct?.id === p.id ? null : p,
                      )
                    }
                    className={
                      selectedProduct?.id === p.id ? "bg-primary/5" : ""
                    }
                  >
                    <TableCell>
                      <div>
                        <p
                          className={`font-medium ${p.is_active ? "text-slate-200" : "text-slate-500 line-through"}`}
                        >
                          {p.name}
                        </p>
                        {p.description && (
                          <p className="text-xs text-slate-500 truncate max-w-xs">
                            {p.description}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell muted className="text-xs">
                      {p.version ?? "—"}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <ActiveToggle
                        active={p.is_active}
                        loading={togglingProduct === p.id}
                        onToggle={() => toggleProduct(p)}
                      />
                    </TableCell>
                    <TableCell
                      className="text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditingProduct(p);
                          setProductFormOpen(true);
                        }}
                      >
                        Editar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* ── Equipments ───────────────────────────────────── */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-4">
          <div>
            <CardTitle>
              Equipamentos
              {selectedProduct && (
                <span className="text-slate-400 font-normal ml-2 text-sm">
                  — {selectedProduct.name}
                </span>
              )}
            </CardTitle>
            {!selectedProduct && (
              <p className="text-xs text-slate-500 mt-0.5">
                Selecione um produto acima para ver seus equipamentos
              </p>
            )}
          </div>
          {selectedProduct && (
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={showInactiveEquip}
                  onChange={(e) => setShowInactiveEquip(e.target.checked)}
                  className="accent-primary"
                />
                Mostrar inativos
              </label>
              <Button
                size="sm"
                onClick={() => {
                  setEditingEquip(null);
                  setEquipFormOpen(true);
                }}
              >
                + Equipamento
              </Button>
            </div>
          )}
        </div>

        {!selectedProduct ? (
          <p className="text-sm text-slate-500 px-4 py-10 text-center">
            Clique em um produto para ver e gerenciar seus equipamentos.
          </p>
        ) : equipmentsError ? (
          <div className="px-4 py-3">
            <Alert variant="danger">{equipmentsError}</Alert>
          </div>
        ) : equipmentsLoading ? (
          <div className="flex h-32 items-center justify-center">
            <Spinner />
          </div>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Nome</TableHeaderCell>
                <TableHeaderCell className="w-36">Nº de série</TableHeaderCell>
                <TableHeaderCell className="w-36">Modelo</TableHeaderCell>
                <TableHeaderCell className="w-20">Ativo</TableHeaderCell>
                <TableHeaderCell className="w-24 text-right">
                  Ações
                </TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {equipments.length === 0 ? (
                <TableEmpty
                  colSpan={5}
                  message="Nenhum equipamento para este produto."
                />
              ) : (
                equipments.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell>
                      <p
                        className={`font-medium ${e.is_active ? "text-slate-200" : "text-slate-500 line-through"}`}
                      >
                        {e.name}
                      </p>
                      {e.description && (
                        <p className="text-xs text-slate-500 truncate max-w-xs">
                          {e.description}
                        </p>
                      )}
                    </TableCell>
                    <TableCell muted className="text-xs font-mono">
                      {e.serial_number ?? "—"}
                    </TableCell>
                    <TableCell muted className="text-xs">
                      {e.model ?? "—"}
                    </TableCell>
                    <TableCell>
                      <ActiveToggle
                        active={e.is_active}
                        loading={togglingEquip === e.id}
                        onToggle={() => toggleEquipment(e)}
                      />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditingEquip(e);
                          setEquipFormOpen(true);
                        }}
                      >
                        Editar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Modals */}
      {productFormOpen && (
        <ProductFormModal
          editing={editingProduct}
          onClose={() => {
            setProductFormOpen(false);
            setEditingProduct(null);
          }}
          onSaved={handleProductSaved}
        />
      )}
      {equipFormOpen && selectedProduct && (
        <EquipmentFormModal
          productId={selectedProduct.id}
          editing={editingEquip}
          onClose={() => {
            setEquipFormOpen(false);
            setEditingEquip(null);
          }}
          onSaved={handleEquipSaved}
        />
      )}
    </div>
  );
}
