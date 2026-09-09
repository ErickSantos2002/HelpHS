import { useEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Icon,
  Pagination,
  PriorityBadge,
  Select,
  Selector,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui";
import { CATEGORIAS, rotuloDeCategoria } from "../../lib/categoria";
import {
  COR_SERIE_TEMPORAL,
  CROMO,
  ENVOLTORIO_DICA,
  ESTILO_DICA,
  preenchimentoCsat,
  slotCategorico,
} from "../../lib/grafico";
import {
  PRIORIDADES,
  graficoDePrioridade,
  rotuloDePrioridade,
} from "../../lib/prioridade";
import { rotuloDeStatus, slotDeStatus } from "../../lib/status";
import { plural } from "../../lib/utils";
import { useAuth } from "../../contexts/AuthContext";
import {
  exportReportsUrl,
  getReports,
  getTechnicianDetailReport,
  getTechnicianListReport,
  type AvgFirstResponseItem,
  type CsatDailyItem,
  type HourlyCount,
  type OldestTicketItem,
  type ProductCount,
  type ReportData,
  type TechnicianDistItem,
  type ReportFilters,
  type TechnicianDetailReport,
  type TechnicianListReport,
} from "../../services/reportService";

// ── Constants ─────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { value: "7",           label: "Últimos 7 dias"   },
  { value: "14",          label: "Últimos 14 dias"  },
  { value: "30",          label: "Últimos 30 dias"  },
  { value: "90",          label: "Últimos 90 dias"  },
  { value: "personalizado", label: "Personalizado"  },
];

/*
 * As opções dos dois filtros saem dos módulos, e não de uma lista paralela.
 *
 * Eram duas cópias — oito categorias e quatro prioridades — que já não tinham
 * como divergir por acidente: divergiriam por edição. `lib/categoria.ts` e
 * `lib/prioridade.ts` são as fontes, e a segunda ainda dá a ORDEM de urgência,
 * que a lista à mão repetia de cor.
 */
const CATEGORY_OPTIONS = CATEGORIAS.map((c) => ({
  value: c.value,
  label: c.label,
}));

const PRIORITY_OPTIONS = PRIORIDADES.map((p) => ({
  value: p,
  label: rotuloDePrioridade(p),
}));

const WEEKDAY_LABELS: Record<number, string> = {
  1: "Seg", 2: "Ter", 3: "Qua", 4: "Qui", 5: "Sex", 6: "Sáb", 7: "Dom",
};
const WEEKDAY_FULL: Record<number, string> = {
  1: "Segunda-feira", 2: "Terça-feira", 3: "Quarta-feira",
  4: "Quinta-feira", 5: "Sexta-feira", 6: "Sábado", 7: "Domingo",
};

/**
 * Os dois grupos do gráfico de dia da semana, e os quatro do de hora do dia.
 *
 * São séries **categóricas**: "fim de semana" não é melhor nem pior que "dia
 * útil", e "madrugada" não é um alerta. Por isso pegam slot pela posição, e
 * quem diz o que cada cor é são a legenda e a marca do eixo — não a cor.
 *
 * O que saiu daqui: `#f59e0b` para o fim de semana (âmbar, a tinta de aviso —
 * dizia que sábado é um problema) e `#475569` para a madrugada (cinza de
 * apagado, sobre fundo escuro).
 */
const SLOT_DIA_UTIL = slotCategorico(0);
const SLOT_FIM_DE_SEMANA = slotCategorico(1);

/** Os quatro períodos, na ordem em que pegam slot. */
const PERIODOS_DO_DIA = ["manhã", "tarde", "noite", "madrugada"] as const;

/** O índice do período de uma hora cheia. A madrugada dá a volta no dia. */
function periodoDaHora(h: number): number {
  if (h >= 6 && h < 12) return 0;
  if (h >= 12 && h < 18) return 1;
  if (h >= 18 && h < 22) return 2;
  return 3;
}

// ── Shared sub-components ─────────────────────────────────────

/**
 * O miolo da dica, sem caixa própria.
 *
 * A caixa passou a ser do `wrapperStyle` (`ENVOLTORIO_DICA`) — era esta a
 * duplicação: seis dicas escreviam o mesmo `backgroundColor`/`border`/`radius`
 * à mão, cada uma com o hexadecimal escolhido por tema em JavaScript. Aqui
 * sobra o que é geometria, e a cor do texto vem do token do papel.
 */
function CorpoDaDica({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: "8px 12px", fontSize: 12, color: CROMO.dicaTexto }}>
      {children}
    </div>
  );
}

/** O título da dica — o nome da fatia sobre a qual o ponteiro está. */
function TituloDaDica({ children }: { children: React.ReactNode }) {
  return <p style={{ fontWeight: 600, marginBottom: 4 }}>{children}</p>;
}

function Delta({ current, prev }: { current: number; prev: number | null }) {
  if (prev === null || prev === 0) return null;
  const pct = Math.round(((current - prev) / prev) * 100);
  if (pct === 0) return <span className="text-[10px] font-semibold text-conteudo-muted">= igual</span>;
  const up = pct > 0;
  return (
    <span className={`flex items-center gap-0.5 text-[10px] font-semibold ${up ? "text-success-700 dark:text-success-400" : "text-danger-700 dark:text-danger-400"}`}>
      {up ? "▲" : "▼"} {Math.abs(pct)}% vs anterior
    </span>
  );
}

