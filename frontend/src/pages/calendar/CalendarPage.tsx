import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "../../contexts/AuthContext";
import {
  Alert,
  Button,
  Icon,
  Input,
  Modal,
  ModalFooter,
  SelectMenu,
  Switch,
  Textarea,
} from "../../components/ui";
import {
  chaveCivil,
  chaveDeOrdem,
  chaveDoDia,
  chaveFlutuante,
  descreveComData,
  descreveHorario,
  diaDaSemana,
  diasNoMes,
  fusoDoNavegador,
  horaCivil,
  instanteDe,
  jaTerminou,
  ocupaODia,
  ocupaOMes,
} from "../../lib/agenda";
import { readableTextColor } from "../../lib/colors";
import { toastApiError } from "../../lib/toastError";
import { cn } from "../../lib/utils";
import {
  getCalendarEvents,
  getCalendarEventTypes,
  createCalendarEvent,
  updateCalendarEvent,
  deleteCalendarEvent,
  type CalendarEvent,
  type CalendarEventPayload,
  type CalendarEventType,
  type CalendarEventTypeColor,
} from "../../services/calendarService";

// ── Constants ─────────────────────────────────────────────────

const EVENT_TYPE_LABELS: Record<CalendarEventType, string> = {
  event: "Evento",
  meeting: "Reunião",
  training: "Treinamento",
  deadline: "Prazo",
  holiday: "Feriado",
};

/*
  ── A cor não mora mais aqui ─────────────────────────────────────────

  Até 15/09/2026 este arquivo tinha 21 hexadecimais: os cinco padrões por tipo e
  as dezesseis fichas que a pessoa escolhia. O §29 os deixou de propósito — eram
  dado, não dívida. O que mudou foi a FONTE: desde o #18 a cor do evento é
  derivada do tipo no backend, e ele ignora a cor mandada.

  Com isso, as fichas viraram controle morto, e o mapa local virou segunda fonte
  para a mesma coisa. Os dois saíram. A tela desenha a `color` que a API devolve,
  e lê de `GET /calendar/event-types` o mapa de que precisa para a legenda e para
  mostrar, no modal, a cor que o tipo escolhido vai ter.

  Não há mapa de reserva para quando a API falha, e isso é deliberado: um mapa de
  reserva seria exatamente a segunda fonte que esta mudança tirou.
*/

const MONTHS = [
  "Janeiro","Fevereiro","Março","Abril","Maio","Junho",
  "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro",
];
const MONTHS_SHORT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
const WEEKDAYS = ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"];
const WEEKDAYS_FULL = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"];

/** Horário que aparece ao desligar "dia inteiro" num evento que não tinha hora. */
const HORA_INICIAL = "09:00";
const HORA_FINAL = "10:00";

/**
 * Quem criou o evento, em palavras.
 *
 * Três casos, e dois deles não podem se confundir. A coluna é `ondelete=SET NULL`:
 * apagar o usuário esvazia `created_by` — o autor foi REMOVIDO. Anonimizar não
 * apaga a linha, só troca o nome por "Usuário Anonimizado …", que chega aqui como
 * nome e já diz o que é. O terceiro caso — id sem nome — não deveria existir com a
 * chave estrangeira, e está escrito para não virar "removido", que seria mentira.
 */
function autoria(e: CalendarEvent): string {
  if (e.creator_name) return `Criado por ${e.creator_name}`;
  return e.created_by ? "Criado por um usuário não identificado" : "Criado por um usuário removido";
}

/** O status HTTP de um erro do axios, ou `undefined`. */
function statusDoErro(err: unknown): number | undefined {
  return (err as { response?: { status?: number } } | undefined)?.response?.status;
}

// ── Event Dialog ──────────────────────────────────────────────

interface EventDialogProps {
  event?: CalendarEvent;
  defaultDate?: string;
  fuso: string;
  tipos: CalendarEventTypeColor[];
  onClose: () => void;
  onSaved: () => void;
}

