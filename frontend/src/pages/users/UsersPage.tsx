import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Button,
  Card,
  FilterSelect,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  Select,
  Spinner,
} from "../../components/ui";
import {
  createUser,
  deleteUser,
  getUsers,
  setUserStatus,
  updateUser,
  type UserSummary,
} from "../../services/userService";

// ── Icons ─────────────────────────────────────────────────────

const IC = {
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
  User: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
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
};

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 10;

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador",
  technician: "Técnico",
  client: "Cliente",
};

const ROLE_BADGE: Record<string, string> = {
  admin: "bg-primary/15 text-primary border border-primary/30",
  technician: "bg-info/15 text-info-700 dark:text-info-400 border border-info/30",
  client: "bg-slate-100 text-slate-600 border border-slate-300 dark:bg-slate-700/40 dark:text-slate-300 dark:border-slate-600/40",
};

const STATUS_LABEL: Record<string, string> = {
  active: "Ativo",
  inactive: "Inativo",
  suspended: "Suspenso",
  anonymized: "Anonimizado",
};


const ROLE_OPTIONS = [
  { value: "admin", label: "Administrador" },
  { value: "technician", label: "Técnico" },
  { value: "client", label: "Cliente" },
];

const FILTER_ROLE_OPTIONS = [
  { value: "admin", label: "Administrador" },
  { value: "technician", label: "Técnico" },
  { value: "client", label: "Cliente" },
];

const FILTER_STATUS_OPTIONS = [
  { value: "active", label: "Ativo" },
  { value: "inactive", label: "Inativo" },
  { value: "suspended", label: "Suspenso" },
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

// ── UserAvatar ────────────────────────────────────────────────

function UserAvatar({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div className="w-9 h-9 rounded-full bg-background-elevated border border-border/60 flex items-center justify-center shrink-0 text-sm font-semibold text-slate-600 dark:text-slate-200 select-none">
      {initials || "?"}
    </div>
  );
}

// ── StatusPill ────────────────────────────────────────────────

const STATUS_DOT: Record<string, string> = {
  active:     "bg-emerald-500",
  inactive:   "bg-slate-400 dark:bg-slate-500",
  suspended:  "bg-red-400",
  anonymized: "bg-slate-400 dark:bg-slate-600",
};

const STATUS_PILL: Record<string, string> = {
  active:     "border-emerald-300 bg-emerald-50 text-emerald-600 hover:bg-emerald-100 dark:border-emerald-700/50 dark:bg-emerald-900/20 dark:text-emerald-300 dark:hover:bg-emerald-900/40",
  inactive:   "border-slate-300 bg-slate-100 text-slate-500 hover:bg-slate-200 dark:border-slate-600/50 dark:bg-slate-800/40 dark:text-slate-400 dark:hover:bg-slate-700/40",
  suspended:  "border-red-300 bg-red-50 text-red-600 hover:bg-red-100 dark:border-red-700/50 dark:bg-red-900/20 dark:text-red-300 dark:hover:bg-red-900/30",
  anonymized: "border-slate-300 bg-slate-100 text-slate-500 cursor-default dark:border-slate-700/50 dark:bg-slate-800/50 dark:text-slate-600",
};

function StatusPill({ user, onToggled }: { user: UserSummary; onToggled: (u: UserSummary) => void }) {
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (user.status === "anonymized" || user.status === "suspended") return;
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

  return (
    <button
      onClick={toggle}
      disabled={!canToggle || loading}
      title={canToggle ? (user.status === "active" ? "Clique para desativar" : "Clique para ativar") : undefined}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors shrink-0 ${STATUS_PILL[user.status] ?? STATUS_PILL.inactive} ${canToggle ? "cursor-pointer" : ""}`}
    >
      {loading ? (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      ) : (
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[user.status] ?? "bg-slate-500"}`} />
      )}
      {STATUS_LABEL[user.status] ?? user.status}
    </button>
  );
}

// ── UserPreviewCard ───────────────────────────────────────────

