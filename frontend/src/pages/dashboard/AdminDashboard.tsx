import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, Cell,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Alert, Icon, KpiCard, Select, Selector, Spinner } from "../../components/ui";
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

// ── Ícones ────────────────────────────────────────────────────
//
// Os 12 `<svg>` soltos desta tela viraram `Icon` do pacote. Casados pelo
// traçado `d`, caractere a caractere: dez batiam com um desenho que já
// existia (`ticket`, `inbox`, `refresh`, `clock` ×2, `check`, `star`,
// `chart`, `calendar`) e não precisavam de nada novo.
//
// Os dois que NÃO batiam são o mesmo triângulo de aviso desenhado de outro
// jeito — `M12 9v2m0 4h.01m-6.938 4h13.856…` contra o `M12 9v2m0 4h.01M10.29
// 3.86L1.82 18…` do pacote. Unificados em `warning`, que é o que a E21 já
// fez com dez casos assim: um "certo" sem círculo, outra lupa, outro aviso.
//
// O décimo segundo é o caso de conferência: a estrela ao lado da média por
// técnico era `viewBox="0 0 20 20" fill="currentColor"` — desenho PREENCHIDO
// de outra família. Trocar por `Icon` às cegas renderiza em escala errada e
// sem preenchimento, e nem `tsc` nem teste de componente acusam, porque
// `ICON_PATHS` é mapa de texto e todo texto cabe. A decisão D9.1 do operador
// resolveu o caso no sentido inverso — ícone é só contorno — e ela está
// escrita no ponto de uso.

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

  // O grupo inteiro é `role="img"`, e a distribuição vai escrita no rótulo.
  //
  // A faixa empilhada é a única portadora da PROPORÇÃO entre os blocos —
  // largura, e nada mais. Sem papel nenhum ela some para quem não vê, e com
  // `aria-hidden` sumiria de propósito. `img` é o papel de "isto é um desenho,
  // e este é o texto dele".
  //
  // O rótulo repete a legenda de baixo PALAVRA POR PALAVRA (`Aberto: 3`),
  // porque `role="img"` substitui a subárvore inteira: o título e a legenda
  // deixam de ser lidos, e o que o rótulo não disser deixa de existir para
  // quem ouve. Dizer o mesmo de outro jeito criaria duas versões da mesma
  // contagem.
  const distribuicao = segs.map((s) => `${s.label}: ${s.value}`).join(", ");

  return (
    <div
      role="img"
      aria-label={
        distribuicao
          ? `Distribuição de status — ${distribuicao}`
          : "Distribuição de status"
      }
      className="rounded-xl bg-surface border border-borda p-5"
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-conteudo-muted mb-3">Distribuição de status</p>
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
            <span className="text-xs text-conteudo-muted">
              {s.label}: <span className="font-semibold text-conteudo">{s.value}</span>
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
      <div className="flex items-center justify-between px-5 py-4 border-b border-borda-muted">
        <p className="text-sm font-semibold text-conteudo">{title}</p>
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
  // Dois denominadores DIFERENTES, e a diferença é o ponto:
  //
  //   `categoryMax`   — o maior da lista. É o que a BARRA desenha: largura
  //                     relativa, tamanho comparado ao campeão.
  //   `categoryTotal` — a soma das categorias EXIBIDAS. É o que o RÓTULO diz:
  //                     "25% do total", que é a fatia do bolo.
  //
  // Exibidas, e não todas as do período: a lista é cortada em oito
  // (`slice(0, 8)`), e uma porcentagem sobre um total que inclui categorias
  // fora da tela não fecharia com nada que se possa ler ali. O denominador é
  // o que está à vista.
  const categoryMax = categoryData[0]?.count || 1;
  const categoryTotal = categoryData.reduce((s, c) => s + c.count, 0) || 1;

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
          <h1 className="text-xl font-extrabold text-conteudo-heading">Dashboard</h1>
          <p className="mt-0.5 text-sm text-conteudo-muted">Visão geral do sistema de atendimento</p>
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Technician filter — D9.2: lista LONGA. As opções vêm da rede
              (`getTechnicianListReport`) e crescem com a equipe, então o
              controle é o `Selector variant="filter"`, e não o `<select>`
              nativo.

              O `label` é a razão da troca: o `FilterSelect` não o repassava, e
              o filtro se anunciava só pelo nome do técnico escolhido. O
              `Selector` desenha o rótulo `sr-only` e soma rótulo + valor no
              nome acessível. */}
          {techList && (
            <Selector
              variant="filter"
              label="Técnico"
              value={selectedTechId}
              onChange={(v) => setSelectedTechId(v ?? "all")}
              options={[
                { value: "all", label: "Todos os técnicos" },
                ...techList.technicians.map((t) => ({ value: t.technician_id, label: t.technician_name })),
              ]}
              placeholder="Todos os técnicos"
            />
          )}

          {/* Period filter — D9.2: oito períodos fixos no código, lista curta e
              conhecida, logo `<select>` nativo.

              Sem `placeholder`, e isso conserta uma queda: a linha de limpar do
              `FilterSelect` devolvia `""`, e `activePeriod` lia
              `PERIOD_OPTIONS.find((p) => p.key === "")!.days` — `days` de
              `undefined`. O `<select>` nativo não tem linha de limpar. */}
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
              <Icon name="calendar" size={14} strokeWidth={2} className="text-conteudo-muted" />
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
      <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="Total de tickets"
          value={tickets.total}
          sub="Todos os status"
          tone="neutral"
          icon={<Icon name="ticket" />}
        />
        <KpiCard
          label="Abertos"
          value={tickets.open}
          sub="Aguardando atendimento"
          tone="info"
          icon={<Icon name="inbox" />}
        />
        <KpiCard
          label="Em andamento"
          value={tickets.in_progress}
          sub="Sendo atendidos"
          tone="primary"
          icon={<Icon name="refresh" />}
        />
        <KpiCard
          label="Aguardando"
          value={tickets.awaiting}
          sub="Resp. do cliente"
          tone="warning"
          icon={<Icon name="clock" />}
        />
        <KpiCard
          label="Resolvidos"
          value={tickets.resolved}
          sub={`+ ${tickets.closed} fechados`}
          tone="success"
          icon={<Icon name="check" />}
        />
        <KpiCard
          label="SLA violado"
          value={sla.resolve_breached}
          sub={`${sla.response_breached} resposta · ${sla.resolve_breached} resolução`}
          tone={sla.resolve_breached > 0 ? "danger" : "neutral"}
          icon={<Icon name="warning" />}
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
          icon={<Icon name="star" />}
        />
        <KpiCard
          label="Tempo médio resolução"
          value={fmtHours(avgResolutionHours)}
          sub={avgResolutionHours != null ? "Média da equipe" : "Sem dados"}
          tone="primary"
          icon={<Icon name="chart" />}
        />
        <KpiCard
          label="SLA Resposta violado"
          value={sla.response_breached}
          sub="1º atendimento fora do prazo"
          tone={sla.response_breached > 0 ? "warning" : "neutral"}
          icon={<Icon name="clock" />}
        />
        <KpiCard
          label="SLA Resolução violado"
          value={sla.resolve_breached}
          sub="Resolução fora do prazo"
          tone={sla.resolve_breached > 0 ? "danger" : "neutral"}
          icon={<Icon name="warning" />}
        />
      </div>

      {/* ── Charts row 1 ────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Area chart */}
        <div className="rounded-xl bg-surface border border-borda overflow-hidden">
          <div className="px-5 py-4 border-b border-borda-muted">
            <p className="text-sm font-semibold text-conteudo">
              {selectedTechId !== "all" && techDetail
                ? `Atendimentos de ${techDetail.technician_name} — ${periodLabel}`
                : `Tickets abertos por dia — ${periodLabel}`}
            </p>
          </div>
          <div className="p-5">
            {chartData.length === 0 ? (
              <div className="flex h-48 items-center justify-center text-conteudo-muted text-sm">Sem dados para o período</div>
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
          <div className="px-5 py-4 border-b border-borda-muted">
            <p className="text-sm font-semibold text-conteudo">Tickets por Status</p>
          </div>
          <div className="p-5">
            {statusData.length === 0 ? (
              <div className="flex h-48 items-center justify-center text-conteudo-muted text-sm">Nenhum ticket</div>
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
                    <p className="text-2xl font-bold tabular-nums text-conteudo-heading">{statusData.reduce((a, b) => a + b.value, 0)}</p>
                    <p className="text-xs text-conteudo-muted">total</p>
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
                        <span className="text-xs text-conteudo-muted">{d.name}</span>
                      </div>
                      <span className="text-xs font-semibold text-conteudo tabular-nums">{d.value}</span>
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
            <div className="flex h-40 items-center justify-center text-conteudo-muted text-sm">Sem categorias no período</div>
          ) : (
            <div className="space-y-3">
              {categoryData.map((cat) => (
                // A LINHA INTEIRA é `role="img"`, e o rótulo traz nome,
                // contagem e proporção.
                //
                // Esconder a barra (abaixo) foi certo, e deixou um buraco:
                // quem ouve lia "Hardware 6" e nada sobre a PROPORÇÃO entre as
                // categorias, que passou a ser informação só visual. `img` é o
                // papel de "isto é um desenho, e este é o texto dele".
                //
                // ⚠️ `role="img"` substitui a subárvore pelo rótulo: o nome e a
                // contagem em texto deixam de ser lidos por conta própria. Por
                // isso o `aria-label` repete os DOIS — omitir qualquer um
                // apagaria da árvore algo que está escrito na tela.
                //
                // A porcentagem é sobre `categoryTotal` (a soma das exibidas),
                // não sobre `categoryMax`: a barra desenha a segunda, e são
                // coisas diferentes — a fatia do bolo contra o tamanho relativo
                // ao campeão.
                <div
                  key={cat.category}
                  role="img"
                  aria-label={`${cat.category}: ${cat.count} chamados, ${Math.round(
                    (cat.count / categoryTotal) * 100,
                  )}% do total`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-conteudo-muted truncate max-w-[70%]">{cat.category}</span>
                    <span className="text-xs font-bold tabular-nums text-conteudo">{cat.count}</span>
                  </div>
                  {/* Barra de COMPARAÇÃO, e por isso sem papel nenhum. Ela vai
                      de zero ao MAIOR VALOR DA LISTA (`categoryMax`), não a um
                      teto conhecido: uma barra cujo máximo é "o maior que
                      aparecer hoje" mede tamanho relativo. Não é progresso
                      (`progressbar` anuncia tarefa avançando) nem medição
                      dentro de faixa fixa (`meter`) — declarar qualquer um dos
                      dois poria um número numa escala que não existe.
                      `aria-hidden` continua na BARRA, e agora é honesto por
                      inteiro: a contagem está escrita logo acima em texto, e a
                      proporção que só a barra desenhava está no `aria-label` do
                      grupo. Sem esse rótulo, esconder o desenho escondia a
                      comparação junto. */}
                  <div
                    className="h-1.5 rounded-full bg-surface-elevated overflow-hidden"
                    aria-hidden="true"
                  >
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
            <div className="flex h-48 items-center justify-center text-conteudo-muted text-sm">Sem dados de SLA</div>
          ) : (
            <div className="space-y-5 py-1">
              {slaCompliance.map((item) => (
                <div key={item.priority}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className={cn("w-2 h-2 rounded-full", slaBg(item.compliance_rate))} />
                      {/* O rótulo sai de `lib/prioridade.ts`, e não da chave
                          crua da API com `capitalize` por cima. `critical` e
                          `low` são nomes de campo, não texto de interface: o
                          `capitalize` só os deixava com maiúscula, em inglês,
                          divergindo do "Crítica"/"Baixa" (feminino da E17) que
                          o selo, a lista e o gráfico desta mesma tela já usam.
                          A classe saiu junto — ela existia só para maquiar a
                          chave. */}
                      <span className="text-sm font-medium text-conteudo">{rotuloDePrioridade(item.priority)}</span>
                    </div>
                    <div className="text-right">
                      <span className={cn("text-sm font-bold tabular-nums", slaColor(item.compliance_rate))}>
                        {item.compliance_rate.toFixed(0)}%
                      </span>
                      <span className="text-xs text-conteudo-muted ml-2">({item.breached} violados)</span>
                    </div>
                  </div>
                  {/* Barra de MEDIÇÃO, e o papel de medição é `meter`. A
                      conformidade vai de 0 a 100 — faixa conhecida e FIXA, ao
                      contrário da barra de categoria, cujo máximo é o maior da
                      lista. Não é `progressbar`: esse é o papel de tarefa
                      avançando, e o leitor de tela anuncia "60 por cento
                      concluído" para ele — a conformidade de SLA não está
                      concluindo nada. A distinção custou uma reversão e está
                      presa em `barra-de-sla.test.ts`. Sem `role`, um `<div>` de
                      largura em porcentagem não é nada para quem não vê a
                      largura, e a porcentagem ao lado é texto de outro
                      elemento, sem vínculo com o desenho.

                      O nome repete o rótulo VISÍVEL de propósito, para o nome
                      acessível não divergir da tela — e por isso acompanhou a
                      troca da chave crua por `rotuloDePrioridade()`: deixá-lo
                      em `critical` criaria exatamente a divergência que ele
                      existe para evitar. */}
                  <div
                    role="meter"
                    aria-valuenow={Math.round(item.compliance_rate)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Conformidade de SLA — ${rotuloDePrioridade(item.priority)}`}
                    className="h-2 rounded-full bg-surface-elevated overflow-hidden"
                  >
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
                <tr className="border-b border-borda-muted">
                  {["Técnico", "Atribuídos", "Resolvidos", "Em aberto", "Conformidade SLA", "Tempo médio", "CSAT"].map((h) => (
                    <th key={h} className="text-left text-xs font-semibold uppercase tracking-wider text-conteudo-muted pb-3 pr-4 last:pr-0">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-borda-muted">
                {techList.technicians.map((t) => {
                  const initials = t.technician_name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase();
                  const isSelected = selectedTechId === t.technician_id;
                  return (
                    // O `onClick` na `<tr>` sem `tabIndex`/`onKeyDown` é
                    // defeito de PRODUTO, já registrado na ficha, e não se
                    // conserta aqui: dar teclado a esta linha é redesenhar o
                    // controle. O que dá para fazer sem redesenhar nada é a
                    // linha passar a ter NOME: antes ela se anunciava pela
                    // colagem das sete células, e o que o clique faz não
                    // estava escrito em lugar nenhum.
                    <tr
                      key={t.technician_id}
                      onClick={() => setSelectedTechId(isSelected ? "all" : t.technician_id)}
                      aria-label={
                        isSelected
                          ? `${t.technician_name} — filtro ativo, clique para remover`
                          : `${t.technician_name} — clique para filtrar o painel por este técnico`
                      }
                      className={cn(
                        "transition-colors cursor-pointer",
                        isSelected
                          ? "bg-primary/5 dark:bg-primary/10"
                          : "hover:bg-surface-elevated",
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
                          <span className="font-medium text-conteudo truncate">{t.technician_name}</span>
                          {isSelected && <span className="text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded">filtrado</span>}
                        </div>
                      </td>
                      <td className="py-3 pr-4 tabular-nums text-conteudo-muted">{t.total_assigned}</td>
                      <td className="py-3 pr-4 tabular-nums text-on-tint-success font-medium">{t.resolved}</td>
                      <td className="py-3 pr-4 tabular-nums text-on-tint-info">{t.open_count}</td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          {/* A mesma medição da seção "Conformidade SLA", uma
                              por técnico: 0 a 100, faixa fixa, `meter`. O nome
                              traz o técnico porque há uma barra por linha e
                              "Conformidade de SLA" repetido sete vezes não
                              distingue nada. */}
                          <div
                            role="meter"
                            aria-valuenow={Math.round(t.sla_compliance_rate)}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-label={`Conformidade de SLA de ${t.technician_name}`}
                            className="w-20 h-1.5 rounded-full bg-surface-elevated overflow-hidden"
                          >
                            <div className={cn("h-full rounded-full", slaBg(t.sla_compliance_rate))} style={{ width: `${t.sla_compliance_rate}%` }} />
                          </div>
                          <span className={cn("text-xs font-bold tabular-nums", slaColor(t.sla_compliance_rate))}>
                            {t.sla_compliance_rate.toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 tabular-nums text-conteudo-muted">{fmtHours(t.avg_resolution_hours)}</td>
                      <td className="py-3">
                        {t.csat_average != null ? (
                          <div className="flex items-center gap-1">
                            <span className="tabular-nums font-bold text-on-tint-warning">{t.csat_average.toFixed(1)}</span>
                            {/* Estrela de CONTORNO, e a mudança é prescrita (D9.1).
                                Aqui vivia um desenho PREENCHIDO em `viewBox="0 0 20 20"`
                                — outra família. A E21 barrou trocá-lo às cegas pelo
                                `Icon`, que é 24×24 só de traço: renderiza em escala
                                errada e sem preenchimento, e nada no `tsc` acusa. O
                                operador decidiu o sentido inverso: ícone é só contorno,
                                e estrela cheia vive dentro do `Rating` do pacote. O
                                `Rating` NÃO serve aqui — ele é de cinco estrelas e a
                                pesquisa do HelpHS é de 1 a 10 com rótulo por nota. */}
                            <Icon name="star" size={14} className="text-on-tint-warning" />
                            <span className="text-xs text-conteudo-muted">({t.csat_count})</span>
                          </div>
                        ) : <span className="text-conteudo-muted">—</span>}
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
