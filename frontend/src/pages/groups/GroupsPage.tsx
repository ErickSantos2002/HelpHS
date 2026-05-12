import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Alert,
  Button,
  Card,
  CardTitle,
  Input,
  Modal,
  ModalFooter,
  Spinner,
  Textarea,
} from "../../components/ui";
import {
  listGroups,
  getGroup,
  createGroup,
  updateGroup,
  deleteGroup,
  getCompany,
  createCompany,
  updateCompany,
  deleteCompany,
  assignClient,
  unassignClient,
  updateClientNotes,
  listUnassignedClients,
  type GroupResponse,
  type GroupDetail,
  type CompanyResponse,
  type CompanyDetail,
  type ClientInCompany,
} from "../../services/groupService";

// ── Icons ─────────────────────────────────────────────────────

function IconPlus() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
    </svg>
  );
}
function IconEdit() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  );
}
function IconTrash() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}
function IconChevronRight() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
function IconBuilding() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  );
}
function IconUsers() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  );
}
function IconNote() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}
function IconX() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

// ── Form schemas ──────────────────────────────────────────────

const groupSchema = z.object({
  name: z.string().min(1, "Nome obrigatório").max(255),
  description: z.string().optional(),
  notes: z.string().optional(),
});
type GroupFormValues = z.infer<typeof groupSchema>;

const companySchema = z.object({
  name: z.string().min(1, "Nome obrigatório").max(255),
  cnpj: z.string().optional(),
  phone: z.string().optional(),
  address: z.string().optional(),
  city: z.string().optional(),
  state: z.string().max(2).optional(),
  notes: z.string().optional(),
});
type CompanyFormValues = z.infer<typeof companySchema>;

// ── Group modal ───────────────────────────────────────────────

function GroupModal({
  initial,
  onSave,
  onClose,
}: {
  initial?: GroupResponse;
  onSave: (values: GroupFormValues) => Promise<void>;
  onClose: () => void;
}) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<GroupFormValues>({
    resolver: zodResolver(groupSchema),
    defaultValues: {
      name: initial?.name ?? "",
      description: initial?.description ?? "",
      notes: initial?.notes ?? "",
    },
  });
  const [error, setError] = useState("");

  const onSubmit = async (values: GroupFormValues) => {
    setError("");
    try {
      await onSave(values);
      onClose();
    } catch {
      setError("Erro ao salvar grupo.");
    }
  };

  return (
    <Modal isOpen onClose={onClose} title={initial ? "Editar Grupo" : "Novo Grupo"}>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {error && <Alert variant="error">{error}</Alert>}
        <Input label="Nome" {...register("name")} error={errors.name?.message} />
        <Textarea label="Descrição" {...register("description")} rows={2} />
        <Textarea label="Notas internas" {...register("notes")} rows={3} />
        <ModalFooter>
          <Button variant="outline" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={isSubmitting}>
            {initial ? "Salvar" : "Criar Grupo"}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── Company modal ─────────────────────────────────────────────

function CompanyModal({
  groupId,
  initial,
  onSave,
  onClose,
}: {
  groupId: string;
  initial?: CompanyResponse;
  onSave: (values: CompanyFormValues) => Promise<void>;
  onClose: () => void;
}) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: {
      name: initial?.name ?? "",
      cnpj: initial?.cnpj ?? "",
      phone: initial?.phone ?? "",
      address: initial?.address ?? "",
      city: initial?.city ?? "",
      state: initial?.state ?? "",
      notes: initial?.notes ?? "",
    },
  });
  const [error, setError] = useState("");

  const onSubmit = async (values: CompanyFormValues) => {
    setError("");
    try {
      await onSave(values);
      onClose();
    } catch {
      setError("Erro ao salvar empresa.");
    }
  };

  return (
    <Modal isOpen onClose={onClose} title={initial ? "Editar Empresa" : "Nova Empresa"}>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {error && <Alert variant="error">{error}</Alert>}
        <Input label="Nome da empresa" {...register("name")} error={errors.name?.message} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="CNPJ" {...register("cnpj")} placeholder="00.000.000/0000-00" />
          <Input label="Telefone" {...register("phone")} />
        </div>
        <Input label="Endereço" {...register("address")} />
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <Input label="Cidade" {...register("city")} />
          </div>
          <Input label="UF" {...register("state")} maxLength={2} placeholder="SP" />
        </div>
        <Textarea label="Notas internas" {...register("notes")} rows={3} />
        <ModalFooter>
          <Button variant="outline" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={isSubmitting}>
            {initial ? "Salvar" : "Criar Empresa"}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── Assign client modal ───────────────────────────────────────

function AssignClientModal({
  groupId,
  companyId,
  onAssigned,
  onClose,
}: {
  groupId: string;
  companyId: string;
  onAssigned: (client: ClientInCompany) => void;
  onClose: () => void;
}) {
  const [clients, setClients] = useState<ClientInCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [assigning, setAssigning] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listUnassignedClients().then(setClients).finally(() => setLoading(false));
  }, []);

  const filtered = clients.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.email.toLowerCase().includes(search.toLowerCase()),
  );

  const handleAssign = async (userId: string) => {
    setAssigning(userId);
    setError("");
    try {
      const client = await assignClient(groupId, companyId, userId);
      onAssigned(client);
      setClients((prev) => prev.filter((c) => c.id !== userId));
    } catch {
      setError("Erro ao vincular cliente.");
    } finally {
      setAssigning(null);
    }
  };

  return (
    <Modal isOpen onClose={onClose} title="Vincular Cliente">
      <div className="space-y-3">
        {error && <Alert variant="error">{error}</Alert>}
        <Input
          placeholder="Buscar por nome ou e-mail..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {loading ? (
          <div className="flex justify-center py-6"><Spinner /></div>
        ) : filtered.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400 text-center py-4">
            {clients.length === 0 ? "Todos os clientes já estão vinculados a uma empresa." : "Nenhum cliente encontrado."}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-border max-h-72 overflow-y-auto rounded-lg border border-slate-200 dark:border-border">
            {filtered.map((c) => (
              <li key={c.id} className="flex items-center justify-between px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-background-elevated">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{c.name}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{c.email}</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  loading={assigning === c.id}
                  onClick={() => handleAssign(c.id)}
                >
                  Vincular
                </Button>
              </li>
            ))}
          </ul>
        )}
        <ModalFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
        </ModalFooter>
      </div>
    </Modal>
  );
}