function UserPreviewCard({ user }: { user: UserSummary }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-background-elevated px-4 py-3">
      <UserAvatar name={user.name} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">{user.name}</p>
        <p className="text-xs text-slate-500 truncate">{user.email}</p>
      </div>
      <span className={`shrink-0 text-xs font-medium px-2.5 py-1 rounded-full ${ROLE_BADGE[user.role] ?? ""}`}>
        {ROLE_LABEL[user.role] ?? user.role}
      </span>
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
          placeholder="Mín. 8 chars, 1 maiúscula, 1 número"
          error={form.formState.errors.password?.message}
          {...form.register("password")}
        />
        <Select
          label="Perfil *"
          options={ROLE_OPTIONS}
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
          options={ROLE_OPTIONS}
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
        <div className="flex gap-3 rounded-xl bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800/40 p-4">
          <div className="shrink-0 w-9 h-9 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center text-red-500 dark:text-red-400">
            {IC.Trash}
          </div>
          <div>
            <p className="text-sm font-semibold text-red-700 dark:text-red-300">Ação irreversível</p>
            <p className="text-xs text-red-500/80 dark:text-red-400/80 mt-0.5">
              Só é possível excluir usuários sem tickets. Se houver tickets vinculados, use "Anonimizar".
            </p>
          </div>
        </div>
        <UserPreviewCard user={user} />
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Tem certeza que deseja excluir permanentemente{" "}
          <span className="font-medium text-slate-800 dark:text-slate-200">{user.name}</span>?
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
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Usuários</h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-0.5">
            {total} {total === 1 ? "usuário cadastrado" : "usuários cadastrados"}
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          {IC.Plus} Novo usuário
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex-1 min-w-48 relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none">
            {IC.Search}
          </span>
          <input
            className="w-full pl-9 pr-3 py-2 rounded-xl border border-border/60 bg-background-surface text-sm text-slate-700 dark:text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            placeholder="Buscar por nome ou e-mail…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <FilterSelect
          options={FILTER_ROLE_OPTIONS}
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
            onClick={() => { setSearch(""); setRoleFilter(""); setStatusFilter(""); setPage(1); }}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors px-2 py-1.5 rounded-lg hover:bg-background-elevated cursor-pointer"
          >
            Limpar filtros
          </button>
        )}
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Card */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Lista de usuários</p>
            <p className="text-xs text-slate-500 mt-0.5">
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
            <div className="w-12 h-12 rounded-full bg-background-elevated border border-border flex items-center justify-center text-slate-600 mb-3">
              {IC.User}
            </div>
            <p className="text-sm text-slate-400">
              {hasFilters ? "Nenhum usuário encontrado para esses filtros." : "Nenhum usuário cadastrado."}
            </p>
            {!hasFilters && (
              <button
                onClick={() => setCreateOpen(true)}
                className="mt-2 text-sm text-primary hover:text-primary/80 transition-colors cursor-pointer"
              >
                Criar o primeiro usuário
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="divide-y divide-border" style={{ minHeight: 520 }}>
              {users.map((u) => (
                <div
                  key={u.id}
                  className="flex items-center gap-4 px-4 py-3 hover:bg-background-elevated/40 transition-colors"
                >
                  {/* Avatar */}
                  <UserAvatar name={u.name} />

                  {/* Name + email + dept */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{u.name}</p>
                    <p className="text-xs text-slate-500 truncate">{u.email}</p>
                    {u.department && (
                      <p className="text-xs text-slate-600 truncate">{u.department}</p>
                    )}
                  </div>

                  {/* Role badge */}
                  <span className={`hidden sm:inline-flex shrink-0 text-xs font-medium px-2.5 py-1 rounded-full ${ROLE_BADGE[u.role] ?? ""}`}>
                    {ROLE_LABEL[u.role] ?? u.role}
                  </span>

                  {/* Status pill */}
                  <div className="hidden md:block shrink-0">
                    <StatusPill user={u} onToggled={handleToggled} />
                  </div>

                  {/* Created date */}
                  <span className="hidden xl:block shrink-0 text-xs text-slate-600">
                    {new Date(u.created_at).toLocaleDateString("pt-BR")}
                  </span>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setEditTarget(u)}
                      title="Editar"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                    >
                      {IC.Edit}
                    </button>
                    <button
                      onClick={() => setDeleteTarget(u)}
                      title="Excluir"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:text-red-400 dark:hover:bg-red-900/20 transition-colors cursor-pointer"
                    >
                      {IC.Trash}
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="px-4 py-2 border-t border-border">
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