function StatCard({ label, value, sub, colorCls = "text-conteudo-heading", delta }: {
  label: string; value: string | number; sub?: string; colorCls?: string;
  delta?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-borda/40 bg-surface p-4">
      <p className="mb-2 text-xs font-medium text-conteudo-muted">{label}</p>
      <p className={`text-2xl font-bold leading-none ${colorCls}`}>{value}</p>
      <div className="mt-1.5 flex items-center gap-2 flex-wrap">
        {sub && <p className="text-xs text-conteudo-muted">{sub}</p>}
        {delta}
      </div>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-borda/40 bg-surface">
      <div className="border-b border-borda/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-conteudo">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

// ── Avg first response chart ──────────────────────────────────

function FirstResponseChart({ data, fmtHours }: {
  data: AvgFirstResponseItem[];
  fmtHours: (h: number | null) => string;
}) {
  const chartData = data.filter((r) => r.avg_hours != null).map((r) => ({ priority: r.priority, avg_hours: r.avg_hours ?? 0 }));
  if (chartData.length === 0) return null;
  return (
    <ChartCard title="Tempo médio de 1ª resposta por prioridade">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barSize={48}>
          <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
          <XAxis dataKey="priority" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
            tickFormatter={(v: string) => rotuloDePrioridade(v)} />
          <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
            tickFormatter={(v: number) => v >= 24 ? `${(v / 24).toFixed(0)}d` : `${v}h`} />
          <Tooltip cursor={{ fill: CROMO.grade }} wrapperStyle={ENVOLTORIO_DICA}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              return (
                <CorpoDaDica>
                  <TituloDaDica>{rotuloDePrioridade(String(label))}</TituloDaDica>
                  <p>Tempo médio: {fmtHours(payload[0].value as number)}</p>
                </CorpoDaDica>
              );
            }} />
          <Bar dataKey="avg_hours" radius={[4, 4, 0, 0]}>
            {chartData.map((e) => <Cell key={e.priority} fill={graficoDePrioridade(e.priority)} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Tickets by product chart ──────────────────────────────────

function ProductChart({ data }: { data: ProductCount[] }) {
  if (data.length === 0) return null;
  return (
    <ChartCard title="Tickets por produto">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 4, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} horizontal={false} />
          <XAxis type="number" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
          <YAxis dataKey="product_name" type="category" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} width={80}
            tickFormatter={(v: string) => v.length > 12 ? `${v.slice(0, 12)}…` : v} />
          <Tooltip cursor={{ fill: CROMO.grade }} wrapperStyle={ENVOLTORIO_DICA}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              return (
                <CorpoDaDica>
                  <TituloDaDica>{label}</TituloDaDica>
                  <p>Tickets: {payload[0].value ?? 0}</p>
                </CorpoDaDica>
              );
            }} />
          {/*
            UMA cor para a série inteira, e não um slot por barra: são sete
            slots e o produto é lista aberta — da oitava barra em diante duas
            pintariam igual, e a cor não diria nada que o nome ao lado já não
            diga. O mesmo vale para o gráfico de categoria, que tem oito.
          */}
          <Bar dataKey="count" fill={slotCategorico(0)} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Hourly distribution chart ─────────────────────────────────

function HourlyChart({ data }: { data: HourlyCount[] }) {
  const hasData = data.some((d) => d.count > 0);
  if (!hasData) return null;

  return (
    <ChartCard title="Tickets por hora do dia">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
          <XAxis dataKey="hour" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
            tickFormatter={(v: number) => v % 3 === 0 ? `${v}h` : ""} />
          <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
          <Tooltip cursor={{ fill: CROMO.grade }} wrapperStyle={ENVOLTORIO_DICA}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const h = Number(label ?? 0);
              return (
                <CorpoDaDica>
                  <TituloDaDica>{h}h — {PERIODOS_DO_DIA[periodoDaHora(h)]}</TituloDaDica>
                  <p>Tickets: {payload[0].value ?? 0}</p>
                </CorpoDaDica>
              );
            }} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((e) => (
              <Cell key={e.hour} fill={slotCategorico(periodoDaHora(e.hour))} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {/*
        A legenda nomeia os quatro períodos. Sem ela a cor seria a única fonte
        de "isto é madrugada" — e as quatro do slot categórico são medidas para
        forma (3:1), não para dizer o que dizem.
      */}
      <p className="mt-2 text-center text-[10px] text-conteudo-muted">
        {PERIODOS_DO_DIA.map((nome, i) => (
          <span key={nome}>
            <span aria-hidden="true" style={{ color: slotCategorico(i) }}>■</span>{" "}
            {nome}
            {i < PERIODOS_DO_DIA.length - 1 ? <>&nbsp;&nbsp;</> : null}
          </span>
        ))}
      </p>
    </ChartCard>
  );
}

// ── Technician distribution chart ────────────────────────────

/**
 * As duas séries deste gráfico **são status**, e por isso ele é o caso da E18.
 *
 * Pintavam `#22c55e` e `#f59e0b` — o verde de sucesso e o âmbar de aviso —, que
 * é a §16 aplicada a gráfico. Não cabe: a E18 mediu que sete séries dentro das
 * rampas semânticas não têm solução no tema claro, e o par que trava é
 * justamente verde × vermelho em protanopia. A tabela fixa resolve, e o preço
 * dela é que a cor deixa de significar — `resolvido` é o quinto slot da paleta
 * e o quinto slot não diz "resolvido" a ninguém.
 *
 * **Por isso a legenda é obrigatória, e não conveniência.** Enquanto o verde
 * era o verde, quem conhecia o sistema lia a cor. Agora quem diz o que cada
 * série é são estas duas palavras.
 */
const SERIES_DE_STATUS = [
  { chave: "resolved", status: "resolved", rotulo: "Resolvidos" },
  { chave: "open_count", status: "open", rotulo: "Em aberto" },
] as const;

function TechnicianDistChart({ data }: { data: TechnicianDistItem[] }) {
  const chartData = [...data].reverse();
  const chartHeight = Math.max(200, chartData.length * 40);
  const rotuloDaSerie = (chave: string) =>
    SERIES_DE_STATUS.find((s) => s.chave === chave)?.rotulo ?? chave;

  return (
    <ChartCard title="Distribuição de tickets por técnico">
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 0, right: 8, left: 4, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} horizontal={false} />
          <XAxis type="number" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
          <YAxis dataKey="technician_name" type="category" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
            width={90} tickFormatter={(v: string) => v.length > 12 ? `${v.slice(0, 12)}…` : v} />
          <Tooltip
            cursor={{ fill: CROMO.grade }}
            wrapperStyle={ENVOLTORIO_DICA}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const resolved = (payload.find((p) => p.dataKey === "resolved")?.value as number) ?? 0;
              const open = (payload.find((p) => p.dataKey === "open_count")?.value as number) ?? 0;
              return (
                <CorpoDaDica>
                  <TituloDaDica>{label}</TituloDaDica>
                  <p>Resolvidos: {resolved}</p>
                  <p>Em aberto: {open}</p>
                  <p style={{ color: CROMO.eixo, marginTop: 2 }}>Total: {resolved + open}</p>
                </CorpoDaDica>
              );
            }}
          />
          <Legend
            formatter={(v) => rotuloDaSerie(String(v))}
            wrapperStyle={{ fontSize: 11, color: CROMO.eixo, paddingTop: 8 }}
          />
          {SERIES_DE_STATUS.map((s, i) => (
            <Bar
              key={s.chave}
              dataKey={s.chave}
              stackId="a"
              fill={slotDeStatus(s.status)}
              radius={i === SERIES_DE_STATUS.length - 1 ? [0, 4, 4, 0] : [0, 0, 0, 0]}
              name={s.chave}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

// ── Oldest open tickets table ─────────────────────────────────

/*
 * O `STATUS_LABELS` local saiu daqui. Era a quarta cópia do rótulo de status, e
 * já divergia: dizia "Aguard. cliente" onde o resto do sistema diz "Aguardando
 * cliente". `lib/status.ts` tem as duas formas — a longa e a `curto`, que
 * existe para a coluna de 268px do quadro —, e numa tabela cabe a longa.
 */

function fmtAge(hours: number): string {
  if (hours < 1)   return `${Math.round(hours * 60)} min`;
  if (hours < 24)  return `${hours.toFixed(1)}h`;
  if (hours < 168) return `${(hours / 24).toFixed(1)} dias`;
  return `${(hours / 168).toFixed(1)} sem`;
}

const OLDEST_PAGE_SIZE = 10;

function OldestOpenTable({ tickets }: { tickets: OldestTicketItem[] }) {
  // O `Pagination` do pacote conta a partir de 1; este estado contava de 0.
  // Guardar 1-based evita o `page - 1` espalhado por três lugares, que é
  // exatamente onde um erro de um some sem barulho.
  const [page, setPage] = useState(1);
  const paged = tickets.slice((page - 1) * OLDEST_PAGE_SIZE, page * OLDEST_PAGE_SIZE);
  const colunas = [
    "Protocolo", "Título", "Prioridade", "Categoria",
    "Status", "Técnico", "Tempo em aberto",
  ];

  return (
    <div className="rounded-xl border border-borda/40 bg-surface overflow-hidden">
      <div className="border-b border-borda/40 px-5 py-3.5 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-conteudo">Tickets em aberto há mais tempo</h2>
        <span className="rounded-full bg-tint-danger px-2 py-0.5 text-[10px] font-semibold text-on-tint-danger">
          {tickets.length} {plural(tickets.length, "ticket", "tickets")}
        </span>
      </div>
      <Table>
        <TableHead>
          <TableRow>
            {colunas.map((h) => (
              <TableHeaderCell key={h} className="text-[11px] font-semibold">
                {h}
              </TableHeaderCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {paged.map((t) => (
            <TableRow key={t.ticket_id} className="hover:bg-surface-elevated/50">
              <TableCell className="font-mono text-xs text-conteudo-link">{t.protocol}</TableCell>
              <TableCell className="max-w-[220px]">
                <span className="block truncate" title={t.title}>{t.title}</span>
              </TableCell>
              <TableCell>
                {/*
                  Era um selo à mão: a mesma cor como fundo a 13% de alfa e
                  como texto. Tinta com o texto no degrau cheio é o par que a
                  E2 e a E8 mediram e reprovaram — e aqui nem era medido, era
                  um sufixo `22` no hexadecimal.
                */}
                <PriorityBadge priority={t.priority} />
              </TableCell>
              <TableCell muted className="text-xs">{rotuloDeCategoria(t.category)}</TableCell>
              <TableCell muted className="text-xs">{rotuloDeStatus(t.status)}</TableCell>
              <TableCell muted className="text-xs">
                {t.assignee_name ?? <span className="text-conteudo-muted">—</span>}
              </TableCell>
              <TableCell>
                <span className={`font-semibold text-xs ${t.sla_breached ? "text-danger-700 dark:text-danger-400" : "text-conteudo"}`}>
                  {fmtAge(t.age_hours)}
                  {t.sla_breached && <span className="ml-1.5 rounded bg-tint-danger px-1 py-0.5 text-[9px] font-bold text-on-tint-danger">SLA</span>}
                </span>
              </TableCell>
            </TableRow>
          ))}
          {paged.length === 0 && (
            <TableEmpty colSpan={colunas.length} message="Nenhum ticket em aberto." />
          )}
        </TableBody>
      </Table>

      {/*
        A paginação à mão saiu inteira. Ela desenhava um botão por página —
        com 40 tickets em aberto isso é uma fileira de quatro, mas a lista não
        tem teto — e a página atual era um `<button>` sem `aria-current`, então
        quem não vê a cor não sabia em qual estava. O primitivo tem janela de
        cinco e o par medido do degrau de ação.
      */}
      <div className="px-5 py-3">
        <Pagination
          page={page}
          pageSize={OLDEST_PAGE_SIZE}
          total={tickets.length}
          onPageChange={setPage}
          itemLabel="tickets"
          className="border-t-0 pt-0"
        />
      </div>
    </div>
  );
}

// ── Global report (admin) ─────────────────────────────────────

/*
 * ── O `useTheme()` saiu daqui, e é o coração desta migração ──────────────
 *
 * Este bloco escolhia cinco hexadecimais no JavaScript pelo tema — fundo,
 * borda e texto da dica, mais o `gridColor` — e era a terceira cópia dele no
 * projeto, nenhuma concordando com as outras. `var(--surface)` já é branco no
 * claro e `#132238` no escuro: ler o tema em JS para escolher a cor é
 * reimplementar o seletor `.dark`, com o agravante de a versão em JS não
 * acompanhar a paleta quando ela muda.
 *
 * ── E um defeito real que sai junto ──────────────────────────────────────
 *
 * O `gridColor` era `theme === "dark" ? "#132238" : "#ffffff"` — os mesmos
 * valores do FUNDO da dica, por cópia. Ele não pinta a grade: pinta o `cursor`
 * do Recharts, o realce atrás da barra sob o ponteiro. No tema claro isso
 * pintava realce branco sobre cartão branco: **o realce não existia**. Passa a
 * `CROMO.grade`, e aparece pela primeira vez no claro.
 *
 * A grade de verdade era `stroke={CROMO.grade}`, doze vezes escrito à mão — um
 * cinza de tema escuro que no claro desenhava linha quase preta sobre branco.
 * As outras duas telas de gráfico usam `#f1f5f9`, que é o valor de
 * `--border-muted` no claro.
 */
function GlobalReport({ data }: { data: ReportData; period?: number }) {
  const totalCsat = data.csat_distribution.reduce((s, d) => s + d.count, 0);
  const criticalSla = data.sla_compliance.find((s) => s.priority === "critical")?.compliance_rate ?? 100;
  const highSla     = data.sla_compliance.find((s) => s.priority === "high")?.compliance_rate ?? 100;

  function BarTooltip({ active, payload, label, labelFn, valueFn, valueLabel }: {
    active?: boolean; payload?: { value: number }[]; label?: string;
    labelFn: (v: string) => string; valueFn: (v: number) => string; valueLabel: string;
  }) {
    if (!active || !payload?.length) return null;
    return (
      <CorpoDaDica>
        <TituloDaDica>{labelFn(String(label ?? ""))}</TituloDaDica>
        <p>{valueLabel}: {valueFn(payload[0].value)}</p>
      </CorpoDaDica>
    );
  }

  function slaColor(rate: number) {
    if (rate >= 90) return "text-success-700 dark:text-success-400";
    if (rate >= 70) return "text-warning-700 dark:text-warning-400";
    return "text-danger-700 dark:text-danger-400";
  }

  function fmtHours(h: number | null): string {
    if (h == null) return "—";
    if (h < 1)  return `${Math.round(h * 60)} min`;
    if (h < 24) return `${h.toFixed(1)}h`;
    return `${(h / 24).toFixed(1)}d`;
  }

  const cmp = data.comparison;
  const prevCriticalSla = cmp?.sla_compliance.find((s) => s.priority === "critical")?.compliance_rate ?? null;
  const prevHighSla     = cmp?.sla_compliance.find((s) => s.priority === "high")?.compliance_rate ?? null;

  const resolutionChartData = (data.avg_resolution_by_priority ?? [])
    .filter((r) => r.avg_hours != null)
    .map((r) => ({ priority: r.priority, avg_hours: r.avg_hours ?? 0 }));

  const csatTrendData: CsatDailyItem[] = (data.csat_by_day ?? []).filter((d) => d.avg_rating != null);
  const hasCsatTrend = csatTrendData.length >= 2;

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <StatCard label="Tickets no período" value={data.total_tickets}
          sub={`últimos ${data.period_days} dias`}
          delta={<Delta current={data.total_tickets} prev={cmp?.total_tickets ?? null} />} />
        <StatCard label="Média CSAT"
          value={data.csat_average ? `${data.csat_average} / 10` : "—"}
          sub={`${totalCsat} ${plural(totalCsat, "avaliação", "avaliações")}`}
          delta={data.csat_average != null && cmp?.csat_average != null
            ? <Delta current={data.csat_average * 10} prev={cmp.csat_average * 10} />
            : undefined} />
        <StatCard label="Recomendação"
          value={data.recommend_average ? `${data.recommend_average} / 10` : "—"}
          sub="o quanto recomendariam a empresa" />
        <StatCard label="SLA Crítico" value={`${criticalSla}%`}
          sub="conformidade resolução" colorCls={slaColor(criticalSla)}
          delta={<Delta current={criticalSla} prev={prevCriticalSla} />} />
        <StatCard label="SLA Alto" value={`${highSla}%`}
          sub="conformidade resolução" colorCls={slaColor(highSla)}
          delta={<Delta current={highSla} prev={prevHighSla} />} />
        <StatCard label="Taxa de reabertura"
          value={`${data.reopen_rate ?? 0}%`}
          sub={`${data.reopened_count ?? 0} ticket${(data.reopened_count ?? 0) !== 1 ? "s" : ""} reaberto${(data.reopened_count ?? 0) !== 1 ? "s" : ""}`}
          colorCls={(data.reopen_rate ?? 0) === 0 ? "text-success-700 dark:text-success-400" : (data.reopen_rate ?? 0) <= 5 ? "text-conteudo-heading" : (data.reopen_rate ?? 0) <= 15 ? "text-warning-700 dark:text-warning-400" : "text-danger-700 dark:text-danger-400"} />
      </div>

      {/* Tickets por dia */}
      <ChartCard title="Tickets criados por dia">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data.tickets_by_day} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="ticketGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={COR_SERIE_TEMPORAL} stopOpacity={0.3} />
                <stop offset="95%" stopColor={COR_SERIE_TEMPORAL} stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
            <XAxis dataKey="date" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
              tickFormatter={(v: string) => v.slice(5)}
              interval={Math.max(1, Math.floor(data.tickets_by_day.length / 6))} />
            <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
            <Tooltip contentStyle={ESTILO_DICA} wrapperStyle={{ outline: "none" }}
              labelFormatter={(v) => `Data: ${v}`} formatter={(v) => [v ?? 0, "Tickets"]} />
            <Area type="monotone" dataKey="count" stroke={COR_SERIE_TEMPORAL} strokeWidth={2}
              fill="url(#ticketGradient)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* 3-column row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ChartCard title="Tickets por categoria">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.tickets_by_category.filter((c) => c.count > 0)}
              layout="vertical" margin={{ top: 0, right: 8, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} horizontal={false} />
              <XAxis type="number" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
              <YAxis dataKey="category" type="category" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
                tickFormatter={rotuloDeCategoria} width={60} />
              <Tooltip
                cursor={{ fill: CROMO.grade }}
                wrapperStyle={ENVOLTORIO_DICA}
                content={({ active, payload, label }) => (
                  <BarTooltip active={active} payload={payload as unknown as { value: number }[]} label={String(label ?? "")}
                    labelFn={rotuloDeCategoria}
                    valueFn={(v) => String(v ?? 0)}
                    valueLabel="Tickets" />
                )} />
              {/* Uma cor para a série — são oito categorias e sete slots. */}
              <Bar dataKey="count" fill={slotCategorico(0)} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Conformidade SLA por prioridade">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.sla_compliance} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
              <XAxis dataKey="priority" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
                tickFormatter={(v: string) => rotuloDePrioridade(v)} />
              <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} domain={[0, 100]}
                tickFormatter={(v: number) => `${v}%`} />
              <Tooltip
                cursor={{ fill: CROMO.grade }}
                wrapperStyle={ENVOLTORIO_DICA}
                content={({ active, payload, label }) => (
                  <BarTooltip active={active} payload={payload as unknown as { value: number }[]} label={String(label ?? "")}
                    labelFn={(v) => rotuloDePrioridade(v)}
                    valueFn={(v) => `${v ?? 0}%`}
                    valueLabel="Conformidade" />
                )} />
              <Bar dataKey="compliance_rate" radius={[4, 4, 0, 0]}>
                {data.sla_compliance.map((entry) => (
                  <Cell key={entry.priority} fill={graficoDePrioridade(entry.priority)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/*
          ── A escala de satisfação, e por que ela tem TRÊS cores e não dez ──

          Saiu a rampa de dez hexadecimais cravados (`#dc2626` … `#22c55e`). Ela
          falhava a separação **por construção**: degraus vizinhos são próximos
          de propósito — é o que faz uma rampa ser rampa —, e o eixo
          vermelho-verde é justamente o que colapsa em protanopia e
          deuteranopia. Dez notas viravam duas manchas.

          Entram as três faixas que o operador decidiu — 1–4, 5–7, 8–10 —, de
          `preenchimentoCsat`. Três faixas não satisfazem 1.4.1 sozinhas: só têm
          menos passos que dez. **O que resolve é o número estar escrito**, e é
          por isso que o `interval={0}` está aqui e não é enfeite — sem ele o
          Recharts esconde as marcas que se sobrepõem quando o cartão estreita,
          e o portador redundante some justamente na largura em que a cor já
          estava difícil.
        */}
        <ChartCard title="Distribuição CSAT (1–10)">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.csat_distribution} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
              <XAxis dataKey="rating" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
                interval={0} tickFormatter={(v: number) => String(v)} />
              <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
              <Tooltip
                cursor={{ fill: CROMO.grade }}
                wrapperStyle={ENVOLTORIO_DICA}
                content={({ active, payload, label }) => (
                  <BarTooltip active={active} payload={payload as unknown as { value: number }[]} label={String(label ?? "")}
                    labelFn={(v) => `Nota ${Number(v ?? 0)}`}
                    valueFn={(v) => String(v ?? 0)}
                    valueLabel="Avaliações" />
                )} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {data.csat_distribution.map((entry) => (
                  <Cell key={entry.rating} fill={preenchimentoCsat(entry.rating)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* 3-col: Tempo médio resolução | Tempo médio 1ª resposta | Tickets por produto */}
      {((resolutionChartData?.length ?? 0) > 0 || (data.avg_first_response_by_priority ?? []).some((r) => r.avg_hours != null) || (data.tickets_by_product?.length ?? 0) > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {(resolutionChartData?.length ?? 0) > 0 && (
            <ChartCard title="Tempo médio de resolução por prioridade">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={resolutionChartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barSize={36}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
                  <XAxis dataKey="priority" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
                    tickFormatter={(v: string) => rotuloDePrioridade(v)} />
                  <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
                    tickFormatter={(v: number) => v >= 24 ? `${(v / 24).toFixed(0)}d` : `${v}h`} />
                  <Tooltip cursor={{ fill: CROMO.grade }} wrapperStyle={ENVOLTORIO_DICA}
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      return (
                        <CorpoDaDica>
                          <TituloDaDica>{rotuloDePrioridade(String(label))}</TituloDaDica>
                          <p>Tempo médio: {fmtHours(payload[0].value as number)}</p>
                        </CorpoDaDica>
                      );
                    }} />
                  <Bar dataKey="avg_hours" radius={[4, 4, 0, 0]}>
                    {resolutionChartData.map((e) => <Cell key={e.priority} fill={graficoDePrioridade(e.priority)} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          )}
          <FirstResponseChart data={data.avg_first_response_by_priority ?? []} fmtHours={fmtHours} />
          <ProductChart data={data.tickets_by_product ?? []} />
        </div>
      )}

      {/* Tendência CSAT */}
      {hasCsatTrend && (
        <ChartCard title="Tendência CSAT ao longo do tempo">
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.csat_by_day} margin={{ top: 8, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="csatGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={COR_SERIE_TEMPORAL} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={COR_SERIE_TEMPORAL} stopOpacity={0}   />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
              <XAxis dataKey="date" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
                tickFormatter={(v: string) => v.slice(5)}
                interval={Math.max(1, Math.floor(data.csat_by_day.length / 6))} />
              <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} domain={[1, 10]} ticks={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]} />
              {/*
                A linha de meta é ANOTAÇÃO, não série: ela não mostra dado
                nenhum, marca onde fica o alvo. Por isso pega o token do cromo e
                não um slot de série — e o `#10b981` que estava aqui pintava
                também o texto "Meta 8.0", a 2,5:1 sobre o cartão claro. O
                `--text-muted` é o degrau já medido para texto de gráfico:
                7,24 / 7,58 / 6,92 no claro.
              */}
              <ReferenceLine y={8} stroke={CROMO.eixo} strokeDasharray="4 3"
                label={{ value: "Meta 8.0", fill: CROMO.eixo, fontSize: 10, position: "insideTopRight" }} />
              <Tooltip contentStyle={ESTILO_DICA} wrapperStyle={{ outline: "none" }}
                labelFormatter={(v) => `Data: ${v}`}
                formatter={(v, _, props: { payload?: CsatDailyItem }) => [
                  v != null ? `${Number(v).toFixed(2)} ★ (${props.payload?.count ?? 0} avaliações)` : "—",
                  "CSAT",
                ]} />
              <Area type="monotone" dataKey="avg_rating" stroke={COR_SERIE_TEMPORAL} strokeWidth={2}
                fill="url(#csatGradient)" dot={false} connectNulls={false} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Tickets em aberto há mais tempo */}
      {(data.oldest_open_tickets?.length ?? 0) > 0 && (
        <OldestOpenTable tickets={data.oldest_open_tickets} />
      )}

      {/* 2-col: Dia da semana | Hora do dia */}
      {((data.tickets_by_weekday ?? []).some((d) => d.count > 0) || (data.tickets_by_hour ?? []).some((d) => d.count > 0)) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {(data.tickets_by_weekday?.length ?? 0) > 0 && (
            <ChartCard title="Volume por dia da semana">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={data.tickets_by_weekday} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barSize={40}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
                  <XAxis dataKey="weekday" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
                    tickFormatter={(v: number) => WEEKDAY_LABELS[v] ?? v} />
                  <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
                  <Tooltip cursor={{ fill: CROMO.grade }} wrapperStyle={ENVOLTORIO_DICA}
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      const wd = Number(label ?? 0);
                      return (
                        <CorpoDaDica>
                          <TituloDaDica>{WEEKDAY_FULL[wd] ?? label}</TituloDaDica>
                          <p>Tickets: {payload[0].value ?? 0}</p>
                        </CorpoDaDica>
                      );
                    }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {data.tickets_by_weekday.map((e) => (
                      <Cell key={e.weekday} fill={e.weekday >= 6 ? SLOT_FIM_DE_SEMANA : SLOT_DIA_UTIL} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 text-center text-[10px] text-conteudo-muted">
                <span aria-hidden="true" style={{ color: SLOT_FIM_DE_SEMANA }}>■</span> fim de semana
              </p>
            </ChartCard>
          )}
          <HourlyChart data={data.tickets_by_hour ?? []} />
        </div>
      )}

      {/* Distribuição de tickets por técnico */}
      {(data.technicians_dist?.length ?? 0) > 0 && (
        <TechnicianDistChart data={data.technicians_dist} />
      )}

    </div>
  );
}

// ── Technician detail ─────────────────────────────────────────

function TechnicianDetail({ data }: { data: TechnicianDetailReport }) {
  function slaColor(rate: number) {
    if (rate >= 90) return "text-success-700 dark:text-success-400";
    if (rate >= 70) return "text-warning-700 dark:text-warning-400";
    return "text-danger-700 dark:text-danger-400";
  }

  function resolutionStr(h: number | null) {
    if (h == null) return "—";
    return h >= 24 ? `${(h / 24).toFixed(1)}d` : `${h.toFixed(1)}h`;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Atribuídos no período"  value={data.total_assigned}
          sub={`últimos ${data.period_days} dias`} />
        <StatCard label="Resolvidos / Fechados"  value={data.resolved}
          sub={data.total_assigned > 0 ? `${Math.round((data.resolved / data.total_assigned) * 100)}% do total` : "—"}
          colorCls="text-success-700 dark:text-success-400" />
        <StatCard label="Conformidade SLA"  value={`${data.sla_compliance_rate}%`}
          sub={`${data.sla_breached} ${plural(data.sla_breached, "violação", "violações")}`}
          colorCls={slaColor(data.sla_compliance_rate)} />
        <StatCard label="CSAT médio"
          value={data.csat_average ? `${data.csat_average} / 10` : "—"}
          sub={data.csat_count > 0 ? `${data.csat_count} ${plural(data.csat_count, "avaliação", "avaliações")}` : "sem avaliações"} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Em andamento"           value={data.in_progress} />
        <StatCard label="Em aberto"              value={data.open_count} />
        <StatCard label="Tempo médio resolução"  value={resolutionStr(data.avg_resolution_hours)}
          sub="tickets fechados" />
        <StatCard label="Taxa de resolução"
          value={data.total_assigned > 0 ? `${Math.round((data.resolved / data.total_assigned) * 100)}%` : "—"} />
      </div>

      <ChartCard title="Tickets atribuídos por dia">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data.tickets_by_day} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="techGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={COR_SERIE_TEMPORAL} stopOpacity={0.3} />
                <stop offset="95%" stopColor={COR_SERIE_TEMPORAL} stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={CROMO.grade} />
            <XAxis dataKey="date" stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }}
              tickFormatter={(v: string) => v.slice(5)}
              interval={Math.max(1, Math.floor(data.tickets_by_day.length / 6))} />
            <YAxis stroke={CROMO.eixo} tick={{ fontSize: 10, fill: CROMO.eixo }} allowDecimals={false} />
            <Tooltip contentStyle={ESTILO_DICA} wrapperStyle={{ outline: "none" }}
              labelFormatter={(v) => `Data: ${v}`} formatter={(v) => [v ?? 0, "Tickets"]} />
            {/*
              A terceira série temporal da tela, e a terceira cor: era `#22c55e`
              aqui, `#6366f1` no "criados por dia" e `#f59e0b` na tendência
              CSAT. Três gráficos da mesma natureza — contagem ao longo do tempo
              — em três cores, e a diferença não afirmava nada. Regra do
              operador: mesma medida, uma cor só.
            */}
            <Area type="monotone" dataKey="count" stroke={COR_SERIE_TEMPORAL} strokeWidth={2}
              fill="url(#techGradient)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}

// ── Technician ranking table (admin) ─────────────────────────

function TechnicianRanking({ data, onSelect }: { data: TechnicianListReport; onSelect: (id: string) => void }) {
  function slaColor(rate: number) {
    if (rate >= 90) return "text-success-700 dark:text-success-400";
    if (rate >= 70) return "text-warning-700 dark:text-warning-400";
    return "text-danger-700 dark:text-danger-400";
  }

  return (
    <div className="rounded-xl border border-borda/40 bg-surface overflow-hidden">
      <div className="border-b border-borda/40 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-conteudo">Desempenho por técnico</h2>
      </div>
      <Table>
        <TableHead>
          <TableRow>
            {["Técnico", "Atribuídos", "Resolvidos", "Em aberto", "SLA", "Tempo médio", "CSAT", ""].map((h) => (
              <TableHeaderCell key={h} className="text-[11px] font-semibold">{h}</TableHeaderCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {data.technicians.map((t) => (
            <TableRow key={t.technician_id} className="hover:bg-surface-elevated/50">
              <TableCell className="font-medium">{t.technician_name}</TableCell>
              <TableCell muted>{t.total_assigned}</TableCell>
              <TableCell className="font-medium text-success-700 dark:text-success-400">{t.resolved}</TableCell>
              <TableCell muted>{t.open_count}</TableCell>
              <TableCell className={`font-semibold ${slaColor(t.sla_compliance_rate)}`}>{t.sla_compliance_rate}%</TableCell>
              <TableCell muted>
                {t.avg_resolution_hours != null
                  ? t.avg_resolution_hours >= 24
                    ? `${(t.avg_resolution_hours / 24).toFixed(1)}d`
                    : `${t.avg_resolution_hours.toFixed(1)}h`
                  : "—"}
              </TableCell>
              <TableCell muted>{t.csat_average != null ? `${t.csat_average} ★` : "—"}</TableCell>
              <TableCell>
                {/*
                  O nome acessível era só "Detalhes", oito vezes seguidas na
                  mesma tabela. Quem navega pela lista de controles ouvia oito
                  botões idênticos e nenhum dizia de quem.
                */}
                <button onClick={() => onSelect(t.technician_id)}
                  aria-label={`Detalhes de ${t.technician_name}`}
                  className="rounded-lg border border-action-tint-border bg-action-tint px-2.5 py-1 text-xs font-medium text-conteudo-link hover:bg-action/20 transition-colors cursor-pointer">
                  Detalhes
                </button>
              </TableCell>
            </TableRow>
          ))}
          {data.technicians.length === 0 && (
            <TableEmpty colSpan={8} message="Nenhum técnico ativo encontrado." />
          )}
        </TableBody>
      </Table>
    </div>
  );
}

// ── Technician detail panel (admin drill-down) ────────────────

function TechnicianDetailPanel({ techDetail, techDetailLoading, onClose }: {
  techDetail: TechnicianDetailReport | null;
  techDetailLoading: boolean;
  onClose: () => void;
}) {
  return (
    <div className="rounded-xl border border-borda/40 bg-surface">
      <div className="flex items-center justify-between border-b border-borda/40 px-5 py-3.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-conteudo">
            {techDetail ? `Detalhes — ${techDetail.technician_name}` : "Carregando detalhes…"}
          </span>
        </div>
        <button onClick={onClose}
          className="rounded-lg border border-borda/40 px-3 py-1 text-xs font-medium text-conteudo-muted hover:bg-surface-elevated hover:text-conteudo transition-colors cursor-pointer">
          <Icon name="chevronLeft" size={14} strokeWidth={2.5} /> Fechar
        </button>
      </div>
      <div className="p-5">
        {techDetailLoading && (
          <div className="flex h-32 items-center justify-center"><Spinner size="md" /></div>
        )}
        {!techDetailLoading && techDetail && <TechnicianDetail data={techDetail} />}
      </div>
    </div>
  );
}

// ── Export dropdown ───────────────────────────────────────────

function ExportDropdown({ filters }: { filters: ReportFilters }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 items-center gap-1.5 rounded-lg border border-borda/40 bg-surface-elevated px-3 text-xs font-medium text-conteudo-muted hover:bg-surface hover:text-conteudo transition-colors cursor-pointer"
      >
        <Icon name="download" size={16} strokeWidth={2} />
        Exportar
        <span className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
          <Icon name="chevronDown" size={14} strokeWidth={2.5} />
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-20 min-w-[140px] rounded-xl border border-borda/40 bg-surface shadow-lg overflow-hidden">
          <a
            href={exportReportsUrl("csv", filters)}
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-conteudo hover:bg-surface-elevated transition-colors"
          >
            <Icon name="download" size={16} strokeWidth={2} /> Exportar CSV
          </a>
          <a
            href={exportReportsUrl("pdf", filters)}
            download
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-conteudo hover:bg-surface-elevated transition-colors border-t border-borda/30"
          >
            <Icon name="download" size={16} strokeWidth={2} /> Exportar PDF
          </a>
        </div>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────

type Tab = "global" | "technicians";

export default function ReportsPage() {
  const { user } = useAuth();
  const isAdmin      = user?.role === "admin";
  const isTechnician = user?.role === "technician";

  const [period,      setPeriod]      = useState("30");
  const [customStart, setCustomStart] = useState("");
  const [customEnd,   setCustomEnd]   = useState("");
  const [category,    setCategory]    = useState("");
  const [priority,    setPriority]    = useState("");
  const [tab,         setTab]         = useState<Tab>(isAdmin ? "global" : "technicians");

  const [globalData,        setGlobalData]        = useState<ReportData | null>(null);
  const [globalLoading,     setGlobalLoading]     = useState(false);

  const [techList,          setTechList]          = useState<TechnicianListReport | null>(null);
  const [techListLoading,   setTechListLoading]   = useState(false);

  const [selectedTechId,    setSelectedTechId]    = useState<string | undefined>(isTechnician ? user?.id : undefined);
  const [techDetail,        setTechDetail]        = useState<TechnicianDetailReport | null>(null);
  const [techDetailLoading, setTechDetailLoading] = useState(false);

  const isCustom = period === "personalizado" && !!customStart && !!customEnd;
  const p = isCustom
    ? Math.max(1, Math.ceil((new Date(customEnd).getTime() - new Date(customStart).getTime()) / 86400000))
    : Number(period) || 30;

  const reportFilters: ReportFilters = {
    ...(isCustom ? { start_date: customStart, end_date: customEnd } : { period: p }),
    ...(category ? { category } : {}),
    ...(priority ? { priority } : {}),
  };

  useEffect(() => {
    if (tab !== "global" || !isAdmin) return;
    setGlobalLoading(true);
    getReports(reportFilters).then(setGlobalData).catch(() => {}).finally(() => setGlobalLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, p, isAdmin, category, priority, customStart, customEnd]);

  useEffect(() => {
    if (tab !== "technicians" || !isAdmin) return;
    setTechListLoading(true);
    getTechnicianListReport(p).then(setTechList).catch(() => {}).finally(() => setTechListLoading(false));
  }, [tab, p, isAdmin]);

  useEffect(() => {
    if (isTechnician) {
      setTechDetailLoading(true);
      getTechnicianDetailReport(p).then(setTechDetail).catch(() => {}).finally(() => setTechDetailLoading(false));
      return;
    }
    if (!selectedTechId) return;
    setTechDetailLoading(true);
    getTechnicianDetailReport(p, selectedTechId).then(setTechDetail).catch(() => {}).finally(() => setTechDetailLoading(false));
  }, [p, selectedTechId, isTechnician]);

  function handleSelectTechnician(id: string) {
    setSelectedTechId(id);
    setTechDetail(null);
  }

  const activeFiltersCount = (category ? 1 : 0) + (priority ? 1 : 0);

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "global",       label: "Visão geral", icon: <Icon name="chart" size={16} strokeWidth={2} /> },
    { key: "technicians",  label: "Por técnico", icon: <Icon name="users" size={16} strokeWidth={2} /> },
  ];

  return (
    <div className="space-y-5 pb-10">
      {/* ── Header ───────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-conteudo-heading">Relatórios</h1>
          <p className="mt-0.5 text-sm text-conteudo-muted">
            {isTechnician ? "Suas métricas de desempenho" : "Visão geral e desempenho da equipe"}
            {activeFiltersCount > 0 && (
              <span className="ml-2 rounded-full bg-tint-primary px-2 py-0.5 text-[10px] font-semibold text-on-tint-primary">
                {activeFiltersCount} filtro{activeFiltersCount > 1 ? "s" : ""} ativo{activeFiltersCount > 1 ? "s" : ""}
              </span>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Tabs inline (admin only) */}
          {isAdmin && (
            <div className="flex h-9 items-center gap-0.5 rounded-xl border border-borda/40 bg-surface-elevated px-1">
              {tabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  // A aba ativa era `bg-primary text-white`: 3,83:1, o par que
                  // a catraca cobrava nesta tela. O degrau de AÇÃO é outro
                  // token que não o de marca, e o par dele é `text-on-primary`
                  // — branco no claro, navy no escuro, porque `text-white`
                  // cravado dá 2,69:1 sobre o degrau de ação do tema escuro.
                  aria-pressed={tab === t.key}
                  className={`flex h-7 items-center gap-2 rounded-lg px-4 text-sm font-medium transition-all cursor-pointer ${
                    tab === t.key
                      ? "bg-action text-on-primary shadow-sm"
                      : "text-conteudo-muted hover:text-conteudo hover:bg-surface"
                  }`}
                >
                  {t.icon}
                  {t.label}
                </button>
              ))}
            </div>
          )}

          {/* D9.2 — cinco períodos fixos no código: lista curta e conhecida,
              logo `<select>` nativo. Sem `placeholder`: a opção vazia que ele
              desenha devolveria `""`, que `Number(period) || 30` traduz de volta
              para trinta dias enquanto o gatilho anuncia "Período" — um estado
              que mostra um número e diz outro. Escolher o período é obrigatório
              e sempre foi.

              O rótulo é `sr-only` porque a barra não tem espaço para ele: sem
              rótulo o filtro se anunciava "Últimos 30 dias", sem dizer de quê. */}
          <span id="rotulo-filtro-periodo" className="sr-only">
            Período
          </span>
          <Select
            id="filtro-periodo"
            aria-labelledby="rotulo-filtro-periodo"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            options={PERIOD_OPTIONS}
          />

          {period === "personalizado" && (
            <div className="flex h-9 items-center gap-1.5 rounded-lg border border-borda/60 bg-surface-elevated px-3 text-sm">
              <span className="shrink-0 text-conteudo-muted"><Icon name="calendar" size={14} strokeWidth={2} /></span>
              <input type="date" value={customStart} max={customEnd || undefined}
                onChange={(e) => setCustomStart(e.target.value)}
                className="bg-transparent text-conteudo text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]" />
              <span className="text-conteudo-muted text-xs">até</span>
              <input type="date" value={customEnd} min={customStart || undefined}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="bg-transparent text-conteudo text-xs outline-none cursor-pointer w-28 [color-scheme:light] dark:[color-scheme:dark]" />
            </div>
          )}

          {/* Filtros de categoria e prioridade (visão geral apenas) */}
          {(isAdmin && tab === "global") || isTechnician ? (
            <>
              {/* D9.2 — oito categorias e quatro prioridades, ambas vindas de
                  `lib/categoria.ts` e `lib/prioridade.ts` e nenhuma da rede:
                  listas curtas e conhecidas, logo `<select>` nativo. Aqui o
                  `placeholder` FICA — o vazio significa "todas", e é o estado
                  inicial dos dois. */}
              <span id="rotulo-filtro-categoria" className="sr-only">
                Categoria
              </span>
              <Select
                id="filtro-categoria"
                aria-labelledby="rotulo-filtro-categoria"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                options={CATEGORY_OPTIONS}
                placeholder="Todas as categorias"
              />
              <span id="rotulo-filtro-prioridade" className="sr-only">
                Prioridade
              </span>
              <Select
                id="filtro-prioridade"
                aria-labelledby="rotulo-filtro-prioridade"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                options={PRIORITY_OPTIONS}
                placeholder="Todas as prioridades"
              />
            </>
          ) : null}

          {isAdmin && <ExportDropdown filters={reportFilters} />}
        </div>
      </div>

      {/* ── Global tab (admin) ── */}
      {isAdmin && tab === "global" && (
        globalLoading
          ? <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
          : globalData
            ? <GlobalReport data={globalData} period={p} />
            : null
      )}

      {/* ── Technicians tab (admin) ── */}
      {isAdmin && tab === "technicians" && (
        <div className="space-y-4">
          {/* Seletor rápido de técnico */}
          {techList && techList.technicians.length > 0 && (
            <div className="flex items-center gap-3 rounded-xl border border-borda/40 bg-surface px-4 py-3">
              <span className="text-xs font-medium text-conteudo-muted shrink-0">Ver detalhes de:</span>
              {/* D9.2 — lista LONGA: os técnicos vêm da rede e crescem com a
                  equipe, então o controle é o `Selector variant="filter"`.

                  O "Ver detalhes de:" ao lado é texto solto, nunca foi
                  `<label>` de nada; o `label` do `Selector` é que dá nome ao
                  controle. */}
              <Selector
                variant="filter"
                label="Técnico"
                value={selectedTechId ?? ""}
                onChange={(v) => v ? handleSelectTechnician(v) : (setSelectedTechId(undefined), setTechDetail(null))}
                options={techList.technicians.map((t) => ({ value: t.technician_id, label: t.technician_name }))}
                placeholder="Selecione um técnico"
              />
              {selectedTechId && (
                <button
                  onClick={() => { setSelectedTechId(undefined); setTechDetail(null); }}
                  className="text-xs text-conteudo-muted hover:text-conteudo transition-colors cursor-pointer shrink-0"
                >
                  Limpar
                </button>
              )}
            </div>
          )}

          {techListLoading
            ? <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
            : techList && <TechnicianRanking data={techList} onSelect={handleSelectTechnician} />
          }

          {selectedTechId && (
            <TechnicianDetailPanel
              techDetail={techDetail}
              techDetailLoading={techDetailLoading}
              onClose={() => { setSelectedTechId(undefined); setTechDetail(null); }}
            />
          )}
        </div>
      )}

      {/* ── Technician own view ── */}
      {isTechnician && (
        techDetailLoading
          ? <div className="flex h-48 items-center justify-center"><Spinner size="lg" /></div>
          : techDetail
            ? <TechnicianDetail data={techDetail} />
            : null
      )}
    </div>
  );
}
