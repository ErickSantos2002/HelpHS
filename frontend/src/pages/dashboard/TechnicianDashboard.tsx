import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Alert, Icon, KpiCard, Select, Spinner, StatusBadge } from "../../components/ui";
import { cn } from "../../lib/utils";
import { CROMO, COR_SERIE_TEMPORAL, ENVOLTORIO_DICA, ESTILO_DICA } from "../../lib/grafico";
import { PRIORIDADE } from "../../lib/prioridade";
import { useAuth } from "../../contexts/AuthContext";
import { getDashboardStats } from "../../services/dashboardService";
import { getTechnicianDetailReport, type TechnicianDetailReport } from "../../services/reportService";
import { getTickets, type Ticket } from "../../services/ticketService";

// ── Period config (same as AdminDashboard) ────────────────────

type PeriodKey = "hoje" | "ontem" | "semana" | "mes" | "mes-passado" | "trimestre" | "ano" | "custom";

const PERIOD_OPTIONS: { key: PeriodKey; label: string; days: number }[] = [
  { key: "hoje",        label: "Hoje",            days: 1   },
  { key: "ontem",       label: "Ontem",           days: 2   },
  { key: "semana",      label: "Esta Semana",      days: 7   },
  { key: "mes",         label: "Este Mês",         days: 30  },
  { key: "mes-passado", label: "Mês Passado",      days: 60  },
  { key: "trimestre",   label: "Este Trimestre",   days: 90  },
  { key: "ano",         label: "Este Ano",         days: 365 },
  { key: "custom",      label: "Personalizado",    days: 0   },
];

function getDefaultCustomDates() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  return {
    start: start.toISOString().slice(0, 10),
    end:   end.toISOString().slice(0, 10),
  };
}

