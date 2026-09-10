import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "../../contexts/AuthContext";
import {
  Button,
  Icon,
  Input,
  Modal,
  ModalFooter,
  Textarea,
} from "../../components/ui";
import { readableTextColor } from "../../lib/colors";
import { cn } from "../../lib/utils";
import {
  getCalendarEvents,
  createCalendarEvent,
  updateCalendarEvent,
  deleteCalendarEvent,
  type CalendarEvent,
  type CalendarEventType,
} from "../../services/calendarService";

// ── Constants ─────────────────────────────────────────────────

const EVENT_TYPE_LABELS: Record<CalendarEventType, string> = {
  event: "Evento",
  meeting: "Reunião",
  training: "Treinamento",
  deadline: "Prazo",
  holiday: "Feriado",
};

/**
 * Os 21 hexadecimais desta tela são **dado**, e é por isso que continuam aqui.
 *
 * A migração troca cor que é decisão de desenho — o azul de "hoje", o cinza do
 * fim de semana — por token. Estas não são: o backend guarda `color` como texto
 * na linha do evento, o usuário escolhe qual é, e a tela só repinta o que veio
 * do banco. Um `var(--chart-3)` gravado nessa coluna não é cor de gráfico: é uma
 * string que vaza para o relatório, para a exportação e para quem ler a tabela.
 *
 * O que o sistema de design resolve aqui não é a cor de fundo — é o **texto por
 * cima dela**, que era `text-white` cravado. Sobre `#ffffff` e `#eab308`, dois
 * dos dezesseis valores oferecidos, branco sobre branco não se lê. Quem decide
 * é `readableTextColor`, por luminância WCAG, uma cor de cada vez.
 *
 * Estes cinco são o **padrão por tipo**: o valor que vai para o banco quando a
 * pessoa escolhe o tipo e não mexe na cor. Os cinco são membros da paleta
 * abaixo, e é ela que manda.
 */
const EVENT_TYPE_COLORS: Record<CalendarEventType, string> = {
  event: "#6366f1",
  meeting: "#3b82f6",
  training: "#10b981",
  deadline: "#f59e0b",
  holiday: "#ef4444",
};

/**
 * Cores disponíveis para os eventos. As cinco primeiras são as cores padrão
 * de cada tipo de evento; as demais servem para diferenciar eventos do mesmo tipo.
 *
 * Continua com hexadecimal por ser a lista de opções de um campo de dado — não
 * a paleta da interface. Qual conjunto de cores se oferece a quem cria evento é
 * decisão de desenho de produto, e ela não se toma de dentro de uma tela.
 */
const EVENT_COLOR_PALETTE: { value: string; label: string }[] = [
  { value: "#6366f1", label: "Índigo" },
  { value: "#3b82f6", label: "Azul" },
  { value: "#10b981", label: "Verde" },
  { value: "#f59e0b", label: "Âmbar" },
  { value: "#ef4444", label: "Vermelho" },
  { value: "#8b5cf6", label: "Violeta" },
  { value: "#0ea5e9", label: "Azul-céu" },
  { value: "#06b6d4", label: "Ciano" },
  { value: "#14b8a6", label: "Turquesa" },
  { value: "#84cc16", label: "Lima" },
  { value: "#eab308", label: "Amarelo" },
  { value: "#f97316", label: "Laranja" },
  { value: "#ec4899", label: "Rosa" },
  { value: "#a855f7", label: "Púrpura" },
  { value: "#64748b", label: "Cinza" },
  { value: "#ffffff", label: "Branco" },
];

const MONTHS = [
  "Janeiro","Fevereiro","Março","Abril","Maio","Junho",
  "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro",
];
const MONTHS_SHORT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
const WEEKDAYS = ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"];
const WEEKDAYS_FULL = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"];
const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 8 }, (_, i) => CURRENT_YEAR - 1 + i);

// ── Helpers ───────────────────────────────────────────────────

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate();
}
function getFirstDayOfMonth(year: number, month: number) {
  return new Date(year, month, 1).getDay();
}