// ── Client notes modal ────────────────────────────────────────

function ClientNotesModal({
  groupId,
  companyId,
  client,
  onSaved,
  onClose,
}: {
  groupId: string;
  companyId: string;
  client: ClientInCompany;
  onSaved: (updated: ClientInCompany) => void;
  onClose: () => void;
}) {
  const [notes, setNotes] = useState(client.client_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const updated = await updateClientNotes(groupId, companyId, client.id, notes || null);
      onSaved(updated);
      onClose();
    } catch {
      setError("Erro ao salvar notas.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal isOpen onClose={onClose} title={`Notas — ${client.name}`}>
      <div className="space-y-3">
        {error && <Alert variant="error">{error}</Alert>}
        <Textarea
          label="Notas internas sobre este cliente"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={5}
          placeholder="Informações relevantes, observações, histórico..."
        />
        <ModalFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} loading={saving}>Salvar Notas</Button>
        </ModalFooter>
      </div>
    </Modal>
  );
}

// ── Company detail panel ──────────────────────────────────────

function CompanyPanel({
  groupId,
  companyId,
  onClose,
  onUpdated,
}: {
  groupId: string;
  companyId: string;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showEdit, setShowEdit] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [noteClient, setNoteClient] = useState<ClientInCompany | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const d = await getCompany(groupId, companyId);
      setDetail(d);
    } catch {
      setError("Erro ao carregar empresa.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [companyId]);

  const handleUnassign = async (clientId: string) => {
    if (!confirm("Desvincular este cliente da empresa?")) return;
    setRemovingId(clientId);
    try {
      await unassignClient(groupId, companyId, clientId);
      setDetail((prev) =>
        prev ? { ...prev, clients: prev.clients.filter((c) => c.id !== clientId), client_count: prev.client_count - 1 } : prev,
      );
      onUpdated();
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Voltar
          </button>
          {detail && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowEdit(true)}>
                <IconEdit />
              </Button>
            </div>
          )}
        </div>

        {loading && <div className="flex justify-center py-8"><Spinner /></div>}
        {error && <Alert variant="error">{error}</Alert>}

        {detail && (
          <div className="flex-1 overflow-y-auto space-y-5">
            <div>
              <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{detail.name}</h2>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                {detail.cnpj && <span>CNPJ: {detail.cnpj}</span>}
                {detail.phone && <span>Tel: {detail.phone}</span>}
                {(detail.city || detail.state) && (
                  <span>{[detail.city, detail.state].filter(Boolean).join(" - ")}</span>
                )}
              </div>
              {detail.address && (
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{detail.address}</p>
              )}
            </div>

            {/* Notes */}
            {detail.notes && (
              <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 p-3">
                <div className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400 text-xs font-semibold mb-1">
                  <IconNote /> Notas internas
                </div>
                <p className="text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap">{detail.notes}</p>
              </div>
            )}

            {/* Clients */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Clientes ({detail.client_count})
                </h3>
                <Button size="sm" onClick={() => setShowAssign(true)}>
                  <IconPlus /> Vincular
                </Button>
              </div>

              {detail.clients.length === 0 ? (
                <div className="text-center py-6 rounded-lg border border-dashed border-slate-200 dark:border-border">
                  <IconUsers />
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                    Nenhum cliente vinculado
                  </p>
                  <Button size="sm" className="mt-3" onClick={() => setShowAssign(true)}>
                    <IconPlus /> Vincular cliente
                  </Button>
                </div>
              ) : (
                <ul className="divide-y divide-slate-100 dark:divide-border rounded-lg border border-slate-200 dark:border-border overflow-hidden">
                  {detail.clients.map((c) => (
                    <li key={c.id} className="px-3 py-2.5 hover:bg-slate-50 dark:hover:bg-background-elevated">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{c.name}</p>
                          <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{c.email}</p>
                          {c.client_notes && (
                            <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-400 line-clamp-1">
                              {c.client_notes}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            title="Editar notas"
                            onClick={() => setNoteClient(c)}
                            className="p-1.5 rounded-md text-slate-400 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors cursor-pointer"
                          >
                            <IconNote />
                          </button>
                          <button
                            title="Desvincular"
                            onClick={() => handleUnassign(c.id)}
                            disabled={removingId === c.id}
                            className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer disabled:opacity-50"
                          >
                            {removingId === c.id ? <Spinner size="sm" /> : <IconX />}
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      {showEdit && detail && (
        <CompanyModal
          groupId={groupId}
          initial={detail}
          onSave={async (values) => {
            const updated = await updateCompany(groupId, companyId, values);
            setDetail((prev) => prev ? { ...prev, ...updated } : prev);
            onUpdated();
          }}
          onClose={() => setShowEdit(false)}
        />
      )}
      {showAssign && (
        <AssignClientModal
          groupId={groupId}
          companyId={companyId}
          onAssigned={(client) => {
            setDetail((prev) =>
              prev
                ? { ...prev, clients: [...prev.clients, client], client_count: prev.client_count + 1 }
                : prev,
            );
            onUpdated();
          }}
          onClose={() => setShowAssign(false)}
        />
      )}
      {noteClient && (
        <ClientNotesModal
          groupId={groupId}
          companyId={companyId}
          client={noteClient}
          onSaved={(updated) => {
            setDetail((prev) =>
              prev
                ? { ...prev, clients: prev.clients.map((c) => (c.id === updated.id ? updated : c)) }
                : prev,
            );
            setNoteClient(null);
          }}
          onClose={() => setNoteClient(null)}
        />
      )}
    </>
  );
}

// ── Group detail panel ────────────────────────────────────────

function GroupPanel({
  group,
  onBack,
  onGroupUpdated,
  onGroupDeleted,
}: {
  group: GroupResponse;
  onBack: () => void;
  onGroupUpdated: (g: GroupResponse) => void;
  onGroupDeleted: () => void;
}) {
  const [detail, setDetail] = useState<GroupDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showEditGroup, setShowEditGroup] = useState(false);
  const [showNewCompany, setShowNewCompany] = useState(false);
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [deletingCompanyId, setDeletingCompanyId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const d = await getGroup(group.id);
      setDetail(d);
    } catch {
      setError("Erro ao carregar grupo.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [group.id]);

  const handleDeleteCompany = async (companyId: string, companyName: string) => {
    if (!confirm(`Deletar a empresa "${companyName}"? Os clientes vinculados serão desvinculados.`)) return;
    setDeletingCompanyId(companyId);
    try {
      await deleteCompany(group.id, companyId);
      setDetail((prev) =>
        prev
          ? { ...prev, companies: prev.companies.filter((c) => c.id !== companyId), company_count: prev.company_count - 1 }
          : prev,
      );
    } finally {
      setDeletingCompanyId(null);
    }
  };

  const handleDeleteGroup = async () => {
    if (!confirm(`Deletar o grupo "${group.name}"? Todas as empresas e vínculos serão removidos.`)) return;
    try {
      await deleteGroup(group.id);
      onGroupDeleted();
    } catch {
      setError("Erro ao deletar grupo.");
    }
  };

  if (selectedCompanyId) {
    return (
      <CompanyPanel
        groupId={group.id}
        companyId={selectedCompanyId}
        onClose={() => setSelectedCompanyId(null)}
        onUpdated={load}
      />
    );
  }

  return (
    <>
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Todos os grupos
          </button>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowEditGroup(true)}>
              <IconEdit />
            </Button>
            <Button size="sm" variant="outline" className="text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20" onClick={handleDeleteGroup}>
              <IconTrash />
            </Button>
          </div>
        </div>

        {loading && <div className="flex justify-center py-8"><Spinner /></div>}
        {error && <Alert variant="error">{error}</Alert>}

        {detail && (
          <div className="flex-1 overflow-y-auto space-y-5">
            <div>
              <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100">{detail.name}</h2>
              {detail.description && (
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{detail.description}</p>
              )}
            </div>

            {/* Group notes */}
            {detail.notes && (
              <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 p-3">
                <div className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400 text-xs font-semibold mb-1">
                  <IconNote /> Notas do grupo
                </div>
                <p className="text-sm text-amber-800 dark:text-amber-300 whitespace-pre-wrap">{detail.notes}</p>
              </div>
            )}

            {/* Companies */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Empresas ({detail.company_count})
                </h3>
                <Button size="sm" onClick={() => setShowNewCompany(true)}>
                  <IconPlus /> Nova Empresa
                </Button>
              </div>

              {detail.companies.length === 0 ? (
                <div className="text-center py-10 rounded-lg border border-dashed border-slate-200 dark:border-border">
                  <IconBuilding />
                  <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                    Nenhuma empresa neste grupo
                  </p>
                  <Button size="sm" className="mt-3" onClick={() => setShowNewCompany(true)}>
                    <IconPlus /> Adicionar empresa
                  </Button>
                </div>
              ) : (
                <div className="grid gap-3">
                  {detail.companies.map((c) => (
                    <div
                      key={c.id}
                      className="rounded-lg border border-slate-200 dark:border-border bg-white dark:bg-background-surface hover:border-primary/40 transition-colors"
                    >
                      <div className="flex items-start justify-between p-4">
                        <button
                          onClick={() => setSelectedCompanyId(c.id)}
                          className="flex-1 text-left cursor-pointer"
                        >
                          <p className="font-medium text-slate-800 dark:text-slate-100">{c.name}</p>
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500 dark:text-slate-400">
                            {c.cnpj && <span>{c.cnpj}</span>}
                            {c.city && <span>{c.city}{c.state ? ` - ${c.state}` : ""}</span>}
                            <span className="flex items-center gap-1">
                              <IconUsers />
                              {c.client_count} cliente{c.client_count !== 1 ? "s" : ""}
                            </span>
                          </div>
                          {c.notes && (
                            <p className="mt-1.5 text-xs text-amber-700 dark:text-amber-400 line-clamp-1">{c.notes}</p>
                          )}
                        </button>
                        <div className="flex items-center gap-1 ml-2 shrink-0">
                          <button
                            onClick={() => setSelectedCompanyId(c.id)}
                            className="p-1.5 rounded-md text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                            title="Ver detalhes"
                          >
                            <IconChevronRight />
                          </button>
                          <button
                            onClick={() => handleDeleteCompany(c.id, c.name)}
                            disabled={deletingCompanyId === c.id}
                            className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer disabled:opacity-50"
                            title="Deletar empresa"
                          >
                            {deletingCompanyId === c.id ? <Spinner size="sm" /> : <IconTrash />}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      {showEditGroup && (
        <GroupModal
          initial={group}
          onSave={async (values) => {
            const updated = await updateGroup(group.id, values);
            onGroupUpdated(updated);
            setDetail((prev) => prev ? { ...prev, ...updated } : prev);
          }}
          onClose={() => setShowEditGroup(false)}
        />
      )}
      {showNewCompany && (
        <CompanyModal
          groupId={group.id}
          onSave={async (values) => {
            const newC = await createCompany(group.id, values);
            setDetail((prev) =>
              prev
                ? { ...prev, companies: [...prev.companies, { ...newC, client_count: 0 }], company_count: prev.company_count + 1 }
                : prev,
            );
          }}
          onClose={() => setShowNewCompany(false)}
        />
      )}
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────

export default function GroupsPage() {
  const [groups, setGroups] = useState<GroupResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<GroupResponse | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await listGroups();
      setGroups(data);
    } catch {
      setError("Erro ao carregar grupos.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (selectedGroup) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <GroupPanel
          group={selectedGroup}
          onBack={() => setSelectedGroup(null)}
          onGroupUpdated={(updated) => {
            setGroups((prev) => prev.map((g) => (g.id === updated.id ? updated : g)));
            setSelectedGroup(updated);
          }}
          onGroupDeleted={() => {
            setGroups((prev) => prev.filter((g) => g.id !== selectedGroup.id));
            setSelectedGroup(null);
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-800 dark:text-slate-100">Grupos</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Organize clientes por empresa e grupo
          </p>
        </div>
        <Button onClick={() => setShowNewGroup(true)}>
          <IconPlus /> Novo Grupo
        </Button>
      </div>

      {error && <Alert variant="error" className="mb-4">{error}</Alert>}

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : groups.length === 0 ? (
        <div className="text-center py-20 rounded-xl border border-dashed border-slate-200 dark:border-border">
          <div className="flex justify-center mb-3 text-slate-300 dark:text-slate-600">
            <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
          </div>
          <p className="text-slate-500 dark:text-slate-400 font-medium">Nenhum grupo criado</p>
          <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">
            Crie um grupo para organizar clientes por empresa
          </p>
          <Button className="mt-4" onClick={() => setShowNewGroup(true)}>
            <IconPlus /> Criar primeiro grupo
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {groups.map((g) => (
            <button
              key={g.id}
              onClick={() => setSelectedGroup(g)}
              className="text-left rounded-xl border border-slate-200 dark:border-border bg-white dark:bg-background-surface p-5 hover:border-primary/50 hover:shadow-sm transition-all duration-150 cursor-pointer group"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-800 dark:text-slate-100 group-hover:text-primary transition-colors truncate">
                    {g.name}
                  </p>
                  {g.description && (
                    <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400 line-clamp-2">
                      {g.description}
                    </p>
                  )}
                </div>
                <span className="shrink-0 text-slate-300 dark:text-slate-600 group-hover:text-primary/50 transition-colors">
                  <IconChevronRight />
                </span>
              </div>

              <div className="mt-4 flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                <span className="flex items-center gap-1">
                  <IconBuilding />
                  {g.company_count} empresa{g.company_count !== 1 ? "s" : ""}
                </span>
                {g.notes && (
                  <span className="flex items-center gap-1 text-amber-600 dark:text-amber-500">
                    <IconNote /> Com notas
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {showNewGroup && (
        <GroupModal
          onSave={async (values) => {
            const newGroup = await createGroup(values);
            setGroups((prev) => [...prev, newGroup]);
          }}
          onClose={() => setShowNewGroup(false)}
        />
      )}
    </div>
  );
}
