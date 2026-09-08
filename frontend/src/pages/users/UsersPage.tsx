import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  FilterSelect,
  Icon,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  Select,
  Spinner,
} from "../../components/ui";
import { cn } from "../../lib/utils";
import {
  createUser,
  deleteUser,
  getUsers,
  setUserStatus,
  updateUser,
  type UserStatus,
  type UserSummary,
} from "../../services/userService";

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 10;

/**
 * O papel do usuário: rótulo e variante do selo, numa tabela só.
 *
 * Aqui ele morava em **quatro** constantes do próprio arquivo — `ROLE_LABEL`,
 * `ROLE_BADGE`, `ROLE_OPTIONS` e `FILTER_ROLE_OPTIONS`, sendo as duas últimas
 * idênticas linha a linha. As quatro viram esta.
 *
 * ⚠️ **A casa dela não é aqui.** A mesma tabela existe em
 * `layout/Topbar.tsx`, `profile/ProfilePage.tsx` e `kb/KBArticlePage.tsx` — e
 * as quatro já divergem: a da KB diz "Admin" onde as outras dizem
 * "Administrador". É o mesmo defeito que `lib/status.ts` e `lib/prioridade.ts`
 * consertaram para chamado, e o conserto tem o mesmo formato: um `lib/papel.ts`
 * consumido pelos quatro. Criar esse módulo é escrita em `src/lib`, fora do
 * escopo da migração de UMA tela — então o que dá para fazer daqui é reduzir
 * quatro cópias locais a uma, e relatar. **Não** inventar um quinto mapa.
 *
 * O `as const` faz `variante` inferir os literais do `Badge` em vez de
 * `string`: acrescentar um papel com variante que não existe para de compilar.
 */
const PAPEIS = [
  { valor: "admin", rotulo: "Administrador", variante: "primary" },
  { valor: "technician", rotulo: "Técnico", variante: "info" },
  { valor: "client", rotulo: "Cliente", variante: "muted" },
] as const;

/** As opções dos seletores — do filtro e dos dois formulários. */
const OPCOES_DE_PAPEL = PAPEIS.map((p) => ({
  value: p.valor,
  label: p.rotulo,
}));

/**
 * Rótulo e variante recuam para o dado cru, e não estouram.
 *
 * Mesma razão dos acessores de `lib/status.ts`: `role` vem da REDE. Um papel
 * novo no backend que o front ainda não conheça mostra o valor cru num selo
 * neutro — em vez de derrubar a lista inteira.
 */
function rotuloDePapel(papel: string): string {
  return PAPEIS.find((p) => p.valor === papel)?.rotulo ?? papel;
}

function varianteDePapel(papel: string) {
  return PAPEIS.find((p) => p.valor === papel)?.variante ?? "muted";
}

/**
 * O estado da CONTA — que não é o status do chamado.
 *
 * Por isso ele não sai de `lib/status.ts`: aquele módulo é dos sete estados de
 * um chamado, e `active`/`inactive`/`anonymized` são outra coisa. Os valores
 * são os de `USER_STATUSES`, no `userService`, que o teste do serviço compara
 * com o enum do backend.
 *
 * As três colunas eram três mapas separados (`STATUS_LABEL`, `STATUS_DOT`,
 * `STATUS_PILL`) com trinta e uma classes de paleta crua e oito `dark:` para
 * inverter à mão o que o token inverte sozinho.
 *
 * **Classes por extenso, nunca por concatenação.** O Tailwind gera utilitário
 * varrendo o texto do arquivo: `"bg-tint-" + estado` some da varredura, a regra
 * não nasce, a pílula fica sem fundo, e não há erro nem aviso.
 *
 * O hover é de BORDA e não de fundo porque `--tint-*` já carrega alfa de 15% no
 * próprio token (regra (a) do D8-a): `hover:bg-tint-success/30` multiplicaria
 * 0,15 × 0,30 e daria um realce praticamente invisível.
 */
const ESTADO_DA_CONTA: Record<
  UserStatus,
  { rotulo: string; pilula: string; ponto: string }
