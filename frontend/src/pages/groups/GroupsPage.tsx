import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { cn } from "../../lib/utils";
import {
  Alert,
  Button,
  Input,
  Modal,
  ModalFooter,
  Pagination,
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
  getCompanySuggestions,
  listGroupNotes,
  createGroupNote,
  deleteGroupNote,
  listCompanyNotes,
  createCompanyNote,
  deleteCompanyNote,
  type GroupResponse,
  type GroupDetail,
  type CompanyResponse,
  type CompanyDetail,
  type ClientInCompany,
  type CompanySuggestion,
  type GroupNote,
  type CompanyNote,
} from "../../services/groupService";

// â”€â”€ Icons â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function IconPlus() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
    </svg>
  );
}
function IconEdit() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  );
}
function IconTrash() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}
function IconNote() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}
function IconX() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
function IconChevronRight() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
function IconChevronLeft() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
    </svg>
  );
}
function IconBuilding() {
  return (
    <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  );
}
function IconUsers() {
  return (
    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  );
}

// â”€â”€ Form schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const groupSchema = z.object({
  name: z.string().min(1, "Nome obrigatÃ³rio").max(255),
  description: z.string().optional(),
});
type GroupFormValues = z.infer<typeof groupSchema>;

const companySchema = z.object({
  name: z.string().min(1, "Nome obrigatÃ³rio").max(255),
  cnpj: z.string().optional(),
  phone: z.string().optional(),
  address: z.string().optional(),
  city: z.string().optional(),
  state: z.string().max(2).optional(),
  notes: z.string().optional(),
});
type CompanyFormValues = z.infer<typeof companySchema>;

