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
  TagBadge,
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
  createTicketNote,
  deleteTicketNote,
  getTicket,
  getTicketHistory,
  listTicketNotes,
  resolveTicket,
  updateClientObservation,
  updateTicket,
  updateTicketStatus,
  type Ticket,
  type TicketHistory,
  type TicketNote,
} from "../../services/ticketService";
import {
  getTicketSurvey,
  submitSurvey,
  type Survey,
} from "../../services/surveyService";
import { getTechnicians, type UserSummary } from "../../services/userService";
import { getTags, setTicketTags, type Tag } from "../../services/tagService";
import { TICKET_TRANSITIONS } from "../../lib/ticketConstants";

// ── Constants ─────────────────────────────────────────────────

const STATUS_LABEL: Record<string, string> = {
  open: "Aberto",
  in_progress: "Em andamento",
  awaiting_client: "Aguardando cliente",
  awaiting_technical: "Aguardando técnico",
  resolved: "Resolvido",
  closed: "Fechado",
  cancelled: "Cancelado",
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
  technician_notes: "Notas internas atualizadas",
};

const CATEGORY_LABEL: Record<string, string> = {
  hardware: "Hardware",
  software: "Software",
  network: "Rede",
  access: "Acesso",
  email: "E-mail",
  security: "Segurança",
  general: "Geral",
  other: "Outro",
};

// ── SVG Icons ─────────────────────────────────────────────────

const IC = {
  ArrowLeft: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
    </svg>
  ),
  Check: (cls = "w-4 h-4") => (
    <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  ),
  User: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  ),
  Calendar: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  ),
  Folder: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7a2 2 0 012-2h3.586a1 1 0 01.707.293l1.414 1.414A1 1 0 0011.414 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
    </svg>
  ),
  Clip: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
    </svg>
  ),
  Clock: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  Edit: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  ),
  Lock: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
    </svg>
  ),
  Trash: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  ),
  Refresh: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  ),
  UserPlus: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
    </svg>
  ),
  Download: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
  ),
  X: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  ),
  Alert: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  Tag: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
    </svg>
  ),
  Text: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h7" />
    </svg>
  ),
  Activity: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  Star: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
    </svg>
  ),
  Plus: (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
    </svg>
  ),
};

// ── SLA Countdown ─────────────────────────────────────────────