> = {
  active: {
    rotulo: "Ativo",
    pilula:
      "border-success/30 bg-tint-success text-on-tint-success hover:border-success/60",
    ponto: "bg-fill-success",
  },
  inactive: {
    rotulo: "Inativo",
    pilula:
      "border-borda bg-tint-neutral text-on-tint-neutral hover:border-borda-strong",
    ponto: "bg-borda-control",
  },
  // Anonimizado pinta igual a inativo, e é deliberado: quem carrega a
  // diferença é a PALAVRA, não a cor. Duas faixas de cinza a distinguiriam
  // para quem enxerga e para mais ninguém — e o que o estado tem de próprio
  // (não dá para alternar) já está no botão desabilitado.
  anonymized: {
    rotulo: "Anonimizado",
    pilula: "border-borda bg-tint-neutral text-on-tint-neutral cursor-default",
    ponto: "bg-borda-control",
  },
};

/** Recuo para o neutro com o valor cru no rótulo — o dado vem da rede. */
function estadoDaConta(status: string) {
  return (
    ESTADO_DA_CONTA[status as UserStatus] ?? {
      ...ESTADO_DA_CONTA.inactive,
      rotulo: status,
    }
  );
}

/**
 * Subconjunto deliberado: filtrar por anonimizado não é uso de tela.
 *
 * E a lista curta tem história: "suspended" já morou no `userService` sem
 * nunca ter existido no banco, e a opção que ele gerava derrubava a lista com
 * 422 — o FastAPI recusa na validação do Query, antes do handler. Por isso os
 * valores saem de `UserStatus` e os rótulos da tabela acima: um estado
 * inventado não compila, e um rótulo divergente não tem onde nascer.
 */
const FILTER_STATUS_OPTIONS: { value: UserStatus; label: string }[] = [
  { value: "active", label: ESTADO_DA_CONTA.active.rotulo },
  { value: "inactive", label: ESTADO_DA_CONTA.inactive.rotulo },
];

// ── Validation ─────────────────────────────────────────────────

const createSchema = z.object({
  name: z.string().min(2, "Nome deve ter ao menos 2 caracteres"),
  email: z.string().email("E-mail inválido"),
  password: z
    .string()
    .min(8, "Senha deve ter ao menos 8 caracteres")
    .regex(/[A-Z]/, "Deve conter ao menos uma letra maiúscula")
    .regex(/[0-9]/, "Deve conter ao menos um número"),
  role: z.enum(["admin", "technician", "client"]),
  phone: z.string().optional(),
  department: z.string().optional(),
});

const editSchema = z.object({
  name: z.string().min(2, "Nome deve ter ao menos 2 caracteres"),
  role: z.enum(["admin", "technician", "client"]),
  phone: z.string().optional(),
  department: z.string().optional(),
});

type CreateValues = z.infer<typeof createSchema>;
type EditValues = z.infer<typeof editSchema>;

// ── StatusPill ────────────────────────────────────────────────

function StatusPill({
  user,
  onToggled,
}: {
  user: UserSummary;
  onToggled: (u: UserSummary) => void;
}) {
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (user.status === "anonymized") return;
    setLoading(true);
    try {
      const next = user.status === "active" ? "inactive" : "active";
      const updated = await setUserStatus(user.id, next);
      onToggled(updated);
    } finally {
      setLoading(false);
    }
  }

  const canToggle = user.status === "active" || user.status === "inactive";
  const estado = estadoDaConta(user.status);

  return (
    <button
      // `type="button"` porque a pílula aparece dentro de blocos que um dia
      // podem virar formulário: o padrão do HTML dentro de `<form>` é
      // `submit`, e um clique aqui gravaria a página inteira.
      type="button"
      onClick={toggle}
      disabled={!canToggle || loading}
      title={
        canToggle
          ? user.status === "active"
            ? "Clique para desativar"
            : "Clique para ativar"
          : undefined
      }
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border",
        "text-xs font-medium transition-colors shrink-0",
        // O foco não estava fraco, estava ausente — o mesmo defeito da E9.
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
        estado.pilula,
        canToggle && "cursor-pointer",
      )}
    >
      {loading ? (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      ) : (
        <span
          className={cn("w-1.5 h-1.5 rounded-full shrink-0", estado.ponto)}
        />
      )}
      {estado.rotulo}
    </button>
  );
}