function dateStr(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isEventOnDay(event: CalendarEvent, year: number, month: number, day: number): boolean {
  const start = new Date(event.start_date);
  const end = new Date(event.end_date);
  // Use UTC to avoid timezone shift (event dates are stored as UTC midnight)
  const target = Date.UTC(year, month, day);
  const startDay = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate());
  const endDay = Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate());
  return target >= startDay && target <= endDay;
}

// ── Event Dialog ──────────────────────────────────────────────

interface EventDialogProps {
  event?: CalendarEvent;
  defaultDate?: string;
  onClose: () => void;
  onSaved: () => void;
}

function EventDialog({ event, defaultDate, onClose, onSaved }: EventDialogProps) {
  const [title, setTitle] = useState(event?.title ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [eventType, setEventType] = useState<CalendarEventType>(event?.event_type ?? "event");
  // O padrão sai da tabela por tipo, e não de um sexto hexadecimal repetido:
  // a cor inicial de um evento novo era `#6366f1` escrito de novo aqui, que
  // podia divergir de `EVENT_TYPE_COLORS.event` sem ninguém perceber.
  const [color, setColor] = useState(event?.color ?? EVENT_TYPE_COLORS.event);
  const [colorOverride, setColorOverride] = useState(!!event?.color);
  const [startDate, setStartDate] = useState(
    event ? event.start_date.slice(0, 10) : (defaultDate ?? ""),
  );
  const [endDate, setEndDate] = useState(
    event ? event.end_date.slice(0, 10) : (defaultDate ?? ""),
  );
  const [saving, setSaving] = useState(false);

  function handleTypeChange(t: CalendarEventType) {
    setEventType(t);
    if (!colorOverride) setColor(EVENT_TYPE_COLORS[t]);
  }

  async function handleSave() {
    if (!title.trim() || !startDate) return;
    setSaving(true);
    try {
      const payload = {
        title: title.trim(),
        description: description.trim() || null,
        event_type: eventType,
        color,
        start_date: startDate + "T00:00:00Z",
        end_date: (endDate || startDate) + "T23:59:59Z",
      };
      if (event) {
        await updateCalendarEvent(event.id, payload);
        toast.success("Evento atualizado!");
      } else {
        await createCalendarEvent(payload);
        toast.success("Evento criado!");
      }
      onSaved();
      onClose();
    } catch {
      toast.error("Erro ao salvar evento.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={event ? "Editar evento" : "Novo evento"} size="md">
      <div className="space-y-4 pb-1">
        <Input
          label="Título"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Nome do evento"
          autoFocus
        />

        <div className="space-y-1.5">
          {/* `htmlFor` e `id`: sem o par, o rótulo fica só POR CIMA do campo —
              quem usa leitor de tela ouve "caixa de combinação" sem saber de
              quê. Item fixo do CHECKLIST-29. */}
          <label htmlFor="evento-tipo" className="text-xs font-medium text-conteudo-muted">Tipo</label>
          <select
            id="evento-tipo"
            value={eventType}
            onChange={(e) => handleTypeChange(e.target.value as CalendarEventType)}
            className="w-full rounded-lg border border-borda bg-surface-elevated px-3 py-2 text-sm text-conteudo focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
          >
            {(Object.keys(EVENT_TYPE_LABELS) as CalendarEventType[]).map((t) => (
              <option key={t} value={t}>{EVENT_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          {/* `<label>` sem `htmlFor` não rotula nada, e aqui não há um campo
              para apontar: são dezesseis botões. Vira nome do GRUPO, que é o
              que o leitor de tela anuncia antes de percorrer as opções. */}
          <span id="evento-cor" className="block text-xs font-medium text-conteudo-muted">Cor</span>
          <div role="group" aria-labelledby="evento-cor" className="grid grid-cols-4 gap-2 sm:grid-cols-8">
            {EVENT_COLOR_PALETTE.map((c) => (
              <button
                key={c.value}
                type="button"
                title={c.label}
                aria-label={c.label}
                aria-pressed={color === c.value}
                onClick={() => { setColor(c.value); setColorOverride(true); }}
                className={cn(
                  "h-8 w-full rounded-md border-2 transition-transform cursor-pointer",
                  // Contorno interno para as cores claras não sumirem no fundo.
                  // Era `ring-black/15`, que sobre a superfície branca do tema
                  // claro dá ~1,3:1 — o limite do controle desaparece
                  // exatamente onde ele mais fazia falta. `--border-control` é
                  // o token da E7 para isto, medido em 4,76 / 4,55 / 4,34 no
                  // claro e 6,23 / 6,78 / 5,29 no escuro.
                  "ring-1 ring-inset ring-borda-control",
                  color === c.value
                    ? "border-action scale-105 shadow-md"
                    : "border-transparent hover:scale-105",
                )}
                style={{ backgroundColor: c.value }}
              />
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Data de início"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <Input
            label="Data de fim"
            type="date"
            value={endDate}
            min={startDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>

        <Textarea
          label="Descrição (opcional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Detalhes do evento..."
          rows={3}
        />
      </div>

      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button
          variant="primary"
          onClick={handleSave}
          loading={saving}
          disabled={!title.trim() || !startDate}
        >
          Salvar
        </Button>
      </ModalFooter>
    </Modal>
  );
}

// ── Calendar Grid ─────────────────────────────────────────────

interface CalendarGridProps {
  year: number;
  month: number;
  events: CalendarEvent[];
  canEdit: boolean;
  selectedDay: number | null;
  onSelectDay: (day: number) => void;
  onEventClick: (event: CalendarEvent) => void;
}

function CalendarGrid({ year, month, events, canEdit, selectedDay, onSelectDay, onEventClick }: CalendarGridProps) {
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const today = new Date();

  const cells: (number | null)[] = [
    ...Array(firstDay).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div>
      <div className="grid grid-cols-7 mb-1">
        {WEEKDAYS.map((d) => (
          <div key={d} className="py-2 text-center text-xs font-semibold text-conteudo-muted uppercase tracking-wide">
            {d}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-px bg-borda rounded-xl overflow-hidden border border-borda">
        {cells.map((day, i) => {
          if (!day) return <div key={i} className="bg-surface/40 min-h-[88px]" />;

          const isToday = today.getFullYear() === year && today.getMonth() === month && today.getDate() === day;
          const isSelected = selectedDay === day;
          const isWeekend = (firstDay + day - 1) % 7 === 0 || (firstDay + day - 1) % 7 === 6;
          const dayEvents = events.filter((e) => isEventOnDay(e, year, month, day));

          return (
            <div
              key={i}
              onClick={() => onSelectDay(day)}
              className={cn(
                "min-h-[88px] p-2 cursor-pointer transition-colors group",
                // `bg-primary/8` NÃO existia: a escala de opacidade do Tailwind
                // v3 vai de 5 em 5, o 8 não está nela, e a regra nunca foi
                // gerada — sem erro e sem aviso. O dia escolhido vinha só com o
                // anel, e o fundo que o autor escreveu nunca chegou a pintar.
                // `bg-tint-primary` é o token da tinta (15%), e não leva
                // modificador de opacidade: ela já carrega o alfa (regra D8-a).
                isSelected
                  ? "bg-tint-primary ring-1 ring-inset ring-primary/30"
                  : isWeekend
                    ? "bg-surface-elevated/30 hover:bg-surface-elevated/60"
                    : "bg-surface hover:bg-surface-elevated/40",
              )}
            >
              <div className={cn(
                "text-xs font-semibold mb-1.5 h-6 w-6 flex items-center justify-center rounded-full transition-colors",
                // `bg-primary` + `text-white` dá 3,83:1, nos dois temas — o
                // degrau 500 é absoluto e não inverte. O par do degrau de AÇÃO
                // é `--action` com `--text-on-primary`, que é branco no claro e
                // navy no escuro (emenda E1).
                isToday
                  ? "bg-action text-on-primary shadow-sm"
                  : isSelected
                    // Sobre `bg-tint-primary`, o degrau de marca como cor de
                    // texto dá 2,77:1 (emenda E8). O par da tinta é o
                    // `--on-tint-primary`.
                    ? "text-on-tint-primary font-bold"
                    : "text-conteudo-muted group-hover:text-conteudo",
              )}>
                {day}
                {/* "Hoje" e "dia escolhido" eram ditos só pela cor e pela
                    forma do disco. Quem não vê a tela não tinha a informação. */}
                {isToday && <span className="sr-only"> (hoje)</span>}
              </div>

              <div className="space-y-0.5">
                {dayEvents.slice(0, 3).map((e) => (
                  <div
                    key={e.id}
                    onClick={(ev) => { ev.stopPropagation(); if (canEdit) onEventClick(e); }}
                    className="flex items-center gap-1 text-[10px] leading-tight rounded-md px-1.5 py-0.5 truncate cursor-pointer hover:opacity-80 transition-opacity"
                    // O fundo é cor escolhida pelo usuário — dado, não token —,
                    // então o texto por cima não pode ser fixo: `text-white`
                    // sobre o "#ffffff" e o "#eab308" da paleta some. Quem
                    // escolhe é a luminância WCAG, uma cor de cada vez.
                    style={{
                      backgroundColor: e.color,
                      color: readableTextColor(e.color),
                    }}
                    title={e.title}
                  >
                    {e.title}
                  </div>
                ))}
                {dayEvents.length > 3 && (
                  <div className="text-[10px] text-conteudo-muted px-1 font-medium">
                    +{dayEvents.length - 3}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Day Detail ────────────────────────────────────────────────

interface DayDetailProps {
  date: Date;
  events: CalendarEvent[];
  canEdit: boolean;
  onAdd: () => void;
  onEdit: (event: CalendarEvent) => void;
  onDelete: (event: CalendarEvent) => void;
  onClose: () => void;
}

function DayDetail({ date, events, canEdit, onAdd, onEdit, onDelete, onClose }: DayDetailProps) {
  return (
    <div className="rounded-xl border border-borda bg-surface p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-conteudo-muted font-medium uppercase tracking-wide">
            {WEEKDAYS_FULL[date.getDay()]}
          </p>
          <p className="text-lg font-bold text-conteudo-heading">
            {date.getDate()} de {MONTHS[date.getMonth()]}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {canEdit && (
            <button
              onClick={onAdd}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-tint-primary text-on-tint-primary hover:bg-primary/20 transition-colors cursor-pointer"
              title="Adicionar evento"
            >
              <Icon name="plus" size={16} strokeWidth={2.5} />
            </button>
          )}
          <button
            onClick={onClose}
            aria-label="Fechar o dia"
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-elevated text-conteudo-muted hover:text-conteudo transition-colors text-sm cursor-pointer"
          >
            ✕
          </button>
        </div>
      </div>

      {events.length === 0 ? (
        <p className="text-sm text-conteudo-muted py-2">Nenhum evento neste dia.</p>
      ) : (
        <div className="space-y-2">
          {events.map((e) => (
            <div key={e.id} className="flex items-center gap-2.5 rounded-lg border border-borda bg-surface-elevated px-3 py-2">
              <div className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-conteudo font-medium truncate">{e.title}</p>
                {e.description && (
                  <p className="text-xs text-conteudo-muted truncate mt-0.5">{e.description}</p>
                )}
              </div>
              <span className="text-[10px] text-conteudo-muted shrink-0">
                {EVENT_TYPE_LABELS[e.event_type]}
              </span>
              {/* Os dois botões não tinham texto, nem `title`, nem
                  `aria-label`: o nome acessível de cada um era vazio, e a lista
                  de eventos do dia terminava em dois controles que o leitor de
                  tela anuncia como "botão", sem dizer de quê nem para quê. */}
              {canEdit && (
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => onEdit(e)}
                    title={`Editar ${e.title}`}
                    aria-label={`Editar ${e.title}`}
                    className="flex h-6 w-6 items-center justify-center rounded-md bg-tint-warning text-on-tint-warning hover:bg-warning/25 transition-colors cursor-pointer"
                  >
                    <Icon name="edit" size={12} strokeWidth={2.5} />
                  </button>
                  <button
                    onClick={() => onDelete(e)}
                    title={`Remover ${e.title}`}
                    aria-label={`Remover ${e.title}`}
                    className="flex h-6 w-6 items-center justify-center rounded-md bg-tint-danger text-on-tint-danger hover:bg-danger/25 transition-colors cursor-pointer"
                  >
                    <Icon name="trash" size={12} strokeWidth={2.5} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Upcoming Events ───────────────────────────────────────────

function UpcomingList({ events }: { events: CalendarEvent[] }) {
  const now = new Date();
  const upcoming = events
    .filter((e) => new Date(e.end_date) >= now)
    .slice(0, 4);

  if (upcoming.length === 0) {
    return <p className="text-xs text-conteudo-muted py-2">Nenhum evento próximo.</p>;
  }

  return (
    <div className="space-y-2 max-h-[168px] overflow-y-auto pr-0.5">
      {upcoming.map((e) => (
        <div key={e.id} className="flex items-start gap-2.5 rounded-lg bg-surface-elevated/40 px-3 py-2">
          <div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-conteudo truncate">{e.title}</p>
            <p className="text-[10px] text-conteudo-muted mt-0.5">
              {new Date(e.start_date).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", timeZone: "UTC" })}
              {e.start_date.slice(0, 10) !== e.end_date.slice(0, 10) && (
                <> → {new Date(e.end_date).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", timeZone: "UTC" })}</>
              )}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────

interface DialogState {
  open: boolean;
  event?: CalendarEvent;
  date?: string;
}

export default function CalendarPage() {
  const { user } = useAuth();
  const canEdit = user?.role === "admin" || user?.role === "technician";

  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState<DialogState>({ open: false });
  const [deleteTarget, setDeleteTarget] = useState<CalendarEvent | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCalendarEvents();
      setEvents(data);
    } catch {
      toast.error("Erro ao carregar eventos.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadEvents(); }, [loadEvents]);

  function prevMonth() {
    if (month === 0) { setMonth(11); setYear((y) => y - 1); }
    else setMonth((m) => m - 1);
    setSelectedDay(null);
  }
  function nextMonth() {
    if (month === 11) { setMonth(0); setYear((y) => y + 1); }
    else setMonth((m) => m + 1);
    setSelectedDay(null);
  }
  function goToToday() {
    setYear(today.getFullYear());
    setMonth(today.getMonth());
    setSelectedDay(today.getDate());
  }

  // O `confirm()` nativo saiu pela D9.3: ele não nomeia o evento — "Remover
  // este evento?" servia para qualquer um dos vinte da lista —, não diz que não
  // volta, e é a única caixa da frota que o tema não alcança.
  function handleDelete(event: CalendarEvent) {
    setDeleteTarget(event);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteCalendarEvent(deleteTarget.id);
      toast.success("Evento removido.");
      setDeleteTarget(null);
      loadEvents();
      setSelectedDay(null);
    } catch {
      toast.error("Erro ao remover evento.");
    } finally {
      setDeleting(false);
    }
  }

  const selectedDate = selectedDay ? new Date(year, month, selectedDay) : null;
  const selectedDayEvents = selectedDay
    ? events.filter((e) => isEventOnDay(e, year, month, selectedDay))
    : [];

  return (
    <div className="space-y-5 pb-10">
      {dialog.open && (
        <EventDialog
          event={dialog.event}
          defaultDate={dialog.date}
          onClose={() => setDialog({ open: false })}
          onSaved={loadEvents}
        />
      )}

      {/* Confirmação de exclusão — forma da frota (D9.3). */}
      {deleteTarget && (
        <Modal
          open
          onClose={() => setDeleteTarget(null)}
          size="sm"
          title="Excluir evento"
        >
          <p className="text-sm text-conteudo-muted">
            Tem certeza que deseja excluir{" "}
            <span className="font-medium text-conteudo">
              {deleteTarget.title}
            </span>
            ? O evento será removido do calendário, e esta ação não pode ser
            desfeita.
          </p>
          <ModalFooter>
            <Button
              variant="secondary"
              onClick={() => setDeleteTarget(null)}
              disabled={deleting}
            >
              Cancelar
            </Button>
            <Button variant="danger" onClick={confirmDelete} loading={deleting}>
              Excluir
            </Button>
          </ModalFooter>
        </Modal>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-tint-primary text-on-tint-primary">
            <Icon name="calendar" size={20} />
          </div>
          <div>
            <h1 className="text-xl font-extrabold text-conteudo-heading">Agenda</h1>
            <p className="text-sm text-conteudo-muted">Calendário da equipe</p>
          </div>
        </div>
        {canEdit && (
          <Button variant="primary" onClick={() => setDialog({ open: true })}>
            <span className="flex items-center gap-1.5">
              <Icon name="plus" size={16} strokeWidth={2.5} />
              Novo evento
            </span>
          </Button>
        )}
      </div>

      {/* Navigation */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Os dois eram setas mudas: o `<svg>` não tem nome, então o controle
            também não tinha. */}
        <button
          onClick={prevMonth}
          aria-label="Mês anterior"
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-borda bg-surface text-conteudo-muted hover:bg-surface-elevated hover:text-conteudo transition-colors cursor-pointer"
        >
          <Icon name="chevronLeft" size={16} strokeWidth={2.5} />
        </button>

        <select
          value={month}
          aria-label="Mês"
          onChange={(e) => { setMonth(Number(e.target.value)); setSelectedDay(null); }}
          className="h-8 rounded-lg border border-borda bg-surface px-3 text-sm font-semibold text-conteudo focus:outline-none focus:ring-2 focus:ring-primary transition-colors cursor-pointer"
        >
          {MONTHS.map((m, i) => (
            <option key={i} value={i}>{m}</option>
          ))}
        </select>

        <select
          value={year}
          aria-label="Ano"
          onChange={(e) => { setYear(Number(e.target.value)); setSelectedDay(null); }}
          className="h-8 rounded-lg border border-borda bg-surface px-3 text-sm font-semibold text-conteudo focus:outline-none focus:ring-2 focus:ring-primary transition-colors cursor-pointer"
        >
          {YEARS.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>

        <button
          onClick={nextMonth}
          aria-label="Próximo mês"
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-borda bg-surface text-conteudo-muted hover:bg-surface-elevated hover:text-conteudo transition-colors cursor-pointer"
        >
          <Icon name="chevronRight" size={16} strokeWidth={2.5} />
        </button>

        <button
          onClick={goToToday}
          className="h-8 rounded-lg border border-primary/30 bg-tint-primary px-3 text-sm font-medium text-on-tint-primary hover:bg-primary/20 transition-colors cursor-pointer"
        >
          Hoje
        </button>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Calendar */}
        <div className="lg:col-span-3 space-y-4">
          {loading ? (
            <div className="flex h-64 items-center justify-center text-conteudo-muted text-sm">
              Carregando eventos...
            </div>
          ) : (
            <CalendarGrid
              year={year}
              month={month}
              events={events}
              canEdit={canEdit}
              selectedDay={selectedDay}
              onSelectDay={setSelectedDay}
              onEventClick={(e) => setDialog({ open: true, event: e })}
            />
          )}

          {/* Day detail */}
          {selectedDate && (
            <DayDetail
              date={selectedDate}
              events={selectedDayEvents}
              canEdit={canEdit}
              onAdd={() => setDialog({ open: true, date: dateStr(selectedDate) })}
              onEdit={(e) => setDialog({ open: true, event: e })}
              onDelete={handleDelete}
              onClose={() => setSelectedDay(null)}
            />
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Upcoming */}
          <div className="rounded-xl border border-borda bg-surface p-4 space-y-3">
            <h3 className="text-sm font-semibold text-conteudo">Próximos eventos</h3>
            <UpcomingList events={events} />
          </div>

          {/* Mini month map */}
          <div className="rounded-xl border border-borda bg-surface p-4 space-y-3">
            <h3 className="text-sm font-semibold text-conteudo">Meses do ano</h3>
            <div className="grid grid-cols-3 gap-1.5">
              {MONTHS_SHORT.map((m, i) => {
                const hasEvents = events.some((e) => {
                  const s = new Date(e.start_date);
                  const en = new Date(e.end_date);
                  return (
                    (s.getUTCFullYear() === year && s.getUTCMonth() === i) ||
                    (en.getUTCFullYear() === year && en.getUTCMonth() === i)
                  );
                });
                const isCurrent = i === month;
                const isCurrentMonth = i === today.getMonth() && year === today.getFullYear();
                return (
                  <button
                    key={i}
                    onClick={() => { setMonth(i); setSelectedDay(null); }}
                    className={cn(
                      "relative rounded-lg py-1.5 text-xs font-medium transition-colors cursor-pointer",
                      // O mesmo par de 3,83:1 do disco de "hoje", pelo mesmo
                      // motivo: `bg-primary` é o degrau de MARCA, e quem veste
                      // o item ativo é `--action`.
                      isCurrent
                        ? "bg-action text-on-primary"
                        : "bg-surface-elevated/50 text-conteudo-muted hover:bg-surface-elevated hover:text-conteudo",
                    )}
                  >
                    {m}
                    {/* Os dois pontos eram a única fonte da informação que
                        carregam — a mesma armadilha que o `lib/prioridade.ts`
                        descreve para o ponto de prioridade. Com o texto ao
                        lado, a cor vira reforço e o piso de 3:1 deixa de se
                        aplicar; sem ele, quem não distingue a cor não tem o
                        dado de forma alguma. */}
                    {hasEvents && !isCurrent && (
                      <>
                        <span className="absolute top-0.5 right-1 h-1.5 w-1.5 rounded-full bg-primary/60" />
                        <span className="sr-only"> — com eventos</span>
                      </>
                    )}
                    {isCurrentMonth && !isCurrent && (
                      <>
                        <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 h-0.5 w-3 rounded-full bg-primary/40" />
                        <span className="sr-only"> — mês atual</span>
                      </>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Manage events — só para admin/technician, filtrado pelo mês visível */}
          {canEdit && (() => {
            const monthEvents = events.filter((e) => {
              const s = new Date(e.start_date);
              const en = new Date(e.end_date);
              const monthStart = Date.UTC(year, month, 1);
              const monthEnd = Date.UTC(year, month + 1, 1) - 1;
              return (
                Date.UTC(s.getUTCFullYear(), s.getUTCMonth(), s.getUTCDate()) <= monthEnd &&
                Date.UTC(en.getUTCFullYear(), en.getUTCMonth(), en.getUTCDate()) >= monthStart
              );
            });
            if (monthEvents.length === 0) return null;
            return (
            <div className="rounded-xl border border-borda bg-surface p-4 space-y-3">
              <h3 className="text-sm font-semibold text-conteudo">
                Gerenciar eventos — {MONTHS_SHORT[month]}
              </h3>
              <div className="space-y-1.5 max-h-[168px] overflow-y-auto pr-0.5">
                {monthEvents.slice(0, 4).map((e) => (
                  <div key={e.id} className="flex items-center gap-2 rounded-lg bg-surface-elevated/30 px-2.5 py-1.5">
                    <div className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
                    <span className="flex-1 text-xs text-conteudo truncate">{e.title}</span>
                    <div className="flex gap-1 shrink-0">
                      <button
                        onClick={() => setDialog({ open: true, event: e })}
                        title={`Editar ${e.title}`}
                        aria-label={`Editar ${e.title}`}
                        className="flex h-6 w-6 items-center justify-center rounded-md bg-tint-warning text-on-tint-warning hover:bg-warning/25 transition-colors cursor-pointer"
                      >
                        <Icon name="edit" size={12} strokeWidth={2.5} />
                      </button>
                      <button
                        onClick={() => handleDelete(e)}
                        title={`Remover ${e.title}`}
                        aria-label={`Remover ${e.title}`}
                        className="flex h-6 w-6 items-center justify-center rounded-md bg-tint-danger text-on-tint-danger hover:bg-danger/25 transition-colors cursor-pointer"
                      >
                        <Icon name="trash" size={12} strokeWidth={2.5} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