function SlaChip({
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
      if (diff <= 0) { setDisplay("Vencido"); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      setDisplay(h > 0 ? `${h}h ${m}m` : `${m}m`);
    }
    update();
    const t = setInterval(update, 60000);
    return () => clearInterval(t);
  }, [dueAt]);

  if (!dueAt) return null;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold ${
        breached
          ? "bg-red-500/15 text-red-700 dark:text-red-400 ring-1 ring-inset ring-red-500/25"
          : "bg-amber-500/15 text-amber-700 dark:text-amber-400 ring-1 ring-inset ring-amber-500/25"
      }`}
    >
      {IC.Clock}
      {label}: <span>{display}</span>
    </span>
  );
}

// ── Activity entry ────────────────────────────────────────────

function ActivityEntry({ entry }: { entry: TicketHistory }) {
  const label = FIELD_LABEL[entry.field] ?? entry.field;
  const diff = Date.now() - new Date(entry.created_at).getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  const relTime =
    days > 0 ? `${days}d atrás` : hours > 0 ? `${hours}h atrás` : mins > 0 ? `${mins}m atrás` : "agora";

  const dotColor =
    entry.field === "created"
      ? "bg-sky-500"
      : entry.field === "status"
      ? "bg-violet-500"
      : entry.field === "assignee_id"
      ? "bg-emerald-500"
      : "bg-slate-500";

  return (
    <div className="flex gap-3 group">
      <div className="flex flex-col items-center pt-1 shrink-0">
        <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
        <span className="w-px flex-1 bg-border/40 mt-1.5" />
      </div>
      <div className="pb-4 min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-medium text-slate-200">{label}</p>
          <time className="text-[11px] text-slate-500 shrink-0">{relTime}</time>
        </div>
        {entry.field === "status" && entry.new_value && (
          <div className="flex items-center gap-2 mt-1">
            {entry.old_value && (
              <>
                <StatusBadge status={entry.old_value as never} />
                <svg className="w-3 h-3 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </>
            )}
            <StatusBadge status={entry.new_value as never} />
          </div>
        )}
        {entry.comment && (
          <p className="mt-1.5 text-xs text-slate-400 italic bg-background-elevated/60 rounded-lg px-3 py-2 border border-border/30">
            "{entry.comment}"
          </p>
        )}
      </div>
    </div>
  );
}

// ── Attachment item ───────────────────────────────────────────

function AttachmentItem({
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
  const ext = attachment.original_name.split(".").pop()?.toUpperCase() ?? "FILE";
  const sizeMb = (attachment.size_bytes / 1024 / 1024).toFixed(1);

  return (
    <div className="group flex items-center gap-3 rounded-lg border border-border/50 bg-background-elevated/40 px-3 py-2.5 hover:border-primary/30 hover:bg-primary/5 transition-all">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-[10px] font-bold text-primary">
        {ext.slice(0, 4)}
      </div>
      <div className="min-w-0 flex-1">
        <button
          onClick={download}
          className="block w-full truncate text-left text-sm font-medium text-slate-200 hover:text-primary transition-colors cursor-pointer"
        >
          {attachment.original_name}
        </button>
        <p className="text-xs text-slate-500">{sizeMb} MB</p>
      </div>
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={download}
          className="p-1.5 rounded-md text-slate-500 hover:text-primary hover:bg-primary/10 transition-colors cursor-pointer"
          title="Baixar"
        >
          {IC.Download}
        </button>
        {canDelete && (
          <button
            onClick={() => onDelete(attachment.id)}
            className="p-1.5 rounded-md text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
            title="Excluir"
          >
            {IC.X}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Sidebar prop row ──────────────────────────────────────────

function PropRow({ icon, label, children }: { icon: JSX.Element; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border/30 last:border-0">
      <span className="mt-0.5 shrink-0 text-slate-500">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</p>
        <div className="text-sm font-medium text-slate-200">{children}</div>
      </div>
    </div>
  );
}

// ── Section header ────────────────────────────────────────────

function SectionHeader({ icon, title, action }: { icon: JSX.Element; title: string; action?: JSX.Element }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
        <span className="text-slate-500">{icon}</span>
        {title}
      </h2>
      {action}
    </div>
  );
}

// ── Collapsible sidebar section ──────────────────────────────

function SidebarSection({
  title,
  icon,
  action,
  accent,
  defaultOpen = true,
  children,
}: {
  title: string;
  icon?: JSX.Element;
  action?: JSX.Element;
  accent?: "amber";
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const isAmber = accent === "amber";
  return (
    <div className={`rounded-xl border ${isAmber ? "border-amber-700/25 bg-amber-950/15" : "border-border/40 bg-background-surface"}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex w-full items-center justify-between px-4 py-3 cursor-pointer transition-colors ${isAmber ? "hover:bg-amber-900/10" : "hover:bg-background-elevated/40"} rounded-xl`}
      >
        <span className={`text-[10px] font-bold uppercase tracking-widest flex items-center gap-1.5 ${isAmber ? "text-amber-500/80" : "text-slate-500"}`}>
          {icon}{title}
        </span>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {action}
          <svg
            className={`w-3 h-3 shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""} ${isAmber ? "text-amber-600/60" : "text-slate-600"}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

// ── Sidebar action button ─────────────────────────────────────

