import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, Cell,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Alert, FilterSelect, KpiCard, Spinner } from "../../components/ui";
import { cn } from "../../lib/utils";
import {
  CROMO, ESTILO_DICA, ENVOLTORIO_DICA, COR_SERIE_TEMPORAL,
} from "../../lib/grafico";
import { rotuloDeStatus, slotDeStatus, type TicketStatus } from "../../lib/status";
import { rotuloDePrioridade, graficoDePrioridade, type TicketPriority } from "../../lib/prioridade";
import { getDashboardStats, type DashboardStats } from "../../services/dashboardService";
import {
  getReports, getTechnicianListReport, getTechnicianDetailReport,
  type ReportData, type TechnicianListReport, type TechnicianDetailReport,
} from "../../services/reportService";

// ── Period config ─────────────────────────────────────────────

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
  const diff = new Date(end).getTime() - new Date(start).getTime();
  return Math.max(1, Math.ceil(diff / 86400000) + 1);
}

// ── Colors ────────────────────────────────────────────────────
//
// Os hexadecimais cravados por status/prioridade que viviam aqui
// (`STATUS_COLORS`, `PRIORITY_COLORS`) saíram: eram exatamente o mapa local
// que a E18 e o `lib/prioridade.ts` existem para substituir, e a rosca e a
// barra empilhada ficaram travadas até a E18 gravar `SLOT_DE_STATUS` — ver
// `lib/status.ts`. Cor de série por status vem de `slotDeStatus()`, por
// prioridade de `graficoDePrioridade()`; nenhuma das duas é reimplementada
// nesta tela.
//
// O `DashboardStats` funde `awaiting_client` e `awaiting_technical` num só
// número (`tickets.awaiting`) — fusão do backend, anterior a esta migração e
// fora do alcance dela consertar. Sem um `TicketStatus` próprio para o bloco
// fundido, ele usa o slot e o rótulo genérico "Aguardando" como aproximação;
// qual dos dois pesa mais aqui é decisão de desenho que este agente não toma
// (ver relato final).
type BlocoDeStatus = "open" | "in_progress" | "awaiting" | "resolved" | "closed" | "cancelled";

/** Os seis blocos que o `DashboardStats` expõe, na ordem do ciclo de vida. */
const BLOCOS_DE_STATUS: BlocoDeStatus[] = [
  "open", "in_progress", "awaiting", "resolved", "closed", "cancelled",
];

function corDoBlocoDeStatus(chave: TicketStatus | "awaiting"): string {
  return slotDeStatus(chave === "awaiting" ? "awaiting_client" : chave);
}
function rotuloDoBlocoDeStatus(chave: TicketStatus | "awaiting"): string {
  return chave === "awaiting" ? "Aguardando" : rotuloDeStatus(chave);
}

// ── Helpers ───────────────────────────────────────────────────

