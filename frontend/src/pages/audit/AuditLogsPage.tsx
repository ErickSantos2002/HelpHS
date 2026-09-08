import { useEffect, useState } from "react";
import {
  Badge,
  Card,
  FilterSelect,
  Icon,
  Input,
  Modal,
  Pagination,
  Spinner,
  type BadgeProps,
} from "../../components/ui";
import {
  getAuditLogs,
  type AuditAction,
  type AuditLog,
} from "../../services/auditService";

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 20;

/** A variante do selo, tirada do próprio primitivo — sem lista paralela. */
type VarianteSelo = NonNullable<BadgeProps["variant"]>;

/**
 * A ação de auditoria, numa fonte só desta tela.
 *
 * Existia em **duas** tabelas que ninguém obrigava a concordar: `ACTION_OPTIONS`
 * dava o rótulo do filtro e `ACTION_BADGE` dava o rótulo do selo — e elas já
 * discordavam em duas das dez linhas ("Mudança de status" contra "Status",
 * "Troca de senha" contra "Senha"), sem regra dizendo qual valia onde. Agora a
 * divergência é **declarada**: `rotulo` é o nome por extenso e `curto` é a forma
 * que cabe na coluna de 110px da lista, exatamente como `lib/status.ts` separa
 * os dois. O que some é a possibilidade de acrescentar uma ação num lugar e
 * esquecê-la no outro.
 *
 * ── Por que o selo perdeu nove matizes ────────────────────────────────
 *
 * A tabela anterior pintava dez cores cruas do Tailwind — emerald, blue, red,
 * slate, yellow, cyan, orange, pink, purple — uma por ação. Fora do sistema de
 * cor: nenhuma medida contra as superfícies, nenhuma com par de texto próprio,
 * e a única com token (`login`) já era a exceção que provava o resto.
 *
 * O sistema tem sete variantes de selo, não dez, então as ações se **agrupam**.
 * O agrupamento é pelo que o evento significa para quem audita, e não pela
 * família da palavra:
 *
 * | grupo | variante | ações |
 * |---|---|---|
 * | destrói de forma irreversível | `danger` | exclusão, anonimização |
 * | expõe dado ou credencial | `warning` | exportação, troca de senha |
 * | altera um registro | `info` | atualização, atribuição, mudança de status |
 * | acrescenta | `success` | criação |
 * | abre sessão | `primary` | login |
 * | encerra sessão | `muted` | logout |
 *
 * Duas ações compartilharem cor é o mesmo caso dos dois "aguardando" do
 * `lib/status.ts`: a cor vira **reforço** e o rótulo carrega a distinção — e o
 * rótulo está escrito dentro do próprio selo, em toda ocorrência. Qual grupo
 * cada ação ocupa é decisão de desenho, e está relatada como tal.
 *
 * **Exportada para que o teste a prenda literal.** O agrupamento acima é
 * decisão, não dedução: nada no código o deriva, e por isso nada além de um
 * caso comparando a tabela inteira por igualdade impede que uma edição
 * distraída troque `danger` por `muted` na exclusão sem ninguém ver. É a mesma
 * razão pela qual `SLOT_DE_STATUS` é comparada literal, e não derivada.
 *
 * O `react-refresh` reclama que um arquivo com componente não deveria exportar
 * mais nada — a queixa é legítima e o remédio dela (arquivo próprio) está fora
 * do escopo desta fase, que pode escrever só nesta tela e no teste dela. Fica
 * silenciado AQUI, na linha, e não na configuração: quando a tabela virar
 * módulo, o silêncio sai junto com ela.
 */
// eslint-disable-next-line react-refresh/only-export-components
export const ACAO: Record<
  AuditAction,
  { rotulo: string; curto: string; variante: VarianteSelo }
> = {
  create: { rotulo: "Criação", curto: "Criação", variante: "success" },
  update: {
    rotulo: "Atualização",
    curto: "Atualização",
    variante: "info",
  },
  delete: { rotulo: "Exclusão", curto: "Exclusão", variante: "danger" },
  login: { rotulo: "Login", curto: "Login", variante: "primary" },
  logout: { rotulo: "Logout", curto: "Logout", variante: "muted" },
  export: { rotulo: "Exportação", curto: "Exportação", variante: "warning" },
  assign: { rotulo: "Atribuição", curto: "Atribuição", variante: "info" },
  status_change: {
    rotulo: "Mudança de status",
    curto: "Status",
    variante: "info",
  },
  password_change: {
    rotulo: "Troca de senha",
    curto: "Senha",
    variante: "warning",
  },
  anonymize: {
    rotulo: "Anonimização",
    curto: "Anonimização",
    variante: "danger",
  },
};

/**
 * A entidade auditada, também numa fonte só.
 *
 * `ENTITY_OPTIONS` e `ENTITY_LABEL` eram o mesmo dado escrito duas vezes, com
 * as seis chaves e os seis rótulos repetidos linha a linha.
 */