// ── UserPreviewCard ───────────────────────────────────────────

function UserPreviewCard({ user }: { user: UserSummary }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-borda bg-surface-elevated px-4 py-3">
      <Avatar name={user.name} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-conteudo-heading truncate">
          {user.name}
        </p>
        <p className="text-xs text-conteudo-muted truncate">{user.email}</p>
      </div>
      <Badge variant={varianteDePapel(user.role)} className="shrink-0">
        {rotuloDePapel(user.role)}
      </Badge>
    </div>
  );
}

// ── CreateModal ───────────────────────────────────────────────

function CreateModal({ onClose, onSaved }: { onClose: () => void; onSaved: (u: UserSummary) => void }) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { role: "client" },
  });

  async function handleSubmit(values: CreateValues) {
    setSubmitError(null);
    try {
      const user = await createUser({
        ...values,
        lgpd_consent: true,
        phone: values.phone || undefined,
        department: values.department || undefined,
      });
      onSaved(user);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setSubmitError(
        msg === "Email already registered"
          ? "Este e-mail já está cadastrado."
          : "Erro ao criar usuário. Tente novamente.",
      );
    }
  }

  return (
    <Modal open onClose={onClose} title="Novo usuário">
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {submitError && <Alert variant="danger">{submitError}</Alert>}
        <Input
          label="Nome *"
          autoFocus
          error={form.formState.errors.name?.message}
          {...form.register("name")}
        />
        <Input
          label="E-mail *"
          type="email"
          error={form.formState.errors.email?.message}
          {...form.register("email")}
        />
        <Input
          label="Senha *"
          type="password"
          placeholder="Mín. 8 caracteres, 1 maiúscula, 1 número"
          error={form.formState.errors.password?.message}
          {...form.register("password")}
        />
        <Select
          label="Perfil *"
          options={OPCOES_DE_PAPEL}
          error={form.formState.errors.role?.message}
          {...form.register("role")}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Telefone" placeholder="(11) 9 9999-9999" {...form.register("phone")} />
          <Input label="Departamento" {...form.register("department")} />
        </div>
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>
            Cancelar
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Criar usuário
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── EditModal ─────────────────────────────────────────────────

function EditModal({ user, onClose, onSaved }: { user: UserSummary; onClose: () => void; onSaved: (u: UserSummary) => void }) {
  const [submitError, setSubmitError] = useState<string | null>(null);
  const form = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      name: user.name,
      role: user.role as "admin" | "technician" | "client",
      phone: user.phone ?? "",
      department: user.department ?? "",
    },
  });

  async function handleSubmit(values: EditValues) {
    setSubmitError(null);
    try {
      const updated = await updateUser(user.id, {
        name: values.name,
        role: values.role,
        phone: values.phone || null,
        department: values.department || null,
      });
      onSaved(updated);
    } catch {
      setSubmitError("Erro ao salvar alterações. Tente novamente.");
    }
  }

  return (
    <Modal open onClose={onClose} title="Editar usuário">
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {submitError && <Alert variant="danger">{submitError}</Alert>}
        <UserPreviewCard user={user} />
        <Input
          label="Nome *"
          autoFocus
          error={form.formState.errors.name?.message}
          {...form.register("name")}
        />
        <Select
          label="Perfil *"
          options={OPCOES_DE_PAPEL}
          error={form.formState.errors.role?.message}
          {...form.register("role")}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Telefone" placeholder="(11) 9 9999-9999" {...form.register("phone")} />
          <Input label="Departamento" {...form.register("department")} />
        </div>
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={form.formState.isSubmitting}>
            Cancelar
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting}>
            Salvar alterações
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── DeleteModal ───────────────────────────────────────────────

