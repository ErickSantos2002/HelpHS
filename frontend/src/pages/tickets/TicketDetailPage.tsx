import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Modal,
  ModalFooter,
  PriorityBadge,
  Select,
  Spinner,
  StatusBadge,
  Textarea,
} from "../../components/ui";
import { ChatPanel } from "../../components/chat/ChatPanel";
import { KBSuggestionsPanel } from "../../components/kb/KBSuggestionsPanel";
import { useAuth } from "../../contexts/AuthContext";
import {
  deleteAttachment,
  getAttachmentUrl,
  getAttachments,
  uploadAttachments,
  type Attachment,
} from "../../services/attachmentService";
import {
  assignTicket,
  getTicket,
  getTicketHistory,
  updateTicketStatus,
  type Ticket,
  type TicketHistory,
} from "../../services/ticketService";
import {
  getTicketSurvey,
  submitSurvey,
  type Survey,
} from "../../services/surveyService";
import { getTechnicians, type UserSummary } from "../../services/userService";

// ── Status options ────────────────────────────────────────────

const STATUS_LABEL: Record<string, string> = {
  open: "Aberto",
  in_progress: "Em andamento",
  awaiting_client: "Aguardando cliente",
  awaiting_technical: "Aguardando técnico",
  resolved: "Resolvido",
  closed: "Fechado",
  cancelled: "Cancelado",
};

const TRANSITIONS: Record<string, string[]> = {
  open: ["in_progress", "cancelled"],
  in_progress: [
    "awaiting_client",
    "awaiting_technical",
    "resolved",
    "cancelled",
  ],
  awaiting_client: ["in_progress", "resolved", "cancelled"],
  awaiting_technical: ["in_progress", "resolved", "cancelled"],
  resolved: ["closed"],
  closed: [],
  cancelled: [],
};

const FIELD_LABEL: Record<string, string> = {
  created: "Ticket aberto",
  status: "Status alterado",
  title: "Título alterado",
  description: "Descrição alterada",
  priority: "Prioridade alterada",
  category: "Categoria alterada",
  assignee_id: "Técnico atribuído",
  product_id: "Produto alterado",
  equipment_id: "Equipamento alterado",
};

// ── SLA Countdown ─────────────────────────────────────────────

function SlaCountdown({
  label,
  dueAt,
  breached,
}: {
  label: string;
  dueAt: string | null;
  breached: boolean;
}) {
  const [display, setDisplay] = useState("");

  useEffect(() => {
    if (!dueAt) return;

    function update() {
      const diff = new Date(dueAt!).getTime() - Date.now();
      if (diff <= 0) {
        setDisplay("Vencido");
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      setDisplay(h > 0 ? `${h}h ${m}m` : `${m}m`);
    }

    update();
    const interval = setInterval(update, 60000);
    return () => clearInterval(interval);
  }, [dueAt]);

  if (!dueAt) return null;

  return (
    <div
      className={`text-xs px-2 py-1 rounded-md font-medium ${
        breached
          ? "bg-danger/20 text-danger-400"
          : "bg-warning/20 text-warning-400"
      }`}
    >
      {label}: {display}
    </div>
  );
}

// ── Timeline entry ────────────────────────────────────────────

function TimelineEntry({ entry }: { entry: TicketHistory }) {
  const label = FIELD_LABEL[entry.field] ?? entry.field;
  const date = new Date(entry.created_at).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="flex gap-3">
      {/* Dot */}
      <div className="flex flex-col items-center">
        <div className="w-2 h-2 rounded-full bg-border mt-1.5 shrink-0" />
        <div className="w-px flex-1 bg-border mt-1" />
      </div>

      <div className="pb-4 min-w-0">
        <p className="text-sm font-medium text-slate-200">{label}</p>
        {entry.field === "status" && entry.new_value && (
          <p className="text-xs text-slate-400 mt-0.5">
            {entry.old_value
              ? `${STATUS_LABEL[entry.old_value] ?? entry.old_value} → `
              : ""}
            <StatusBadge status={entry.new_value as never} />
          </p>
        )}
        {entry.comment && (
          <p className="text-xs text-slate-400 mt-1 italic">
            "{entry.comment}"
          </p>
        )}
        <p className="text-xs text-slate-600 mt-0.5">{date}</p>
      </div>
    </div>
  );
}