// `text-on-tint-*` e `bg-fill-*` no lugar da cor cheia de significado usada
// como texto (a reprovação da regra 2 — "danger"/"warning" sem sufixo de
// tinta) e de `bg-emerald-500` (paleta crua do Tailwind, regra 1, por cima de
// um caso que já tem token semântico próprio).
function slaColor(r: number) {
  return r >= 90 ? "text-on-tint-success" : r >= 70 ? "text-on-tint-warning" : "text-on-tint-danger";
}
function slaBg(r: number) {
  return r >= 90 ? "bg-fill-success" : r >= 70 ? "bg-fill-warning" : "bg-fill-danger";
}
function fmtHours(h: number | null) {
  if (h == null) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)} dias`;
}
function fmtDate(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

// ── KPI Card ──────────────────────────────────────────────────



// ── Status distribution bar ───────────────────────────────────

function StatusBar({ t }: { t: DashboardStats["tickets"] }) {
  const total = t.total || 1;
  const segs = BLOCOS_DE_STATUS
    .map((chave) => ({
      label: rotuloDoBlocoDeStatus(chave),
      value: t[chave],
      color: corDoBlocoDeStatus(chave),
    }))
    .filter((s) => s.value > 0);

  return (
    <div className="rounded-xl bg-surface border border-borda p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Distribuição de status</p>
      <div className="flex h-3 rounded-full overflow-hidden gap-px">
        {segs.map((s) => (
          <div
            key={s.label}
            style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.color }}
            title={`${s.label}: ${s.value}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3">
        {segs.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
            <span className="text-xs text-slate-500">
              {s.label}: <span className="font-semibold text-slate-700 dark:text-slate-200">{s.value}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Section card ──────────────────────────────────────────────

function SectionCard({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-surface border border-borda overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-borda/60">
        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</p>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

// ── AdminDashboard ────────────────────────────────────────────

export default function AdminDashboard() {
  // Period state
  const [periodKey, setPeriodKey] = useState<PeriodKey>("mes");
  const [customDates, setCustomDates] = useState(getDefaultCustomDates);

  // Technician filter
  const [selectedTechId, setSelectedTechId] = useState<string>("all");

  // Data
  const [stats, setStats]         = useState<DashboardStats | null>(null);
  const [report, setReport]       = useState<ReportData | null>(null);
  const [techList, setTechList]   = useState<TechnicianListReport | null>(null);
  const [techDetail, setTechDetail] = useState<TechnicianDetailReport | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  const activePeriod = periodKey === "custom"
    ? customDays(customDates.start, customDates.end)
    : PERIOD_OPTIONS.find((p) => p.key === periodKey)!.days;

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboardStats(),
      getReports({ period: activePeriod }),
      getTechnicianListReport(activePeriod),
    ])
      .then(([s, r, tl]) => { setStats(s); setReport(r); setTechList(tl); setTechDetail(null); })
      .catch(() => setError("Não foi possível carregar as estatísticas."))
      .finally(() => setLoading(false));
  }, [activePeriod]);

  useEffect(() => {
    if (selectedTechId === "all") { setTechDetail(null); return; }
    getTechnicianDetailReport(activePeriod, selectedTechId)
      .then(setTechDetail)
      .catch(() => setTechDetail(null));
  }, [selectedTechId, activePeriod]);

  // O cromo (eixo, grade, dica) e a cor da série temporal única vêm de
  // `lib/grafico.ts` — não mais de `theme === "dark" ? A : B` escrito à mão.
  // `var(--text-muted)` etc. já resolvem sozinhos por tema no CSS; escolher o
  // hexadecimal aqui em JS era reimplementar o seletor `.dark`, e sem essa
  // escolha o `useTheme()` desta tela deixou de ter uso.

  if (loading) return <div className="flex h-64 items-center justify-center"><Spinner size="lg" /></div>;
  if (error || !stats || !report) return <Alert variant="danger">{error ?? "Erro desconhecido."}</Alert>;

  const { tickets, surveys, sla } = stats;
  const avgRating = surveys.average_rating?.toFixed(1) ?? "—";

  const avgResolutionHours = (() => {
    if (!techList?.technicians.length) return null;
    const withData = techList.technicians.filter((t) => t.avg_resolution_hours != null);
    if (!withData.length) return null;
    return withData.reduce((s, t) => s + (t.avg_resolution_hours ?? 0), 0) / withData.length;
  })();

  const categoryData = [...(report.tickets_by_category ?? [])]
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
  const categoryMax = categoryData[0]?.count || 1;

  // Rótulo e cor por `lib/status.ts` / `SLOT_DE_STATUS` (E18) — nunca mapa
  // local. `name` é o que a legenda mostra: obrigatória num gráfico de status,
  // porque `--chart-*` é categórico e não diz sozinho "cancelado" a quem olha.
  const statusData = BLOCOS_DE_STATUS
    .map((chave) => ({
      chave,
      name: rotuloDoBlocoDeStatus(chave),
      value: tickets[chave],
      cor: corDoBlocoDeStatus(chave),
    }))
    .filter((d) => d.value > 0);

  // Rótulo e preenchimento por `lib/prioridade.ts` — a mesma fonte que o selo
  // e o ponto da lista usam. O rótulo passa a sair no feminino (E17: "Alta",
  // não "Alto"), que é a mesma palavra que o resto do sistema já usa.
  const priorityData = (
    [
      ["critical", tickets.by_priority_critical],
      ["high",     tickets.by_priority_high],
      ["medium",   tickets.by_priority_medium],
      ["low",      tickets.by_priority_low],
    ] as [TicketPriority, number][]
  ).map(([chave, value]) => ({
    name: rotuloDePrioridade(chave),
    value,
    cor: graficoDePrioridade(chave),
  }));

  const chartData      = techDetail ? techDetail.tickets_by_day  : report.tickets_by_day;
  const slaCompliance  = report.sla_compliance;
  const periodLabel    = PERIOD_OPTIONS.find((p) => p.key === periodKey)?.label ?? "";

  return (
    <div className="space-y-5">

      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-slate-100">Dashboard</h1>
          <p className="mt-0.5 text-sm text-slate-500">Visão geral do sistema de atendimento</p>
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Technician filter */}
          {techList && (
            <FilterSelect
              value={selectedTechId}
              onChange={setSelectedTechId}
              options={[
                { value: "all", label: "Todos os técnicos" },
                ...techList.technicians.map((t) => ({ value: t.technician_id, label: t.technician_name })),
              ]}
              placeholder="Todos os técnicos"
            />
          )}

          {/* Period filter */}
          <FilterSelect
            value={periodKey}
            onChange={(v) => setPeriodKey(v as PeriodKey)}
            options={PERIOD_OPTIONS.map((p) => ({ value: p.key, label: p.label }))}
            placeholder="Período"
          />

          {/* Custom date range */}
          {periodKey === "custom" && (
            <div className="flex h-9 items-center gap-1.5 rounded-lg border border-borda/60 bg-surface-elevated px-3 text-sm">
              <svg className="w-3.5 h-3.5 shrink-0 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
              <input
                type="date"
                value={customDates.start}
                max={customDates.end}
                onChange={(e) => setCustomDates((d) => ({ ...d, start: e.target.value }))}
                className="bg-transparent text-slate-700 dark:text-slate-300 text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
              />
              <span className="text-slate-500 text-xs">até</span>
              <input
                type="date"
                value={customDates.end}
                min={customDates.start}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setCustomDates((d) => ({ ...d, end: e.target.value }))}
                className="bg-transparent text-slate-700 dark:text-slate-300 text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]"
              />
            </div>
          )}
        </div>
      </div>

      {/* ── KPI Row ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="Total de tickets"
          value={tickets.total}
          sub="Todos os status"
          tone="neutral"
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" /></svg>}
        />
        <KpiCard
          label="Abertos"
          value={tickets.open}
          sub="Aguardando atendimento"
          tone="info"
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>}
        />
        <KpiCard
          label="Em andamento"
          value={tickets.in_progress}
          sub="Sendo atendidos"
          tone="primary"
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>}
        />
        <KpiCard
          label="Aguardando"
          value={tickets.awaiting}
          sub="Resp. do cliente"
          tone="warning"
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <KpiCard
          label="Resolvidos"
          value={tickets.resolved}
          sub={`+ ${tickets.closed} fechados`}
          tone="success"
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <KpiCard
          label="SLA violado"
          value={sla.resolve_breached}
          sub={`${sla.response_breached} resposta · ${sla.resolve_breached} resolução`}
          tone={sla.resolve_breached > 0 ? "danger" : "neutral"}
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
        />
      </div>

      {/* ── Status bar ──────────────────────────────────────── */}
      <StatusBar t={tickets} />

      {/* ── Stats row ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="CSAT médio"
          value={avgRating === "—" ? "—" : `${avgRating} / 10`}
          sub={`${surveys.total} avaliações`}
          tone="warning"
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>}
        />
        <KpiCard
          label="Tempo médio resolução"
          value={fmtHours(avgResolutionHours)}
          sub={avgResolutionHours != null ? "Média da equipe" : "Sem dados"}
          tone="primary"
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>}
        />
        <KpiCard
          label="SLA Resposta violado"
          value={sla.response_breached}
          sub="1º atendimento fora do prazo"
          tone={sla.response_breached > 0 ? "warning" : "neutral"}
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
        />
        <KpiCard
          label="SLA Resolução violado"
          value={sla.resolve_breached}
          sub="Resolução fora do prazo"
          tone={sla.resolve_breached > 0 ? "danger" : "neutral"}
          icon={<svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
        />
      </div>

      {/* ── Charts row 1 ────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Area chart */}
        <div className="rounded-xl bg-surface border border-borda overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-borda/60">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              {selectedTechId !== "all" && techDetail
                ? `Atendimentos de ${techDetail.technician_name} — ${periodLabel}`
                : `Tickets abertos por dia — ${periodLabel}`}
            </p>
          </div>
          <div className="p-5">
            {chartData.length === 0 ? (
              <div className="flex h-48 items-center justify-center text-slate-400 text-sm">Sem dados para o período</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                {/* Série temporal ÚNICA (chamados por dia): uma cor só, por
                    `COR_SERIE_TEMPORAL` — regra do operador, para os cinco
                    gráficos desta mesma natureza pararem de divergir em cor. */}
                <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="aGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={COR_SERIE_TEMPORAL} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={COR_SERIE_TEMPORAL} stopOpacity={0}    />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: CROMO.eixo, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: CROMO.eixo, fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={ESTILO_DICA} wrapperStyle={ENVOLTORIO_DICA} labelFormatter={(v) => fmtDate(String(v))} formatter={(v) => [v, "Tickets"]} />
                  <Area type="monotone" dataKey="count" stroke={COR_SERIE_TEMPORAL} strokeWidth={2.5} fill="url(#aGrad)" dot={false} activeDot={{ r: 4, fill: COR_SERIE_TEMPORAL, strokeWidth: 0 }} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Donut */}
        <div className="rounded-xl bg-surface border border-borda overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-borda/60">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Tickets por Status</p>
          </div>
          <div className="p-5">
            {statusData.length === 0 ? (
              <div className="flex h-48 items-center justify-center text-slate-400 text-sm">Nenhum ticket</div>
            ) : (
              <>
                <div className="relative">
                  <ResponsiveContainer width="100%" height={180}>
                    <PieChart>
                      <Pie data={statusData} cx="50%" cy="50%" innerRadius={55} outerRadius={82} paddingAngle={3} dataKey="value">
                        {statusData.map((e) => <Cell key={e.chave} fill={e.cor} />)}
                      </Pie>
                      <Tooltip contentStyle={ESTILO_DICA} wrapperStyle={ENVOLTORIO_DICA} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <p className="text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">{statusData.reduce((a, b) => a + b.value, 0)}</p>
                    <p className="text-xs text-slate-500">total</p>
                  </div>
                </div>
                {/* Legenda obrigatória (E18): com `--chart-*` a cor deixou de
                    significar por si só — é este nome, ao lado da cor, que diz
                    "cancelado". */}
                <div className="flex flex-col gap-1.5 mt-2">
                  {statusData.map((d) => (
                    <div key={d.chave} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: d.cor }} />
                        <span className="text-xs text-slate-500">{d.name}</span>
                      </div>
                      <span className="text-xs font-semibold text-slate-700 dark:text-slate-200 tabular-nums">{d.value}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Category + Charts row 2 ─────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Category breakdown */}
        <SectionCard title="Chamados por Categoria">
          {categoryData.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-slate-400 text-sm">Sem categorias no período</div>
          ) : (
            <div className="space-y-3">
              {categoryData.map((cat) => (
                <div key={cat.category}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-slate-600 dark:text-slate-300 truncate max-w-[70%]">{cat.category}</span>
                    <span className="text-xs font-bold tabular-nums text-slate-700 dark:text-slate-200">{cat.count}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-surface-elevated overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-700"
                      style={{ width: `${(cat.count / categoryMax) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        {/* Priority */}
        <SectionCard title="Tickets por Prioridade">
          {/* Prioridade TEM significado próprio — não é série categórica —,
              então usa `graficoDePrioridade()` e não `--chart-*` (E16-b). O
              eixo já rotula cada barra; sem legenda separada. */}
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={priorityData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }} barSize={36}>
              <XAxis dataKey="name" tick={{ fill: CROMO.eixo, fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: CROMO.eixo, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: CROMO.grade }}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  // A cor do texto acompanha a barra sob o cursor (`cor`, do
                  // próprio dado) — antes era um azul cravado sem relação
                  // nenhuma com a cor da barra.
                  const cor = (payload[0].payload as { cor: string }).cor;
                  return (
                    <div style={{ backgroundColor: CROMO.dicaFundo, border: `1px solid ${CROMO.dicaBorda}`, borderRadius: 8, padding: "8px 12px", fontSize: 12, color: CROMO.dicaTexto }}>
                      <p style={{ fontWeight: 600, marginBottom: 4 }}>{label}</p>
                      <p style={{ color: cor }}>Tickets : {payload[0].value}</p>
                    </div>
                  );
                }}
              />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} name="Tickets">
                {priorityData.map((e) => <Cell key={e.name} fill={e.cor} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* SLA compliance */}
        <SectionCard title={`Conformidade SLA — ${periodLabel}`}>
          {slaCompliance.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-slate-400 text-sm">Sem dados de SLA</div>
          ) : (
            <div className="space-y-5 py-1">
              {slaCompliance.map((item) => (
                <div key={item.priority}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={cn("w-2 h-2 rounded-full", slaBg(item.compliance_rate))} />
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-200 capitalize">{item.priority}</span>
                    </div>
                    <div className="text-right">
                      <span className={cn("text-sm font-bold tabular-nums", slaColor(item.compliance_rate))}>
                        {item.compliance_rate.toFixed(0)}%
                      </span>
                      <span className="text-xs text-slate-400 ml-2">({item.breached} violados)</span>
                    </div>
                  </div>
                  <div className="h-2 rounded-full bg-surface-elevated overflow-hidden">
                    <div className={cn("h-full rounded-full transition-all duration-700", slaBg(item.compliance_rate))} style={{ width: `${item.compliance_rate}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Team table ───────────────────────────────────────── */}
      {techList && techList.technicians.length > 0 && (
        <SectionCard title={`Performance da equipe — ${periodLabel}`}>
          <div className="overflow-x-auto -mx-5 px-5">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b border-slate-100 dark:border-borda/60">
                  {["Técnico", "Atribuídos", "Resolvidos", "Em aberto", "Conformidade SLA", "Tempo médio", "CSAT"].map((h) => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wider text-slate-400 pb-3 pr-4 last:pr-0">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50 dark:divide-borda/30">
                {techList.technicians.map((t) => {
                  const initials = t.technician_name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase();
                  const isSelected = selectedTechId === t.technician_id;
                  return (
                    <tr
                      key={t.technician_id}
                      onClick={() => setSelectedTechId(isSelected ? "all" : t.technician_id)}
                      className={cn(
                        "transition-colors cursor-pointer",
                        isSelected
                          ? "bg-primary/5 dark:bg-primary/10"
                          : "hover:bg-slate-50 dark:hover:bg-surface-elevated",
                      )}
                    >
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2.5">
                          {/* `bg-primary` + `text-white` dava 3,83:1. O par do
                              degrau de ação é `bg-action` + `text-on-primary`
                              (tailwind.config.js). */}
                          <div className={cn("w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold", isSelected ? "bg-action text-on-primary" : "bg-primary/10 text-primary border border-primary/20")}>
                            {initials}
                          </div>
                          <span className="font-medium text-slate-700 dark:text-slate-200 truncate">{t.technician_name}</span>
                          {isSelected && <span className="text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded">filtrado</span>}
                        </div>
                      </td>
                      <td className="py-3 pr-4 tabular-nums text-slate-600 dark:text-slate-300">{t.total_assigned}</td>
                      <td className="py-3 pr-4 tabular-nums text-emerald-600 dark:text-emerald-400 font-medium">{t.resolved}</td>
                      <td className="py-3 pr-4 tabular-nums text-sky-600 dark:text-sky-400">{t.open_count}</td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
                            <div className={cn("h-full rounded-full", slaBg(t.sla_compliance_rate))} style={{ width: `${t.sla_compliance_rate}%` }} />
                          </div>
                          <span className={cn("text-xs font-bold tabular-nums", slaColor(t.sla_compliance_rate))}>
                            {t.sla_compliance_rate.toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 tabular-nums text-slate-600 dark:text-slate-300">{fmtHours(t.avg_resolution_hours)}</td>
                      <td className="py-3">
                        {t.csat_average != null ? (
                          <div className="flex items-center gap-1">
                            <span className="tabular-nums font-bold text-amber-600 dark:text-amber-400">{t.csat_average.toFixed(1)}</span>
                            <svg className="w-3.5 h-3.5 text-amber-400" viewBox="0 0 20 20" fill="currentColor">
                              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                            </svg>
                            <span className="text-xs text-slate-400">({t.csat_count})</span>
                          </div>
                        ) : <span className="text-slate-400">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
