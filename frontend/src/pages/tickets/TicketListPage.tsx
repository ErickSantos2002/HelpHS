import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Avatar,
  Button,
  Icon,
  PriorityBadge,
  Select,
  Spinner,
} from "../../components/ui";
import {
  PRIORIDADE,
  PRIORIDADES,
  TOM_PRIORIDADE,
  varianteDePrioridade,
  type TicketPriority,
} from "../../lib/prioridade";
import {
  STATUS,
  STATUS_ORDEM,
  TOM_STATUS,
  type TicketStatus,
} from "../../lib/status";
import { cn } from "../../lib/utils";
import { getTickets, type Ticket } from "../../services/ticketService";

/**
 * A prioridade e o status saem dos modulos, e nao de mapas locais.
 *
 * Havia dois aqui, e os dois divergiam do resto do sistema:
 *
 *   PRIORITY_CFG era o SETIMO mapa de prioridade das telas. Dizia "Critico",
 *   "Alto", "Medio", "Baixo" no masculino — contra o feminino que a emenda E17
 *   fixou no pacote — e pintava `medium` de INDIGO (#818cf8), que nao e a
 *   variante `info` de nenhum dos outros seis.
 *
 *   COLUMNS mapeava os seis status com a paleta CRUA do Tailwind (sky, indigo,
 *   amber, violet, emerald, slate) mais seis hexadecimais cravados, e com
 *   rotulos proprios ("Ag. Tecnico" contra "Aguardando tecnico").
 *
 * As colunas agora vem de `lib/status.ts`, na ordem do ciclo de vida.
 */
const COLUNAS = STATUS_ORDEM.filter((s) => s !== "cancelled");

/**
 * O `cancelled` NAO tem coluna, e isso e anterior a esta migracao.
 *
 * O quadro mostra seis dos sete status. Um chamado cancelado simplesmente
 * DESAPARECE da lista — nao ha coluna para ele e nenhum aviso de que ele
 * existe. Nao foi mexido aqui porque acrescentar uma setima coluna e decisao de
 * produto, nao de sistema de design.
 *
 * Fica registrado no relatorio da Fase 11 e no escopo da Fase 16.
 */

// ── SLA indicator ─────────────────────────────────────────────

const TERMINAL_STATUSES = ["resolved", "closed", "cancelled"];

