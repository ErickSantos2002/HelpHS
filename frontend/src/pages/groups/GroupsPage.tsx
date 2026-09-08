import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { toastApiError } from "../../lib/toastError";
import { cn } from "../../lib/utils";
import { formatCnpj, onlyDigits } from "../../lib/documents";
import {
  Button,
  Icon,
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
  createCompanyFromSuggestion,
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

// ── Form schemas ──────────────────────────────────────────────

const groupSchema = z.object({
  name: z.string().min(1, "Nome obrigatório").max(255),
  description: z.string().optional(),
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
  onSave: (v: GroupFormValues) => Promise<void>;
  onClose: () => void;
}) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<GroupFormValues>({
    resolver: zodResolver(groupSchema),
    defaultValues: { name: initial?.name ?? "", description: initial?.description ?? "" },
  });
  const onSubmit = async (v: GroupFormValues) => {
    try { await onSave(v); onClose(); } catch (err) { toastApiError(err, "Erro ao salvar grupo."); }
  };
  return (
    <Modal open onClose={onClose} title={initial ? "Editar Grupo" : "Novo Grupo"}>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input label="Nome" {...register("name")} error={errors.name?.message} />
        <Textarea label="Descrição" {...register("description")} rows={3} />
        <ModalFooter>
          <Button variant="ghost" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={isSubmitting}>{initial ? "Salvar" : "Criar Grupo"}</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── Add company modal (suggestions + manual) ──────────────────

const SUGG_PAGE_SIZE = 5;

/**
 * Identidade da sugestão na lista. O nome sozinho colidia: o agrupamento do
 * backend é pela tupla inteira, então a mesma empresa com endereço digitado
 * diferente vira duas sugestões — duas `key` iguais, e o React embaralha.
 */
function sugKey(s: CompanySuggestion): string {
  return [s.company_name, s.cnpj, s.city, s.state, s.address].join("|");
}

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
  const [adding, setAdding] = useState(false);
  // Sugestão aguardando confirmação. Vincular em massa sem ver quem é ação
  // que ninguém desfaz — o admin confere a lista antes de gravar.
  const [confirmando, setConfirmando] = useState<CompanySuggestion | null>(null);

  const { register, handleSubmit, setValue, formState: { errors, isSubmitting } } = useForm<CompanyFormValues>({
    resolver: zodResolver(companySchema),
    defaultValues: { name: "", cnpj: "", phone: "", address: "", city: "", state: "", notes: "" },
  });

  useEffect(() => {
    getCompanySuggestions().then(setSuggestions).finally(() => setLoadingSugg(false));
  }, []);

  const filtered = suggestions.filter((s) =>
    s.company_name.toLowerCase().includes(search.toLowerCase()) ||
    onlyDigits(s.cnpj ?? "").includes(onlyDigits(search)),
  );
  const pagedSugg = filtered.slice((suggPage - 1) * SUGG_PAGE_SIZE, suggPage * SUGG_PAGE_SIZE);

  const handleConfirmSuggestion = async () => {
    if (!confirmando) return;
    setAdding(true);
    try {
      const r = await createCompanyFromSuggestion(
        groupId,
        confirmando,
        confirmando.clients.map((c) => c.id),
      );
      toast.success(
        r.company_created
          ? `Empresa criada e ${r.linked_clients.length} cliente(s) vinculado(s).`
          : `${r.linked_clients.length} cliente(s) vinculado(s) a "${r.company.name}", que já existia neste grupo.`,
      );
      onAdded(r.company);
      onClose();
    } catch (err) {
      toastApiError(err, "Erro ao adicionar empresa.");
    } finally {
      setAdding(false);
    }
  };

  const handleManualSubmit = async (v: CompanyFormValues) => {
    try {
      const newC = await createCompany(groupId, v);
      onAdded(newC);
      onClose();
    } catch (err) {
      toastApiError(err, "Erro ao criar empresa.");
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
      <div className="flex border-b border-borda mb-4 -mt-1">
        {(["suggestions", "manual"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer",
              tab === t
                ? "border-action text-conteudo-link"
                : "border-transparent text-conteudo-muted hover:text-conteudo",
            )}
          >
            {t === "suggestions" ? "Empresas cadastradas" : "Cadastrar nova"}
          </button>
        ))}
      </div>


      {tab === "suggestions" && (
        <div className="space-y-3">
          {confirmando ? (
            <div className="rounded-lg border border-borda p-4 space-y-3">
              <div>
                <p className="text-sm font-medium text-conteudo-heading">{confirmando.company_name}</p>
                {confirmando.cnpj && (
                  <p className="text-xs text-conteudo-muted mt-0.5">{formatCnpj(confirmando.cnpj)}</p>
                )}
              </div>
              <div>
                <p className="text-xs text-conteudo-muted mb-1.5">
                  {confirmando.clients.length === 1
                    ? "Este cliente será vinculado à empresa:"
                    : `Estes ${confirmando.clients.length} clientes serão vinculados à empresa:`}
                </p>
                <ul className="max-h-48 overflow-y-auto divide-y divide-borda rounded border border-borda">
                  {confirmando.clients.map((c) => (
                    <li key={c.id} className="px-3 py-2">
                      <p className="text-sm text-conteudo truncate">{c.name}</p>
                      <p className="text-xs text-conteudo-muted truncate">{c.email}</p>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setConfirmando(null)} disabled={adding}>
                  Voltar
                </Button>
                <Button size="sm" loading={adding} onClick={handleConfirmSuggestion}>
                  Confirmar vínculo
                </Button>
              </div>
            </div>
          ) : (
          <>
          <Input
            // O `Input` sem `label` não desenha rótulo nenhum, e placeholder
            // some ao digitar: quem volta ao campo não sabe mais o que ele
            // filtra.
            aria-label="Buscar empresa por nome ou CNPJ"
            placeholder="Buscar por nome ou CNPJ..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setSuggPage(1); }}
          />
          {loadingSugg ? (
            <div className="flex justify-center py-6"><Spinner /></div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-8 text-conteudo-muted text-sm">
              {suggestions.length === 0
                ? "Nenhum cliente com empresa cadastrada ainda."
                : "Nenhuma empresa encontrada."}
              <div className="mt-3">
                <Button size="sm" variant="ghost" onClick={() => setTab("manual")}>
                  Cadastrar nova empresa
                </Button>
              </div>
            </div>
          ) : (
            <div>
              <ul className="divide-y divide-borda rounded-lg border border-borda overflow-hidden">
                {pagedSugg.map((s) => (
                  <li key={sugKey(s)} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-3 hover:bg-surface-elevated">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-conteudo-heading truncate">{s.company_name}</p>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-conteudo-muted mt-0.5">
                        {s.cnpj && <span>{formatCnpj(s.cnpj)}</span>}
                        {s.city && <span>{s.city}{s.state ? ` - ${s.state}` : ""}</span>}
                        <span className="flex items-center gap-1"><Icon name="users" size={16} />{s.client_count} cliente{s.client_count !== 1 ? "s" : ""}</span>
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0 justify-end">
                      <Button size="sm" variant="ghost" onClick={() => prefillManual(s)} title="Editar antes de adicionar">
                        <Icon name="edit" size={16} strokeWidth={2} />
                      </Button>
                      <Button size="sm" onClick={() => setConfirmando(s)}>
                        <Icon name="plus" size={16} strokeWidth={2} /> Adicionar
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
          </>
          )}
        </div>
      )}

      {tab === "manual" && (
        <form onSubmit={handleSubmit(handleManualSubmit)} className="space-y-4">
          <Input label="Nome da empresa" {...register("name")} error={errors.name?.message} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="CNPJ" {...register("cnpj")} placeholder="00000000000000" />
            <Input label="Telefone" {...register("phone")} />
          </div>
          <Input label="Endereço" {...register("address")} />
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2"><Input label="Cidade" {...register("city")} /></div>
            <Input label="UF" {...register("state")} maxLength={2} placeholder="SP" />
          </div>
          <Textarea label="Notas internas" {...register("notes")} rows={2} />
          <ModalFooter>
            <Button variant="ghost" type="button" onClick={onClose}>Cancelar</Button>
            <Button type="submit" loading={isSubmitting}>Criar Empresa</Button>
          </ModalFooter>
        </form>
      )}
    </Modal>
  );
}

// ── Edit company modal ────────────────────────────────────────

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
  const onSubmit = async (v: CompanyFormValues) => {
    try { const c = await updateCompany(groupId, company.id, v); onSaved(c); onClose(); } catch (err) { toastApiError(err, "Erro ao salvar empresa."); }
  };
  return (
    <Modal open onClose={onClose} title="Editar Empresa">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input label="Nome da empresa" {...register("name")} error={errors.name?.message} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="CNPJ" {...register("cnpj")} placeholder="00000000000000" />
          <Input label="Telefone" {...register("phone")} />
        </div>
        <Input label="Endereço" {...register("address")} />
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2"><Input label="Cidade" {...register("city")} /></div>
          <Input label="UF" {...register("state")} maxLength={2} />
        </div>
        <Textarea label="Notas internas" {...register("notes")} rows={2} />
        <ModalFooter>
          <Button variant="ghost" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={isSubmitting}>Salvar</Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ── Assign client modal ───────────────────────────────────────

const ASSIGN_PAGE_SIZE = 5;

function AssignClientModal({
  groupId, companyId, onAssigned, onClose,
}: { groupId: string; companyId: string; onAssigned: (c: ClientInCompany) => void; onClose: () => void; }) {
  const [clients, setClients] = useState<ClientInCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [assignPage, setAssignPage] = useState(1);
  const [assigning, setAssigning] = useState<string | null>(null);

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
    } catch (err) { toastApiError(err, "Erro ao vincular cliente."); }
    finally { setAssigning(null); }
  };

  return (
    <Modal open onClose={onClose} title="Vincular Cliente" size="2xl">
      <div className="space-y-3">
        <Input aria-label="Buscar cliente por nome ou e-mail" placeholder="Buscar por nome ou e-mail..." value={search} onChange={(e) => { setSearch(e.target.value); setAssignPage(1); }} />
        {loading ? <div className="flex justify-center py-6"><Spinner /></div>
          : filtered.length === 0 ? (
            <p className="text-sm text-conteudo-muted text-center py-4">
              {clients.length === 0 ? "Todos os clientes já estão vinculados." : "Nenhum resultado."}
            </p>
          ) : (
            <div>
              <ul className="divide-y divide-borda rounded-lg border border-borda">
                {pagedClients.map((c) => (
                  <li key={c.id} className="flex items-center justify-between px-3 py-2.5 hover:bg-surface-elevated">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-conteudo-heading truncate">{c.name}</p>
                      <p className="text-xs text-conteudo-muted truncate">{c.email}</p>
                    </div>
                    <Button size="sm" variant="ghost" loading={assigning === c.id} onClick={() => handleAssign(c.id)}>Vincular</Button>
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
        <ModalFooter><Button variant="ghost" onClick={onClose}>Fechar</Button></ModalFooter>
      </div>
    </Modal>
  );
}

// ── Client notes modal ────────────────────────────────────────

function ClientNotesModal({
  groupId, companyId, client, onSaved, onClose,
}: { groupId: string; companyId: string; client: ClientInCompany; onSaved: (u: ClientInCompany) => void; onClose: () => void; }) {
  const [notes, setNotes] = useState(client.client_notes ?? "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try { const u = await updateClientNotes(groupId, companyId, client.id, notes || null); onSaved(u); onClose(); }
    catch (err) { toastApiError(err, "Erro ao salvar notas."); }
    finally { setSaving(false); }
  };
  return (
    <Modal open onClose={onClose} title={`Notas — ${client.name}`}>
      <div className="space-y-3">
        <Textarea label="Notas internas" value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} placeholder="Informações relevantes, histórico..." />
        <ModalFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} loading={saving}>Salvar</Button>
        </ModalFooter>
      </div>
    </Modal>
  );
}

// ── Company detail modal ──────────────────────────────────────

const CLIENTS_PAGE_SIZE = 5;

// Exportado só para o teste: `GroupsPage.test.tsx` precisa montar este modal
// direto para contar as chamadas do efeito. Continua sendo renderizado apenas
// por este arquivo.
export function CompanyDetailModal({
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

  // `load` era redefinido a cada render e o efeito dependia só de `company.id`,
  // o que deixava `groupId` de fora: se ele mudasse sozinho, o modal seguiria
  // mostrando a empresa carregada pelo grupo anterior. Hoje isso não acontece
  // — o backdrop do Modal cobre a tela e intercepta o clique, então trocar de
  // grupo com o modal aberto fecha o modal antes — mas a dependência que falta
  // é dívida esperando alguém tornar o modal não-bloqueante.
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await getCompany(groupId, company.id);
      setDetail(d);
      listCompanyNotes(groupId, company.id).then(setCompanyNotes).catch(() => {});
    } finally { setLoading(false); }
  }, [groupId, company.id]);

  useEffect(() => { load(); }, [load]);

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
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-conteudo-muted mb-4">
                {detail.cnpj && <span>CNPJ: <span className="text-conteudo">{formatCnpj(detail.cnpj)}</span></span>}
                {detail.phone && <span>Tel: <span className="text-conteudo">{detail.phone}</span></span>}
                {detail.city && <span>{detail.city}{detail.state ? ` - ${detail.state}` : ""}</span>}
                {detail.address && <span>{detail.address}</span>}
              </div>

              {/* Tabs */}
              <div className="flex border-b border-borda mb-4 -mt-1">
                <button
                  onClick={() => setActiveTab("clients")}
                  className={cn(
                    "px-4 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer",
                    activeTab === "clients"
                      ? "border-action text-conteudo-link"
                      : "border-transparent text-conteudo-muted hover:text-conteudo",
                  )}
                >
                  Clientes ({detail.client_count})
                </button>
                <button
                  onClick={() => setActiveTab("notes")}
                  className={cn(
                    "px-4 py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer flex items-center gap-1.5",
                    activeTab === "notes"
                      ? "border-warning text-on-tint-warning"
                      : "border-transparent text-conteudo-muted hover:text-conteudo",
                  )}
                >
                  <Icon name="document" size={16} strokeWidth={2} />
                  Notas ({companyNotes.length})
                </button>
              </div>

              {/* Clients tab */}
              {activeTab === "clients" && (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-semibold text-conteudo">Clientes</p>
                    <Button size="sm" onClick={() => setShowAssign(true)}><Icon name="plus" size={16} strokeWidth={2} />Vincular</Button>
                  </div>

                  {detail.clients.length === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center py-6 rounded-lg border border-dashed border-borda text-sm text-conteudo-muted">
                      Nenhum cliente vinculado.
                      <div className="mt-2"><Button size="sm" onClick={() => setShowAssign(true)}><Icon name="plus" size={16} strokeWidth={2} />Vincular cliente</Button></div>
                    </div>
                  ) : (
                    <div className="flex-1 flex flex-col min-h-0">
                      <ul className="divide-y divide-borda rounded-lg border border-borda overflow-y-auto flex-1">
                        {pagedClients.map((c) => (
                          <li key={c.id} className="flex items-center justify-between px-3 py-2.5 hover:bg-surface-elevated">
                            <div className="min-w-0 flex-1">
                              <p className="text-sm font-medium text-conteudo-heading truncate">{c.name}</p>
                              <p className="text-xs text-conteudo-muted truncate">{c.email}</p>
                              {c.client_notes && <p className="text-xs text-on-tint-warning line-clamp-1 mt-0.5">{c.client_notes}</p>}
                            </div>
                            <div className="flex gap-1 ml-2 shrink-0">
                              <button title="Notas" onClick={() => setNoteClient(c)} className="p-1.5 rounded text-conteudo-muted hover:text-on-tint-warning hover:bg-tint-warning transition-colors cursor-pointer"><Icon name="document" size={16} strokeWidth={2} /></button>
                              <button title="Desvincular" onClick={() => handleUnassign(c.id)} disabled={removingId === c.id} className="p-1.5 rounded text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-colors cursor-pointer disabled:opacity-50">
                                {removingId === c.id ? <Spinner size="sm" /> : <Icon name="close" size={16} strokeWidth={2} />}
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
                    <p className="text-sm font-semibold text-on-tint-warning">Notas da empresa</p>
                    <Button size="sm" variant="ghost" onClick={() => setShowAddCompanyNote(true)}>
                      <Icon name="plus" size={16} strokeWidth={2} />Adicionar nota
                    </Button>
                  </div>

                  {companyNotes.length === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-center py-8 rounded-lg border border-dashed border-warning/30 text-sm text-on-tint-warning">
                      Nenhuma nota ainda.
                      <div className="mt-2">
                        <Button size="sm" variant="ghost" onClick={() => setShowAddCompanyNote(true)}>
                          <Icon name="plus" size={16} strokeWidth={2} />Adicionar nota
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex-1 overflow-y-auto space-y-2 pr-0.5">
                      {companyNotes.map((n) => (
                        <div
                          key={n.id}
                          className="group rounded-lg border border-warning/20 bg-tint-warning p-3 cursor-pointer hover:border-warning/40 transition-colors"
                          onClick={() => setViewCompanyNote(n)}
                        >
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <span className="text-[11px] font-semibold text-on-tint-warning truncate">{n.author_name}</span>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <span className="text-[10px] text-on-tint-warning">
                                {new Date(n.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" })}
                              </span>
                              <button
                                // O botão é só o ícone, e o `Icon` é
                                // `aria-hidden`: sem isto o leitor de tela
                                // anuncia "botão" e mais nada.
                                aria-label="Deletar nota"
                                onClick={(e) => { e.stopPropagation(); handleDeleteCompanyNote(n.id); }}
                                disabled={companyNoteDeleting === n.id}
                                className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-on-tint-warning hover:text-on-tint-danger transition-all cursor-pointer"
                              >
                                {companyNoteDeleting === n.id ? <Spinner size="sm" /> : <Icon name="trash" size={16} strokeWidth={2} />}
                              </button>
                            </div>
                          </div>
                          <p className="text-xs text-on-tint-warning line-clamp-3 whitespace-pre-wrap">{n.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              <ModalFooter>
                <Button variant="ghost" onClick={() => setShowEdit(true)}><Icon name="edit" size={16} strokeWidth={2} />Editar empresa</Button>
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
            placeholder="Escreva a nota aqui..."
            value={newCompanyNoteContent}
            onChange={(e) => setNewCompanyNoteContent(e.target.value)}
          />
          <ModalFooter>
            <Button variant="ghost" onClick={() => { setShowAddCompanyNote(false); setNewCompanyNoteContent(""); }}>Cancelar</Button>
            <Button onClick={handleAddCompanyNote} loading={companyNoteSaving} disabled={!newCompanyNoteContent.trim()}>Salvar</Button>
          </ModalFooter>
        </div>
      </Modal>

      {/* View company note */}
      {viewCompanyNote && (
        <Modal open onClose={() => setViewCompanyNote(null)} title="Nota da empresa" size="lg">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-on-tint-warning">
              <span className="font-semibold">{viewCompanyNote.author_name}</span>
              <span>{new Date(viewCompanyNote.created_at).toLocaleString("pt-BR")}</span>
            </div>
            <p className="text-sm text-on-tint-warning whitespace-pre-wrap leading-relaxed min-h-[80px]">{viewCompanyNote.content}</p>
            <ModalFooter>
              <Button
                variant="ghost"
                size="sm"
                className="text-on-tint-danger hover:bg-tint-danger"
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

// ── Group notes list (shared mobile/desktop) ──────────────────

function GroupNotesList({ notes, noteDeleting, onView, onDelete, onAdd }: {
  notes: GroupNote[];
  noteDeleting: string | null;
  onView: (n: GroupNote) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
}) {
  if (notes.length === 0) return (
    <div className="text-center py-8 text-xs text-on-tint-warning italic">
      Nenhuma nota ainda.
      <button onClick={onAdd} className="block mt-2 text-on-tint-warning hover:underline cursor-pointer mx-auto not-italic">
        Adicionar nota
      </button>
    </div>
  );
  return (
    <div className="space-y-2">
      {notes.map((n) => (
        <div
          key={n.id}
          className="group rounded-lg border border-warning/20 bg-tint-warning p-3 cursor-pointer hover:border-warning/40 transition-colors"
          onClick={() => onView(n)}
        >
          <div className="flex items-center justify-between gap-1 mb-1">
            <span className="text-[10px] font-semibold text-on-tint-warning truncate">{n.author_name}</span>
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-[10px] text-on-tint-warning">
                {new Date(n.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" })}
              </span>
              <button
                aria-label="Deletar nota"
                onClick={(e) => { e.stopPropagation(); onDelete(n.id); }}
                disabled={noteDeleting === n.id}
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-on-tint-warning hover:text-on-tint-danger transition-all cursor-pointer"
              >
                {noteDeleting === n.id ? <Spinner size="sm" /> : <Icon name="trash" size={16} strokeWidth={2} />}
              </button>
            </div>
          </div>
          <p className="text-xs text-on-tint-warning line-clamp-3 whitespace-pre-wrap">{n.content}</p>
        </div>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────

export default function GroupsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [groups, setGroups] = useState<GroupResponse[]>([]);
  const [groupSearch, setGroupSearch] = useState("");
  const [loading, setLoading] = useState(true);
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
    try { setGroups(await listGroups()); } catch { toast.error("Não foi possível carregar os grupos."); } finally { setLoading(false); }
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
    } catch (err) { toastApiError(err, "Erro ao deletar grupo."); }
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

      {/* ── Left: Groups list ──────────────────────────────── */}
      <aside className={cn(
        "shrink-0 flex flex-col w-64 border-r border-borda bg-surface overflow-hidden",
        "transition-transform duration-300 ease-in-out",
        "absolute inset-y-0 left-0 z-30",
        sidebarOpen ? "translate-x-0" : "-translate-x-full",
        "xl:relative xl:inset-auto xl:z-auto xl:translate-x-0",
      )}>
        <div className="flex items-center justify-between px-4 py-4 border-b border-borda">
          <h1 className="text-sm font-semibold text-conteudo">Grupos</h1>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowNewGroup(true)}
              title="Novo grupo"
              className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-action-tint transition-colors cursor-pointer"
            >
              <Icon name="plus" size={16} strokeWidth={2} />
            </button>
            {selectedGroup && (
              <button
                onClick={() => setSidebarOpen(false)}
                className="xl:hidden p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo hover:bg-surface-elevated transition-colors cursor-pointer"
                title="Fechar"
              >
                <Icon name="close" size={16} strokeWidth={2} />
              </button>
            )}
          </div>
        </div>

        <div className="px-3 py-2 border-b border-borda">
          <div className="relative">
            {/* Outra lupa, com o traçado de outra família — a E21 unificou as
                três que o inventário achou num `search` só. */}
            <Icon
              name="search"
              size={14}
              strokeWidth={2}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-conteudo-muted pointer-events-none"
            />
            <input
              type="text"
              aria-label="Pesquisar grupos"
              placeholder="Pesquisar grupos..."
              value={groupSearch}
              onChange={(e) => setGroupSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md bg-surface-elevated border border-transparent focus:border-action focus:outline-none text-conteudo placeholder:text-conteudo-muted"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {loading ? (
            <div className="flex justify-center py-8"><Spinner /></div>
          ) : groups.length === 0 ? (
            <div className="text-center px-4 py-8 text-sm text-conteudo-muted">
              Nenhum grupo ainda.
              <button onClick={() => setShowNewGroup(true)} className="block mt-2 text-conteudo-link hover:underline cursor-pointer mx-auto text-xs">
                Criar primeiro grupo
              </button>
            </div>
          ) : (() => {
            const filtered = groups.filter((g) =>
              g.name.toLowerCase().includes(groupSearch.toLowerCase())
            );
            if (filtered.length === 0) return (
              <div className="text-center px-4 py-8 text-sm text-conteudo-muted">
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
                    ? "bg-action-tint text-conteudo-link border-l-2 border-action"
                    : "text-conteudo-muted hover:bg-surface-elevated",
                )}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{g.name}</p>
                  <p className="text-xs opacity-60 mt-0.5">{g.company_count} empresa{g.company_count !== 1 ? "s" : ""}</p>
                </div>
                <Icon name="chevronRight" size={16} strokeWidth={2} />
              </button>
            ));
          })()}
        </div>
      </aside>

      {/* ── Center: Group detail + companies ──────────────── */}
      <main className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6 min-w-0">

        {/* Mobile toggle — abrir sidebar */}
        <button
          onClick={() => setSidebarOpen(true)}
          className={cn(
            "xl:hidden mb-4 flex items-center gap-1.5 text-xs font-medium border rounded-lg px-3 py-1.5 transition-colors cursor-pointer",
            selectedGroup
              ? "text-conteudo-link border-action/30 bg-action-tint hover:bg-action/20"
              : "text-conteudo-muted border-borda/50 bg-surface-elevated hover:bg-surface",
          )}
        >
          <Icon name="chevronLeft" size={16} strokeWidth={2} />
          {selectedGroup ? selectedGroup.name : "Ver grupos"}
        </button>

        {!selectedGroup ? (
          <div className="flex flex-col items-center justify-center h-3/4 text-center">
            <div className="text-conteudo-faint mb-3">
              <Icon name="groups" size={64} strokeWidth={0.75} className="mx-auto" />
            </div>
            <p className="text-conteudo-muted font-medium">Selecione um grupo</p>
            {/* `faint` é o degrau do desenho, não do texto: sobre `--surface`
                ele dá 2,6:1. Quem lê a frase precisa do `muted`. */}
            <p className="text-sm text-conteudo-muted mt-1">Escolha um grupo à esquerda para ver detalhes</p>
          </div>
        ) : (
          <div>
            {/* Group header */}
            <div className="flex items-start justify-between mb-6 gap-3">
              <div className="min-w-0">
                <h2 className="text-xl font-semibold text-conteudo-heading break-words">{selectedGroup.name}</h2>
                {groupDetail?.description && (
                  <p className="text-sm text-conteudo-muted mt-0.5">{groupDetail.description}</p>
                )}
              </div>
              <div className="flex gap-2 shrink-0">
                <Button size="sm" variant="ghost" onClick={() => setShowEditGroup(true)}><Icon name="edit" size={16} strokeWidth={2} />Editar</Button>
                <Button size="sm" variant="ghost" className="text-on-tint-danger hover:bg-tint-danger" onClick={handleDeleteGroup}><Icon name="trash" size={16} strokeWidth={2} /></Button>
              </div>
            </div>

            {/* Companies section */}
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-conteudo">
                Empresas {groupDetail && `(${groupDetail.company_count})`}
              </p>
              <Button size="sm" onClick={() => setShowAddCompany(true)}><Icon name="plus" size={16} strokeWidth={2} />Adicionar empresa</Button>
            </div>

            {loadingDetail ? (
              <div className="flex justify-center py-12"><Spinner /></div>
            ) : !groupDetail || groupDetail.companies.length === 0 ? (
              <div className="text-center py-14 rounded-xl border border-dashed border-borda">
                <div className="flex justify-center mb-2 text-conteudo-faint"><Icon name="building" size={20} /></div>
                <p className="text-sm text-conteudo-muted">Nenhuma empresa neste grupo</p>
                <Button size="sm" className="mt-3" onClick={() => setShowAddCompany(true)}><Icon name="plus" size={16} strokeWidth={2} />Adicionar empresa</Button>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {groupDetail.companies.map((c) => (
                  <div key={c.id} className="rounded-xl border border-borda bg-surface hover:border-action/40 transition-colors">
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-2">
                        <button onClick={() => setSelectedCompany(c)} className="flex-1 text-left cursor-pointer min-w-0">
                          <p className="font-medium text-conteudo-heading truncate">{c.name}</p>
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-conteudo-muted">
                            {c.cnpj && <span>{formatCnpj(c.cnpj)}</span>}
                            {c.city && <span>{c.city}{c.state ? ` - ${c.state}` : ""}</span>}
                          </div>
                        </button>
                        <div className="flex gap-1 shrink-0">
                          <button onClick={() => setSelectedCompany(c)} title="Ver detalhes" className="p-1.5 rounded text-conteudo-muted hover:text-conteudo-link hover:bg-action-tint transition-colors cursor-pointer"><Icon name="chevronRight" size={16} strokeWidth={2} /></button>
                          <button onClick={() => handleDeleteCompany(c)} disabled={deletingCompanyId === c.id} title="Deletar" className="p-1.5 rounded text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-colors cursor-pointer disabled:opacity-50">
                            {deletingCompanyId === c.id ? <Spinner size="sm" /> : <Icon name="trash" size={16} strokeWidth={2} />}
                          </button>
                        </div>
                      </div>
                      <button onClick={() => setSelectedCompany(c)} className="mt-3 flex items-center gap-2 text-xs text-conteudo-muted hover:text-conteudo-link transition-colors cursor-pointer">
                        <span className="flex items-center gap-1"><Icon name="users" size={16} />{c.client_count} cliente{c.client_count !== 1 ? "s" : ""}</span>
                        {c.note_count > 0 && (
                          <span className="flex items-center gap-1 text-on-tint-warning bg-tint-warning border border-warning/30 rounded-full px-2 py-0.5">
                            <Icon name="document" size={16} strokeWidth={2} />{c.note_count} nota{c.note_count !== 1 ? "s" : ""}
                          </span>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ── Notas — mobile only (below companies) ── */}
            <div className="mt-5 xl:hidden rounded-xl border border-warning/20 bg-surface overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-warning/20">
                <p className="text-xs font-bold uppercase tracking-widest text-on-tint-warning flex items-center gap-1.5">
                  <Icon name="document" size={16} strokeWidth={2} />Notas do grupo
                </p>
                <button
                  onClick={() => setShowAddNote(true)}
                  title="Adicionar nota"
                  className="p-1.5 rounded-lg text-conteudo-muted hover:text-on-tint-warning hover:bg-tint-warning transition-colors cursor-pointer"
                >
                  <Icon name="plus" size={16} strokeWidth={2} />
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

      {/* ── Right: Notes panel — desktop only ─────────────── */}
      {selectedGroup && (
        <aside className="hidden xl:flex w-72 shrink-0 flex-col border-l border-borda bg-surface overflow-hidden">
          <div className="flex items-center justify-between px-4 py-4 border-b border-borda">
            <p className="text-xs font-bold uppercase tracking-widest text-on-tint-warning flex items-center gap-1.5">
              <Icon name="document" size={16} strokeWidth={2} />
              Notas do grupo
            </p>
            <button
              onClick={() => setShowAddNote(true)}
              title="Adicionar nota"
              className="p-1.5 rounded-lg text-conteudo-muted hover:text-on-tint-warning hover:bg-tint-warning transition-colors cursor-pointer"
            >
              <Icon name="plus" size={16} strokeWidth={2} />
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

      {/* ── Modals ────────────────────────────────────────── */}
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
            placeholder="Escreva a nota aqui..."
            value={newNoteContent}
            onChange={(e) => setNewNoteContent(e.target.value)}
          />
          <ModalFooter>
            <Button variant="ghost" onClick={() => { setShowAddNote(false); setNewNoteContent(""); }}>Cancelar</Button>
            <Button onClick={handleAddNote} loading={noteSaving} disabled={!newNoteContent.trim()}>Salvar</Button>
          </ModalFooter>
        </div>
      </Modal>

      {/* View note */}
      {viewNote && (
        <Modal open onClose={() => setViewNote(null)} title="Nota do grupo" size="lg">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-on-tint-warning">
              <span className="font-semibold">{viewNote.author_name}</span>
              <span>{new Date(viewNote.created_at).toLocaleString("pt-BR")}</span>
            </div>
            <p className="text-sm text-on-tint-warning whitespace-pre-wrap leading-relaxed min-h-[80px]">{viewNote.content}</p>
            <ModalFooter>
              <Button
                variant="ghost"
                size="sm"
                className="text-on-tint-danger hover:bg-tint-danger"
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