// ── Attachment row ────────────────────────────────────────────

function AttachmentRow({
  attachment,
  canDelete,
  onDelete,
}: {
  attachment: Attachment;
  canDelete: boolean;
  onDelete: (id: string) => void;
}) {
  async function download() {
    const url = await getAttachmentUrl(attachment.id);
    window.open(url, "_blank");
  }

  const sizeMb = (attachment.size_bytes / 1024 / 1024).toFixed(1);

  return (
    <div className="flex items-center justify-between rounded-md bg-background-elevated px-3 py-2 text-sm">
      <button
        onClick={download}
        className="text-primary hover:underline truncate max-w-xs text-left"
      >
        {attachment.original_name}
      </button>
      <span className="flex items-center gap-3 shrink-0">
        <span className="text-slate-500 text-xs">{sizeMb} MB</span>
        {canDelete && (
          <button
            onClick={() => onDelete(attachment.id)}
            className="text-slate-500 hover:text-danger transition-colors text-xs"
            aria-label="Excluir anexo"
          >
            ✕
          </button>
        )}
      </span>
    </div>
  );
}

// ── Info row ──────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-0.5">
        {label}
      </p>
      <p className="text-sm text-slate-200">{value}</p>
    </div>
  );
}

// ── SurveyPanel ───────────────────────────────────────────────

function StarRating({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  const [hovered, setHovered] = useState(0);
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onClick={() => onChange(star)}
          onMouseEnter={() => setHovered(star)}
          onMouseLeave={() => setHovered(0)}
          className="text-2xl leading-none transition-colors"
          aria-label={`${star} estrela${star > 1 ? "s" : ""}`}
        >
          <span
            className={
              star <= (hovered || value) ? "text-yellow-400" : "text-slate-600"
            }
          >
            ★
          </span>
        </button>
      ))}
    </div>
  );
}

const RATING_LABELS: Record<number, string> = {
  1: "Péssimo",
  2: "Ruim",
  3: "Regular",
  4: "Bom",
  5: "Excelente",
};

