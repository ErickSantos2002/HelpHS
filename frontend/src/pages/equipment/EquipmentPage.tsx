import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Badge,
  Button,
  Card,
  Icon,
  Input,
  KpiCard,
  Modal,
  ModalFooter,
  Pagination,
  Select,
  Spinner,
} from "../../components/ui";
import type { BadgeProps } from "../../components/ui";
import { cn } from "../../lib/utils";
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

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 10;

// ── O estado do equipamento ───────────────────────────────────

/**
 * Ativo e inativo, numa tabela só desta tela.
 *
 * ── Por que ela é local, e não um módulo de `src/lib` ─────────────────
 *
 * Porque `is_active` não é status de chamado, prioridade nem categoria: é um
 * booleano de equipamento, e nenhum outro arquivo do front precisa saber como
 * ele se chama. `src/lib/**` está fora do escopo desta passagem, e o módulo
 * teria um consumidor só — a mesma conclusão que a `AuditLogsPage` registrou
 * para a tabela de ação de auditoria.
 *
 * O que ela ganhou foi a **disciplina** dos módulos: rótulo singular e plural
 * declarados lado a lado (o selo diz "Ativo", a aba diz "Ativos" — antes as
 * duas palavras estavam escritas em lugares diferentes, sem regra ligando-as),
 * variante do `Badge` em vez de classe de cor, e as abas de filtro derivadas
 * daqui em vez de reescritas.
 *
 * ── Este selo é uma de TRÊS cópias divergentes ────────────────────────
 *
 * O mesmo componente existe na `ProductsPage` (como botão que alterna) e na
 * `UsersPage` (como `StatusPill`, com três estados e mapa de rótulo próprio).
 * A daqui trazia um `dark:bg-emerald-400` no ponto que a da `ProductsPage` não
 * tinha — divergiram em silêncio, porque nada obriga três cópias a concordar.
 *
 * O componente compartilhado **não nasce aqui**: `components/ui` está fora do
 * escopo, e três agentes inventando três abstrações é o defeito que esta
 * migração existe para eliminar. Fica registrado na ficha.
 *
 * ── Sem modificador de opacidade nas tintas ───────────────────────────
 *
 * Regra (a) do D8-a: as tintas já carregam 15% de alfa no próprio token, e
 * `bg-tint-success/20` multiplicaria os dois. As classes abaixo estão escritas
 * por extenso pelo mesmo motivo de sempre — o Tailwind gera utilitário varrendo
 * o TEXTO do arquivo, e `"bg-fill-" + algo` some da varredura sem erro nem
 * aviso.
 */
const ESTADO = {
  ativo: {
    rotulo: "Ativo",
    plural: "Ativos",
    variante: "success",
    // O ponto é FORMA, não texto: `--fill-*` da E19 existe porque o degrau 500
    // da rampa reprova o piso de 3:1 no tema claro.
    ponto: "bg-fill-success",
  },
  inativo: {
    rotulo: "Inativo",
    plural: "Inativos",
    variante: "muted",
    // O único que inverte por tema — é contorno de controle, e o par neutro do
    // `Badge` não tem preenchimento próprio.
    ponto: "bg-borda-control",
  },
} as const satisfies Record<
  string,
  { rotulo: string; plural: string; variante: BadgeProps["variant"]; ponto: string }
>;

function estadoDe(ativo: boolean) {
  return ativo ? ESTADO.ativo : ESTADO.inativo;
}

/** As três abas, derivadas da tabela — antes eram três literais soltos. */
type Filtro = "all" | "active" | "inactive";

const FILTROS: { chave: Filtro; rotulo: string }[] = [
  { chave: "all", rotulo: "Todos" },
  { chave: "active", rotulo: ESTADO.ativo.plural },
  { chave: "inactive", rotulo: ESTADO.inativo.plural },
];

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

// ── SeloDeEstado ──────────────────────────────────────────────