function EventDialog({ event, defaultDate, fuso, tipos, onClose, onSaved }: EventDialogProps) {
  const [title, setTitle] = useState(event?.title ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [eventType, setEventType] = useState<CalendarEventType>(event?.event_type ?? "event");
  /*
    Dia inteiro DESLIGADO ao abrir um evento novo, por pedido do operador em
    22/09/2026. O evento que se marca na agenda tem hora; dia inteiro é o caso
    raro, e ligar a chave é um clique — o mesmo que desligá-la era.

    O padrão antigo era o oposto, e tinha um motivo que segue verdadeiro: quem
    esquecer a chave agora grava um evento de 09:00 a 10:00, e não um dia
    inteiro. A troca aceita esse preço; o teste
    "sem tocar na chave, o evento novo grava hora" prende a consequência, para
    que ela seja uma decisão e não uma surpresa.

    Evento que já existe continua abrindo como foi gravado.
  */
  const [diaInteiro, setDiaInteiro] = useState(event ? event.all_day : false);
  /*
    As duas naturezas se leem diferente, e é aqui que o erro custaria um dia.
    Dia inteiro é data FLUTUANTE: `00:00Z` é a data. Lido no fuso de Recife, o
    mesmo `00:00Z` seria 21:00 da VÉSPERA — o campo mostraria o dia anterior, e
    salvar gravaria o evento um dia antes. Evento com hora é instante, e se lê no
    fuso de quem olha.
  */
  const lerData = (instante: string) =>
    event?.all_day ? chaveFlutuante(instante) : chaveCivil(instante, fuso);
  const [startDate, setStartDate] = useState(event ? lerData(event.start_date) : (defaultDate ?? ""));
  const [endDate, setEndDate] = useState(event ? lerData(event.end_date) : (defaultDate ?? ""));
  const [startTime, setStartTime] = useState(
    event && !event.all_day ? horaCivil(event.start_date, fuso) : HORA_INICIAL,
  );
  const [endTime, setEndTime] = useState(
    event && !event.all_day ? horaCivil(event.end_date, fuso) : HORA_FINAL,
  );
  const [saving, setSaving] = useState(false);

  const fimDoEvento = endDate || startDate;
  /*
    O fim vem DEPOIS do início — a mesma regra da API, que recusa duração zero.
    A tela confere antes para travar o botão e dizer por quê; quem decide
    continua sendo o servidor, e a recusa dele chega pelo `toastApiError`.

    Cada recusa vai para o CAMPO que a causa. A revisão achou a data de fim errada
    marcando a hora de fim como inválida: quem estava na data não ouvia erro
    nenhum, e quem corrigia a hora não via o erro sair.
  */
  const instanteDoInicio = diaInteiro ? null : instanteDe(startDate, startTime, fuso);
  const instanteDoFim = diaInteiro ? null : instanteDe(fimDoEvento, endTime, fuso);
  const dataDoFimAntes = !!startDate && fimDoEvento < startDate;
  // `instanteDe` devolve null para hora vazia: um Backspace no campo de hora
  // deixa o valor "", e antes isso derrubava a tela inteira.
  const horaDoInicioFalta = !diaInteiro && !!startDate && instanteDoInicio === null;
  const horaDoFimFalta = !diaInteiro && !!startDate && !dataDoFimAntes && instanteDoFim === null;
  const horasForaDeOrdem =
    !diaInteiro && !dataDoFimAntes && instanteDoInicio !== null && instanteDoFim !== null &&
    instanteDoFim <= instanteDoInicio;
  const podeSalvar =
    !!title.trim() && !!startDate && !dataDoFimAntes &&
    !horaDoInicioFalta && !horaDoFimFalta && !horasForaDeOrdem;

  /*
    O instante que ninguém mexeu volta como estava.

    Recalcular a partir do "HH:MM" mostrado reescreve o instante gravado — e na
    hora que se repete no fim do horário de verão, a leitura convencional é a
    PRIMEIRA ocorrência: o evento recuava uma hora e mudava de duração só por ter
    sido aberto e salvo. Achado da revisão.
  */
  const intacto = (instante: string, dia: string, hora: string) =>
    !!event && !event.all_day && !diaInteiro &&
    chaveCivil(instante, fuso) === dia && horaCivil(instante, fuso) === hora;

  const corDoTipo = tipos.find((t) => t.value === eventType)?.color;

  async function handleSave() {
    if (!podeSalvar) return;
    setSaving(true);
    /*
      `all_day` vai SEMPRE, e a cor não vai nunca.

      A API infere dia inteiro quando a chave não vem e as bordas são 00:00:00 e
      23:59:59 (#17) — regra feita para a tela antiga. Esta diz o que quer, e
      explícito vence. A cor saiu do contrato no #18: vem do tipo.

      Dia inteiro manda a data à meia-noite UTC dos dois lados; a API deriva as
      bordas do dia. Com hora, o relógio digitado vira instante no fuso de quem
      digitou — e sem segundos, para nunca fabricar a pegada do #17.
    */
    const payload: CalendarEventPayload = diaInteiro
      ? {
          title: title.trim(),
          description: description.trim() || null,
          event_type: eventType,
          start_date: `${startDate}T00:00:00Z`,
          end_date: `${fimDoEvento}T00:00:00Z`,
          all_day: true,
        }
      : {
          title: title.trim(),
          description: description.trim() || null,
          event_type: eventType,
          start_date:
            event && intacto(event.start_date, startDate, startTime)
              ? event.start_date
              : instanteDoInicio!,
          end_date:
            event && intacto(event.end_date, fimDoEvento, endTime)
              ? event.end_date
              : instanteDoFim!,
          all_day: false,
        };
    try {
      if (event) {
        await updateCalendarEvent(event.id, payload);
        toast.success("Evento atualizado!");
      } else {
        await createCalendarEvent(payload);
        toast.success("Evento criado!");
      }
      onSaved();
      onClose();
    } catch (err) {
      // Era "Erro ao salvar evento." para qualquer recusa. A API diz o motivo —
      // fim antes do início, fuso desconhecido —, e ele precisa chegar a quem salvou.
      toastApiError(err, "Não foi possível salvar o evento.");
      // 404: outra pessoa já removeu o evento. Deixar o modal aberto faria cada
      // novo "Salvar" repetir a recusa, com o evento ainda desenhado na grade.
      if (statusDoErro(err) === 404) {
        onSaved();
        onClose();
      }
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
          {/* O rótulo precisa estar LIGADO ao campo: solto, ele fica só POR
              CIMA dele, e quem usa leitor de tela ouve "caixa de combinação"
              sem saber de quê. Item fixo do CHECKLIST-29.
              São duas ligações, e cada uma serve a uma ponta. O par
              `htmlFor`/`id` é o CLIQUE: clicar no rótulo foca o campo. O
              `aria-labelledby` é o NOME, e passou a ser obrigatório aqui
              quando o alvo deixou de ser um `<select>`: o `<label for>` nomeia
              sozinho os elementos rotuláveis, e o gatilho é um `<button>`,
              cujo nome a especificação manda tirar do CONTEÚDO — que aqui é o
              tipo escolhido. Sem esta linha o campo se anunciaria "Reunião",
              sem dizer reunião de quê. */}
          <label
            id="evento-tipo-rotulo"
            htmlFor="evento-tipo"
            className="text-xs font-medium text-conteudo-muted"
          >
            Tipo
          </label>
          <SelectMenu
            id="evento-tipo"
            aria-labelledby="evento-tipo-rotulo"
            value={eventType}
            onChange={(v) => setEventType(v as CalendarEventType)}
            options={(Object.keys(EVENT_TYPE_LABELS) as CalendarEventType[]).map((t) => ({
              value: t,
              label: EVENT_TYPE_LABELS[t],
            }))}
            className="w-full"
          />
          {/*
            No lugar das dezesseis fichas, a cor que o tipo vai ter — e a frase que
            diz por que não há escolha. Sem a frase, quem procurava as fichas
            acharia que elas sumiram por defeito. A amostra é reforço: o que
            informa é o tipo escrito no seletor.
          */}
          {corDoTipo && (
            <p className="flex items-center gap-1.5 pt-0.5 text-xs text-conteudo-muted">
              <span
                data-testid="cor-do-tipo"
                aria-hidden="true"
                className="h-2.5 w-2.5 shrink-0 rounded-full ring-1 ring-inset ring-borda-control"
                style={{ backgroundColor: corDoTipo }}
              />
              A cor do evento vem do tipo.
            </p>
          )}
        </div>

        <Switch checked={diaInteiro} onChange={setDiaInteiro} label="Dia inteiro" />

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
            error={dataDoFimAntes ? "O fim precisa ser depois do início." : undefined}
          />
        </div>

        {!diaInteiro && (
          <div className="grid grid-cols-2 gap-3">
            {/*
              `step={60}`: minutos, sem segundos. O backend (#17) infere dia
              inteiro quando o fim é 23:59:59 com os segundos cravados, e um campo
              que aceitasse segundos poderia fabricar essa pegada por acidente.
            */}
            <Input
              label="Hora de início"
              type="time"
              step={60}
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              error={horaDoInicioFalta ? "Informe a hora de início." : undefined}
            />
            <Input
              label="Hora de fim"
              type="time"
              step={60}
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              error={
                horaDoFimFalta
                  ? "Informe a hora de fim."
                  : horasForaDeOrdem
                    ? "O fim precisa ser depois do início."
                    : undefined
              }
            />
          </div>
        )}

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
          disabled={!podeSalvar}
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
  fuso: string;
  hoje: string;
  canEdit: boolean;
  selectedDay: number | null;
  onSelectDay: (day: number) => void;
  onEventClick: (event: CalendarEvent) => void;
}

function CalendarGrid({ year, month, events, fuso, hoje, canEdit, selectedDay, onSelectDay, onEventClick }: CalendarGridProps) {
  // Aritmética de data civil, sem fuso: o dia 1º cai no mesmo dia da semana em
  // qualquer lugar do mundo. Com `new Date(ano, mês, 1).getDay()` a conta usava o
  // fuso da máquina, e a grade dependia de onde a tela abria.
  const daysInMonth = diasNoMes(year, month);
  const firstDay = diaDaSemana(chaveDoDia(year, month, 1));

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

          const chave = chaveDoDia(year, month, day);
          const isToday = chave === hoje;
          const isSelected = selectedDay === day;
          const isWeekend = (firstDay + day - 1) % 7 === 0 || (firstDay + day - 1) % 7 === 6;
          const dayEvents = events
            .filter((e) => ocupaODia(e, chave, fuso))
            .sort((a, b) => chaveDeOrdem(a, fuso).localeCompare(chaveDeOrdem(b, fuso)));

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
                {dayEvents.slice(0, 3).map((e) => {
                  // A hora aparece só no dia em que o evento COMEÇA. No dia
                  // seguinte de um plantão que atravessa a meia-noite, "22:00"
                  // diria que ele começa de novo.
                  const comecaHoje = !e.all_day && chaveCivil(e.start_date, fuso) === chave;
                  return (
                    <div
                      key={e.id}
                      onClick={(ev) => { ev.stopPropagation(); if (canEdit) onEventClick(e); }}
                      className="flex items-center gap-1 text-[10px] leading-tight rounded-md px-1.5 py-0.5 truncate cursor-pointer hover:opacity-80 transition-opacity"
                      // O fundo vem da API — dado, não token —, então o texto por
                      // cima não pode ser fixo. Quem escolhe é a luminância, uma
                      // cor de cada vez.
                      style={{
                        backgroundColor: e.color,
                        color: readableTextColor(e.color),
                      }}
                      title={e.title}
                    >
                      {comecaHoje && <span className="font-semibold">{horaCivil(e.start_date, fuso)}</span>}
                      {e.title}
                      {/* O tipo em texto. Com a cor derivada do tipo e a legenda de
                          volta, a cor passou a CARREGAR o tipo — sem este texto ela
                          seria a única portadora, que é a regra do §29. No chip não
                          cabe visível; o detalhe do dia o mostra por extenso. */}
                      <span className="sr-only"> — {EVENT_TYPE_LABELS[e.event_type]}</span>
                    </div>
                  );
                })}
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

// ── Legend ────────────────────────────────────────────────────

/**
 * A legenda dos tipos, de volta ao rodapé do calendário.
 *
 * Saiu em 04/08/2026 (`2a300e4`), a pedido, quando a cor era livre — e nessa época
 * ela mentia: a legenda dizia que Prazo era âmbar, e o prazo podia estar em roxo.
 * Com a cor derivada do tipo (#18) ela passa a dizer a verdade, e é o que o
 * operador procurava.
 *
 * As cores vêm da API; os nomes, da tela. Sem o mapa, não há legenda — não uma
 * legenda com cores inventadas.
 */
function Legend({ tipos }: { tipos: CalendarEventTypeColor[] }) {
  if (tipos.length === 0) return null;
  return (
    <ul aria-label="Legenda dos tipos de evento" className="flex flex-wrap gap-x-4 gap-y-2 px-1">
      {tipos.map((t) => (
        <li key={t.value} className="flex items-center gap-1.5 text-xs text-conteudo-muted">
          <span
            data-testid="cor-da-legenda"
            aria-hidden="true"
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: t.color }}
          />
          {EVENT_TYPE_LABELS[t.value] ?? t.value}
        </li>
      ))}
    </ul>
  );
}

// ── Day Detail ────────────────────────────────────────────────

interface DayDetailProps {
  chave: string;
  events: CalendarEvent[];
  fuso: string;
  canEdit: boolean;
  onAdd: () => void;
  onEdit: (event: CalendarEvent) => void;
  onDelete: (event: CalendarEvent) => void;
  onClose: () => void;
}

function DayDetail({ chave, events, fuso, canEdit, onAdd, onEdit, onDelete, onClose }: DayDetailProps) {
  const dia = Number(chave.slice(8, 10));
  const mes = Number(chave.slice(5, 7)) - 1;
  return (
    // `section` com nome: o detalhe do dia vira uma REGIÃO que o leitor de tela
    // lista e alcança pelo nome, em vez de um bloco solto depois da grade.
    <section
      aria-label={`${dia} de ${MONTHS[mes]}`}
      className="rounded-xl border border-borda bg-surface p-4 space-y-3"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-conteudo-muted font-medium uppercase tracking-wide">
            {WEEKDAYS_FULL[diaDaSemana(chave)]}
          </p>
          <p className="text-lg font-bold text-conteudo-heading">
            {dia} de {MONTHS[mes]}
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
                <p className="text-xs text-conteudo-muted mt-0.5">{descreveHorario(e, fuso)}</p>
                {e.description && (
                  <p className="text-xs text-conteudo-muted truncate mt-0.5">{e.description}</p>
                )}
                <p className="text-[10px] text-conteudo-muted mt-0.5">{autoria(e)}</p>
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
    </section>
  );
}

// ── Upcoming Events ───────────────────────────────────────────

function UpcomingList({ events, fuso, falhou }: { events: CalendarEvent[]; fuso: string; falhou: boolean }) {
  // Lista que não carregou não pode se passar por lista vazia: "Nenhum evento
  // próximo" numa falha de rede faria alguém achar que a agenda está livre.
  if (falhou) {
    return <p className="text-xs text-conteudo-muted py-2">Não foi possível carregar os próximos eventos.</p>;
  }

  const agora = new Date();
  /*
    `jaTerminou`, e não `end_date >= agora`. O fim de um dia inteiro é 23:59:59Z,
    que em Recife é 20:59: comparado como instante, o treinamento de hoje sumia da
    lista às nove da noite. E a ordem é a do calendário, não a do instante.
  */
  const upcoming = events
    .filter((e) => !jaTerminou(e, agora, fuso))
    .sort((a, b) => chaveDeOrdem(a, fuso).localeCompare(chaveDeOrdem(b, fuso)))
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
            {/* O tipo visível ao lado da data: o ponto de cor não pode ser o único
                portador dele (§29). */}
            <p className="text-[10px] text-conteudo-muted mt-0.5">
              {descreveComData(e, fuso)} · {EVENT_TYPE_LABELS[e.event_type]}
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

  // O fuso de quem olha, lido uma vez. Tudo o que é "que dia é" passa por ele —
  // inclusive "hoje", que com `new Date().getDate()` seria o dia da máquina.
  const fuso = useMemo(() => fusoDoNavegador(), []);
  const hoje = chaveCivil(new Date(), fuso);
  const anoDeHoje = Number(hoje.slice(0, 4));
  const mesDeHoje = Number(hoje.slice(5, 7)) - 1;
  const diaDeHoje = Number(hoje.slice(8, 10));
  const anos = Array.from({ length: 8 }, (_, i) => anoDeHoje - 1 + i);

  const [year, setYear] = useState(anoDeHoje);
  const [month, setMonth] = useState(mesDeHoje);
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [eventosDoMes, setEventosDoMes] = useState<CalendarEvent[]>([]);
  const [todos, setTodos] = useState<CalendarEvent[]>([]);
  const [todosFalharam, setTodosFalharam] = useState(false);
  const [tipos, setTipos] = useState<CalendarEventTypeColor[]>([]);
  const [loading, setLoading] = useState(true);
  const [mesFalhou, setMesFalhou] = useState(false);
  const [dialog, setDialog] = useState<DialogState>({ open: false });
  const [deleteTarget, setDeleteTarget] = useState<CalendarEvent | null>(null);
  const [deleting, setDeleting] = useState(false);

  /*
    A grade pede à API o MÊS visível, com o fuso — é a API que decide quais
    eventos pertencem ao mês, no relógio de quem olha. O mês da API vai de 1 a 12.

    O contador descarta resposta velha: trocar de mês duas vezes seguidas dispara
    duas consultas, e sem ele a do mês anterior, se chegasse por último, pintaria
    a grade do mês novo com os eventos do velho.
  */
  const pedidoDoMes = useRef(0);
  const carregarMes = useCallback(async () => {
    const pedido = ++pedidoDoMes.current;
    setLoading(true);
    try {
      const data = await getCalendarEvents(year, month + 1, fuso);
      if (pedido === pedidoDoMes.current) {
        setEventosDoMes(data);
        setMesFalhou(false);
      }
    } catch {
      /*
        A grade que não carregou precisa DIZER, e não se passar por vazia. Era um
        toast passageiro com a grade limpa por baixo, e a lateral mostrando evento
        no mesmo dia. E a lista é esvaziada: sem isso, depois de excluir com a
        recarga falhando, o evento apagado continuava desenhado. Achado da revisão.
      */
      if (pedido === pedidoDoMes.current) {
        setEventosDoMes([]);
        setMesFalhou(true);
      }
    } finally {
      if (pedido === pedidoDoMes.current) setLoading(false);
    }
  }, [year, month, fuso]);

  /*
    A lateral olha além do mês — a lista de próximos e o mapa do ano —, e a API
    não tem consulta de ano nem de próximos. Por isso ela faz a consulta sem mês.
  */
  const pedidoDosTodos = useRef(0);
  const carregarTodos = useCallback(async () => {
    // O mesmo descarte da grade. A consulta da lateral é a de TODOS os eventos,
    // a mais lenta, e sem ele a resposta de antes de uma exclusão, chegando por
    // último, trazia o evento apagado de volta. Achado da revisão.
    const pedido = ++pedidoDosTodos.current;
    try {
      const data = await getCalendarEvents();
      if (pedido === pedidoDosTodos.current) {
        setTodos(data);
        setTodosFalharam(false);
      }
    } catch {
      if (pedido === pedidoDosTodos.current) setTodosFalharam(true);
    }
  }, []);

  useEffect(() => { carregarMes(); }, [carregarMes]);
  useEffect(() => { carregarTodos(); }, [carregarTodos]);
  useEffect(() => {
    getCalendarEventTypes().then(setTipos).catch(() => setTipos([]));
  }, []);

  function recarregar() {
    carregarMes();
    carregarTodos();
  }

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
    setYear(anoDeHoje);
    setMonth(mesDeHoje);
    setSelectedDay(diaDeHoje);
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
      recarregar();
      setSelectedDay(null);
    } catch (err) {
      toastApiError(err, "Não foi possível remover o evento.");
      // 404: outra pessoa já removeu. O diálogo aberto repetiria a recusa a cada
      // clique, com o evento ainda na grade. Fecha e busca de novo.
      if (statusDoErro(err) === 404) {
        setDeleteTarget(null);
        recarregar();
      }
    } finally {
      setDeleting(false);
    }
  }

  const ordenar = (lista: CalendarEvent[]) =>
    [...lista].sort((a, b) => chaveDeOrdem(a, fuso).localeCompare(chaveDeOrdem(b, fuso)));

  const chaveSelecionada = selectedDay ? chaveDoDia(year, month, selectedDay) : null;
  const selectedDayEvents = chaveSelecionada
    ? ordenar(eventosDoMes.filter((e) => ocupaODia(e, chaveSelecionada, fuso)))
    : [];
  const monthEvents = ordenar(eventosDoMes.filter((e) => ocupaOMes(e, year, month, fuso)));

  return (
    <div className="space-y-5 pb-10">
      {dialog.open && (
        <EventDialog
          event={dialog.event}
          defaultDate={dialog.date}
          fuso={fuso}
          tipos={tipos}
          onClose={() => setDialog({ open: false })}
          onSaved={recarregar}
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

        {/* O valor do menu é texto, como era o do `<option>`. O estado continua
            número — é o `Number` da volta que o mantém assim. */}
        <SelectMenu
          value={String(month)}
          aria-label="Mês"
          onChange={(v) => { setMonth(Number(v)); setSelectedDay(null); }}
          options={MONTHS.map((m, i) => ({ value: String(i), label: m }))}
          className="h-8 font-semibold"
        />

        <SelectMenu
          value={String(year)}
          aria-label="Ano"
          onChange={(v) => { setYear(Number(v)); setSelectedDay(null); }}
          options={anos.map((y) => ({ value: String(y), label: String(y) }))}
          className="h-8 font-semibold"
        />

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
          ) : mesFalhou ? (
            <Alert variant="danger">Não foi possível carregar os eventos deste mês.</Alert>
          ) : (
            <CalendarGrid
              year={year}
              month={month}
              events={eventosDoMes}
              fuso={fuso}
              hoje={hoje}
              canEdit={canEdit}
              selectedDay={selectedDay}
              onSelectDay={setSelectedDay}
              onEventClick={(e) => setDialog({ open: true, event: e })}
            />
          )}

          <Legend tipos={tipos} />

          {/* Day detail */}
          {/* Sem a grade, o detalhe diria "Nenhum evento neste dia." de um dia que
              ninguém conseguiu consultar. */}
          {chaveSelecionada && !mesFalhou && (
            <DayDetail
              chave={chaveSelecionada}
              events={selectedDayEvents}
              fuso={fuso}
              canEdit={canEdit}
              onAdd={() => setDialog({ open: true, date: chaveSelecionada })}
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
            <UpcomingList events={todos} fuso={fuso} falhou={todosFalharam} />
          </div>

          {/* Mini month map */}
          <div className="rounded-xl border border-borda bg-surface p-4 space-y-3">
            <h3 className="text-sm font-semibold text-conteudo">Meses do ano</h3>
            <div className="grid grid-cols-3 gap-1.5">
              {MONTHS_SHORT.map((m, i) => {
                // O mesmo corte da grade: dia inteiro pela data, evento com hora
                // pelo instante no fuso de quem olha. Com `getUTCMonth()`, o
                // evento das 22:00 do último dia marcava o mês seguinte.
                const hasEvents = todos.some((e) => ocupaOMes(e, year, i, fuso));
                const isCurrent = i === month;
                const isCurrentMonth = i === mesDeHoje && year === anoDeHoje;
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
          {canEdit && monthEvents.length > 0 && (
            <div className="rounded-xl border border-borda bg-surface p-4 space-y-3">
              <h3 className="text-sm font-semibold text-conteudo">
                Gerenciar eventos — {MONTHS_SHORT[month]}
              </h3>
              <div className="space-y-1.5 max-h-[168px] overflow-y-auto pr-0.5">
                {monthEvents.slice(0, 4).map((e) => (
                  <div key={e.id} className="flex items-center gap-2 rounded-lg bg-surface-elevated/30 px-2.5 py-1.5">
                    <div className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: e.color }} />
                    <span className="flex-1 text-xs text-conteudo truncate">
                      {e.title}
                      <span className="sr-only"> — {EVENT_TYPE_LABELS[e.event_type]}</span>
                    </span>
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
          )}
        </div>
      </div>
    </div>
  );
}