function DeleteModal({ user, onClose, onDeleted }: { user: UserSummary; onClose: () => void; onDeleted: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setLoading(true);
    setError(null);
    try {
      await deleteUser(user.id);
      onDeleted();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Erro ao excluir usuário.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Excluir usuário">
      <div className="space-y-4">
        {error && <Alert variant="danger">{error}</Alert>}
        {/* O disco por cima do painel repete `bg-tint-danger` de propósito: a
            tinta tem 15% de alfa, então a segunda camada soma sobre a primeira
            e dá o degrau mais forte que o `red-100` sobre `red-50` dava — sem
            modificador de opacidade, que nas tintas multiplicaria em vez de
            somar. */}
        <div className="flex gap-3 rounded-xl bg-tint-danger border border-danger/30 p-4">
          <div className="shrink-0 w-9 h-9 rounded-full bg-tint-danger flex items-center justify-center text-on-tint-danger">
            <Icon name="trash" size={16} strokeWidth={2} />
          </div>
          <div>
            <p className="text-sm font-semibold text-on-tint-danger">Ação irreversível</p>
            <p className="text-xs text-on-tint-danger mt-0.5">
              Só é possível excluir usuários sem tickets. Se houver tickets vinculados, use "Anonimizar".
            </p>
          </div>
        </div>
        <UserPreviewCard user={user} />
        <p className="text-sm text-conteudo-muted">
          Tem certeza que deseja excluir permanentemente{" "}
          <span className="font-medium text-conteudo-heading">{user.name}</span>?
        </p>
      </div>
      <ModalFooter>
        <Button variant="secondary" onClick={onClose} disabled={loading}>
          Cancelar
        </Button>
        <Button variant="danger" onClick={handleDelete} loading={loading}>
          Excluir permanentemente
        </Button>
      </ModalFooter>
    </Modal>
  );
}

// ── UsersPage ─────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<UserSummary | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserSummary | null>(null);

  function load(p = page) {
    setLoading(true);
    setError(null);
    getUsers({
      search: search || undefined,
      role: roleFilter || undefined,
      status: statusFilter || undefined,
      limit: PAGE_SIZE,
      offset: (p - 1) * PAGE_SIZE,
    })
      .then((res) => { setUsers(res.items); setTotal(res.total); })
      .catch(() => setError("Não foi possível carregar os usuários."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [search, roleFilter, statusFilter, page]);

  function handleSaved(user: UserSummary) {
    const wasEditing = !!editTarget;
    setCreateOpen(false);
    setEditTarget(null);
    setUsers((prev) => {
      const idx = prev.findIndex((u) => u.id === user.id);
      if (idx >= 0) { const next = [...prev]; next[idx] = user; return next; }
      return [user, ...prev];
    });
    if (!wasEditing) setTotal((t) => t + 1);
  }

  function handleToggled(updated: UserSummary) {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
  }

  function handleDeleted() {
    const id = deleteTarget?.id;
    setDeleteTarget(null);
    setUsers((prev) => prev.filter((u) => u.id !== id));
    setTotal((t) => t - 1);
  }

  const hasFilters = !!(search || roleFilter || statusFilter);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="text-center sm:text-left">
          <h1 className="text-2xl font-bold text-conteudo-heading">Usuários</h1>
          <p className="text-conteudo-muted text-sm mt-0.5">
            {total} {total === 1 ? "usuário cadastrado" : "usuários cadastrados"}
          </p>
        </div>
        <Button
          onClick={() => setCreateOpen(true)}
          className="w-full sm:w-auto"
          icon={<Icon name="plus" size={16} strokeWidth={2} />}
        >
          Novo usuário
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row md:items-center gap-2">
        <div className="relative md:flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 z-10 text-conteudo-muted pointer-events-none">
            <Icon name="search" size={16} strokeWidth={2} />
          </span>
          {/*
            Campo do primitivo, e não `<input>` à mão — e o `aria-label` é
            carga: o campo só tinha `placeholder`, que NÃO é nome acessível.
            Quem navega por leitor de tela chegava num campo de texto sem nome
            nenhum no meio da barra de filtros.
          */}
          <Input
            aria-label="Buscar usuários"
            className="pl-9"
            placeholder="Buscar por nome ou e-mail…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <div className="flex flex-wrap gap-2 items-center justify-center sm:justify-start">
          <FilterSelect
            options={OPCOES_DE_PAPEL}
            placeholder="Perfil"
            value={roleFilter}
            onChange={(v) => { setRoleFilter(v); setPage(1); }}
          />
          <FilterSelect
            options={FILTER_STATUS_OPTIONS}
            placeholder="Status"
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); setPage(1); }}
          />
          {hasFilters && (
            <button
              type="button"
              onClick={() => { setSearch(""); setRoleFilter(""); setStatusFilter(""); setPage(1); }}
              className="text-xs text-conteudo-muted hover:text-conteudo transition-colors px-2 py-1.5 rounded-lg hover:bg-surface-elevated cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
            >
              Limpar filtros
            </button>
          )}
        </div>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Card */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-borda flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-conteudo-heading">Lista de usuários</p>
            <p className="text-xs text-conteudo-muted mt-0.5">
              Gerencie acessos e perfis dos usuários.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <Spinner size="lg" />
          </div>
        ) : users.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-surface-elevated border border-borda flex items-center justify-center text-conteudo-muted mb-3">
              <Icon name="user" size={20} strokeWidth={2} />
            </div>
            <p className="text-sm text-conteudo-muted">
              {hasFilters ? "Nenhum usuário encontrado para esses filtros." : "Nenhum usuário cadastrado."}
            </p>
            {/* Só o vazio SEM filtro convida a criar: com filtro, o cadastro
                provavelmente existe e está escondido — oferecer "criar" ali
                empurra para o duplicado. */}
            {!hasFilters && (
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="mt-2 text-sm text-conteudo-link hover:text-conteudo-link-hover transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action rounded"
              >
                Criar o primeiro usuário
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="divide-y divide-borda" style={{ minHeight: 520 }}>
              {users.map((u) => (
                <div
                  key={u.id}
                  className="flex items-center gap-4 px-4 py-3 hover:bg-surface-elevated/40 transition-colors"
                >
                  {/* Avatar */}
                  <Avatar name={u.name} />

                  {/* Name + email + dept */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-conteudo-heading truncate">{u.name}</p>
                    <p className="text-xs text-conteudo-muted truncate">{u.email}</p>
                    {u.department && (
                      <p className="text-xs text-conteudo-muted truncate">{u.department}</p>
                    )}
                  </div>

                  {/* Role badge */}
                  <Badge
                    variant={varianteDePapel(u.role)}
                    className="hidden sm:inline-flex shrink-0"
                  >
                    {rotuloDePapel(u.role)}
                  </Badge>

                  {/* Status pill */}
                  <div className="hidden md:block shrink-0">
                    <StatusPill user={u} onToggled={handleToggled} />
                  </div>

                  {/* Created date */}
                  <span className="hidden xl:block shrink-0 text-xs text-conteudo-muted">
                    {new Date(u.created_at).toLocaleDateString("pt-BR")}
                  </span>

                  {/*
                    Ações. O nome do usuário entra no `aria-label` porque são N
                    botões por página: sem ele, uma lista de dez cadastros
                    anuncia dez controles chamados "Editar" e dez chamados
                    "Excluir", e quem não vê a linha não tem como saber qual é
                    qual. O `title` fica curto — é dica de mouse, e o mouse já
                    sabe em que linha está.
                  */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => setEditTarget(u)}
                      title="Editar"
                      aria-label={`Editar ${u.name}`}
                      className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-action-tint transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
                    >
                      <Icon name="edit" size={16} strokeWidth={2} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(u)}
                      title="Excluir"
                      aria-label={`Excluir ${u.name}`}
                      className="p-1.5 rounded-lg text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
                    >
                      <Icon name="trash" size={16} strokeWidth={2} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="px-4 py-2 border-t border-borda">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={total}
                onPageChange={setPage}
                itemLabel="usuários"
              />
            </div>
          </>
        )}
      </Card>

      {/* Modals */}
      {createOpen && (
        <CreateModal onClose={() => setCreateOpen(false)} onSaved={handleSaved} />
      )}
      {editTarget && (
        <EditModal user={editTarget} onClose={() => setEditTarget(null)} onSaved={handleSaved} />
      )}
      {deleteTarget && (
        <DeleteModal user={deleteTarget} onClose={() => setDeleteTarget(null)} onDeleted={handleDeleted} />
      )}
    </div>
  );
}