function SeloDeEstado({ ativo }: { ativo: boolean }) {
  const estado = estadoDe(ativo);
  return (
    <Badge variant={estado.variante} className="shrink-0 gap-1.5">
      {/* O ponto é decorativo: a palavra ao lado já diz o estado, e é ela que
          sobra para quem não enxerga a cor. */}
      <span
        aria-hidden="true"
        className={cn("h-1.5 w-1.5 shrink-0 rounded-full", estado.ponto)}
      />
      {estado.rotulo}
    </Badge>
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
        {/* Era um `<select>` com classe à mão e um `<label>` sem `htmlFor` —
            campo sem nome acessível. O primitivo amarra os dois e traz o anel
            de foco do degrau de AÇÃO, o mesmo dos `Input` logo abaixo. */}
        <Select
          id="equipamento-produto"
          label="Produto *"
          options={products.map((p) => ({
            value: p.id,
            label: p.name + (p.version ? ` (${p.version})` : ""),
          }))}
          error={form.formState.errors.product_id?.message}
          {...form.register("product_id")}
        />
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
        {/* `live={false}` pela E12: este aviso já está na tela quando o modal
            abre. Região viva anuncia MUDANÇA — anunciá-lo aqui atropelaria o
            anúncio do próprio diálogo, e o `Alert` acima, esse sim, é o que
            muda. */}
        <Alert variant="danger" live={false} title="Ação irreversível">
          Este equipamento será removido permanentemente.
        </Alert>
        <div className="flex items-center gap-3 rounded-xl border border-borda bg-surface-elevated px-4 py-3">
          <div className="w-9 h-9 rounded-lg bg-surface border border-borda flex items-center justify-center text-conteudo-muted">
            <Icon name="cpu" size={16} strokeWidth={2} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-conteudo-heading truncate">{equipment.name}</p>
            {equipment.serial_number && <p className="text-xs font-mono text-conteudo-muted">{equipment.serial_number}</p>}
          </div>
        </div>
        <p className="text-sm text-conteudo-muted">
          Tem certeza que deseja excluir <span className="font-medium text-conteudo">{equipment.name}</span>?
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
  const [filter, setFilter] = useState<Filtro>("all");

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
  const contagem: Record<Filtro, number> = { all: total, active, inactive };

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
          <h1 className="text-2xl font-bold text-conteudo-heading">Meus equipamentos</h1>
          <p className="text-conteudo-muted text-sm mt-0.5">
            Gerencie os equipamentos sob sua responsabilidade.
          </p>
        </div>
        {products.length > 0 && (
          <Button onClick={() => setAddOpen(true)} icon={<Icon name="plus" size={16} strokeWidth={2} />}>
            Adicionar equipamento
          </Button>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-3">
        {/* O cartão local tinha uma prop `accent` de CLASSE CRUA — a mesma
            porta pela qual `text-emerald-600` entrou sem revisão, e a razão de
            o primitivo existir. O tom é união fechada. */}
        <KpiCard label="Total" value={total} />
        <KpiCard label={ESTADO.ativo.plural} value={active} tone="success" />
        <KpiCard label={ESTADO.inativo.plural} value={inactive} />
      </div>

      {/* Card */}
      <Card padding="none">
        {/* Filter tabs */}
        <div className="flex gap-0 border-b border-borda">
          {FILTROS.map(({ chave, rotulo }) => (
            <button
              key={chave}
              type="button"
              // O selecionado só se via na cor e na linha de baixo. Como
              // botão que alterna, ele passa a DIZER que está ligado — é o
              // item "visual = árvore" da §29, e não muda pixel nenhum.
              aria-pressed={filter === chave}
              onClick={() => { setFilter(chave); setPage(1); }}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors cursor-pointer -mb-px",
                filter === chave
                  ? "border-action text-conteudo-link"
                  : "border-transparent text-conteudo-muted hover:text-conteudo",
              )}
            >
              {rotulo} ({contagem[chave]})
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-surface-elevated border border-borda flex items-center justify-center text-conteudo-muted mb-3">
              <Icon name="cpu" size={16} strokeWidth={2} />
            </div>
            <p className="text-sm text-conteudo-muted">
              {total === 0
                ? "Nenhum equipamento cadastrado ainda."
                : "Nenhum equipamento neste filtro."}
            </p>
            {total === 0 && products.length > 0 && (
              <button
                type="button"
                onClick={() => setAddOpen(true)}
                className="mt-2 text-sm text-conteudo-link hover:text-conteudo-link-hover transition-colors cursor-pointer"
              >
                Adicionar primeiro equipamento
              </button>
            )}
            {total === 0 && products.length === 0 && (
              <p className="mt-1 text-xs text-conteudo-muted">Nenhum produto disponível no sistema ainda.</p>
            )}
          </div>
        ) : (
          <>
            <div className="divide-y divide-borda">
              {paginated.map((e) => {
                const prod = productMap[e.product_id];
                return (
                  <div key={e.id} className="flex items-center gap-4 px-4 py-3 hover:bg-surface-elevated/40 transition-colors">
                    {/* Icon */}
                    <div className="w-9 h-9 rounded-lg bg-surface-elevated border border-borda/60 flex items-center justify-center shrink-0 text-conteudo-muted">
                      <Icon name="cpu" size={16} strokeWidth={2} />
                    </div>

                    {/* Name + details */}
                    <div className="flex-1 min-w-0">
                      <p className={cn(
                        "text-sm font-medium truncate",
                        e.is_active ? "text-conteudo" : "text-conteudo-muted line-through",
                      )}>
                        {e.name}
                      </p>
                      <div className="flex items-center gap-2 flex-wrap mt-0.5">
                        {e.serial_number && (
                          <span className="text-xs font-mono text-conteudo-muted">{e.serial_number}</span>
                        )}
                        {e.location && (
                          <span className="flex items-center gap-0.5 text-xs text-conteudo-muted">
                            <Icon name="mapPin" size={14} strokeWidth={2} /> {e.location}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Product badge */}
                    {prod && (
                      <Badge variant="primary" className="hidden sm:inline-flex shrink-0 truncate max-w-[120px]">
                        {prod.name}
                      </Badge>
                    )}

                    {/* Status */}
                    <SeloDeEstado ativo={e.is_active} />

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      {/* O nome acessível diz QUAL equipamento: dez linhas na
                          página davam dez botões chamados "Editar", e o `title`
                          sozinho não resolve isso para quem navega por lista de
                          controles. */}
                      <button
                        type="button"
                        onClick={() => setEditTarget(e)}
                        title="Editar"
                        aria-label={`Editar ${e.name}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-surface-elevated transition-colors cursor-pointer"
                      >
                        <Icon name="edit" size={16} strokeWidth={2} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(e)}
                        title="Excluir"
                        aria-label={`Excluir ${e.name}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-colors cursor-pointer"
                      >
                        <Icon name="trash" size={16} strokeWidth={2} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="px-4 py-2 border-t border-borda">
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
