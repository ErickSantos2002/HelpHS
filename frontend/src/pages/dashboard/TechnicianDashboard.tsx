import { useNavigate } from "react-router-dom";
import {
  Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Icon, KpiCard, Spinner, StatusBadge } from "../../components/ui";
import { FalhaDoBloco } from "../../components/relatorios/FalhaDoBloco";
import { SeletorDePeriodo } from "../../components/relatorios/SeletorDePeriodo";
import { cn } from "../../lib/utils";
import { CROMO, COR_SERIE_TEMPORAL, ENVOLTORIO_DICA, ESTILO_DICA } from "../../lib/grafico";
import { PRIORIDADE } from "../../lib/prioridade";
import { rotuloDoPreset } from "../../lib/periodoRelatorio";
import { useCarga, type Carga } from "../../lib/useCarga";
import { usePeriodoDoRelatorio } from "../../lib/usePeriodoDoRelatorio";
import { useAuth } from "../../contexts/AuthContext";
import { getDashboardStats } from "../../services/dashboardService";
import { getTechnicianDetailReport } from "../../services/reportService";
import { getTickets, type Ticket } from "../../services/ticketService";

// ── Period config ─────────────────────────────────────────────
//
// As opções e as datas saem de `lib/periodoRelatorio.ts`, as mesmas do
// dashboard do admin e dos Relatórios (F1-B-03b). Só o relatório do técnico
// depende do período; as listas de chamados e a fila são o estado de AGORA.

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
  // Chamado que ainda nao foi triado nao tem entrada no mapa: `undefined`
  // cai no mesmo recuo neutro que o `?.` abaixo ja dava.
  const prioridade = ticket.priority ? PRIORIDADE[ticket.priority] : undefined;

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
      <span className="sr-only">
        {prioridade ? `Prioridade ${prioridade.rotulo}.` : "Sem prioridade."}
      </span>
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
  title, count, tickets, emptyMsg, showTech, carga,
}: {
  title: string; count: number; tickets: Ticket[]; emptyMsg: string; showTech?: boolean;
  /** A carga da lista: enquanto não está pronta, nem contagem nem "lista vazia". */
  carga: Carga<unknown>;
}) {
  const pronta = carga.fase === "pronto";
  return (
    <div className="rounded-xl bg-surface border border-borda overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-borda/60 shrink-0">
        <p className="text-sm font-semibold text-conteudo">{title}</p>
        {pronta && (
          <span className="text-xs font-medium text-conteudo-muted bg-surface-elevated px-2 py-0.5 rounded-full">{count}</span>
        )}
      </div>
      {!pronta ? (
        // Falha não é "Fila limpa": a lista vazia só é dita quando a lista
        // chegou e veio vazia.
        <div className="flex items-center justify-center py-10 text-sm text-conteudo-muted">
          {carga.fase === "falha" ? "Indisponível — veja o aviso acima." : <Spinner size="md" />}
        </div>
      ) : tickets.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 gap-2">
          <div className="w-8 h-8 rounded-full bg-surface-elevated flex items-center justify-center">
            <Icon name="check" size={16} strokeWidth={1.5} className="text-conteudo-muted" />
          </div>
          <p className="text-sm text-conteudo-muted">{emptyMsg}</p>
        </div>
      ) : (
        // `relative`: quem rola, contém. O "Prioridade …" de cada linha é
        // `sr-only`, e o das linhas abaixo dos 168px escapava da caixa e
        // esticava a rolagem da página. Ver o `<main>` na `AppLayout`.
        <div className="relative overflow-y-auto max-h-[168px] divide-y divide-borda/60">
          {tickets.map((t) => <TicketRow key={t.id} ticket={t} showTech={showTech} />)}
        </div>
      )}
    </div>
  );
}

// ── TechnicianDashboard ───────────────────────────────────────

interface TechGroup { name: string; tickets: Ticket[] }

