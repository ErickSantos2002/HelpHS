import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Alert,
  Button,
  Input,
  Modal,
  ModalFooter,
  Pagination,
  Select,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui";
import {
  anonymizeUser,
  createUser,
  deleteUser,
  getUsers,
  setUserStatus,
  updateUser,
  type UserSummary,
} from "../../services/userService";

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 20;

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador",
  technician: "Técnico",
  client: "Cliente",
};

const ROLE_COLOR: Record<string, string> = {
  admin: "text-primary",
  technician: "text-info",
  client: "text-slate-300",
};

const STATUS_LABEL: Record<string, string> = {
  active: "Ativo",
  inactive: "Inativo",
  suspended: "Suspenso",
  anonymized: "Anonimizado",
};

const STATUS_COLOR: Record<string, string> = {
  active: "text-primary",
  inactive: "text-slate-500",
  suspended: "text-danger",
  anonymized: "text-slate-600",
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

// ── Validation schemas ────────────────────────────────────────

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

// ── UserFormModal ─────────────────────────────────────────────

interface UserFormModalProps {
  editing: UserSummary | null;
  onClose: () => void;
  onSaved: (user: UserSummary) => void;
}

function UserFormModal({ editing, onClose, onSaved }: UserFormModalProps) {
  const [submitError, setSubmitError] = useState<string | null>(null);

  const createForm = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { role: "client", lgpd_consent: true } as never,
  });

  const editForm = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: editing
      ? {
          name: editing.name,
          role: editing.role,
          phone: editing.phone ?? "",
          department: editing.department ?? "",
        }
      : undefined,
  });

  async function handleCreate(values: CreateValues) {
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
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setSubmitError(
        msg === "Email already registered"
          ? "Este e-mail já está cadastrado."
          : "Erro ao criar usuário. Tente novamente.",
      );
    }
  }

  async function handleEdit(values: EditValues) {
    if (!editing) return;
    setSubmitError(null);
    try {
      const user = await updateUser(editing.id, {
        name: values.name,
        role: values.role,
        phone: values.phone || null,
        department: values.department || null,
      });
      onSaved(user);
    } catch {
      setSubmitError("Erro ao salvar alterações. Tente novamente.");
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? "Editar usuário" : "Novo usuário"}
    >
      {submitError && (
        <Alert variant="danger" className="mb-4">
          {submitError}
        </Alert>
      )}

      {editing ? (
        <form
          onSubmit={editForm.handleSubmit(handleEdit)}
          className="space-y-4"
        >
          <Input
            label="Nome *"
            error={editForm.formState.errors.name?.message}
            {...editForm.register("name")}
          />
          <Select
            label="Perfil *"
            options={ROLE_OPTIONS}
            error={editForm.formState.errors.role?.message}
            {...editForm.register("role")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Telefone"
              placeholder="(11) 9 9999-9999"
              {...editForm.register("phone")}
            />
            <Input label="Departamento" {...editForm.register("department")} />
          </div>
          <ModalFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={editForm.formState.isSubmitting}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={editForm.formState.isSubmitting}>
              Salvar
            </Button>
          </ModalFooter>
        </form>
      ) : (
        <form
          onSubmit={createForm.handleSubmit(handleCreate)}
          className="space-y-4"
        >
          <Input
            label="Nome *"
            error={createForm.formState.errors.name?.message}
            {...createForm.register("name")}
          />
          <Input
            label="E-mail *"
            type="email"
            error={createForm.formState.errors.email?.message}
            {...createForm.register("email")}
          />
          <Input
            label="Senha *"
            type="password"
            placeholder="Mín. 8 chars, 1 maiúscula, 1 número"
            error={createForm.formState.errors.password?.message}
            {...createForm.register("password")}
          />
          <Select
            label="Perfil *"
            options={ROLE_OPTIONS}
            error={createForm.formState.errors.role?.message}
            {...createForm.register("role")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Telefone"
              placeholder="(11) 9 9999-9999"
              {...createForm.register("phone")}
            />
            <Input
              label="Departamento"
              {...createForm.register("department")}
            />
          </div>
          <ModalFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={onClose}
              disabled={createForm.formState.isSubmitting}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={createForm.formState.isSubmitting}>
              Criar
            </Button>
          </ModalFooter>
        </form>
      )}
    </Modal>
  );
}

// ── StatusToggle ──────────────────────────────────────────────

interface StatusToggleProps {
  user: UserSummary;
  onToggled: (updated: UserSummary) => void;
}

function StatusToggle({ user, onToggled }: StatusToggleProps) {
  const [loading, setLoading] = useState(false);

  async function toggle() {
    setLoading(true);
    try {
      const next = user.status === "active" ? "inactive" : "active";
      const updated = await setUserStatus(user.id, next);
      onToggled(updated);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <Spinner size="sm" />;

  return (
    <button
      onClick={toggle}
      title={user.status === "active" ? "Desativar" : "Ativar"}
      className={`w-10 h-5 rounded-full transition-colors relative ${
        user.status === "active" ? "bg-primary" : "bg-border"
      }`}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
          user.status === "active" ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

// ── UsersPage ─────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  // Modals
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<UserSummary | null>(null);
  const [confirmAnonymize, setConfirmAnonymize] = useState<UserSummary | null>(
    null,
  );
  const [confirmDelete, setConfirmDelete] = useState<UserSummary | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

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
      .then((res) => {
        setUsers(res.items);
        setTotal(res.total);
      })
      .catch(() => setError("Não foi possível carregar os usuários."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, roleFilter, statusFilter, page]);

  function handleSaved(user: UserSummary) {
    setFormOpen(false);
    setEditing(null);
    // Update in-place if editing, prepend if new
    setUsers((prev) => {
      const idx = prev.findIndex((u) => u.id === user.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = user;
        return next;
      }
      return [user, ...prev];
    });
    if (!editing) setTotal((t) => t + 1);
  }

  function handleToggled(updated: UserSummary) {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
  }

  async function handleAnonymize(user: UserSummary) {
    setActionLoading(user.id);
    try {
      const updated = await anonymizeUser(user.id);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } finally {
      setActionLoading(null);
      setConfirmAnonymize(null);
    }
  }

  async function handleDelete(user: UserSummary) {
    setActionLoading(user.id);
    try {
      await deleteUser(user.id);
      setUsers((prev) => prev.filter((u) => u.id !== user.id));
      setTotal((t) => t - 1);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setError(msg ?? "Erro ao excluir usuário.");
    } finally {
      setActionLoading(null);
      setConfirmDelete(null);
    }
  }

  const createdAt = (u: UserSummary) =>
    new Date(u.created_at).toLocaleDateString("pt-BR");

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Usuários</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {total} {total === 1 ? "usuário" : "usuários"} cadastrados
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          Novo usuário
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="flex-1 min-w-48">
          <Input
            placeholder="Buscar por nome ou e-mail…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="w-44">
          <Select
            options={FILTER_ROLE_OPTIONS}
            placeholder="Perfil"
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="w-36">
          <Select
            options={FILTER_STATUS_OPTIONS}
            placeholder="Status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
          />
        </div>
        {(search || roleFilter || statusFilter) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearch("");
              setRoleFilter("");
              setStatusFilter("");
              setPage(1);
            }}
          >
            Limpar
          </Button>
        )}
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Table */}
      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-background-surface overflow-hidden">
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Nome</TableHeaderCell>
                <TableHeaderCell className="w-52">E-mail</TableHeaderCell>
                <TableHeaderCell className="w-32">Perfil</TableHeaderCell>
                <TableHeaderCell className="w-28">Status</TableHeaderCell>
                <TableHeaderCell className="w-20">LGPD</TableHeaderCell>
                <TableHeaderCell className="w-28">Cadastrado</TableHeaderCell>
                <TableHeaderCell className="w-32 text-right">
                  Ações
                </TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {users.length === 0 ? (
                <TableEmpty colSpan={7} message="Nenhum usuário encontrado." />
              ) : (
                users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium text-slate-200">{u.name}</p>
                        {u.department && (
                          <p className="text-xs text-slate-500">
                            {u.department}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell muted className="text-xs">
                      {u.email}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`text-xs font-medium ${ROLE_COLOR[u.role]}`}
                      >
                        {ROLE_LABEL[u.role]}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {u.status !== "anonymized" && (
                          <StatusToggle user={u} onToggled={handleToggled} />
                        )}
                        <span className={`text-xs ${STATUS_COLOR[u.status]}`}>
                          {STATUS_LABEL[u.status]}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        title={
                          u.lgpd_consent
                            ? `Consentimento em ${new Date(u.lgpd_consent_at!).toLocaleDateString("pt-BR")}`
                            : "Sem consentimento"
                        }
                        className={`text-xs font-medium ${u.lgpd_consent ? "text-green-500" : "text-slate-600"}`}
                      >
                        {u.lgpd_consent ? "✓ Sim" : "✗ Não"}
                      </span>
                    </TableCell>
                    <TableCell muted className="text-xs">
                      {createdAt(u)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {u.status !== "anonymized" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditing(u);
                              setFormOpen(true);
                            }}
                          >
                            Editar
                          </Button>
                        )}
                        {u.status !== "anonymized" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-warning hover:text-warning"
                            onClick={() => setConfirmAnonymize(u)}
                            loading={actionLoading === u.id}
                          >
                            Anonimizar
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-danger hover:text-danger"
                          onClick={() => setConfirmDelete(u)}
                          loading={actionLoading === u.id}
                        >
                          Excluir
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Pagination */}
      {!loading && total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={setPage}
        />
      )}

      {/* Form modal */}
      {formOpen && (
        <UserFormModal
          editing={editing}
          onClose={() => {
            setFormOpen(false);
            setEditing(null);
          }}
          onSaved={handleSaved}
        />
      )}

      {/* Anonymize confirmation */}
      {confirmAnonymize && (
        <Modal
          open
          onClose={() => setConfirmAnonymize(null)}
          title="Anonimizar usuário"
        >
          <p className="text-sm text-slate-300 mb-2">
            Esta ação irá substituir os dados pessoais de{" "}
            <span className="font-semibold text-slate-100">
              {confirmAnonymize.name}
            </span>{" "}
            por valores anonimizados, conforme a LGPD.
          </p>
          <p className="text-xs text-slate-500 mb-4">
            Os tickets e registros de auditoria serão preservados. Esta ação não
            pode ser desfeita.
          </p>
          <ModalFooter>
            <Button
              variant="secondary"
              onClick={() => setConfirmAnonymize(null)}
            >
              Cancelar
            </Button>
            <Button
              variant="danger"
              loading={actionLoading === confirmAnonymize.id}
              onClick={() => handleAnonymize(confirmAnonymize)}
            >
              Confirmar anonimização
            </Button>
          </ModalFooter>
        </Modal>
      )}

      {/* Delete confirmation */}
      {confirmDelete && (
        <Modal
          open
          onClose={() => setConfirmDelete(null)}
          title="Excluir usuário"
        >
          <p className="text-sm text-slate-300 mb-2">
            Tem certeza que deseja excluir permanentemente o usuário{" "}
            <span className="font-semibold text-slate-100">
              {confirmDelete.name}
            </span>
            ?
          </p>
          <p className="text-xs text-slate-500 mb-4">
            Só é possível excluir usuários sem tickets. Se o usuário possuir
            tickets, use &ldquo;Anonimizar&rdquo; em vez disso.
          </p>
          <ModalFooter>
            <Button variant="secondary" onClick={() => setConfirmDelete(null)}>
              Cancelar
            </Button>
            <Button
              variant="danger"
              loading={actionLoading === confirmDelete.id}
              onClick={() => handleDelete(confirmDelete)}
            >
              Excluir permanentemente
            </Button>
          </ModalFooter>
        </Modal>
      )}
    </div>
  );
}