function SurveyPanel({ ticketId }: { ticketId: string }) {
  const [survey, setSurvey] = useState<Survey | null | undefined>(undefined);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTicketSurvey(ticketId).then(setSurvey);
  }, [ticketId]);

  if (survey === undefined) return null; // loading

  async function handleSubmit() {
    if (rating === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await submitSurvey(ticketId, {
        rating,
        comment: comment.trim() || undefined,
      });
      setSurvey(result);
    } catch {
      setError("Não foi possível enviar a avaliação. Tente novamente.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl bg-background-surface border border-border p-5 space-y-4">
      <h2 className="text-sm font-semibold text-slate-300">
        Pesquisa de satisfação
      </h2>

      {survey ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-slate-400 text-sm">Sua avaliação:</span>
            <div className="flex gap-0.5">
              {[1, 2, 3, 4, 5].map((star) => (
                <span
                  key={star}
                  className={`text-xl leading-none ${
                    star <= survey.rating ? "text-yellow-400" : "text-slate-600"
                  }`}
                >
                  ★
                </span>
              ))}
            </div>
            <span className="text-xs text-slate-400">
              {RATING_LABELS[survey.rating]}
            </span>
          </div>
          {survey.comment && (
            <p className="text-sm text-slate-400 italic">"{survey.comment}"</p>
          )}
          <p className="text-xs text-slate-600">
            Enviado em{" "}
            {new Date(survey.created_at).toLocaleString("pt-BR", {
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-slate-400">
            Como você avalia o atendimento deste ticket?
          </p>
          <div className="flex items-center gap-3">
            <StarRating value={rating} onChange={setRating} />
            {rating > 0 && (
              <span className="text-sm text-slate-300">
                {RATING_LABELS[rating]}
              </span>
            )}
          </div>
          <Textarea
            placeholder="Comentário opcional…"
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          {error && <Alert variant="danger">{error}</Alert>}
          <Button
            onClick={handleSubmit}
            loading={submitting}
            disabled={rating === 0}
            size="sm"
          >
            Enviar avaliação
          </Button>
        </div>
      )}
    </div>
  );
}

// ── TicketDetailPage ──────────────────────────────────────────

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [history, setHistory] = useState<TicketHistory[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [technicians, setTechnicians] = useState<UserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [statusModal, setStatusModal] = useState(false);
  const [assignModal, setAssignModal] = useState(false);
  const [uploadModal, setUploadModal] = useState(false);

  // Status change form
  const [newStatus, setNewStatus] = useState("");
  const [statusComment, setStatusComment] = useState("");
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Assign form
  const [newAssignee, setNewAssignee] = useState("");
  const [assignLoading, setAssignLoading] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  // Upload
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const isStaff = user?.role === "admin" || user?.role === "technician";

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [t, h, a] = await Promise.all([
        getTicket(id),
        getTicketHistory(id),
        getAttachments(id),
      ]);
      setTicket(t);
      setHistory(h.items);
      setAttachments(a.items);
    } catch {
      setError("Não foi possível carregar o ticket.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Load technicians for admin assign modal
  useEffect(() => {
    if (user?.role === "admin") {
      getTechnicians()
        .then(setTechnicians)
        .catch(() => {});
    }
  }, [user?.role]);

  async function handleStatusChange() {
    if (!ticket || !newStatus) return;
    setStatusLoading(true);
    setStatusError(null);
    try {
      const updated = await updateTicketStatus(
        ticket.id,
        newStatus,
        statusComment || undefined,
      );
      setTicket(updated);
      const h = await getTicketHistory(ticket.id);
      setHistory(h.items);
      setStatusModal(false);
      setNewStatus("");
      setStatusComment("");
    } catch {
      setStatusError("Não foi possível alterar o status.");
    } finally {
      setStatusLoading(false);
    }
  }

  async function handleAssign(assigneeId: string | null) {
    if (!ticket) return;
    setAssignLoading(true);
    setAssignError(null);
    try {
      const updated = await assignTicket(ticket.id, assigneeId);
      setTicket(updated);
      setAssignModal(false);
      setNewAssignee("");
    } catch {
      setAssignError("Não foi possível atribuir o ticket.");
    } finally {
      setAssignLoading(false);
    }
  }

  async function handleUpload() {
    if (!ticket || uploadFiles.length === 0) return;
    setUploadLoading(true);
    setUploadError(null);
    try {
      await uploadAttachments(ticket.id, uploadFiles);
      const a = await getAttachments(ticket.id);
      setAttachments(a.items);
      setUploadModal(false);
      setUploadFiles([]);
    } catch {
      setUploadError(
        "Falha no upload. Verifique os arquivos e tente novamente.",
      );
    } finally {
      setUploadLoading(false);
    }
  }

  async function handleDeleteAttachment(attachmentId: string) {
    try {
      await deleteAttachment(attachmentId);
      setAttachments((prev) => prev.filter((a) => a.id !== attachmentId));
    } catch {
      // silent — attachment stays visible
    }
  }

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !ticket) {
    return <Alert variant="danger">{error ?? "Ticket não encontrado."}</Alert>;
  }

  const transitions = TRANSITIONS[ticket.status] ?? [];
  const transitionOptions = transitions.map((s) => ({
    value: s,
    label: STATUS_LABEL[s] ?? s,
  }));

  const createdDate = new Date(ticket.created_at).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const assignedTech = technicians.find((t) => t.id === ticket.assignee_id);

  return (
    <div className="space-y-6">
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate(-1)}
            className="text-xs text-slate-500 hover:text-slate-300 mb-2 flex items-center gap-1 transition-colors"
          >
            ← Voltar
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-mono text-slate-500">
              {ticket.protocol}
            </span>
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
            {(ticket.sla_response_breach || ticket.sla_resolve_breach) && (
              <span className="text-xs font-medium text-danger bg-danger/10 px-2 py-0.5 rounded-full">
                ⚠ SLA violado
              </span>
            )}
          </div>
          <h1 className="text-xl font-bold text-slate-100 mt-1">
            {ticket.title}
          </h1>
        </div>

        {/* SLA countdowns */}
        <div className="flex flex-wrap gap-2 shrink-0">
          <SlaCountdown
            label="Resposta"
            dueAt={ticket.sla_response_due_at}
            breached={ticket.sla_response_breach}
          />
          <SlaCountdown
            label="Resolução"
            dueAt={ticket.sla_resolve_due_at}
            breached={ticket.sla_resolve_breach}
          />
        </div>
      </div>

      {/* ── Body: main + sidebar ────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Main content ──────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-6">
          {/* Description */}
          <div className="rounded-xl bg-background-surface border border-border p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-3">
              Descrição
            </h2>
            <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">
              {ticket.description}
            </p>
          </div>

          {/* Attachments */}
          <div className="rounded-xl bg-background-surface border border-border p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-300">
                Anexos ({attachments.length})
              </h2>
              {isStaff && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setUploadModal(true)}
                >
                  + Adicionar
                </Button>
              )}
            </div>
            {attachments.length === 0 ? (
              <p className="text-sm text-slate-500">Nenhum anexo.</p>
            ) : (
              <div className="space-y-1.5">
                {attachments.map((a) => (
                  <AttachmentRow
                    key={a.id}
                    attachment={a}
                    canDelete={isStaff}
                    onDelete={handleDeleteAttachment}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Chat */}
          <ChatPanel
            ticketId={ticket.id}
            currentUserId={user?.id ?? ""}
            currentUserRole={user?.role}
            savedSummary={ticket.ai_conversation_summary}
          />

          {/* KB Suggestions (staff only) */}
          {isStaff && <KBSuggestionsPanel ticketId={ticket.id} />}

          {/* CSAT survey — client only, ticket resolved or closed */}
          {user?.role === "client" &&
            (ticket.status === "resolved" || ticket.status === "closed") && (
              <SurveyPanel ticketId={ticket.id} />
            )}

          {/* Timeline */}
          <div className="rounded-xl bg-background-surface border border-border p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-4">
              Histórico
            </h2>
            {history.length === 0 ? (
              <p className="text-sm text-slate-500">Sem histórico.</p>
            ) : (
              <div>
                {history.map((entry) => (
                  <TimelineEntry key={entry.id} entry={entry} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Sidebar ───────────────────────────────────────── */}
        <div className="space-y-4">
          {/* Actions */}
          {isStaff && (
            <div className="rounded-xl bg-background-surface border border-border p-4 space-y-2">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
                Ações
              </h2>
              {transitions.length > 0 && (
                <Button
                  className="w-full"
                  variant="secondary"
                  size="sm"
                  onClick={() => setStatusModal(true)}
                >
                  Alterar status
                </Button>
              )}
              <Button
                className="w-full"
                variant="secondary"
                size="sm"
                onClick={() => setAssignModal(true)}
              >
                {ticket.assignee_id ? "Reatribuir" : "Atribuir técnico"}
              </Button>
              <Button
                className="w-full"
                variant="ghost"
                size="sm"
                onClick={() => navigate(`/tickets/${ticket.id}/edit`)}
              >
                Editar ticket
              </Button>
            </div>
          )}

          {/* Ticket info */}
          <div className="rounded-xl bg-background-surface border border-border p-4 space-y-3">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Informações
            </h2>
            <InfoRow
              label="Categoria"
              value={
                {
                  hardware: "Hardware",
                  software: "Software",
                  network: "Rede",
                  access: "Acesso",
                  email: "E-mail",
                  security: "Segurança",
                  general: "Geral",
                  other: "Outro",
                }[ticket.category] ?? ticket.category
              }
            />
            <InfoRow
              label="Atribuído a"
              value={
                assignedTech?.name ??
                (ticket.assignee_id ? "Técnico" : "Não atribuído")
              }
            />
            <InfoRow label="Aberto em" value={createdDate} />
            {ticket.closed_at && (
              <InfoRow
                label="Fechado em"
                value={new Date(ticket.closed_at).toLocaleString("pt-BR")}
              />
            )}
          </div>
        </div>
      </div>

      {/* ── Status modal ────────────────────────────────────── */}
      <Modal
        open={statusModal}
        onClose={() => {
          setStatusModal(false);
          setStatusError(null);
          setNewStatus("");
          setStatusComment("");
        }}
        title="Alterar status"
      >
        <div className="space-y-4">
          {statusError && <Alert variant="danger">{statusError}</Alert>}
          <Select
            label="Novo status"
            options={transitionOptions}
            placeholder="Selecione"
            value={newStatus}
            onChange={(e) => setNewStatus(e.target.value)}
          />
          <Textarea
            label="Comentário (opcional)"
            placeholder="Motivo da alteração…"
            rows={3}
            value={statusComment}
            onChange={(e) => setStatusComment(e.target.value)}
          />
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setStatusModal(false)}
            disabled={statusLoading}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleStatusChange}
            loading={statusLoading}
            disabled={!newStatus}
          >
            Confirmar
          </Button>
        </ModalFooter>
      </Modal>

      {/* ── Assign modal ─────────────────────────────────────── */}
      <Modal
        open={assignModal}
        onClose={() => {
          setAssignModal(false);
          setAssignError(null);
        }}
        title={ticket.assignee_id ? "Reatribuir ticket" : "Atribuir técnico"}
      >
        <div className="space-y-4">
          {assignError && <Alert variant="danger">{assignError}</Alert>}
          {user?.role === "admin" ? (
            <Select
              label="Técnico"
              options={technicians.map((t) => ({
                value: t.id,
                label: t.name,
              }))}
              placeholder="Selecione um técnico"
              value={newAssignee}
              onChange={(e) => setNewAssignee(e.target.value)}
            />
          ) : (
            <p className="text-sm text-slate-300">
              Deseja assumir este ticket para você?
            </p>
          )}
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setAssignModal(false)}
            disabled={assignLoading}
          >
            Cancelar
          </Button>
          {user?.role === "admin" ? (
            <Button
              onClick={() => handleAssign(newAssignee || null)}
              loading={assignLoading}
              disabled={!newAssignee}
            >
              Atribuir
            </Button>
          ) : (
            <Button
              onClick={() => handleAssign(user!.id)}
              loading={assignLoading}
            >
              Assumir ticket
            </Button>
          )}
        </ModalFooter>
      </Modal>

      {/* ── Upload modal ─────────────────────────────────────── */}
      <Modal
        open={uploadModal}
        onClose={() => {
          setUploadModal(false);
          setUploadFiles([]);
          setUploadError(null);
        }}
        title="Adicionar anexos"
      >
        <div className="space-y-4">
          {uploadError && <Alert variant="danger">{uploadError}</Alert>}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) setUploadFiles(Array.from(e.target.files));
            }}
          />
          <Button
            variant="secondary"
            className="w-full"
            onClick={() => fileInputRef.current?.click()}
          >
            Selecionar arquivos
          </Button>
          {uploadFiles.length > 0 && (
            <ul className="space-y-1">
              {uploadFiles.map((f, i) => (
                <li key={i} className="text-sm text-slate-300">
                  {f.name}
                </li>
              ))}
            </ul>
          )}
        </div>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setUploadModal(false)}
            disabled={uploadLoading}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleUpload}
            loading={uploadLoading}
            disabled={uploadFiles.length === 0}
          >
            Enviar
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