const ENTIDADE: Record<string, string> = {
  user: "Usuário",
  ticket: "Ticket",
  attachment: "Anexo",
  kb_article: "Artigo KB",
  product: "Produto",
  equipment: "Equipamento",
};

/** As opções do filtro saem das tabelas acima — nunca de uma lista paralela. */
const ACTION_OPTIONS = (Object.keys(ACAO) as AuditAction[]).map((value) => ({
  value,
  label: ACAO[value].rotulo,
}));

const ENTITY_OPTIONS = Object.entries(ENTIDADE).map(([value, label]) => ({
  value,
  label,
}));

/**
 * Os acessores recuam para o neutro, e não derrubam a tela.
 *
 * O dado vem da REDE: uma ação nova no backend que o front ainda não conheça
 * não pode virar "cannot read properties of undefined" — é o mesmo recuo que
 * `varianteDeStatus` e `varianteDePrioridade` já fazem. O rótulo recua para o
 * valor cru, que ao menos diz à pessoa o que aconteceu.
 */
function rotuloDeAcao(a: string): string {
  return ACAO[a as AuditAction]?.rotulo ?? a;
}

function curtoDeAcao(a: string): string {
  return ACAO[a as AuditAction]?.curto ?? a;
}

function varianteDeAcao(a: string): VarianteSelo {
  return ACAO[a as AuditAction]?.variante ?? "muted";
}

function rotuloDeEntidade(e: string): string {
  return ENTIDADE[e] ?? e;
}

// ── Helpers ───────────────────────────────────────────────────

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function shortUuid(id: string | null) {
  if (!id) return "—";
  return id.slice(0, 8) + "…";
}

// ── DetailModal ───────────────────────────────────────────────