// â”€â”€ Group modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function GroupModal({
  initial,
  onSave,
  onClose,
}: {
  initial?: GroupResponse;
  onSave: (v: GroupFormValues) => Promise<void>;
  onClose: () => void;
}) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<GroupFormValues>({
    resolver: zodResolver(groupSchema),
    defaultValues: { name: initial?.name ?? "", description: initial?.description ?? "" },
  });
  const [error, setError] = useState("");
  const onSubmit = async (v: GroupFormValues) => {
    setError("");
    try { await onSave(v); onClose(); } catch { setError("Erro ao salvar grupo."); }
  };
  return (
    <Modal open onClose={onClose} title={initial ? "Editar Grupo" : "Novo Grupo"}>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {error && <Alert variant="error">{error}</Alert>}
        <Input label="Nome" {...register("name")} error={errors.name?.message} />
        <Textarea label="DescriÃ§Ã£o" {...register("description")} rows={3} />
        <ModalFooter>
          <Button variant="outline" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={isSubmitting}>{initial ? "Salvar" : "Criar Grupo"}</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// â”€â”€ Add company modal (suggestions + manual) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const SUGG_PAGE_SIZE = 5;

function AddCompanyModal({
  groupId,
  onAdded,
  onClose,
}: {
  groupId: string;
  onAdded: (c: CompanyResponse) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"suggestions" | "manual">("suggestions");
  const [suggestions, setSuggestions] = useState<CompanySuggestion[]>([]);
  const [loadingSugg, setLoadingSugg] = useState(true);
  const [search, setSearch] = useState("");
  const [suggPage, setSuggPage] = useState(1);
  const [adding, setAdding] = useState<string | null>(null);
  const [error, setError] = useState("");

  const { register, handleSubmit, setValue, formState: { errors, isSubmitting } } = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: { name: "", cnpj: "", phone: "", address: "", city: "", state: "", notes: "" },
  });

  useEffect(() => {
    getCompanySuggestions().then(setSuggestions).finally(() => setLoadingSugg(false));
  }, []);

  const filtered = suggestions.filter((s) =>
    s.company_name.toLowerCase().includes(search.toLowerCase()) ||
    (s.cnpj ?? "").includes(search),
  );
  const pagedSugg = filtered.slice((suggPage - 1) * SUGG_PAGE_SIZE, suggPage * SUGG_PAGE_SIZE);

  const handleAddFromSuggestion = async (s: CompanySuggestion) => {
    setAdding(s.company_name);
    setError("");
    try {
      const newC = await createCompany(groupId, {
        name: s.company_name,
        cnpj: s.cnpj ?? undefined,
        address: s.address ?? undefined,
        city: s.city ?? undefined,
        state: s.state ?? undefined,
      });
      onAdded(newC);
      onClose();
    } catch {
      setError("Erro ao adicionar empresa.");
    } finally {
      setAdding(null);
    }
  };

  const handleManualSubmit = async (v: CompanyFormValues) => {
    setError("");
    try {
      const newC = await createCompany(groupId, v);
      onAdded(newC);
      onClose();
    } catch {
      setError("Erro ao criar empresa.");
    }
  };

  const prefillManual = (s: CompanySuggestion) => {
    setValue("name", s.company_name);
    setValue("cnpj", s.cnpj ?? "");
    setValue("address", s.address ?? "");
    setValue("city", s.city ?? "");
    setValue("state", s.state ?? "");
    setTab("manual");
  };

  return (
    <Modal open onClose={onClose} title="Adicionar Empresa" size="2xl">
      {/* Tabs */}
      <div className="flex border-b border-border mb-4 -mt-1">
        {(["suggestions", "manual"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer",
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-slate-500 hover:text-slate-300",
            )}
          >
            {t === "suggestions" ? "Empresas cadastradas" : "Cadastrar nova"}
          </button>
        ))}
      </div>

      {error && <Alert variant="error" className="mb-3">{error}</Alert>}

      {tab === "suggestions" && (
        <div className="space-y-3">
          <Input
            placeholder="Buscar por nome ou CNPJ..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setSuggPage(1); }}
          />
          {loadingSugg ? (
            <div className="flex justify-center py-6"><Spinner /></div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-8 text-slate-500 dark:text-slate-400 text-sm">
              {suggestions.length === 0
                ? "Nenhum cliente com empresa cadastrada ainda."
                : "Nenhuma empresa encontrada."}
              <div className="mt-3">
                <Button size="sm" variant="outline" onClick={() => setTab("manual")}>
                  Cadastrar nova empresa
                </Button>
              </div>
            </div>
          ) : (
            <div>
              <ul className="divide-y divide-border rounded-lg border border-border overflow-hidden">
                {pagedSugg.map((s) => (
                  <li key={s.company_name} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-3 hover:bg-background-elevated">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-100 truncate">{s.company_name}</p>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500 mt-0.5">
                        {s.cnpj && <span>{s.cnpj}</span>}
                        {s.city && <span>{s.city}{s.state ? ` - ${s.state}` : ""}</span>}
                        <span className="flex items-center gap-1"><IconUsers />{s.client_count} cliente{s.client_count !== 1 ? "s" : ""}</span>
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0 justify-end">
                      <Button size="sm" variant="outline" onClick={() => prefillManual(s)} title="Editar antes de adicionar">
                        <IconEdit />
                      </Button>
                      <Button size="sm" loading={adding === s.company_name} onClick={() => handleAddFromSuggestion(s)}>
                        <IconPlus /> Adicionar
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
              <Pagination
                page={suggPage}
                pageSize={SUGG_PAGE_SIZE}
                total={filtered.length}
                onPageChange={setSuggPage}
                itemLabel="empresas"
              />
            </div>
          )}
        </div>
      )}

      {tab === "manual" && (
        <form onSubmit={handleSubmit(handleManualSubmit)} className="space-y-4">
          <Input label="Nome da empresa" {...register("name")} error={errors.name?.message} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="CNPJ" {...register("cnpj")} placeholder="00.000.000/0000-00" />
            <Input label="Telefone" {...register("phone")} />
          </div>
          <Input label="EndereÃ§o" {...register("address")} />
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2"><Input label="Cidade" {...register("city")} /></div>
            <Input label="UF" {...register("state")} maxLength={2} placeholder="SP" />
          </div>
          <Textarea label="Notas internas" {...register("notes")} rows={2} />
          <ModalFooter>
            <Button variant="outline" type="button" onClick={onClose}>Cancelar</Button>
            <Button type="submit" loading={isSubmitting}>Criar Empresa</Button>
          </ModalFooter>
        </form>
      )}
    </Modal>
  );
}

// â”€â”€ Edit company modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function EditCompanyModal({
  groupId,
  company,
  onSaved,
  onClose,
}: {
  groupId: string;
  company: CompanyResponse;
  onSaved: (c: CompanyResponse) => void;
  onClose: () => void;
}) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: { name: company.name, cnpj: company.cnpj ?? "", phone: company.phone ?? "", address: company.address ?? "", city: company.city ?? "", state: company.state ?? "", notes: company.notes ?? "" },
  });
  const [error, setError] = useState("");
  const onSubmit = async (v: CompanyFormValues) => {
    setError("");
    try { const c = await updateCompany(groupId, company.id, v); onSaved(c); onClose(); } catch { setError("Erro ao salvar empresa."); }
  };
  return (
    <Modal open onClose={onClose} title="Editar Empresa">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {error && <Alert variant="error">{error}</Alert>}
        <Input label="Nome da empresa" {...register("name")} error={errors.name?.message} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="CNPJ" {...register("cnpj")} />
          <Input label="Telefone" {...register("phone")} />
        </div>
        <Input label="EndereÃ§o" {...register("address")} />
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2"><Input label="Cidade" {...register("city")} /></div>
          <Input label="UF" {...register("state")} maxLength={2} />
        </div>
        <Textarea label="Notas internas" {...register("notes")} rows={2} />
        <ModalFooter>
          <Button variant="outline" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={isSubmitting}>Salvar</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// â”€â”€ Assign client modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const ASSIGN_PAGE_SIZE = 5;

function AssignClientModal({
  groupId, companyId, onAssigned, onClose,
}: { groupId: string; companyId: string; onAssigned: (c: ClientInCompany) => void; onClose: () => void; }) {
  const [clients, setClients] = useState<ClientInCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [assignPage, setAssignPage] = useState(1);
  const [assigning, setAssigning] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { listUnassignedClients().then(setClients).finally(() => setLoading(false)); }, []);

  const filtered = clients.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase()),
  );
  const pagedClients = filtered.slice((assignPage - 1) * ASSIGN_PAGE_SIZE, assignPage * ASSIGN_PAGE_SIZE);

  const handleAssign = async (userId: string) => {
    setAssigning(userId);
    try {
      const client = await assignClient(groupId, companyId, userId);
      onAssigned(client);
      setClients((prev) => prev.filter((c) => c.id !== userId));
      setAssignPage(1);
    } catch { setError("Erro ao vincular cliente."); }
    finally { setAssigning(null); }
  };

  return (
    <Modal open onClose={onClose} title="Vincular Cliente" size="2xl">
      <div className="space-y-3">
        {error && <Alert variant="error">{error}</Alert>}
        <Input placeholder="Buscar por nome ou e-mail..." value={search} onChange={(e) => { setSearch(e.target.value); setAssignPage(1); }} />
        {loading ? <div className="flex justify-center py-6"><Spinner /></div>
          : filtered.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-4">
              {clients.length === 0 ? "Todos os clientes jÃ¡ estÃ£o vinculados." : "Nenhum resultado."}
            </p>
          ) : (
            <div>
              <ul className="divide-y divide-border rounded-lg border border-border">
                {pagedClients.map((c) => (
                  <li key={c.id} className="flex items-center justify-between px-3 py-2.5 hover:bg-background-elevated">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-100 truncate">{c.name}</p>
                      <p className="text-xs text-slate-500 truncate">{c.email}</p>
                    </div>
                    <Button size="sm" variant="outline" loading={assigning === c.id} onClick={() => handleAssign(c.id)}>Vincular</Button>
                  </li>
                ))}
              </ul>
              <Pagination
                page={assignPage}
                pageSize={ASSIGN_PAGE_SIZE}
                total={filtered.length}
                onPageChange={setAssignPage}
                itemLabel="clientes"
              />
            </div>
          )}
        <ModalFooter><Button variant="outline" onClick={onClose}>Fechar</Button></ModalFooter>
      </div>
    </Modal>
  );
}