function formatDuration(ms: number): string {
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  if (h >= 24) {
    const d = Math.floor(h / 24);
    const rh = h % 24;
    return rh > 0 ? `${d}d ${rh}h` : `${d}d`;
  }
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function SlaIndicator({ ticket, now }: { ticket: Ticket; now: number }) {
  const isOpen     = ticket.status === "open";
  const isTerminal = TERMINAL_STATUSES.includes(ticket.status);

  // Terminal: mostrar tempo total que o ticket ficou aberto
  if (isTerminal) {
    const endMs     = ticket.closed_at ? new Date(ticket.closed_at).getTime() : new Date(ticket.updated_at).getTime();
    const createdMs = new Date(ticket.created_at).getTime();
    const duration  = formatDuration(endMs - createdMs);
    const breached  = ticket.sla_response_breach || ticket.sla_resolve_breach;
    return (
      <div className="mt-2.5 space-y-1">
        <div
          className={cn(
            "flex items-center gap-1 text-[10px] font-bold",
            breached ? "text-on-tint-danger" : "text-on-tint-success",
          )}
        >
          <Icon name="check" size={12} strokeWidth={2} />
          <span>{breached ? `Concluído em ${duration} • SLA vencido` : `Concluído em ${duration} • No prazo`}</span>
        </div>
      </div>
    );
  }

  // Phase: 1ª resposta enquanto aberto, resolução depois
  const dueAt  = isOpen ? ticket.sla_response_due_at : ticket.sla_resolve_due_at;
  const breach = isOpen ? ticket.sla_response_breach  : ticket.sla_resolve_breach;
  const phase  = isOpen ? "1ª Resposta" : "Resolução";

  if (!dueAt) return null;

  // Resposta já dada: o relógio da 1ª resposta não corre mais. Sem isto, o
  // chamado respondido pelo chat — que não sai de "open" — virava "SLA
  // Vencido" assim que o prazo passava, com a resposta dada há horas. Quem
  // pode calar o "Vencido" é a resposta, nunca a flag `breach`: ela só é
  // recalculada em escrita, e um chamado vencido e intocado chega com ela
  // falsa. Ver SlaChip.
  if (isOpen && ticket.sla_first_response) {
    return (
      <div className="mt-2.5 space-y-1">
        <div
          role="progressbar"
          aria-label={`Prazo de ${phase}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={100}
          aria-valuetext={breach ? "respondida com atraso" : "respondida"}
          className="h-1 w-full overflow-hidden rounded-full bg-surface-elevated"
        >
          <div className="h-full w-full rounded-full bg-fill-success" />
        </div>
        <div
          className={cn(
            "flex items-center gap-1 text-[10px] font-bold",
            breach ? "text-on-tint-danger" : "text-on-tint-success",
          )}
        >
          <Icon name="check" size={12} strokeWidth={2} />
          <span>{breach ? "1ª Resposta: respondida com atraso" : "1ª Resposta: respondida"}</span>
        </div>
      </div>
    );
  }

  const dueMs     = new Date(dueAt).getTime();
  const createdMs = new Date(ticket.created_at).getTime();
  const totalMs   = dueMs - createdMs;
  const timeLeft  = dueMs - now;
  const breached  = timeLeft <= 0 || breach;
  const pct       = totalMs > 0 ? Math.min(100, Math.max(0, ((now - createdMs) / totalMs) * 100)) : 100;

  // Color thresholds
  const isRed    = breached || pct >= 80;
  const isAmber  = !isRed && pct >= 60;
  // Preenchimento pelos `--fill-*`, e texto pelos `on-tint-*`. Sao pares
  // diferentes de propositos diferentes: a barra e forma (piso 3:1) e o rotulo
  // e texto (piso 4,5:1). Os hexadecimais que estavam aqui — #ef4444, #f59e0b,
  // #10b981 — nao passavam por nenhum dos dois: o ambar dava 1,96 no claro.
  const barraCls = isRed
    ? "bg-fill-danger"
    : isAmber
      ? "bg-fill-warning"
      : "bg-fill-success";
  const textCls = isRed
    ? "text-on-tint-danger"
    : isAmber
      ? "text-on-tint-warning"
      : "text-on-tint-success";

  // Format remaining time
  let display = "";
  if (!breached && timeLeft > 0) {
    const h = Math.floor(timeLeft / 3_600_000);
    const m = Math.floor((timeLeft % 3_600_000) / 60_000);
    display = h > 0 ? `${h}h ${m}m` : `${m}m`;
  }

  return (
    <div className="mt-2.5 space-y-1">
      {/* A barra é `progressbar` de verdade, e não uma div colorida: tem escala
          de 0 a 100 e um alvo. O `aria-valuetext` troca o anúncio de "65%" —
          que não diz nada a quem ouve — pelo tempo que sobra, que é o que a
          pessoa precisa saber. O `Progress.jsx` do pacote já nasceu com essa
          semântica, copiada do ChamadosHS; ela nunca tinha voltado para cá. */}
      <div
        role="progressbar"
        aria-label={`Prazo de ${phase}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        aria-valuetext={breached ? "prazo vencido" : `${display} restantes`}
        
        className="h-1 w-full overflow-hidden rounded-full bg-surface-elevated"
      >
        <div
          className={cn("h-full rounded-full transition-all duration-700", barraCls)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className={cn("flex items-center gap-1 text-[10px] font-bold", textCls)}>
        <Icon name="clock" size={12} strokeWidth={2} />
        <span>{breached ? "SLA Vencido" : `${phase}: ${display}`}</span>
      </div>
    </div>
  );
}

// ── TicketCard ────────────────────────────────────────────────

/**
 * O cartao do chamado.
 *
 * ── Era um `<button onClick={navigate}>` ──────────────────────────────
 *
 * Navegacao e link (regra registrada no `DECISOES.md`). O botao tirava do
 * cartao tudo o que um link tem: nao abre em aba nova com Ctrl, nao aparece no
 * menu de contexto, nao mostra o destino na barra de status, e o leitor de tela
 * anuncia "botao" para algo que muda de pagina.
 *
 * ── O ponto de prioridade some da arvore ──────────────────────────────
 *
 * Ele tinha `title` com o rotulo, e `title` nao e nome acessivel confiavel — em
 * varios leitores nao e anunciado. Mas a informacao nao se perdeu: o selo do
 * rodape mostra a prioridade em TEXTO. O ponto passa a ser o que sempre foi na
 * pratica, decoracao, e sai da arvore com `aria-hidden`.
 */
function TicketCard({ ticket, now }: { ticket: Ticket; now: number }) {
  const variante = varianteDePrioridade(ticket.priority);
  const hasBreach = ticket.sla_response_breach || ticket.sla_resolve_breach;

  return (
    <Link
      to={`/tickets/${ticket.id}`}
      className={cn(
        "block w-full rounded-lg text-left",
        "bg-surface",
        "border border-borda border-l-4",
        "p-3 shadow-sm hover:shadow-md hover:-translate-y-0.5 active:translate-y-0",
        "transition-all duration-150 group",
        TOM_PRIORIDADE[variante].borda,
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-1">
        <span className="truncate font-mono text-[11px] text-conteudo-muted">
          {ticket.protocol}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          {hasBreach && (
            <span className="rounded bg-tint-danger px-1.5 py-0.5 text-[10px] font-bold text-on-tint-danger">
              SLA
            </span>
          )}
          <span
            aria-hidden="true"
            className={cn("h-2 w-2 rounded-full", TOM_PRIORIDADE[variante].ponto)}
          />
        </div>
      </div>

      <p className="mb-3 line-clamp-2 text-sm font-medium leading-snug text-conteudo transition-colors duration-150 group-hover:text-conteudo-link">
        {ticket.title}
      </p>

      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
          <span className="max-w-[100px] truncate rounded bg-surface-elevated px-2 py-0.5 text-[11px] text-conteudo-muted">
            {ticket.category}
          </span>
          <PriorityBadge priority={ticket.priority} />
        </div>
        {ticket.assignee_name ? (
          <Avatar name={ticket.assignee_name} size="xs" />
        ) : (
          <span
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-borda bg-surface-elevated text-conteudo-muted"
            title="Sem responsável"
          >
            <Icon name="user" size={12} strokeWidth={2} />
            <span className="sr-only">Sem responsável</span>
          </span>
        )}
      </div>

      <SlaIndicator ticket={ticket} now={now} />
    </Link>
  );
}

// ── KanbanColumn ──────────────────────────────────────────────

/**
 * Uma coluna do quadro.
 *
 * A cor vem da variante da §16, e nao de uma paleta propria. Consequencia
 * visivel e deliberada: `awaiting_technical` e `awaiting_client` passam a
 * compartilhar o ambar, onde antes eram ambar e violeta.
 *
 * Isso e a §16, nao descuido — os dois SAO o mesmo estado para quem olha o
 * quadro, e o que os separa e quem esta devendo resposta, que e informacao de
 * texto. E a medicao da E18 mostrou que nem daria para mante-los distintos com
 * rigor: no tema claro, dois degraus de `warning` que passem 3:1 nas tres
 * superficies ficam a 12,2 de DeltaE, contra um piso de 20.
 *
 * O titulo da coluna e um `<h2>`, e nao um `<p>`: seis regioes com nome sao o
 * que da a quem navega por cabecalho um sumario do quadro. Antes eram seis
 * paragrafos, e o leitor de tela nao tinha como pular de coluna em coluna.
 */
function KanbanColumn({
  status,
  tickets,
  now,
}: {
  status: TicketStatus;
  tickets: Ticket[];
  now: number;
}) {
  const s = STATUS[status];
  const tom = TOM_STATUS[s.variante];

  return (
    <section
      aria-labelledby={`coluna-${status}`}
      className="flex w-[268px] min-w-[268px] flex-col overflow-hidden rounded-xl border border-borda bg-surface-elevated"
    >
      <div className={cn("shrink-0 px-3 py-3", tom.fundo)}>
        <div className="flex items-center justify-between">
          <div className="flex min-w-0 items-center gap-2">
            <span
              aria-hidden="true"
              className={cn("h-2 w-2 shrink-0 rounded-full", tom.ponto)}
            />
            <h2
              id={`coluna-${status}`}
              className={cn("truncate text-sm font-semibold", tom.texto)}
            >
              {s.curto}
            </h2>
          </div>
          <span
            className={cn(
              "ml-2 shrink-0 rounded-full bg-surface px-2 py-0.5 text-xs font-bold",
              tom.texto,
            )}
          >
            {tickets.length}
            <span className="sr-only">
              {tickets.length === 1 ? " chamado" : " chamados"}
            </span>
          </span>
        </div>
        <p className={cn("mt-0.5 pl-4 text-[11px]", tom.texto)}>{s.descricao}</p>
      </div>

      <div className={cn("h-0.5 shrink-0", tom.ponto)} />

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {tickets.length === 0 ? (
          <div className="mx-1 mt-1 flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-borda/60 py-10">
            <Icon
              name="check"
              size={24}
              strokeWidth={1.25}
              className="mb-1.5 text-conteudo-muted"
            />
            <p className="text-xs text-conteudo-muted">Nenhum chamado</p>
          </div>
        ) : (
          tickets.map((t) => <TicketCard key={t.id} ticket={t} now={now} />)
        )}
      </div>
    </section>
  );
}

// ── TicketListPage ────────────────────────────────────────────

export default function TicketListPage() {

  const [tickets, setTickets]               = useState<Ticket[]>([]);
  const [loading, setLoading]               = useState(true);
  const [error, setError]                   = useState<string | null>(null);
  const [search, setSearch]                 = useState("");
  const [filterPriority, setFilterPriority] = useState("");
  const [filterAssignee, setFilterAssignee] = useState<"all" | "unassigned" | "assigned">("all");

  // Clock compartilhado — atualiza todos os cards a cada minuto sem um interval por card
  const [now, setNow] = useState(() => Date.now());
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    clockRef.current = setInterval(() => setNow(Date.now()), 60_000);
    return () => { if (clockRef.current) clearInterval(clockRef.current); };
  }, []);

  // Drag-to-scroll no Kanban
  const scrollRef = useRef<HTMLDivElement>(null);
  const dragState = useRef({ active: false, startX: 0, scrollLeft: 0 });

  function onMouseDown(e: React.MouseEvent) {
    if (!scrollRef.current) return;
    dragState.current = { active: true, startX: e.pageX - scrollRef.current.offsetLeft, scrollLeft: scrollRef.current.scrollLeft };
    scrollRef.current.classList.add("dragging");
  }
  function onMouseMove(e: React.MouseEvent) {
    if (!dragState.current.active || !scrollRef.current) return;
    e.preventDefault();
    const x = e.pageX - scrollRef.current.offsetLeft;
    scrollRef.current.scrollLeft = dragState.current.scrollLeft - (x - dragState.current.startX);
  }
  function stopDrag() {
    dragState.current.active = false;
    scrollRef.current?.classList.remove("dragging");
  }

  useEffect(() => {
    setLoading(true);
    getTickets({ limit: 500 })
      .then((r) => setTickets(r.items))
      .catch(() => setError("Não foi possível carregar os tickets."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    let items = tickets;
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter((t) =>
        t.title.toLowerCase().includes(q) || t.protocol.toLowerCase().includes(q),
      );
    }
    if (filterPriority) items = items.filter((t) => t.priority === filterPriority);
    if (filterAssignee === "unassigned") items = items.filter((t) => !t.assignee_id);
    if (filterAssignee === "assigned")   items = items.filter((t) => !!t.assignee_id);
    return items;
  }, [tickets, search, filterPriority, filterAssignee]);

  const grouped = useMemo(() => {
    const map = new Map<string, Ticket[]>();
    COLUNAS.forEach((s) => map.set(s, []));
    for (const t of filtered) {
      if (map.has(t.status)) map.get(t.status)!.push(t);
    }
    for (const arr of map.values()) {
      // A ordem vem do modulo: `ordem` e a urgencia, do mais critico ao menos.
      arr.sort(
        (a, b) =>
          (PRIORIDADE[a.priority as TicketPriority]?.ordem ?? 3) -
          (PRIORIDADE[b.priority as TicketPriority]?.ordem ?? 3),
      );
    }
    return map;
  }, [filtered]);

  const totalShown = filtered.filter((t) =>
    COLUNAS.some((s) => s === t.status),
  ).length;
  const hasFilters = !!(search || filterPriority || filterAssignee !== "all");

  if (loading) return <div className="flex h-64 items-center justify-center"><Spinner size="lg" /></div>;
  if (error)   return <Alert variant="danger">{error}</Alert>;

  return (
    // h-full fills the <main> container; flex-col stacks header + board
    <div className="h-full flex flex-col gap-4 min-h-0">

      {/* ── Top bar ─────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center sm:justify-between gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4 shrink-0">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-conteudo-heading">Tickets</h1>
          <p className="mt-0.5 text-sm text-conteudo-muted">
            {totalShown} ticket{totalShown !== 1 ? "s" : ""} encontrado{totalShown !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Filters + new */}
        <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
          {/* Search */}
          <div className="relative w-full sm:w-auto">
            <Icon
              name="search"
              size={16}
              strokeWidth={2}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-conteudo-muted"
            />
            <input
              type="text"
              placeholder="Título, protocolo ou nº de série…"
              title="Busca por título do chamado, protocolo (HS-2026-0001) ou número de série do equipamento"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-8 py-2 text-sm w-full sm:w-52 rounded-lg border border-borda/60 bg-surface-elevated text-conteudo placeholder:text-conteudo-muted focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-colors"
            />
            {search && (
              // Este botao nao tinha nome acessivel: so o `<svg>` dentro, e o
              // `Icon` e `aria-hidden`. Quem usa leitor de tela ouvia "botao".
              <button
                type="button"
                aria-label="Limpar busca"
                onClick={() => setSearch("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 cursor-pointer text-conteudo-muted hover:text-conteudo"
              >
                <Icon name="close" size={14} strokeWidth={2.5} />
              </button>
            )}
          </div>

          {/* Priority — D9.2: quatro prioridades, fixas em `lib/prioridade.ts` e
              nenhuma vinda da rede. Lista curta e conhecida, logo `<select>`
              nativo.

              O ponto de cor sai junto: o `<option>` nativo não aceita marcador,
              e a cor nunca foi o que distinguia as quatro — o rótulo escrito é.
              O selo da própria linha do chamado continua pintando pela mesma
              fonte.

              O rótulo é `sr-only`: sem ele o filtro se anunciava "Alta". */}
          <span id="rotulo-filtro-prioridade" className="sr-only">
            Prioridade
          </span>
          <Select
            id="filtro-prioridade"
            aria-labelledby="rotulo-filtro-prioridade"
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            placeholder="Todas prioridades"
            options={PRIORIDADES.map((p) => ({
              value: p,
              label: PRIORIDADE[p].rotulo,
            }))}
          />

          {/* Assignee — D9.2: duas opções escritas aqui mesmo. Não há lista
              mais curta nem mais conhecida que esta. */}
          <span id="rotulo-filtro-tecnico" className="sr-only">
            Atribuição
          </span>
          <Select
            id="filtro-tecnico"
            aria-labelledby="rotulo-filtro-tecnico"
            value={filterAssignee === "all" ? "" : filterAssignee}
            onChange={(e) => setFilterAssignee((e.target.value || "all") as typeof filterAssignee)}
            placeholder="Todos"
            options={[
              { value: "unassigned", label: "Sem técnico" },
              { value: "assigned",   label: "Com técnico" },
            ]}
          />

          {/* Clear filters */}
          {hasFilters && (
            <button
              type="button"
              onClick={() => { setSearch(""); setFilterPriority(""); setFilterAssignee("all"); }}
              className="flex items-center gap-1.5 text-xs font-medium text-conteudo-muted hover:text-on-tint-danger transition-colors cursor-pointer px-2 py-2 rounded-lg border border-borda/40 hover:border-danger/30"
            >
              <Icon name="close" size={14} strokeWidth={2.5} />
              Limpar
            </button>
          )}

          {/* Era `<button onClick={navigate}>` com `bg-primary text-white`
              cravado — navegacao vestida de botao, e o par que a emenda E1
              mediu em 3,83:1. O primitivo resolve as duas coisas. */}
          <Button
            to="/tickets/new"
            icon={<Icon name="plus" size={16} strokeWidth={2.5} />}
          >
            Abrir chamado
          </Button>
        </div>
      </div>

      {/* ── Kanban Board ─────────────────────────────────────── */}
      {/* flex-1 min-h-0 = preenche o restante sem overflow vertical */}
      {/* O fundo do quadro era `bg-slate-200/60 dark:bg-slate-900/50`, dois
          valores crus escolhidos a mao por tema. `--bg-base` ja e o degrau
          abaixo da superficie, e ja inverte. */}
      <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-borda bg-surface-base">
        {/* overflow-x-auto = scroll horizontal quando colunas não cabem */}
        <div
          ref={scrollRef}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseLeave={stopDrag}
          onMouseUp={stopDrag}
          className="h-full overflow-x-auto kanban-scroll cursor-grab"
        >
          <div className="flex gap-3 h-full p-3 min-w-max">
            {COLUNAS.map((status) => (
              <KanbanColumn
                key={status}
                status={status}
                tickets={grouped.get(status) ?? []}
                now={now}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