function SidebarAction({
  icon,
  label,
  onClick,
  variant = "default",
}: {
  icon: JSX.Element;
  label: string;
  onClick: () => void;
  variant?: "primary" | "default" | "ghost";
}) {
  const cls = {
    primary:
      "bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-600",
    default:
      "bg-background-elevated hover:bg-background-elevated/80 text-slate-200 border-border/50 hover:border-border",
    ghost:
      "bg-transparent hover:bg-background-elevated text-slate-400 hover:text-slate-200 border-border/30",
  }[variant];

  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold transition-all cursor-pointer ${cls}`}
    >
      {icon}
      {label}
    </button>
  );
}

// ── CSAT Survey ───────────────────────────────────────────────

function ScoreRating({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const [hovered, setHovered] = useState(0);
  return (
    <div className="flex flex-wrap gap-1.5">
      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => {
        const active = n <= (hovered || value);
        return (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            onMouseEnter={() => setHovered(n)}
            onMouseLeave={() => setHovered(0)}
            aria-label={`Nota ${n}`}
            className={`h-9 w-9 rounded-lg text-sm font-bold transition-all border cursor-pointer ${
              active
                ? "bg-yellow-400 border-yellow-400 text-slate-900 shadow-sm"
                : "border-border/60 text-slate-400 hover:border-yellow-400/60 hover:text-yellow-400"
            }`}
          >
            {n}
          </button>
        );
      })}
    </div>
  );
}

const RATING_LABELS: Record<number, string> = {
  1: "Péssimo", 2: "Muito ruim", 3: "Ruim", 4: "Abaixo do esperado", 5: "Regular",
  6: "Satisfatório", 7: "Bom", 8: "Muito bom", 9: "Ótimo", 10: "Excelente",
};

function SurveyPanel({ ticketId }: { ticketId: string }) {
  const [survey, setSurvey] = useState<Survey | null | undefined>(undefined);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { getTicketSurvey(ticketId).then(setSurvey); }, [ticketId]);
  if (survey === undefined) return null;

  async function handleSubmit() {
    if (rating === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      setSurvey(await submitSurvey(ticketId, { rating, comment: comment.trim() || undefined }));
    } catch {
      setError("Não foi possível enviar a avaliação.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl border border-border/50 bg-background-surface">
      <div className="flex items-center gap-2 border-b border-border/40 px-5 py-3.5">
        <span className="text-yellow-400">{IC.Star}</span>
        <h2 className="text-sm font-semibold text-slate-200">Pesquisa de satisfação</h2>
      </div>
      <div className="p-5">
        {survey ? (
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-3xl font-extrabold text-yellow-400">
                {survey.rating}<span className="text-base font-normal text-slate-500">/10</span>
              </span>
              <span className="text-sm text-slate-400">{RATING_LABELS[survey.rating]}</span>
            </div>
            {survey.comment && (
              <p className="text-sm italic text-slate-400 bg-background-elevated/60 rounded-lg px-3 py-2">
                "{survey.comment}"
              </p>
            )}
            <p className="text-xs text-slate-600">
              Enviado em {new Date(survey.created_at).toLocaleString("pt-BR")}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-slate-400">Como você avalia o atendimento?</p>
            <div className="space-y-2">
              <ScoreRating value={rating} onChange={setRating} />
              {rating > 0 && (
                <p className="text-sm font-semibold text-yellow-400">{RATING_LABELS[rating]}</p>
              )}
            </div>
            <Textarea placeholder="Comentário opcional…" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
            {error && <Alert variant="danger">{error}</Alert>}
            <Button onClick={handleSubmit} loading={submitting} disabled={rating === 0} size="sm">
              Enviar avaliação
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────

type Tab = "conversa" | "kb" | "detalhes" | "historico" | "anexos";

function TabBar({ active, setActive, counts, showKb }: { active: Tab; setActive: (t: Tab) => void; counts: Partial<Record<Tab, number>>; showKb: boolean }) {
  const tabs: { id: Tab; label: string }[] = [
    { id: "conversa",  label: "Conversa" },
    { id: "detalhes",  label: "Detalhes" },
    ...(showKb ? [{ id: "kb" as Tab, label: "Base de Conhecimento" }] : []),
    { id: "historico", label: "Atividade" },
    { id: "anexos",    label: "Anexos" },
  ];
  return (
    <div className="flex gap-0.5 rounded-xl bg-background-elevated/50 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => setActive(tab.id)}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold transition-all cursor-pointer ${
            active === tab.id
              ? "bg-background-surface text-slate-100 shadow-sm"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {tab.label}
          {counts[tab.id] !== undefined && counts[tab.id]! > 0 && (
            <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold leading-none ${
              active === tab.id ? "bg-primary/20 text-primary" : "bg-background-elevated text-slate-500"
            }`}>
              {counts[tab.id]}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("conversa");

  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [history, setHistory] = useState<TicketHistory[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [technicians, setTechnicians] = useState<UserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusModal, setStatusModal] = useState(false);
  const [assignModal, setAssignModal] = useState(false);
  const [uploadModal, setUploadModal] = useState(false);
  const [resolveModal, setResolveModal] = useState(false);

  const [resolveNote, setResolveNote] = useState("");
  const [resolveLoading, setResolveLoading] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const [newStatus, setNewStatus] = useState("");
  const [statusComment, setStatusComment] = useState("");
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [newAssignee, setNewAssignee] = useState("");
  const [assignLoading, setAssignLoading] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [ticketNotes, setTicketNotes] = useState<TicketNote[]>([]);
  const [showAddNote, setShowAddNote] = useState(false);
  const [viewNote, setViewNote] = useState<TicketNote | null>(null);
  const [newNoteContent, setNewNoteContent] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteDeleting, setNoteDeleting] = useState<string | null>(null);

  const [obsEdit, setObsEdit] = useState(false);
  const [obsValue, setObsValue] = useState("");
  const [obsSaving, setObsSaving] = useState(false);

  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [tagsEdit, setTagsEdit] = useState(false);
  const [selectedTagIds, setSelectedTagIds] = useState<Set<string>>(new Set());
  const [tagsSaving, setTagsSaving] = useState(false);

  const isStaff = user?.role === "admin" || user?.role === "technician";
  const isClosed = ticket?.status === "resolved" || ticket?.status === "closed" || ticket?.status === "cancelled";

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [t, h, a] = await Promise.all([getTicket(id), getTicketHistory(id), getAttachments(id)]);
      setTicket(t);
      setObsValue(t.client_observation ?? "");
      setHistory(h.items);
      setAttachments(a.items);
      listTicketNotes(id).then(setTicketNotes).catch(() => {});
    } catch {
      setError("Não foi possível carregar o ticket.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (user?.role === "admin") getTechnicians().then(setTechnicians).catch(() => {});
  }, [user?.role]);

  useEffect(() => {
    if (isStaff) getTags().then(setAllTags).catch(() => {});
  }, [isStaff]);

  async function handleStatusChange() {
    if (!ticket || !newStatus) return;
    setStatusLoading(true); setStatusError(null);
    try {
      const updated = await updateTicketStatus(ticket.id, newStatus, statusComment || undefined);
      setTicket(updated);
      setHistory((await getTicketHistory(ticket.id)).items);
      setStatusModal(false); setNewStatus(""); setStatusComment("");
    } catch { setStatusError("Não foi possível alterar o status."); }
    finally { setStatusLoading(false); }
  }

  async function handleResolve() {
    if (!ticket || !resolveNote.trim()) return;
    setResolveLoading(true); setResolveError(null);
    try {
      const updated = await resolveTicket(ticket.id, resolveNote.trim());
      setTicket(updated);
      setHistory((await getTicketHistory(ticket.id)).items);
      setResolveModal(false); setResolveNote("");
    } catch { setResolveError("Não foi possível concluir o ticket."); }
    finally { setResolveLoading(false); }
  }

  async function handleAssign(assigneeId: string | null) {
    if (!ticket) return;
    setAssignLoading(true); setAssignError(null);
    try {
      setTicket(await assignTicket(ticket.id, assigneeId));
      setAssignModal(false); setNewAssignee("");
    } catch { setAssignError("Não foi possível atribuir o ticket."); }
    finally { setAssignLoading(false); }
  }

  async function handleUpload() {
    if (!ticket || uploadFiles.length === 0) return;
    setUploadLoading(true); setUploadError(null);
    try {
      await uploadAttachments(ticket.id, uploadFiles);
      setAttachments((await getAttachments(ticket.id)).items);
      setUploadModal(false); setUploadFiles([]);
    } catch { setUploadError("Falha no upload. Verifique os arquivos e tente novamente."); }
    finally { setUploadLoading(false); }
  }

  async function handleAddNote() {
    if (!ticket || !newNoteContent.trim()) return;
    setNoteSaving(true);
    try {
      const note = await createTicketNote(ticket.id, newNoteContent.trim());
      setTicketNotes((p) => [note, ...p]);
      setNewNoteContent("");
      setShowAddNote(false);
    } finally { setNoteSaving(false); }
  }

  async function handleDeleteNote(noteId: string) {
    if (!ticket || !confirm("Deletar esta nota?")) return;
    setNoteDeleting(noteId);
    try {
      await deleteTicketNote(ticket.id, noteId);
      setTicketNotes((p) => p.filter((n) => n.id !== noteId));
    } finally { setNoteDeleting(null); }
  }

  async function handleSaveObs() {
    if (!ticket) return;
    setObsSaving(true);
    try {
      setTicket(await updateClientObservation(ticket.id, obsValue || null));
      setObsEdit(false);
    } finally { setObsSaving(false); }
  }

  function openTagsEdit() {
    setSelectedTagIds(new Set(ticket?.tags.map((t) => t.id) ?? []));
    setTagsEdit(true);
  }

  async function handleSaveTags() {
    if (!ticket) return;
    setTagsSaving(true);
    try {
      setTicket({ ...ticket, tags: await setTicketTags(ticket.id, [...selectedTagIds]) });
      setTagsEdit(false);
    } finally { setTagsSaving(false); }
  }

  async function handleDeleteAttachment(attachmentId: string) {
    try {
      await deleteAttachment(attachmentId);
      setAttachments((prev) => prev.filter((a) => a.id !== attachmentId));
    } catch { /* silent */ }
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

  const transitions = TICKET_TRANSITIONS[ticket.status] ?? [];
  const transitionOptions = transitions.map((s) => ({ value: s, label: STATUS_LABEL[s] ?? s }));
  const assignedTech = ticket.assignee_name ?? (ticket.assignee_id ? "Técnico" : null);
  const slaBreach = ticket.sla_response_breach || ticket.sla_resolve_breach;

  const visibleHistory = user?.role === "client"
    ? history.filter((e) => ["created", "status"].includes(e.field))
    : history;

  return (
    <div className="flex flex-col h-full gap-4">
      {/* ── Page Header ──────────────────────────────────────── */}
      <div className="shrink-0 flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        {/* Breadcrumb + title */}
        <div className="min-w-0">
          <button
            onClick={() => navigate(-1)}
            className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-primary transition-colors cursor-pointer"
          >
            {IC.ArrowLeft}
            <span>Tickets</span>
            <span className="text-slate-600">/</span>
            <span className="font-mono text-slate-500">{ticket.protocol}</span>
          </button>
          <h1 className="text-xl font-extrabold leading-tight text-slate-100">{ticket.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={ticket.status} />
            <PriorityBadge priority={ticket.priority} />
            {ticket.tags.map((tag) => (
              <TagBadge key={tag.id} name={tag.name} color={tag.color} />
            ))}
            {slaBreach && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 px-2.5 py-0.5 text-xs font-semibold text-red-700 dark:text-red-400 ring-1 ring-inset ring-red-500/25">
                {IC.Alert}
                SLA violado
              </span>
            )}
            <SlaChip label="Resposta" dueAt={ticket.sla_response_due_at} breached={ticket.sla_response_breach} />
            <SlaChip label="Resolução" dueAt={ticket.sla_resolve_due_at} breached={ticket.sla_resolve_breach} />
          </div>
        </div>

        {/* Quick resolve button in header */}
        {isStaff && !isClosed && (
          <button
            onClick={() => setResolveModal(true)}
            className="flex shrink-0 items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-emerald-500 transition-colors cursor-pointer"
          >
            {IC.Check("w-4 h-4")}
            Concluir ticket
          </button>
        )}
      </div>

      {/* ── Body ─────────────────────────────────────────────── */}
      {/* TabBar acima do grid — ambas as colunas começam na mesma altura */}
      <TabBar
        active={activeTab}
        setActive={setActiveTab}
        counts={{ historico: visibleHistory.length, anexos: attachments.length }}
        showKb={isStaff}
      />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_256px] gap-5 flex-1 min-h-0">
        {/* ── Main column ───────────────────────────────────── */}
        <div className="flex flex-col min-h-0 min-w-0">
          <div className="flex-1 min-h-0 overflow-y-auto">

          {/* ── TAB: Conversa ───────────────────────────────── */}
          {activeTab === "conversa" && (
            <div className="flex flex-col gap-4 h-full">
              {/* Client observation */}
              {(ticket.client_observation || user?.role === "client") && (
                <div className="shrink-0 rounded-xl border border-border/40 bg-background-surface">
                  <div className="flex items-center justify-between border-b border-border/40 px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500">{IC.User}</span>
                      <h2 className="text-sm font-semibold text-slate-200">Observações do solicitante</h2>
                    </div>
                    {user?.role === "client" && !isClosed && !obsEdit && (
                      <button
                        onClick={() => setObsEdit(true)}
                        className="flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition-colors cursor-pointer"
                      >
                        {IC.Edit}
                        {ticket.client_observation ? "Editar" : "Adicionar"}
                      </button>
                    )}
                  </div>
                  <div className="px-5 py-4">
                    {obsEdit ? (
                      <div className="space-y-3">
                        <Textarea rows={4} placeholder="Informações adicionais…" value={obsValue} onChange={(e) => setObsValue(e.target.value)} />
                        <div className="flex justify-end gap-2">
                          <Button variant="secondary" size="sm" onClick={() => { setObsEdit(false); setObsValue(ticket.client_observation ?? ""); }} disabled={obsSaving}>Cancelar</Button>
                          <Button size="sm" onClick={handleSaveObs} loading={obsSaving}>Salvar</Button>
                        </div>
                      </div>
                    ) : ticket.client_observation ? (
                      <p className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap">{ticket.client_observation}</p>
                    ) : (
                      <p className="text-xs italic text-slate-500">Nenhuma observação registrada.</p>
                    )}
                  </div>
                </div>
              )}

              {/* Resolution note */}
              {ticket.resolution_note && (
                <div className="shrink-0 rounded-xl border border-emerald-700/30 bg-emerald-950/20">
                  <div className="flex items-center gap-2 border-b border-emerald-700/20 px-5 py-3.5">
                    <span className="text-emerald-400">{IC.Check("w-4 h-4")}</span>
                    <h2 className="text-sm font-semibold text-emerald-400">Resolução</h2>
                  </div>
                  <div className="px-5 py-4">
                    <p className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap">{ticket.resolution_note}</p>
                  </div>
                </div>
              )}

              {/* Chat — cresce para preencher o espaço disponível */}
              <div className="flex-1 min-h-0">
                <ChatPanel
                  ticketId={ticket.id}
                  currentUserId={user?.id ?? ""}
                  currentUserRole={user?.role}
                  savedSummary={ticket.ai_conversation_summary}
                  locked={!!isClosed}
                  onStatusChange={(s) =>
                    setTicket((prev) => prev ? { ...prev, status: s as typeof prev.status } : prev)
                  }
                />
              </div>

              {/* CSAT */}
              {user?.role === "client" && (ticket.status === "resolved" || ticket.status === "closed") && (
                <div className="shrink-0"><SurveyPanel ticketId={ticket.id} /></div>
              )}
            </div>
          )}

          {/* ── TAB: Base de Conhecimento ───────────────────── */}
          {activeTab === "kb" && (
            <KBSuggestionsPanel ticketId={ticket.id} />
          )}

          {/* ── TAB: Detalhes ────────────────────────────────── */}
          {activeTab === "detalhes" && (
            <div className="rounded-xl border border-border/40 bg-background-surface">
              <div className="border-b border-border/40 px-5 py-3.5">
                <h2 className="text-sm font-semibold text-slate-200">Descrição completa</h2>
              </div>
              <div className="px-5 py-4">
                <p className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap">{ticket.description}</p>
              </div>
            </div>
          )}

          {/* ── TAB: Atividade ───────────────────────────────── */}
          {activeTab === "historico" && (
            <div className="rounded-xl border border-border/40 bg-background-surface">
              <div className="flex items-center gap-2 border-b border-border/40 px-5 py-3.5">
                <span className="text-slate-500">{IC.Activity}</span>
                <h2 className="text-sm font-semibold text-slate-200">Histórico de atividades</h2>
              </div>
              <div className="px-5 py-5">
                {visibleHistory.length === 0 ? (
                  <div className="py-10 text-center">
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-background-elevated text-slate-600">
                      {IC.Activity}
                    </div>
                    <p className="text-sm text-slate-500">Sem histórico de atividades.</p>
                  </div>
                ) : (
                  <div>
                    {visibleHistory.map((entry) => (
                      <ActivityEntry key={entry.id} entry={entry} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── TAB: Anexos ──────────────────────────────────── */}
          {activeTab === "anexos" && (
            <div className="rounded-xl border border-border/40 bg-background-surface">
              <div className="flex items-center justify-between border-b border-border/40 px-5 py-3.5">
                <div className="flex items-center gap-2">
                  <span className="text-slate-500">{IC.Clip}</span>
                  <h2 className="text-sm font-semibold text-slate-200">Anexos ({attachments.length})</h2>
                </div>
                {!isClosed && (
                  <button
                    onClick={() => setUploadModal(true)}
                    className="flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition-colors cursor-pointer"
                  >
                    {IC.Plus}
                    Adicionar
                  </button>
                )}
              </div>
              <div className="p-5">
                {attachments.length === 0 ? (
                  <div className="py-10 text-center">
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-background-elevated text-slate-600">
                      {IC.Clip}
                    </div>
                    <p className="text-sm text-slate-500">Nenhum anexo adicionado.</p>
                    {!isClosed && (
                      <button
                        onClick={() => setUploadModal(true)}
                        className="mt-3 text-xs font-medium text-primary hover:text-primary/80 cursor-pointer transition-colors"
                      >
                        + Adicionar arquivo
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {attachments.map((a) => (
                      <AttachmentItem key={a.id} attachment={a} canDelete={isStaff} onDelete={handleDeleteAttachment} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          </div>{/* flex-1 tab wrapper */}
        </div>

        {/* ── Sidebar ───────────────────────────────────────── */}
        <div className="space-y-4 overflow-y-auto min-h-0 pr-1">
          {/* Actions (staff only) */}
          {isStaff && (
            <SidebarSection title="Ações">
              <div className="space-y-2">
                {!isClosed && (
                  <SidebarAction icon={IC.Check("w-4 h-4")} label="Concluir ticket" onClick={() => setResolveModal(true)} variant="primary" />
                )}
                {transitions.length > 0 && (
                  <SidebarAction icon={IC.Refresh} label="Alterar status" onClick={() => setStatusModal(true)} variant="default" />
                )}
                <SidebarAction icon={IC.UserPlus} label={ticket.assignee_id ? "Reatribuir" : "Atribuir técnico"} onClick={() => setAssignModal(true)} variant="default" />
                {user?.role === "admin" && (
                  <SidebarAction icon={IC.Edit} label="Editar ticket" onClick={() => navigate(`/tickets/${ticket.id}/edit`)} variant="ghost" />
                )}
              </div>
            </SidebarSection>
          )}

          {/* Properties */}
          <SidebarSection title="Propriedades">
            <PropRow icon={IC.Activity} label="Status">
              <StatusBadge status={ticket.status} />
            </PropRow>
            <PropRow icon={IC.Alert} label="Prioridade">
              <PriorityBadge priority={ticket.priority} />
            </PropRow>
            <PropRow icon={IC.User} label="Responsável">
              {assignedTech ? (
                <span className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/20 text-[10px] font-bold text-primary">
                    {assignedTech.charAt(0).toUpperCase()}
                  </span>
                  {assignedTech}
                </span>
              ) : (
                <span className="text-slate-500 font-normal italic text-xs">Não atribuído</span>
              )}
            </PropRow>
            <PropRow icon={IC.Folder} label="Categoria">
              {CATEGORY_LABEL[ticket.category] ?? ticket.category}
            </PropRow>
            <PropRow icon={IC.Calendar} label="Criado em">
              {new Date(ticket.created_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
            </PropRow>
            {ticket.closed_at && (
              <PropRow icon={IC.Check("w-4 h-4")} label="Fechado em">
                {new Date(ticket.closed_at).toLocaleString("pt-BR")}
              </PropRow>
            )}
          </SidebarSection>

          {/* SLA status */}
          {(ticket.sla_response_due_at || ticket.sla_resolve_due_at) && (
            <SidebarSection title="SLA" defaultOpen={slaBreach}>
              <div className="space-y-2">
                {ticket.sla_response_due_at && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Resposta</span>
                    <SlaChip label="" dueAt={ticket.sla_response_due_at} breached={ticket.sla_response_breach} />
                  </div>
                )}
                {ticket.sla_resolve_due_at && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Resolução</span>
                    <SlaChip label="" dueAt={ticket.sla_resolve_due_at} breached={ticket.sla_resolve_breach} />
                  </div>
                )}
              </div>
            </SidebarSection>
          )}

          {/* Tags */}
          {(ticket.tags.length > 0 || isStaff) && (
            <SidebarSection
              title="Etiquetas"
              icon={IC.Tag}
              action={
                isStaff && !tagsEdit ? (
                  <button onClick={openTagsEdit} className="flex items-center gap-1 text-[10px] font-semibold text-primary hover:text-primary/80 cursor-pointer transition-colors">
                    {IC.Edit}
                    {ticket.tags.length > 0 ? "Editar" : "Adicionar"}
                  </button>
                ) : undefined
              }
            >
              {tagsEdit ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap gap-1.5">
                    {allTags.map((tag) => {
                      const sel = selectedTagIds.has(tag.id);
                      return (
                        <button
                          key={tag.id}
                          type="button"
                          onClick={() => setSelectedTagIds((prev) => { const n = new Set(prev); if (n.has(tag.id)) n.delete(tag.id); else n.add(tag.id); return n; })}
                          className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition-all cursor-pointer ${sel ? "opacity-100" : "opacity-35 hover:opacity-60"}`}
                          style={{ backgroundColor: `${tag.color}22`, borderColor: `${tag.color}55`, color: tag.color }}
                        >
                          {tag.name}
                        </button>
                      );
                    })}
                    {allTags.length === 0 && <p className="text-xs text-slate-500">Nenhuma etiqueta cadastrada.</p>}
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="secondary" size="sm" onClick={() => setTagsEdit(false)} disabled={tagsSaving}>Cancelar</Button>
                    <Button size="sm" onClick={handleSaveTags} loading={tagsSaving}>Salvar</Button>
                  </div>
                </div>
              ) : ticket.tags.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {ticket.tags.map((tag) => <TagBadge key={tag.id} name={tag.name} color={tag.color} />)}
                </div>
              ) : (
                <p className="text-xs italic text-slate-500">Nenhuma etiqueta.</p>
              )}
            </SidebarSection>
          )}

          {/* Internal notes */}
          {isStaff && (
            <SidebarSection
              title="Notas internas"
              icon={IC.Lock}
              accent="amber"
              action={
                <button
                  onClick={() => setShowAddNote(true)}
                  className="flex items-center gap-1 text-[10px] font-semibold text-amber-500/70 hover:text-amber-400 cursor-pointer transition-colors"
                >
                  {IC.Edit}
                  Adicionar
                </button>
              }
            >
              {ticketNotes.length === 0 ? (
                <p className="text-xs italic text-amber-700/50">Nenhuma nota registrada.</p>
              ) : (
                <ul className="space-y-2">
                  {ticketNotes.map((n) => (
                    <li
                      key={n.id}
                      className="group relative rounded-lg border border-amber-700/20 bg-amber-950/20 p-3 cursor-pointer hover:border-amber-600/40 transition-colors"
                      onClick={() => setViewNote(n)}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-[10px] font-semibold text-amber-500/70 truncate">{n.author_name}</span>
                        <div className="flex items-center gap-1 shrink-0">
                          <span className="text-[10px] text-amber-700/50">
                            {new Date(n.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" })}
                          </span>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDeleteNote(n.id); }}
                            disabled={noteDeleting === n.id}
                            className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-amber-700/60 hover:text-red-400 transition-all cursor-pointer"
                          >
                            {noteDeleting === n.id ? <Spinner size="sm" /> : IC.Trash}
                          </button>
                        </div>
                      </div>
                      <p className="text-xs text-amber-200/60 line-clamp-2 whitespace-pre-wrap">{n.content}</p>
                    </li>
                  ))}
                </ul>
              )}
            </SidebarSection>
          )}
        </div>
      </div>

      {/* ── Modals ───────────────────────────────────────────── */}

      {/* Add note */}
      <Modal open={showAddNote} onClose={() => { setShowAddNote(false); setNewNoteContent(""); }} title="Nova nota interna">
        <div className="space-y-4">
          <Textarea
            rows={5}
            placeholder="Observações internas, diagnósticos, próximos passos…"
            value={newNoteContent}
            onChange={(e) => setNewNoteContent(e.target.value)}
          />
          <ModalFooter>
            <Button variant="secondary" onClick={() => { setShowAddNote(false); setNewNoteContent(""); }}>Cancelar</Button>
            <Button onClick={handleAddNote} loading={noteSaving} disabled={!newNoteContent.trim()}>Salvar nota</Button>
          </ModalFooter>
        </div>
      </Modal>

      {/* View note */}
      {viewNote && (
        <Modal open onClose={() => setViewNote(null)} title="Nota interna" size="lg">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-amber-500/70">
              <span className="font-semibold">{viewNote.author_name}</span>
              <span>{new Date(viewNote.created_at).toLocaleString("pt-BR")}</span>
            </div>
            <p className="text-sm text-amber-200/80 whitespace-pre-wrap leading-relaxed min-h-[80px]">{viewNote.content}</p>
            <ModalFooter>
              <Button
                variant="outline"
                size="sm"
                className="text-red-500 hover:bg-red-900/20"
                loading={noteDeleting === viewNote.id}
                onClick={() => { handleDeleteNote(viewNote.id); setViewNote(null); }}
              >
                Deletar
              </Button>
              <Button onClick={() => setViewNote(null)}>Fechar</Button>
            </ModalFooter>
          </div>
        </Modal>
      )}

      <Modal
        open={statusModal}
        onClose={() => { setStatusModal(false); setStatusError(null); setNewStatus(""); setStatusComment(""); }}
        title="Alterar status"
      >
        <div className="space-y-4">
          {statusError && <Alert variant="danger">{statusError}</Alert>}
          <Select label="Novo status" options={transitionOptions} placeholder="Selecione" value={newStatus} onChange={(e) => setNewStatus(e.target.value)} />
          <Textarea label="Comentário (opcional)" placeholder="Motivo da alteração…" rows={3} value={statusComment} onChange={(e) => setStatusComment(e.target.value)} />
        </div>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setStatusModal(false)} disabled={statusLoading}>Cancelar</Button>
          <Button onClick={handleStatusChange} loading={statusLoading} disabled={!newStatus}>Confirmar</Button>
        </ModalFooter>
      </Modal>

      <Modal
        open={assignModal}
        onClose={() => { setAssignModal(false); setAssignError(null); }}
        title={ticket.assignee_id ? "Reatribuir ticket" : "Atribuir técnico"}
      >
        <div className="space-y-4">
          {assignError && <Alert variant="danger">{assignError}</Alert>}
          {user?.role === "admin" ? (
            <Select label="Técnico" options={technicians.map((t) => ({ value: t.id, label: t.name }))} placeholder="Selecione um técnico" value={newAssignee} onChange={(e) => setNewAssignee(e.target.value)} />
          ) : (
            <p className="text-sm text-slate-300">Deseja assumir este ticket para você?</p>
          )}
        </div>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setAssignModal(false)} disabled={assignLoading}>Cancelar</Button>
          {user?.role === "admin" ? (
            <Button onClick={() => handleAssign(newAssignee || null)} loading={assignLoading} disabled={!newAssignee}>Atribuir</Button>
          ) : (
            <Button onClick={() => handleAssign(user!.id)} loading={assignLoading}>Assumir ticket</Button>
          )}
        </ModalFooter>
      </Modal>

      <Modal
        open={uploadModal}
        onClose={() => { setUploadModal(false); setUploadFiles([]); setUploadError(null); }}
        title="Adicionar anexos"
      >
        <div className="space-y-4">
          {uploadError && <Alert variant="danger">{uploadError}</Alert>}
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(e) => { if (e.target.files) setUploadFiles(Array.from(e.target.files)); }} />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border/60 bg-background-elevated/30 py-10 text-sm text-slate-400 hover:border-primary/40 hover:bg-primary/5 hover:text-primary transition-all cursor-pointer"
          >
            {IC.Clip}
            <span>Clique para selecionar arquivos</span>
          </button>
          {uploadFiles.length > 0 && (
            <ul className="space-y-1">
              {uploadFiles.map((f, i) => (
                <li key={i} className="flex items-center gap-2 rounded-lg bg-background-elevated px-3 py-2 text-sm text-slate-300">
                  <span className="text-slate-500">{IC.Clip}</span>
                  {f.name}
                </li>
              ))}
            </ul>
          )}
        </div>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setUploadModal(false)} disabled={uploadLoading}>Cancelar</Button>
          <Button onClick={handleUpload} loading={uploadLoading} disabled={uploadFiles.length === 0}>Enviar</Button>
        </ModalFooter>
      </Modal>

      <Modal
        open={resolveModal}
        onClose={() => { setResolveModal(false); setResolveError(null); setResolveNote(""); }}
        title="Concluir ticket"
      >
        <div className="space-y-4">
          {resolveError && <Alert variant="danger">{resolveError}</Alert>}
          <p className="text-sm text-slate-400">
            Descreva como o problema foi resolvido. O chat será bloqueado e o cliente receberá uma notificação.
          </p>
          <Textarea label="Nota de resolução" placeholder="Descreva a solução aplicada…" rows={5} value={resolveNote} onChange={(e) => setResolveNote(e.target.value)} />
        </div>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setResolveModal(false)} disabled={resolveLoading}>Cancelar</Button>
          <Button onClick={handleResolve} loading={resolveLoading} disabled={!resolveNote.trim()}>Confirmar conclusão</Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
