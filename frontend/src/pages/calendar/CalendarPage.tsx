import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "../../contexts/AuthContext";
import { Button, Input, Modal, ModalFooter, Textarea } from "../../components/ui";
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

const EVENT_TYPE_COLORS: Record<CalendarEventType, string> = {
  event: "#6366f1",
  meeting: "#3b82f6",
  training: "#10b981",
  deadline: "#f59e0b",
  holiday: "#ef4444",
};

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
  const target = new Date(year, month, day);
  const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const endDay = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  return target >= startDay && target <= endDay;
}

// ── SVG Icons ─────────────────────────────────────────────────

function IconCalendar() {
  return (
    <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  );
}
function IconChevronLeft() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
    </svg>
  );
}
function IconChevronRight() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
function IconPlus() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
    </svg>
  );
}
function IconPencil() {
  return (
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
    </svg>
  );
}
function IconTrash() {
  return (
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
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
  const [color, setColor] = useState(event?.color ?? "#6366f1");
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

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-400">Tipo</label>
            <select
              value={eventType}
              onChange={(e) => handleTypeChange(e.target.value as CalendarEventType)}
              className="w-full rounded-lg border border-border bg-background-elevated px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            >
              {(Object.keys(EVENT_TYPE_LABELS) as CalendarEventType[]).map((t) => (
                <option key={t} value={t}>{EVENT_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-400">Cor</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={color}
                onChange={(e) => { setColor(e.target.value); setColorOverride(true); }}
                className="h-9 w-12 cursor-pointer rounded border border-border bg-transparent"
              />
              <span className="text-xs text-slate-500 font-mono">{color}</span>
            </div>
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
          <div key={d} className="py-2 text-center text-xs font-semibold text-slate-500 uppercase tracking-wide">
            {d}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-px bg-border rounded-xl overflow-hidden border border-border">
        {cells.map((day, i) => {
          if (!day) return <div key={i} className="bg-background-surface/40 min-h-[88px]" />;

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
                isSelected
                  ? "bg-primary/8 ring-1 ring-inset ring-primary/30"
                  : isWeekend
                    ? "bg-background-elevated/30 hover:bg-background-elevated/60"
                    : "bg-background-surface hover:bg-background-elevated/40",
              )}
            >
              <div className={cn(
                "text-xs font-semibold mb-1.5 h-6 w-6 flex items-center justify-center rounded-full transition-colors",
                isToday
                  ? "bg-primary text-white shadow-sm"
                  : isSelected
                    ? "text-primary font-bold"
                    : "text-slate-400 group-hover:text-slate-200",
              )}>
                {day}
              </div>

              <div className="space-y-0.5">
                {dayEvents.slice(0, 3).map((e) => (
                  <div
                    key={e.id}
                    onClick={(ev) => { ev.stopPropagation(); if (canEdit) onEventClick(e); }}
                    className="flex items-center gap-1 text-[10px] leading-tight rounded-md px-1.5 py-0.5 text-white truncate cursor-pointer hover:opacity-80 transition-opacity"
                    style={{ backgroundColor: e.color }}
                    title={e.title}
                  >
                    {e.title}
                  </div>
                ))}
                {dayEvents.length > 3 && (
                  <div className="text-[10px] text-slate-500 px-1 font-medium">
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
  onDelete: (id: string) => void;
  onClose: () => void;
}

function DayDetail({ date, events, canEdit, onAdd, onEdit, onDelete, onClose }: DayDetailProps) {
  return (
    <div className="rounded-xl border border-border bg-background-surface p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">
            {WEEKDAYS_FULL[date.getDay()]}
          </p>
          <p className="text-lg font-bold text-slate-100">
            {date.getDate()} de {MONTHS[date.getMonth()]}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {canEdit && (
            <button
              onClick={onAdd}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors cursor-pointer"
              title="Adicionar evento"
            >
              <IconPlus />
            </button>
          )}
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-background-elevated text-slate-400 hover:text-slate-200 transition-colors text-sm cursor-pointer"
          >
            ✕
          </button>
        </div>
      </div>

      {events.length === 0 ? (
        <p className="text-sm text-slate-500 py-2">Nenhum evento neste dia.</p>
      ) : (
        <div className="space-y-2">
          {events.map((e) => (
            <div key={e.id} className="flex items-center gap-2.5 rounded-lg border border-border bg-background-elevated px-3 py-2">
              <div className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-200 font-medium truncate">{e.title}</p>
                {e.description && (
                  <p className="text-xs text-slate-500 truncate mt-0.5">{e.description}</p>
                )}
              </div>
              <span className="text-[10px] text-slate-500 shrink-0">
                {EVENT_TYPE_LABELS[e.event_type]}
              </span>
              {canEdit && (
                <div className="flex gap-1 shrink-0">
                  <button
                    onClick={() => onEdit(e)}
                    className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 transition-colors cursor-pointer"
                  >
                    <IconPencil />
                  </button>
                  <button
                    onClick={() => onDelete(e.id)}
                    className="flex h-6 w-6 items-center justify-center rounded-md bg-danger/15 text-danger hover:bg-danger/25 transition-colors cursor-pointer"
                  >
                    <IconTrash />
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
    .slice(0, 6);

  if (upcoming.length === 0) {
    return <p className="text-xs text-slate-500 py-2">Nenhum evento próximo.</p>;
  }

  return (
    <div className="space-y-2">
      {upcoming.map((e) => (
        <div key={e.id} className="flex items-start gap-2.5 rounded-lg bg-background-elevated/40 px-3 py-2">
          <div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-slate-200 truncate">{e.title}</p>
            <p className="text-[10px] text-slate-500 mt-0.5">
              {new Date(e.start_date).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}
              {e.start_date.slice(0, 10) !== e.end_date.slice(0, 10) && (
                <> → {new Date(e.end_date).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}</>
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

  async function handleDelete(id: string) {
    if (!confirm("Remover este evento?")) return;
    try {
      await deleteCalendarEvent(id);
      toast.success("Evento removido.");
      loadEvents();
      setSelectedDay(null);
    } catch {
      toast.error("Erro ao remover evento.");
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

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/40 bg-background-surface px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <IconCalendar />
          </div>
          <div>
            <h1 className="text-xl font-extrabold text-slate-100">Agenda</h1>
            <p className="text-sm text-slate-500">Calendário da equipe</p>
          </div>
        </div>
        {canEdit && (
          <Button variant="primary" onClick={() => setDialog({ open: true })}>
            <span className="flex items-center gap-1.5">
              <IconPlus />
              Novo evento
            </span>
          </Button>
        )}
      </div>

      {/* Navigation */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={prevMonth}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-background-surface text-slate-400 hover:bg-background-elevated hover:text-slate-200 transition-colors cursor-pointer"
        >
          <IconChevronLeft />
        </button>

        <select
          value={month}
          onChange={(e) => { setMonth(Number(e.target.value)); setSelectedDay(null); }}
          className="h-8 rounded-lg border border-border bg-background-surface px-3 text-sm font-semibold text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary transition-colors cursor-pointer"
        >
          {MONTHS.map((m, i) => (
            <option key={i} value={i}>{m}</option>
          ))}
        </select>

        <select
          value={year}
          onChange={(e) => { setYear(Number(e.target.value)); setSelectedDay(null); }}
          className="h-8 rounded-lg border border-border bg-background-surface px-3 text-sm font-semibold text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary transition-colors cursor-pointer"
        >
          {YEARS.map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>

        <button
          onClick={nextMonth}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-background-surface text-slate-400 hover:bg-background-elevated hover:text-slate-200 transition-colors cursor-pointer"
        >
          <IconChevronRight />
        </button>

        <button
          onClick={goToToday}
          className="h-8 rounded-lg border border-primary/30 bg-primary/10 px-3 text-sm font-medium text-primary hover:bg-primary/20 transition-colors cursor-pointer"
        >
          Hoje
        </button>
      </div>

      {/* Main layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Calendar */}
        <div className="lg:col-span-3 space-y-4">
          {loading ? (
            <div className="flex h-64 items-center justify-center text-slate-500 text-sm">
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

          {/* Legend */}
          <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1">
            {(Object.keys(EVENT_TYPE_LABELS) as CalendarEventType[]).map((type) => (
              <div key={type} className="flex items-center gap-1.5 text-xs text-slate-500">
                <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: EVENT_TYPE_COLORS[type] }} />
                {EVENT_TYPE_LABELS[type]}
              </div>
            ))}
          </div>

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
          <div className="rounded-xl border border-border bg-background-surface p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Próximos eventos</h3>
            <UpcomingList events={events} />
          </div>

          {/* Mini month map */}
          <div className="rounded-xl border border-border bg-background-surface p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Meses do ano</h3>
            <div className="grid grid-cols-3 gap-1.5">
              {MONTHS_SHORT.map((m, i) => {
                const hasEvents = events.some((e) => {
                  const s = new Date(e.start_date);
                  const en = new Date(e.end_date);
                  return (
                    (s.getFullYear() === year && s.getMonth() === i) ||
                    (en.getFullYear() === year && en.getMonth() === i)
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
                      isCurrent
                        ? "bg-primary text-white"
                        : "bg-background-elevated/50 text-slate-400 hover:bg-background-elevated hover:text-slate-200",
                    )}
                  >
                    {m}
                    {hasEvents && !isCurrent && (
                      <span className="absolute top-0.5 right-1 h-1.5 w-1.5 rounded-full bg-primary/60" />
                    )}
                    {isCurrentMonth && !isCurrent && (
                      <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 h-0.5 w-3 rounded-full bg-primary/40" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Manage events — só para admin/technician */}
          {canEdit && events.length > 0 && (
            <div className="rounded-xl border border-border bg-background-surface p-4 space-y-3">
              <h3 className="text-sm font-semibold text-slate-200">Gerenciar eventos</h3>
              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {events.slice(0, 10).map((e) => (
                  <div key={e.id} className="flex items-center gap-2 rounded-lg bg-background-elevated/30 px-2.5 py-1.5">
                    <div className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
                    <span className="flex-1 text-xs text-slate-300 truncate">{e.title}</span>
                    <div className="flex gap-1 shrink-0">
                      <button
                        onClick={() => setDialog({ open: true, event: e })}
                        className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 transition-colors cursor-pointer"
                      >
                        <IconPencil />
                      </button>
                      <button
                        onClick={() => handleDelete(e.id)}
                        className="flex h-6 w-6 items-center justify-center rounded-md bg-danger/15 text-danger hover:bg-danger/25 transition-colors cursor-pointer"
                      >
                        <IconTrash />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