// â”€â”€ Client notes modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function ClientNotesModal({
  groupId, companyId, client, onSaved, onClose,
}: { groupId: string; companyId: string; client: ClientInCompany; onSaved: (u: ClientInCompany) => void; onClose: () => void; }) {
  const [notes, setNotes] = useState(client.client_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    setSaving(true);
    try { const u = await updateClientNotes(groupId, companyId, client.id, notes || null); onSaved(u); onClose(); }
    catch { setError("Erro ao salvar notas."); }
    finally { setSaving(false); }
  };
  return (
    <Modal open onClose={onClose} title={`Notas â€” ${client.name}`}>
      <div className="space-y-3">
        {error && <Alert variant="error">{error}</Alert>}
        <Textarea label="Notas internas" value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} placeholder="InformaÃ§Ãµes relevantes, histÃ³rico..." />
        <ModalFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} loading={saving}>Salvar</Button>
        </ModalFooter>
      </div>
    </Modal>
  );
}

// â”€â”€ Company detail modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const CLIENTS_PAGE_SIZE = 5;

function CompanyDetailModal({
  groupId, company, onClose, onUpdated,
}: { groupId: string; company: CompanyResponse; onClose: () => void; onUpdated: () => void; }) {
  const [detail, setDetail] = useState<CompanyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [showEdit, setShowEdit] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [noteClient, setNoteClient] = useState<ClientInCompany | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [clientsPage, setClientsPage] = useState(1);

  // Company notes
  const [companyNotes, setCompanyNotes] = useState<CompanyNote[]>([]);
  const [showAddCompanyNote, setShowAddCompanyNote] = useState(false);
  const [viewCompanyNote, setViewCompanyNote] = useState<CompanyNote | null>(null);
  const [newCompanyNoteContent, setNewCompanyNoteContent] = useState("");
  const [companyNoteSaving, setCompanyNoteSaving] = useState(false);
  const [companyNoteDeleting, setCompanyNoteDeleting] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"clients" | "notes">("clients");

  const load = async () => {
    setLoading(true);
    try {
      const d = await getCompany(groupId, company.id);
      setDetail(d);
      listCompanyNotes(groupId, company.id).then(setCompanyNotes).catch(() => {});
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [company.id]);

  const handleUnassign = async (clientId: string) => {
    if (!confirm("Desvincular este cliente?")) return;
    setRemovingId(clientId);
    try {
      await unassignClient(groupId, company.id, clientId);
      setDetail((p) => p ? { ...p, clients: p.clients.filter((c) => c.id !== clientId), client_count: p.client_count - 1 } : p);
      onUpdated();
    } finally { setRemovingId(null); }
  };

  const handleAddCompanyNote = async () => {
    if (!newCompanyNoteContent.trim()) return;
    setCompanyNoteSaving(true);
    try {
      const note = await createCompanyNote(groupId, company.id, newCompanyNoteContent.trim());
      setCompanyNotes((p) => [note, ...p]);
      setNewCompanyNoteContent("");
      setShowAddCompanyNote(false);
      onUpdated();
    } finally { setCompanyNoteSaving(false); }
  };

  const handleDeleteCompanyNote = async (noteId: string) => {
    if (!confirm("Deletar esta nota?")) return;
    setCompanyNoteDeleting(noteId);
    try {
      await deleteCompanyNote(groupId, company.id, noteId);
      setCompanyNotes((p) => p.filter((n) => n.id !== noteId));
      if (viewCompanyNote?.id === noteId) setViewCompanyNote(null);
      onUpdated();
    } finally { setCompanyNoteDeleting(null); }
  };

  const pagedClients = detail
    ? detail.clients.slice((clientsPage - 1) * CLIENTS_PAGE_SIZE, clientsPage * CLIENTS_PAGE_SIZE)
    : [];

  return (
    <>
      <Modal open onClose={onClose} title={company.name} size="2xl">
        <div className="flex flex-col" style={{ minHeight: 480, maxHeight: "75vh" }}>
          {loading ? (
            <div className="flex justify-center items-center flex-1 py-8"><Spinner /></div>
          ) : detail && (
            <>
              {/* Company info */}
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-400 mb-4">
                {detail.cnpj && <span>CNPJ: <span className="text-slate-300">{detail.cnpj}</span></span>}
                {detail.phone && <span>Tel: <span className="text-slate-300">{detail.phone}</span></span>}
                {detail.city && <span>{detail.city}{detail.state ? ` - ${detail.state}` : ""}</span>}
                {detail.address && <span>{detail.address}</span>}
              </div>

              {/* Tabs */}
              <div className="flex border-b border-border mb-4 -mt-1">
                <button
                  onClick={() => setActiveTab("clients")}
                  className={cn(
                    "px-4 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer",
                    activeTab === "clients"
                      ? "border-primary text-primary"
                      : "border-transparent text-slate-500 hover:text-slate-300",
                  )}
                >
                  Clientes ({detail.client_count})
                </button>
                <button
                  onClick={() => setActiveTab("notes")}
                  className={cn(
                    "px-4 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer flex items-center gap-1.5",
                    activeTab === "notes"
                      ? "border-amber-500 text-amber-500 dark:text-amber-400"
                      : "border-transparent text-slate-500 hover:text-slate-300",
                  )}
                >
                  <IconNote />
                  Notas ({companyNotes.length})
                </button>
              </div>

              {/* Clients tab */}
              {activeTab === "clients" && (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-semibold text-slate-300">Clientes</p>
                    <Button size="sm" onClick={() => setShowAssign(true)}><IconPlus />Vincular</Button>
                  </div>

                  {detail.clients.length === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center py-6 rounded-lg border border-dashed border-border text-sm text-slate-500">
                      Nenhum cliente vinculado.
                      <div className="mt-2"><Button size="sm" onClick={() => setShowAssign(true)}><IconPlus />Vincular cliente</Button></div>
                    </div>
                  ) : (
                    <div className="flex-1 flex flex-col min-h-0">
                      <ul className="divide-y divide-border rounded-lg border border-border overflow-y-auto flex-1">
                        {pagedClients.map((c) => (
                          <li key={c.id} className="flex items-center justify-between px-3 py-2.5 hover:bg-background-elevated">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-slate-100 truncate">{c.name}</p>
                              <p className="text-xs text-slate-500 truncate">{c.email}</p>
                              {c.client_notes && <p className="text-xs text-amber-600 dark:text-amber-400 line-clamp-1 mt-0.5">{c.client_notes}</p>}
                            </div>
                            <div className="flex gap-1 ml-2 shrink-0">
                              <button title="Notas" onClick={() => setNoteClient(c)} className="p-1.5 rounded text-slate-500 hover:text-amber-500 hover:bg-amber-100 dark:hover:text-amber-400 dark:hover:bg-amber-900/20 transition-colors cursor-pointer"><IconNote /></button>
                              <button title="Desvincular" onClick={() => handleUnassign(c.id)} disabled={removingId === c.id} className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors cursor-pointer disabled:opacity-50">
                                {removingId === c.id ? <Spinner size="sm" /> : <IconX />}
                              </button>
                            </div>
                          </li>
                        ))}
                      </ul>
                      <Pagination
                        page={clientsPage}
                        pageSize={CLIENTS_PAGE_SIZE}
                        total={detail.client_count}
                        onPageChange={(p) => setClientsPage(p)}
                        itemLabel="clientes"
                        className="pt-3"
                      />
                    </div>
                  )}
                </>
              )}

              {/* Notes tab */}
              {activeTab === "notes" && (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm font-semibold text-amber-600 dark:text-amber-400/80">Notas da empresa</p>
                    <Button size="sm" variant="outline" onClick={() => setShowAddCompanyNote(true)}>
                      <IconPlus />Adicionar nota
                    </Button>
                  </div>

                  {companyNotes.length === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center py-8 rounded-lg border border-dashed border-amber-200 dark:border-amber-800/30 text-sm text-amber-600/70 dark:text-amber-700/50">
                      Nenhuma nota ainda.
                      <div className="mt-2">
                        <Button size="sm" variant="outline" onClick={() => setShowAddCompanyNote(true)}>
                          <IconPlus />Adicionar nota
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex-1 overflow-y-auto space-y-2 pr-0.5">
                      {companyNotes.map((n) => (
                        <div
                          key={n.id}
                          className="group rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-700/20 dark:bg-amber-950/15 p-3 cursor-pointer hover:border-amber-300 dark:hover:border-amber-600/40 transition-colors"
                          onClick={() => setViewCompanyNote(n)}
                        >
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-500/70 truncate">{n.author_name}</span>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <span className="text-[10px] text-amber-600/70 dark:text-amber-700/50">
                                {new Date(n.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" })}
                              </span>
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDeleteCompanyNote(n.id); }}
                                disabled={companyNoteDeleting === n.id}
                                className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-amber-500 dark:text-amber-700/60 hover:text-red-400 transition-all cursor-pointer"
                              >
                                {companyNoteDeleting === n.id ? <Spinner size="sm" /> : <IconTrash />}
                              </button>
                            </div>
                          </div>
                          <p className="text-xs text-slate-600 dark:text-amber-200/60 line-clamp-3 whitespace-pre-wrap">{n.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              <ModalFooter>
                <Button variant="outline" onClick={() => setShowEdit(true)}><IconEdit />Editar empresa</Button>
                <Button onClick={onClose}>Fechar</Button>
              </ModalFooter>
            </>
          )}
        </div>
      </Modal>

      {showEdit && detail && (
        <EditCompanyModal
          groupId={groupId}
          company={detail}
          onSaved={(updated) => { setDetail((p) => p ? { ...p, ...updated } : p); onUpdated(); }}
          onClose={() => setShowEdit(false)}
        />
      )}
      {showAssign && (
        <AssignClientModal
          groupId={groupId}
          companyId={company.id}
          onAssigned={(client) => {
            setDetail((p) => p ? { ...p, clients: [...p.clients, client], client_count: p.client_count + 1 } : p);
            onUpdated();
          }}
          onClose={() => setShowAssign(false)}
        />
      )}
      {noteClient && (
        <ClientNotesModal
          groupId={groupId}
          companyId={company.id}
          client={noteClient}
          onSaved={(u) => { setDetail((p) => p ? { ...p, clients: p.clients.map((c) => c.id === u.id ? u : c) } : p); setNoteClient(null); }}
          onClose={() => setNoteClient(null)}
        />
      )}

      {/* Add company note */}
      <Modal open={showAddCompanyNote} onClose={() => { setShowAddCompanyNote(false); setNewCompanyNoteContent(""); }} title="Nova nota da empresa">
        <div className="space-y-4">
          <Textarea
            rows={5}
            placeholder="Escreva a nota aquiâ€¦"
            value={newCompanyNoteContent}
            onChange={(e) => setNewCompanyNoteContent(e.target.value)}
          />
          <ModalFooter>
            <Button variant="outline" onClick={() => { setShowAddCompanyNote(false); setNewCompanyNoteContent(""); }}>Cancelar</Button>
            <Button onClick={handleAddCompanyNote} loading={companyNoteSaving} disabled={!newCompanyNoteContent.trim()}>Salvar</Button>
          </ModalFooter>
        </div>
      </Modal>

      {/* View company note */}
      {viewCompanyNote && (
        <Modal open onClose={() => setViewCompanyNote(null)} title="Nota da empresa" size="lg">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-amber-600 dark:text-amber-500/70">
              <span className="font-semibold">{viewCompanyNote.author_name}</span>
              <span>{new Date(viewCompanyNote.created_at).toLocaleString("pt-BR")}</span>
            </div>
            <p className="text-sm text-slate-700 dark:text-amber-200/80 whitespace-pre-wrap leading-relaxed min-h-[80px]">{viewCompanyNote.content}</p>
            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                className="text-red-500 hover:bg-red-900/20"
                loading={companyNoteDeleting === viewCompanyNote.id}
                onClick={() => handleDeleteCompanyNote(viewCompanyNote.id)}
              >
                Deletar
              </Button>
              <Button onClick={() => setViewCompanyNote(null)}>Fechar</Button>
            </ModalFooter>
          </div>
        </Modal>
      )}
    </>
  );
}

// â”€â”€ Group notes list (shared mobile/desktop) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function GroupNotesList({ notes, noteDeleting, onView, onDelete, onAdd }: {
  notes: GroupNote[];
  noteDeleting: string | null;
  onView: (n: GroupNote) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
}) {
  if (notes.length === 0) return (
    <div className="text-center py-8 text-xs text-amber-600/70 dark:text-amber-700/50 italic">
      Nenhuma nota ainda.
      <button onClick={onAdd} className="block mt-2 text-amber-500 hover:text-amber-600 dark:text-amber-500/70 dark:hover:text-amber-400 cursor-pointer mx-auto not-italic">
        Adicionar nota
      </button>
    </div>
  );
  return (
    <div className="space-y-2">
      {notes.map((n) => (
        <div
          key={n.id}
          className="group rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-700/20 dark:bg-amber-950/15 p-3 cursor-pointer hover:border-amber-300 dark:hover:border-amber-600/40 transition-colors"
          onClick={() => onView(n)}
        >
          <div className="flex items-center justify-between gap-1 mb-1">
            <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-500/70 truncate">{n.author_name}</span>
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-[10px] text-amber-600/70 dark:text-amber-700/50">
                {new Date(n.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" })}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(n.id); }}
                disabled={noteDeleting === n.id}
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-amber-500 dark:text-amber-700/60 hover:text-red-400 transition-all cursor-pointer"
              >
                {noteDeleting === n.id ? <Spinner size="sm" /> : <IconTrash />}
              </button>
            </div>
          </div>
          <p className="text-xs text-slate-600 dark:text-amber-200/60 line-clamp-3 whitespace-pre-wrap">{n.content}</p>
        </div>
      ))}
    </div>
  );
}

// â”€â”€ Main page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function GroupsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [groups, setGroups] = useState<GroupResponse[]>([]);
  const [groupSearch, setGroupSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedGroup, setSelectedGroup] = useState<GroupResponse | null>(null);
  const [groupDetail, setGroupDetail] = useState<GroupDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [showEditGroup, setShowEditGroup] = useState(false);
  const [showAddCompany, setShowAddCompany] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<CompanyResponse | null>(null);
  const [deletingCompanyId, setDeletingCompanyId] = useState<string | null>(null);

  // Notes
  const [groupNotes, setGroupNotes] = useState<GroupNote[]>([]);
  const [showAddNote, setShowAddNote] = useState(false);
  const [viewNote, setViewNote] = useState<GroupNote | null>(null);
  const [newNoteContent, setNewNoteContent] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteDeleting, setNoteDeleting] = useState<string | null>(null);

  const loadGroups = async () => {
    setLoading(true);
    try { setGroups(await listGroups()); } catch { setError("Erro ao carregar grupos."); } finally { setLoading(false); }
  };

  const loadGroupDetail = async (g: GroupResponse) => {
    setLoadingDetail(true);
    setGroupDetail(null);
    try { setGroupDetail(await getGroup(g.id)); } finally { setLoadingDetail(false); }
  };

  useEffect(() => { loadGroups(); }, []);

  const handleSelectGroup = (g: GroupResponse) => {
    setSelectedGroup(g);
    setGroupNotes([]);
    loadGroupDetail(g);
    listGroupNotes(g.id).then(setGroupNotes).catch(() => {});
    setSidebarOpen(false);
  };

  const handleAddNote = async () => {
    if (!selectedGroup || !newNoteContent.trim()) return;
    setNoteSaving(true);
    try {
      const note = await createGroupNote(selectedGroup.id, newNoteContent.trim());
      setGroupNotes((p) => [note, ...p]);
      setNewNoteContent("");
      setShowAddNote(false);
    } finally { setNoteSaving(false); }
  };

  const handleDeleteNote = async (noteId: string) => {
    if (!selectedGroup || !confirm("Deletar esta nota?")) return;
    setNoteDeleting(noteId);
    try {
      await deleteGroupNote(selectedGroup.id, noteId);
      setGroupNotes((p) => p.filter((n) => n.id !== noteId));
      if (viewNote?.id === noteId) setViewNote(null);
    } finally { setNoteDeleting(null); }
  };

  const handleDeleteGroup = async () => {
    if (!selectedGroup) return;
    if (!confirm(`Deletar o grupo "${selectedGroup.name}"?`)) return;
    try {
      await deleteGroup(selectedGroup.id);
      setGroups((p) => p.filter((g) => g.id !== selectedGroup.id));
      setSelectedGroup(null);
      setGroupDetail(null);
    } catch { setError("Erro ao deletar grupo."); }
  };

  const handleDeleteCompany = async (company: CompanyResponse) => {
    if (!selectedGroup) return;
    if (!confirm(`Deletar a empresa "${company.name}"?`)) return;
    setDeletingCompanyId(company.id);
    try {
      await deleteCompany(selectedGroup.id, company.id);
      setGroupDetail((p) => p ? { ...p, companies: p.companies.filter((c) => c.id !== company.id), company_count: p.company_count - 1 } : p);
      setGroups((p) => p.map((g) => g.id === selectedGroup.id ? { ...g, company_count: g.company_count - 1 } : g));
    } finally { setDeletingCompanyId(null); }
  };

  const refreshDetail = () => selectedGroup && loadGroupDetail(selectedGroup);

  return (
    <div className="relative flex h-full overflow-hidden">

      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="xl:hidden absolute inset-0 z-20 bg-black/60 backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* â”€â”€ Left: Groups list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <aside className={cn(
        "shrink-0 flex flex-col w-64 border-r border-slate-200 dark:border-border bg-white dark:bg-background-surface overflow-hidden",
        "transition-transform duration-300 ease-in-out",
        "absolute inset-y-0 left-0 z-30",
        sidebarOpen ? "translate-x-0" : "-translate-x-full",
        "xl:relative xl:inset-auto xl:z-auto xl:translate-x-0",
      )}>
        <div className="flex items-center justify-between px-4 py-4 border-b border-slate-200 dark:border-border">
          <h1 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Grupos</h1>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowNewGroup(true)}
              title="Novo grupo"
              className="p-1.5 rounded-lg text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
            >
              <IconPlus />
            </button>
            {selectedGroup && (
              <button
                onClick={() => setSidebarOpen(false)}
                className="xl:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-background-elevated transition-colors cursor-pointer"
                title="Fechar"
              >
                <IconX />
              </button>
            )}
          </div>
        </div>

        <div className="px-3 py-2 border-b border-slate-200 dark:border-border">
          <div className="relative">
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 111 11a6 6 0 0116 0z" />
            </svg>
            <input
              type="text"
              placeholder="Pesquisar grupos..."
              value={groupSearch}
              onChange={(e) => setGroupSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md bg-slate-100 dark:bg-background-elevated border border-transparent focus:border-primary focus:outline-none text-slate-700 dark:text-slate-300 placeholder-slate-400"
            />
          </div>
        </div>

        {error && <Alert variant="error" className="m-3">{error}</Alert>}

        <div className="flex-1 overflow-y-auto py-2">
          {loading ? (
            <div className="flex justify-center py-8"><Spinner /></div>
          ) : groups.length === 0 ? (
            <div className="text-center px-4 py-8 text-sm text-slate-500">
              Nenhum grupo ainda.
              <button onClick={() => setShowNewGroup(true)} className="block mt-2 text-primary hover:underline cursor-pointer mx-auto text-xs">
                Criar primeiro grupo
              </button>
            </div>
          ) : (() => {
            const filtered = groups.filter((g) =>
              g.name.toLowerCase().includes(groupSearch.toLowerCase())
            );
            if (filtered.length === 0) return (
              <div className="text-center px-4 py-8 text-sm text-slate-500">
                Nenhum resultado para "{groupSearch}".
              </div>
            );
            return filtered.map((g) => (
              <button
                key={g.id}
                onClick={() => handleSelectGroup(g)}
                className={cn(
                  "w-full text-left px-4 py-3 flex items-center justify-between gap-2 transition-colors cursor-pointer",
                  selectedGroup?.id === g.id
                    ? "bg-primary/10 text-primary border-l-2 border-primary"
                    : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-background-elevated",
                )}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{g.name}</p>
                  <p className="text-xs opacity-60 mt-0.5">{g.company_count} empresa{g.company_count !== 1 ? "s" : ""}</p>
                </div>
                <IconChevronRight />
              </button>
            ));
          })()}
        </div>
      </aside>

      {/* â”€â”€ Center: Group detail + companies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <main className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 min-w-0">

        {/* Mobile toggle â€” abrir sidebar */}
        <button
          onClick={() => setSidebarOpen(true)}
          className={cn(
            "xl:hidden mb-4 flex items-center gap-1.5 text-xs font-medium border rounded-lg px-3 py-1.5 transition-colors cursor-pointer",
            selectedGroup
              ? "text-primary border-primary/30 bg-primary/10 hover:bg-primary/20"
              : "text-slate-400 border-border/50 bg-background-elevated hover:bg-background-surface",
          )}
        >
          <IconChevronLeft />
          {selectedGroup ? selectedGroup.name : "Ver grupos"}
        </button>

        {!selectedGroup ? (
          <div className="flex flex-col items-center justify-center h-3/4 text-center">
            <div className="text-slate-300 dark:text-slate-700 mb-3">
              <svg className="w-16 h-16 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={0.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
            <p className="text-slate-500 dark:text-slate-400 font-medium">Selecione um grupo</p>
            <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">Escolha um grupo Ã  esquerda para ver detalhes</p>
          </div>
        ) : (
          <div>
            {/* Group header */}
            <div className="flex items-start justify-between mb-6 gap-3">
              <div className="min-w-0">
                <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100 break-words">{selectedGroup.name}</h2>
                {groupDetail?.description && (
                  <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{groupDetail.description}</p>
                )}
              </div>
              <div className="flex gap-2 shrink-0">
                <Button size="sm" variant="outline" onClick={() => setShowEditGroup(true)}><IconEdit />Editar</Button>
                <Button size="sm" variant="outline" className="text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20" onClick={handleDeleteGroup}><IconTrash /></Button>
              </div>
            </div>

            {/* Companies section */}
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                Empresas {groupDetail && `(${groupDetail.company_count})`}
              </p>
              <Button size="sm" onClick={() => setShowAddCompany(true)}><IconPlus />Adicionar empresa</Button>
            </div>

            {loadingDetail ? (
              <div className="flex justify-center py-12"><Spinner /></div>
            ) : !groupDetail || groupDetail.companies.length === 0 ? (
              <div className="text-center py-14 rounded-xl border border-dashed border-slate-200 dark:border-border">
                <div className="flex justify-center mb-2 text-slate-300 dark:text-slate-700"><IconBuilding /></div>
                <p className="text-sm text-slate-500 dark:text-slate-400">Nenhuma empresa neste grupo</p>
                <Button size="sm" className="mt-3" onClick={() => setShowAddCompany(true)}><IconPlus />Adicionar empresa</Button>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {groupDetail.companies.map((c) => (
                  <div key={c.id} className="rounded-xl border border-slate-200 dark:border-border bg-white dark:bg-background-surface hover:border-primary/40 transition-colors">
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-2">
                        <button onClick={() => setSelectedCompany(c)} className="flex-1 text-left cursor-pointer min-w-0">
                          <p className="font-medium text-slate-800 dark:text-slate-100 truncate">{c.name}</p>
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
                            {c.cnpj && <span>{c.cnpj}</span>}
                            {c.city && <span>{c.city}{c.state ? ` - ${c.state}` : ""}</span>}
                          </div>
                        </button>
                        <div className="flex gap-1 shrink-0">
                          <button onClick={() => setSelectedCompany(c)} title="Ver detalhes" className="p-1.5 rounded text-slate-400 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"><IconChevronRight /></button>
                          <button onClick={() => handleDeleteCompany(c)} disabled={deletingCompanyId === c.id} title="Deletar" className="p-1.5 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors cursor-pointer disabled:opacity-50">
                            {deletingCompanyId === c.id ? <Spinner size="sm" /> : <IconTrash />}
                          </button>
                        </div>
                      </div>
                      <button onClick={() => setSelectedCompany(c)} className="mt-3 flex items-center gap-2 text-xs text-slate-500 hover:text-primary transition-colors cursor-pointer">
                        <span className="flex items-center gap-1"><IconUsers />{c.client_count} cliente{c.client_count !== 1 ? "s" : ""}</span>
                        {c.note_count > 0 && (
                          <span className="flex items-center gap-1 text-amber-600 bg-amber-100 border border-amber-300 dark:text-amber-500 dark:bg-amber-900/20 dark:border-amber-700/30 rounded-full px-2 py-0.5">
                            <IconNote />{c.note_count} nota{c.note_count !== 1 ? "s" : ""}
                          </span>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* â”€â”€ Notas â€” mobile only (below companies) â”€â”€ */}
            <div className="mt-5 xl:hidden rounded-xl border border-amber-200/50 dark:border-amber-800/20 bg-white dark:bg-background-surface overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-amber-200/50 dark:border-amber-800/20">
                <p className="text-xs font-bold uppercase tracking-widest text-amber-600 dark:text-amber-500/80 flex items-center gap-1.5">
                  <IconNote />Notas do grupo
                </p>
                <button
                  onClick={() => setShowAddNote(true)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-amber-500 hover:bg-amber-100 dark:hover:text-amber-400 dark:hover:bg-amber-900/20 transition-colors cursor-pointer"
                >
                  <IconPlus />
                </button>
              </div>
              <div className="p-3">
                <GroupNotesList
                  notes={groupNotes}
                  noteDeleting={noteDeleting}
                  onView={setViewNote}
                  onDelete={handleDeleteNote}
                  onAdd={() => setShowAddNote(true)}
                />
              </div>
            </div>
          </div>
        )}
      </main>

      {/* â”€â”€ Right: Notes panel â€” desktop only â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {selectedGroup && (
        <aside className="hidden xl:flex w-72 shrink-0 flex-col border-l border-slate-200 dark:border-border bg-white dark:bg-background-surface overflow-hidden">
          <div className="flex items-center justify-between px-4 py-4 border-b border-slate-200 dark:border-border">
            <p className="text-xs font-bold uppercase tracking-widest text-amber-600 dark:text-amber-500/80 flex items-center gap-1.5">
              <IconNote />
              Notas do grupo
            </p>
            <button
              onClick={() => setShowAddNote(true)}
              title="Adicionar nota"
              className="p-1.5 rounded-lg text-slate-400 hover:text-amber-500 hover:bg-amber-100 dark:hover:text-amber-400 dark:hover:bg-amber-900/20 transition-colors cursor-pointer"
            >
              <IconPlus />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <GroupNotesList
              notes={groupNotes}
              noteDeleting={noteDeleting}
              onView={setViewNote}
              onDelete={handleDeleteNote}
              onAdd={() => setShowAddNote(true)}
            />
          </div>
        </aside>
      )}

      {/* â”€â”€ Modals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {showNewGroup && (
        <GroupModal
          onSave={async (v) => { const g = await createGroup(v); setGroups((p) => [...p, g]); }}
          onClose={() => setShowNewGroup(false)}
        />
      )}
      {showEditGroup && selectedGroup && (
        <GroupModal
          initial={selectedGroup}
          onSave={async (v) => {
            const updated = await updateGroup(selectedGroup.id, v);
            setGroups((p) => p.map((g) => g.id === updated.id ? updated : g));
            setSelectedGroup(updated);
            setGroupDetail((p) => p ? { ...p, ...updated } : p);
          }}
          onClose={() => setShowEditGroup(false)}
        />
      )}
      {showAddCompany && selectedGroup && (
        <AddCompanyModal
          groupId={selectedGroup.id}
          onAdded={(c) => {
            setGroupDetail((p) => p ? { ...p, companies: [...p.companies, c], company_count: p.company_count + 1 } : p);
            setGroups((p) => p.map((g) => g.id === selectedGroup.id ? { ...g, company_count: g.company_count + 1 } : g));
          }}
          onClose={() => setShowAddCompany(false)}
        />
      )}
      {selectedCompany && selectedGroup && (
        <CompanyDetailModal
          groupId={selectedGroup.id}
          company={selectedCompany}
          onClose={() => setSelectedCompany(null)}
          onUpdated={refreshDetail}
        />
      )}

      {/* Add note */}
      <Modal open={showAddNote} onClose={() => { setShowAddNote(false); setNewNoteContent(""); }} title="Nova nota">
        <div className="space-y-4">
          <Textarea
            rows={5}
            placeholder="Escreva a nota aquiâ€¦"
            value={newNoteContent}
            onChange={(e) => setNewNoteContent(e.target.value)}
          />
          <ModalFooter>
            <Button variant="outline" onClick={() => { setShowAddNote(false); setNewNoteContent(""); }}>Cancelar</Button>
            <Button onClick={handleAddNote} loading={noteSaving} disabled={!newNoteContent.trim()}>Salvar</Button>
          </ModalFooter>
        </div>
      </Modal>

      {/* View note */}
      {viewNote && (
        <Modal open onClose={() => setViewNote(null)} title="Nota do grupo" size="lg">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-amber-600 dark:text-amber-500/70">
              <span className="font-semibold">{viewNote.author_name}</span>
              <span>{new Date(viewNote.created_at).toLocaleString("pt-BR")}</span>
            </div>
            <p className="text-sm text-slate-700 dark:text-amber-200/80 whitespace-pre-wrap leading-relaxed min-h-[80px]">{viewNote.content}</p>
            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                className="text-red-500 hover:bg-red-900/20"
                loading={noteDeleting === viewNote.id}
                onClick={() => handleDeleteNote(viewNote.id)}
              >
                Deletar
              </Button>
              <Button onClick={() => setViewNote(null)}>Fechar</Button>
            </ModalFooter>
          </div>
        </Modal>
      )}
    </div>
  );
}