function customDays(start: string, end: string) {
  return Math.max(1, Math.ceil((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 1);
}

// ── Helpers ───────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function formatHours(h: number | null): string {
  if (h == null) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)} dias`;
}

// ── Sub-components ────────────────────────────────────────────

function TicketRow({ ticket, showTech }: { ticket: Ticket; showTech?: boolean }) {
  const navigate = useNavigate();
  const hasBreach = ticket.sla_response_breach || ticket.sla_resolve_breach;
  // `PRIORITY_DOT` era um sexto mapa de prioridade, com "médio" em
  // `bg-primary` — divergindo do canônico (`bg-info`, no `lib/prioridade.ts`).
  // Sai o mapa local; o ponto usa a mesma fonte que o selo e o gráfico.
  const prioridade = PRIORIDADE[ticket.priority];

  return (
    <button
      onClick={() => navigate(`/tickets/${ticket.id}`)}
      className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-elevated transition-colors"
    >
      {/* O ponto nunca pode ser a única fonte da prioridade (regra do
          `lib/prioridade.ts`): fica decorativo, e o rótulo entra em sr-only —
          antes não existia nenhum dos dois, e quem não distinguisse a cor
          não tinha a informação de jeito nenhum. */}
      <div
        aria-hidden="true"
        className={cn("w-1.5 h-1.5 rounded-full shrink-0", prioridade?.ponto ?? "bg-borda-control")}
      />
      <span className="sr-only">Prioridade {prioridade?.rotulo ?? ticket.priority}.</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-xs font-mono text-conteudo-muted">{ticket.protocol}</span>
          {hasBreach && (
            <span className="text-[10px] font-bold text-on-tint-danger bg-tint-danger px-1.5 py-0.5 rounded">SLA</span>
          )}
        </div>
        <p className="text-sm text-conteudo truncate">{ticket.title}</p>
        {showTech && ticket.assignee_name && (
          <p className="text-xs text-conteudo-muted mt-0.5">{ticket.assignee_name}</p>
        )}
      </div>
      <StatusBadge status={ticket.status} />
    </button>
  );
}

function TicketListCard({
  title, count, tickets, emptyMsg, showTech,
}: {
  title: string; count: number; tickets: Ticket[]; emptyMsg: string; showTech?: boolean;
}) {
  return (
    <div className="rounded-xl bg-surface border border-borda overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-borda/60 shrink-0">
        <p className="text-sm font-semibold text-conteudo">{title}</p>
        <span className="text-xs font-medium text-conteudo-muted bg-surface-elevated px-2 py-0.5 rounded-full">{count}</span>
      </div>
      {tickets.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 gap-2">
          <div className="w-8 h-8 rounded-full bg-surface-elevated flex items-center justify-center">
            <Icon name="check" size={16} strokeWidth={1.5} className="text-conteudo-muted" />
          </div>
          <p className="text-sm text-conteudo-muted">{emptyMsg}</p>
        </div>
      ) : (
        <div className="overflow-y-auto max-h-[168px] divide-y divide-borda/60">
          {tickets.map((t) => <TicketRow key={t.id} ticket={t} showTech={showTech} />)}
        </div>
      )}
    </div>
  );
}

// ── TechnicianDashboard ───────────────────────────────────────

interface TechGroup { name: string; tickets: Ticket[] }

export default function TechnicianDashboard() {
  const { user } = useAuth();

  // Period state
  const [periodKey, setPeriodKey] = useState<PeriodKey>("mes");
  const [customDates, setCustomDates] = useState(getDefaultCustomDates);

  // O recuo existe porque `find` devolve `undefined` para chave desconhecida,
  // e o `!` que estava aqui lia `days` dela — a tela quebrava inteira. O
  // caminho conhecido era a opção de limpar do filtro antigo, que devolvia
  // `""`; ela saiu na D9.2, mas o estouro nunca dependeu dela.
  //
  // Recuo para 30 e não para o primeiro da lista: 30 é o padrão declarado no
  // backend (`period: Annotated[int, Query(ge=1, le=365)] = 30`), ou seja, o
  // que o servidor faria sozinho se o parâmetro não fosse mandado. E é por
  // esse mesmo `ge=1` que **não existe "todo o período"**: a opção de limpar
  // não tem para onde apontar, e por isso saiu em vez de virar estado válido.
  const activePeriod = periodKey === "custom"
    ? customDays(customDates.start, customDates.end)
    : (PERIOD_OPTIONS.find((p) => p.key === periodKey)?.days ?? 30);

  const periodLabel = PERIOD_OPTIONS.find((p) => p.key === periodKey)?.label ?? "";

  // Data
  const [detail, setDetail]       = useState<TechnicianDetailReport | null>(null);
  const [openCount, setOpenCount] = useState(0);
  const [myTickets, setMyTickets] = useState<Ticket[]>([]);
  const [queue, setQueue]         = useState<Ticket[]>([]);
  const [teamGroups, setTeamGroups] = useState<TechGroup[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);


  useEffect(() => {
    if (!user) return;
    setLoading(true);
    const emptyDetail: TechnicianDetailReport = {
      period_days: activePeriod,
      technician_id: user.id,
      technician_name: user.name,
      total_assigned: 0, resolved: 0, in_progress: 0, open_count: 0,
      sla_breached: 0, sla_compliance_rate: 100,
      avg_resolution_hours: null, csat_average: null, csat_count: 0,
      tickets_by_day: [],
    };
    Promise.all([
      getTechnicianDetailReport(activePeriod).catch(() => emptyDetail),
      getDashboardStats(),
      getTickets({ assignee_id: user.id, limit: 200 }),
      getTickets({ status: "open", limit: 200 }),
      Promise.all([
        getTickets({ status: "open", limit: 200 }),
        getTickets({ status: "in_progress", limit: 200 }),
        getTickets({ status: "awaiting_client", limit: 200 }),
        getTickets({ status: "awaiting_technical", limit: 200 }),
      ]).then((r) => r.flatMap((x) => x.items)),
    ])
      .then(([detailData, statsData, myData, queueData, activeTickets]) => {
        setDetail(detailData);
        setOpenCount(statsData.tickets.open);
        setMyTickets(myData.items);
        setQueue(queueData.items);

        const map = new Map<string, TechGroup>();
        for (const t of activeTickets) {
          if (!t.assignee_id || t.assignee_id === user.id) continue;
          if (!map.has(t.assignee_id)) map.set(t.assignee_id, { name: t.assignee_name ?? "Técnico", tickets: [] });
          map.get(t.assignee_id)!.tickets.push(t);
        }
        setTeamGroups([...map.values()].sort((a, b) => a.name.localeCompare(b.name)));
      })
      .catch(() => setError("Não foi possível carregar os tickets."))
      .finally(() => setLoading(false));
  }, [user, activePeriod]);

  if (loading) return <div className="flex h-64 items-center justify-center"><Spinner size="lg" /></div>;
  if (error)   return <Alert variant="danger">{error}</Alert>;
  if (!detail) return <Alert variant="danger">Erro ao carregar dados.</Alert>;

  const myActiveCount = myTickets.filter((t) => t.status === "open" || t.status === "in_progress").length;
  const myBreachCount = myTickets.filter((t) => t.sla_response_breach || t.sla_resolve_breach).length;
  const teamAllTickets = teamGroups.flatMap((g) => g.tickets);

  /*
   * Os tres icones dos indicadores ficaram como `<svg>` solto na primeira
   * passada desta tela, porque nenhum deles tinha par no pacote — e aquela
   * passada foi ANTES da **E21**.
   *
   * Hoje `clipboard` e `inbox` existem e batem caractere a caractere; foi
   * esta tela, entre outras, que os pediu. O terceiro e o triangulo de aviso,
   * unificado com `warning` pelo significado — o mesmo caso que a E21 nomeia
   * dez vezes.
   *
   * Fica a licao de ordem: tela migrada antes de uma emenda de icone precisa
   * de uma segunda olhada depois dela, senao o `<svg>` solto vira permanente
   * por motivo que ja deixou de existir.
   */
  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-conteudo-heading">Dashboard</h1>
          <p className="mt-0.5 text-sm text-conteudo-muted">
            Olá, <span className="font-semibold text-conteudo">{user?.name?.split(" ")[0]}</span>! Aqui está sua fila de hoje.
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Period filter */}
          {/* D9.2 — oito períodos fixos no código: lista curta e conhecida,
              logo `<select>` nativo.

              Sem `placeholder`, e isso conserta uma queda. A linha de limpar do
              `FilterSelect` devolvia `""`, e logo abaixo
              `PERIOD_OPTIONS.find((p) => p.key === periodKey)!.days` lia `days`
              de `undefined`. O `<select>` nativo não tem linha de limpar, e o
              período passa a ser o que sempre foi: uma escolha obrigatória.

              O rótulo é `sr-only`: sem ele o filtro se anunciava "Este Mês". */}
          <span id="rotulo-filtro-periodo" className="sr-only">
            Período
          </span>
          <Select
            id="filtro-periodo"
            aria-labelledby="rotulo-filtro-periodo"
            value={periodKey}
            onChange={(e) => setPeriodKey(e.target.value as PeriodKey)}
            options={PERIOD_OPTIONS.map((p) => ({ value: p.key, label: p.label }))}
          />

          {/* Custom date range */}
          {periodKey === "custom" && (
            <div className="flex h-9 items-center gap-1.5 rounded-lg border border-borda/60 bg-surface-elevated px-3 text-sm">
              <Icon name="calendar" size={14} strokeWidth={2} className="shrink-0 text-conteudo-muted" />
              <input
                type="date"
                value={customDates.start}
                max={customDates.end}
                onChange={(e) => setCustomDates((d) => ({ ...d, start: e.target.value }))}
                className="bg-transparent text-conteudo text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
              />
              <span className="text-conteudo-muted text-xs">até</span>
              <input
                type="date"
                value={customDates.end}
                min={customDates.start}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setCustomDates((d) => ({ ...d, end: e.target.value }))}
                className="bg-transparent text-conteudo text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
              />
            </div>
          )}
        </div>
      </div>

      {/* ── KPI Row ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Meus tickets ativos"
          value={myActiveCount}
          sub="Abertos + em andamento"
          tone={myActiveCount > 0 ? "info" : "neutral"}
          icon={<Icon name="clipboard" size={20} />}
        />
        <KpiCard
          label="Fila geral aberta"
          value={openCount}
          sub="Aguardando atendimento"
          tone="neutral"
          icon={<Icon name="inbox" size={20} />}
        />
        <KpiCard
          label="SLA em risco"
          value={myBreachCount}
          sub="Nos meus tickets"
          tone={myBreachCount > 0 ? "danger" : "neutral"}
          icon={<Icon name="warning" size={20} />}
        />
        <KpiCard
          label="Meu CSAT"
          value={detail.csat_average != null ? `${detail.csat_average.toFixed(1)} / 10` : "—"}
          sub={`${detail.csat_count} avaliações · ${periodLabel}`}
          tone="warning"
          icon={<Icon name="star" />}
        />
      </div>

      {/* ── Charts + stats ───────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Area chart */}
        <div className="lg:col-span-2 rounded-xl bg-surface border border-borda overflow-hidden">
          <div className="px-5 py-4 border-b border-borda/60">
            <p className="text-sm font-semibold text-conteudo">
              Meus atendimentos por dia — {periodLabel}
            </p>
          </div>
          <div className="p-5">
            {detail.tickets_by_day.length === 0 ? (
              <p className="text-conteudo-muted text-sm py-8 text-center">Sem dados para o período</p>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                {/* Série temporal de medida única — chamados por dia —, então uma
                    cor só, `COR_SERIE_TEMPORAL`. Era `#0ea5e9` cravado, a quarta
                    cor diferente entre cinco gráficos da mesma natureza. */}
                <AreaChart data={detail.tickets_by_day} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="techGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={COR_SERIE_TEMPORAL} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={COR_SERIE_TEMPORAL} stopOpacity={0}   />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: CROMO.eixo, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: CROMO.eixo, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={ESTILO_DICA} wrapperStyle={ENVOLTORIO_DICA} labelFormatter={(v) => fmtDate(String(v))} formatter={(v) => [v, "Tickets"]} />
                  <Area type="monotone" dataKey="count" stroke={COR_SERIE_TEMPORAL} strokeWidth={2} fill="url(#techGradient)" dot={false} activeDot={{ r: 4, fill: COR_SERIE_TEMPORAL }} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Personal stats summary */}
        <div className="rounded-xl bg-surface border border-borda overflow-hidden">
          <div className="px-5 py-4 border-b border-borda/60">
            <p className="text-sm font-semibold text-conteudo">
              Meu desempenho — {periodLabel}
            </p>
          </div>
          <div className="p-5 space-y-4">
            {[
              { label: "Atribuídos",        value: detail.total_assigned },
              { label: "Resolvidos",         value: detail.resolved },
              { label: "Em andamento",       value: detail.in_progress },
              { label: "SLA violados",       value: detail.sla_breached,                             danger: detail.sla_breached > 0 },
              { label: "Tempo médio",        value: formatHours(detail.avg_resolution_hours),        raw: true },
              { label: "Conformidade SLA",   value: `${detail.sla_compliance_rate.toFixed(0)}%`,     raw: true },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between">
                <span className="text-sm text-conteudo-muted">{item.label}</span>
                <span className={cn(
                  "text-sm font-semibold tabular-nums",
                  item.danger ? "text-on-tint-danger" : "text-conteudo",
                )}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Ticket lists ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TicketListCard
          title="Meus tickets"
          count={myTickets.length}
          tickets={myTickets}
          emptyMsg="Nenhum ticket atribuído"
        />
        <TicketListCard
          title="Tickets da equipe"
          count={teamAllTickets.length}
          tickets={teamAllTickets}
          emptyMsg="Nenhum ticket ativo na equipe"
          showTech
        />
        <TicketListCard
          title="Fila — Tickets abertos"
          count={queue.length}
          tickets={queue}
          emptyMsg="Fila limpa"
        />
      </div>
    </div>
  );
}