/** Os chamados ativos dos colegas, agrupados por técnico. */
async function carregaEquipe(meuId: string): Promise<TechGroup[]> {
  const respostas = await Promise.all([
    getTickets({ status: "open", limit: 200 }),
    getTickets({ status: "in_progress", limit: 200 }),
    getTickets({ status: "awaiting_client", limit: 200 }),
    getTickets({ status: "awaiting_technical", limit: 200 }),
  ]);
  const map = new Map<string, TechGroup>();
  for (const t of respostas.flatMap((x) => x.items)) {
    if (!t.assignee_id || t.assignee_id === meuId) continue;
    if (!map.has(t.assignee_id)) map.set(t.assignee_id, { name: t.assignee_name ?? "Técnico", tickets: [] });
    map.get(t.assignee_id)!.tickets.push(t);
  }
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export default function TechnicianDashboard() {
  const { user } = useAuth();
  const periodo = usePeriodoDoRelatorio();
  const { intervalo } = periodo;
  const periodLabel = periodo.preset === "personalizado"
    ? (periodo.descricao ?? "Personalizado")
    : rotuloDoPreset(periodo.preset);

  // ── As cargas, uma por bloco (F1-B-03b) ──────────────────────────────
  //
  // Eram um `Promise.all` só. A falha do relatório virava ZEROS e SLA de 100%
  // sem aviso nenhum (um `.catch(() => emptyDetail)` fabricava o relatório),
  // e a falha de qualquer outra chamada derrubava a tela inteira, com o
  // seletor junto e sem saída além de recarregar a página.
  //
  // Só o relatório (`detail`) depende do período. As listas e a fila são o
  // estado de agora, e trocar de período não as pede de novo.
  const detail = useCarga(
    user && intervalo ? () => getTechnicianDetailReport(intervalo) : null,
    `${periodo.chave}|${user?.id ?? ""}`,
    "Não foi possível carregar o seu desempenho no período.",
  );
  const stats = useCarga(
    user ? getDashboardStats : null,
    "stats",
    "Não foi possível carregar a fila geral.",
  );
  const meus = useCarga(
    user ? () => getTickets({ assignee_id: user.id, limit: 200 }).then((r) => r.items) : null,
    `meus|${user?.id ?? ""}`,
    "Não foi possível carregar os seus chamados.",
  );
  const fila = useCarga(
    user ? () => getTickets({ status: "open", limit: 200 }).then((r) => r.items) : null,
    "fila",
    "Não foi possível carregar a fila de chamados abertos.",
  );
  const equipe = useCarga(
    user ? () => carregaEquipe(user.id) : null,
    `equipe|${user?.id ?? ""}`,
    "Não foi possível carregar os chamados da equipe.",
  );

  const myTickets = meus.dados ?? [];
  const queue = fila.dados ?? [];
  const teamAllTickets = (equipe.dados ?? []).flatMap((g) => g.tickets);
  const myActiveCount = myTickets.filter((t) => t.status === "open" || t.status === "in_progress").length;
  const myBreachCount = myTickets.filter((t) => t.sla_response_breach || t.sla_resolve_breach).length;
  const d = detail.dados;

  /** O subtítulo de um indicador cuja carga ainda não está pronta. */
  const subDaCarga = (c: Carga<unknown>, pronto: string) =>
    c.fase === "pronto" ? pronto : c.fase === "falha" ? "Indisponível" : "Carregando…";

  const falhas: { titulo: string; carga: Carga<unknown> }[] = [
    { titulo: "Meu desempenho", carga: detail },
    { titulo: "Fila geral", carga: stats },
    { titulo: "Meus tickets", carga: meus },
    { titulo: "Fila — tickets abertos", carga: fila },
    { titulo: "Tickets da equipe", carga: equipe },
  ].filter((f) => f.carga.fase === "falha");

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

        {/* O seletor fica fora de qualquer ramo de erro: é por ele que a pessoa
            sai de uma falha trocando de período. */}
        <SeletorDePeriodo
          preset={periodo.preset}
          onPreset={periodo.setPreset}
          inicio={periodo.inicio}
          fim={periodo.fim}
          onInicio={periodo.setInicio}
          onFim={periodo.setFim}
          erro={periodo.erro}
          descricao={periodo.descricao}
        />
      </div>

      {/* ── Falhas, uma por carga, cada uma com o seu "Tentar de novo" ── */}
      {falhas.map((f) => (
        <FalhaDoBloco
          key={f.titulo}
          titulo={f.titulo}
          erro={f.carga.erro}
          onTentarDeNovo={f.carga.tentarDeNovo}
        />
      ))}

      {/* ── KPI Row ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Meus tickets ativos"
          value={meus.fase === "pronto" ? myActiveCount : "—"}
          sub={subDaCarga(meus, "Abertos + em andamento")}
          tone={myActiveCount > 0 ? "info" : "neutral"}
          icon={<Icon name="clipboard" size={20} />}
        />
        <KpiCard
          label="Fila geral aberta"
          value={stats.dados?.tickets.open ?? "—"}
          sub={subDaCarga(stats, "Aguardando atendimento")}
          tone="neutral"
          icon={<Icon name="inbox" size={20} />}
        />
        <KpiCard
          label="SLA em risco"
          value={meus.fase === "pronto" ? myBreachCount : "—"}
          sub={subDaCarga(meus, "Nos meus tickets")}
          tone={myBreachCount > 0 ? "danger" : "neutral"}
          icon={<Icon name="warning" size={20} />}
        />
        <KpiCard
          label="Meu CSAT"
          value={d?.csat_average != null ? `${d.csat_average.toFixed(1)} / 10` : "—"}
          sub={subDaCarga(detail, `${d?.csat_count ?? 0} avaliações · ${periodLabel}`)}
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
            {!d ? (
              <div className="flex h-44 items-center justify-center text-sm text-conteudo-muted">
                {detail.fase === "falha" ? "Indisponível — veja o aviso acima." : <Spinner size="md" />}
              </div>
            ) : d.tickets_by_day.length === 0 ? (
              <p className="text-conteudo-muted text-sm py-8 text-center">Sem dados para o período</p>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                {/* Série temporal de medida única — chamados por dia —, então uma
                    cor só, `COR_SERIE_TEMPORAL`. Era `#0ea5e9` cravado, a quarta
                    cor diferente entre cinco gráficos da mesma natureza. */}
                <AreaChart data={d.tickets_by_day} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
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
          {/* Sem relatório, nenhum número: a falha virava zeros e "100%" de
              conformidade, e quem olhava lia "não atendi nada, tudo no
              prazo". */}
          {!d ? (
            <div className="flex h-44 items-center justify-center text-sm text-conteudo-muted">
              {detail.fase === "falha" ? "Indisponível — veja o aviso acima." : <Spinner size="md" />}
            </div>
          ) : (
          <div className="p-5 space-y-4">
            {[
              { label: "Atribuídos",        value: d.total_assigned },
              { label: "Resolvidos",         value: d.resolved },
              { label: "Em andamento",       value: d.in_progress },
              { label: "SLA violados",       value: d.sla_breached,                             danger: d.sla_breached > 0 },
              { label: "Tempo médio",        value: formatHours(d.avg_resolution_hours),        raw: true },
              // Sem chamado atribuído no período não há conformidade a medir
              // (D3): a API manda 100, e a tela diz "—".
              { label: "Conformidade SLA",   value: d.total_assigned > 0 ? `${d.sla_compliance_rate.toFixed(0)}%` : "—", raw: true },
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
          )}
        </div>
      </div>

      {/* ── Ticket lists ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TicketListCard
          title="Meus tickets"
          count={myTickets.length}
          tickets={myTickets}
          emptyMsg="Nenhum ticket atribuído"
          carga={meus}
        />
        <TicketListCard
          title="Tickets da equipe"
          count={teamAllTickets.length}
          tickets={teamAllTickets}
          emptyMsg="Nenhum ticket ativo na equipe"
          showTech
          carga={equipe}
        />
        <TicketListCard
          title="Fila — Tickets abertos"
          count={queue.length}
          tickets={queue}
          emptyMsg="Fila limpa"
          carga={fila}
        />
      </div>
    </div>
  );
}