function DetailModal({ log, onClose }: { log: AuditLog; onClose: () => void }) {
  const hasOld = log.old_data && Object.keys(log.old_data).length > 0;
  const hasNew = log.new_data && Object.keys(log.new_data).length > 0;

  return (
    <Modal open onClose={onClose} title="Detalhes do log">
      <div className="space-y-4 text-sm">

        {/* Action + Entity */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Por extenso aqui: o modal não tem a coluna de 110px da lista. */}
          <Badge variant={varianteDeAcao(log.action)}>
            {rotuloDeAcao(log.action)}
          </Badge>
          <span className="text-conteudo-muted">
            {rotuloDeEntidade(log.entity_type)}
          </span>
        </div>

        {/* Info grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-surface-elevated border border-borda/40 p-3 space-y-0.5">
            <p className="text-[10px] text-conteudo-muted uppercase tracking-wide">Data / Hora</p>
            <p className="text-conteudo text-xs font-mono">{formatDate(log.created_at)}</p>
          </div>
          <div className="rounded-lg bg-surface-elevated border border-borda/40 p-3 space-y-0.5">
            <p className="text-[10px] text-conteudo-muted uppercase tracking-wide">IP</p>
            <p className="text-conteudo text-xs font-mono">{log.ip_address ?? "—"}</p>
          </div>
          <div className="rounded-lg bg-surface-elevated border border-borda/40 p-3 space-y-0.5">
            <p className="text-[10px] text-conteudo-muted uppercase tracking-wide">Usuário</p>
            <p className="text-conteudo text-xs">{log.user_name ?? "—"}</p>
            {/* `conteudo-faint` daria 2,34:1 sobre a superfície elevada deste
                cartão — não é par, e um UUID é dado, não decoração. */}
            {log.user_id && <p className="text-conteudo-muted text-[10px] font-mono">{log.user_id}</p>}
          </div>
          <div className="rounded-lg bg-surface-elevated border border-borda/40 p-3 space-y-0.5">
            <p className="text-[10px] text-conteudo-muted uppercase tracking-wide">ID Entidade</p>
            <p className="text-conteudo text-[10px] font-mono break-all">{log.entity_id ?? "—"}</p>
          </div>
        </div>

        {/* User agent */}
        {log.user_agent && (
          <div className="rounded-lg bg-surface-elevated border border-borda/40 p-3 space-y-0.5">
            <p className="text-[10px] text-conteudo-muted uppercase tracking-wide">User Agent</p>
            <p className="text-conteudo-muted text-xs break-all">{log.user_agent}</p>
          </div>
        )}

        {/* Data diff */}
        {(hasOld || hasNew) && (
          <div className={`grid gap-3 ${hasOld && hasNew ? "grid-cols-2" : "grid-cols-1"}`}>
            {hasOld && (
              <div>
                <p className="text-[10px] text-conteudo-muted uppercase tracking-wide mb-1.5">Dados anteriores</p>
                {/* Tinta + par da tinta, a receita medida pela E8 e usada pelo
                    `Badge`. A cor cheia de significado como cor de texto
                    reprova o piso em 16 das 24 combinações medidas — e nem o
                    nome da classe pode ser escrito aqui: a varredura das cores
                    cheias casa por linha, sem saber o que é comentário. */}
                <pre className="text-xs text-on-tint-danger bg-tint-danger border border-danger/30 rounded-lg p-3 overflow-auto max-h-48 whitespace-pre-wrap break-all">
                  {JSON.stringify(log.old_data, null, 2)}
                </pre>
              </div>
            )}
            {hasNew && (
              <div>
                <p className="text-[10px] text-conteudo-muted uppercase tracking-wide mb-1.5">Dados novos</p>
                <pre className="text-xs text-on-tint-success bg-tint-success border border-success/30 rounded-lg p-3 overflow-auto max-h-48 whitespace-pre-wrap break-all">
                  {JSON.stringify(log.new_data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

// ── AuditLogsPage ─────────────────────────────────────────────

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<AuditLog | null>(null);

  const [actionFilter, setActionFilter] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [userIdFilter, setUserIdFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const hasFilters = actionFilter || entityFilter || userIdFilter || dateFrom || dateTo;

  useEffect(() => { setPage(1); }, [actionFilter, entityFilter, userIdFilter, dateFrom, dateTo]);

  useEffect(() => {
    setLoading(true);
    getAuditLogs({
      action: actionFilter || undefined,
      entity_type: entityFilter || undefined,
      user_id: userIdFilter || undefined,
      date_from: dateFrom ? `${dateFrom}T00:00:00Z` : undefined,
      date_to: dateTo ? `${dateTo}T23:59:59Z` : undefined,
      offset: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    })
      .then((res) => { setLogs(res.items); setTotal(res.total); })
      .finally(() => setLoading(false));
  }, [actionFilter, entityFilter, userIdFilter, dateFrom, dateTo, page]);

  function clearFilters() {
    setActionFilter(""); setEntityFilter(""); setUserIdFilter("");
    setDateFrom(""); setDateTo("");
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="text-center sm:text-left">
          <h1 className="text-2xl font-bold text-conteudo-heading">Logs de Auditoria</h1>
          <p className="text-conteudo-muted text-sm mt-0.5">Registro completo de operações — conformidade LGPD</p>
        </div>
        {!loading && (
          <span className="self-center sm:self-auto text-xs text-conteudo-muted bg-surface-elevated border border-borda/60 px-3 py-1.5 rounded-full">
            {total} {total === 1 ? "registro" : "registros"}
          </span>
        )}
      </div>

      {/* Filters */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-borda flex items-center gap-2">
          <Icon name="filter" size={16} strokeWidth={2} className="text-conteudo-muted" />
          <p className="text-sm font-semibold text-conteudo">Filtros</p>
          {hasFilters && (
            <button onClick={clearFilters} className="ml-auto inline-flex items-center gap-1 text-xs text-conteudo-muted hover:text-conteudo transition-colors cursor-pointer">
              <Icon name="close" size={14} strokeWidth={2.5} /> Limpar filtros
            </button>
          )}
        </div>
        <div className="px-4 py-3 flex flex-col gap-3">
          {/* Dropdowns */}
          <div className="flex flex-wrap gap-3 items-center justify-center sm:justify-start">
            <FilterSelect value={actionFilter} onChange={setActionFilter} options={ACTION_OPTIONS} placeholder="Todas as ações" />
            <FilterSelect value={entityFilter} onChange={setEntityFilter} options={ENTITY_OPTIONS} placeholder="Todas as entidades" />
          </div>
          {/* Date range */}
          <div className="flex flex-wrap items-center gap-2">
            {/* O "De" e o "até" ficam: são a leitura do intervalo. Mas eles nunca
                foram `<label>` de nada, então o campo em si não tinha nome
                acessível nenhum — daí o `aria-label`, que diz qual das duas
                pontas é esta sem mudar o que está desenhado. */}
            <span className="text-xs text-conteudo-muted shrink-0">De</span>
            <div className="flex-1 min-w-[130px]">
              <Input
                type="date"
                aria-label="Data inicial"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="py-[7px] text-sm [color-scheme:light] dark:[color-scheme:dark]"
              />
            </div>
            <span className="text-xs text-conteudo-muted shrink-0">até</span>
            <div className="flex-1 min-w-[130px]">
              <Input
                type="date"
                aria-label="Data final"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="py-[7px] text-sm [color-scheme:light] dark:[color-scheme:dark]"
              />
            </div>
          </div>
          {/* User ID search */}
          <div className="relative">
            <Icon
              name="search"
              size={16}
              strokeWidth={2}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-conteudo-muted pointer-events-none z-10"
            />
            <Input
              className="pl-9 w-full"
              aria-label="Buscar por User ID"
              placeholder="Buscar por User ID (UUID)…"
              value={userIdFilter}
              onChange={(e) => setUserIdFilter(e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Logs list */}
      <Card padding="none">
        {/* Column headers — desktop only */}
        <div className="hidden lg:grid grid-cols-[1fr_110px_110px_160px_100px_44px] px-4 py-2.5 border-b border-borda bg-surface-elevated/30">
          {["Evento", "Entidade", "Ação", "Usuário", "IP", ""].map((h, i) => (
            <span key={i} className="text-[11px] font-medium text-conteudo-muted uppercase tracking-wide">{h}</span>
          ))}
        </div>

        {loading ? (
          <div className="flex h-48 items-center justify-center"><Spinner /></div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-10 h-10 rounded-full bg-surface-elevated border border-borda flex items-center justify-center text-conteudo-muted mb-3">
              <Icon name="filter" size={16} strokeWidth={2} />
            </div>
            <p className="text-sm text-conteudo-muted">Nenhum registro encontrado.</p>
            {hasFilters && (
              <button onClick={clearFilters} className="mt-2 text-sm text-conteudo-link hover:text-conteudo-link-hover transition-colors cursor-pointer">Limpar filtros</button>
            )}
          </div>
        ) : (
          <div className="divide-y divide-borda">
            {logs.map((log) => {
              const hasData = (log.old_data && Object.keys(log.old_data).length > 0) || (log.new_data && Object.keys(log.new_data).length > 0);
              return (
                <div key={log.id}>
                  {/* Mobile layout */}
                  <div
                    className="lg:hidden flex items-start justify-between gap-3 px-4 py-3 hover:bg-surface-elevated/40 transition-colors cursor-pointer"
                    onClick={() => setDetail(log)}
                  >
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant={varianteDeAcao(log.action)}>{curtoDeAcao(log.action)}</Badge>
                        <span className="text-xs text-conteudo-muted">{rotuloDeEntidade(log.entity_type)}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-conteudo-muted">
                        <Icon name="clock" size={14} strokeWidth={2} />
                        <span>{formatDate(log.created_at)}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-conteudo-muted truncate">
                        <Icon name="user" size={14} strokeWidth={2} />
                        <span className="truncate">{log.user_name ?? "—"}</span>
                        {log.ip_address && <span className="font-mono ml-1">· {log.ip_address}</span>}
                      </div>
                    </div>
                    <button
                      title="Ver detalhes"
                      aria-label="Ver detalhes"
                      className={`shrink-0 p-1.5 rounded-lg transition-colors cursor-pointer hover:bg-surface-elevated ${hasData ? "text-conteudo-link" : "text-conteudo-muted"}`}
                      onClick={(e) => { e.stopPropagation(); setDetail(log); }}
                    >
                      <Icon name="eye" size={16} strokeWidth={2} />
                    </button>
                  </div>

                  {/* Desktop layout */}
                  <div className="hidden lg:grid grid-cols-[1fr_110px_110px_160px_100px_44px] items-center px-4 py-3 hover:bg-surface-elevated/40 transition-colors">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 text-xs text-conteudo-muted">
                        <Icon name="clock" size={14} strokeWidth={2} />
                        <span className="whitespace-nowrap">{formatDate(log.created_at)}</span>
                      </div>
                      <p className="text-[11px] text-conteudo-muted font-mono mt-0.5">
                        {log.entity_id ? shortUuid(log.entity_id) : "—"}
                      </p>
                    </div>
                    <span className="text-xs text-conteudo">{rotuloDeEntidade(log.entity_type)}</span>
                    <div>
                      {/* A forma curta: a coluna tem 110px. */}
                      <Badge variant={varianteDeAcao(log.action)}>{curtoDeAcao(log.action)}</Badge>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1 text-xs text-conteudo truncate">
                        <Icon name="user" size={14} strokeWidth={2} className="text-conteudo-muted" />
                        <span className="truncate">{log.user_name ?? "—"}</span>
                      </div>
                      {log.user_id && <p className="text-[11px] text-conteudo-muted font-mono mt-0.5">{shortUuid(log.user_id)}</p>}
                    </div>
                    <span className="text-xs text-conteudo-muted font-mono">{log.ip_address ?? "—"}</span>
                    <button
                      onClick={() => setDetail(log)}
                      title="Ver detalhes"
                      aria-label="Ver detalhes"
                      className={`p-1.5 rounded-lg transition-colors cursor-pointer hover:bg-surface-elevated ${hasData ? "text-conteudo-link" : "text-conteudo-muted"}`}
                    >
                      <Icon name="eye" size={16} strokeWidth={2} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!loading && total > 0 && (
          <div className="px-4 py-2 border-t border-borda">
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} itemLabel="registros" />
          </div>
        )}
      </Card>

      {detail && <DetailModal log={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
