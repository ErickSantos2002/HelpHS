import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Icon,
  Pagination,
  Spinner,
  type IconName,
} from "../../components/ui";
import { toastApiError } from "../../lib/toastError";
import { TOM_STATUS, type VarianteStatus } from "../../lib/status";
import { cn } from "../../lib/utils";
import {
  deleteNotification,
  getNotifications,
  markAllRead,
  markRead,
  type Notification,
  type NotificationType,
} from "../../services/notificationService";

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 20;

/**
 * O tipo da notificação, numa fonte só desta tela.
 *
 * Existia em **duas** tabelas paralelas que nada obrigava a concordar:
 * `TYPE_LABEL` dava o nome e `TYPE_META` dava o ícone mais uma string de
 * classe. Acrescentar um tipo numa e esquecê-lo na outra era uma edição
 * distraída de distância — e o resultado silencioso seria um selo com o valor
 * cru do backend ao lado de um sino genérico, sem ninguém notar.
 *
 * ── Por que a cor virou variante, e não classe ────────────────────────
 *
 * A tabela antiga pintava a classe direto: `bg-primary/10 text-primary` em
 * três tipos, `bg-green-500/10 text-green-600 dark:text-green-400` num,
 * `bg-slate-100 dark:bg-slate-700/50 text-slate-500` em três, e a cor cheia
 * semântica como cor de TEXTO nos outros três. As duas últimas famílias são
 * exatamente o que a catraca cobra: paleta crua não tem medida contra
 * superfície nenhuma, e a cor cheia como texto reprova o piso em 16 das 24
 * combinações medidas.
 *
 * Aqui a linha declara a **variante**, e quem sabe traduzir variante em classe
 * é o `Badge` (para o selo) e o `TOM_STATUS` (para o quadrado do ícone). Não é
 * um mapa novo de classes: é o mesmo que o quadro kanban já consome, e as
 * classes lá estão escritas por extenso, que é o que o Tailwind exige — ele
 * gera utilitário varrendo o texto do arquivo, e `"bg-tint-" + variante` some
 * da varredura sem erro nem aviso.
 *
 * O nome `TOM_STATUS` carrega a origem dele, não o limite do uso: a chave é a
 * **variante**, não o status. Reimplementá-lo aqui com outro nome seria a
 * variante local que esta migração existe para eliminar.
 *
 * ── Os dez tipos em seis variantes ────────────────────────────────────
 *
 * | grupo | variante | tipos |
 * |---|---|---|
 * | acontece algo no chamado | `primary` | criado, atualizado, nova mensagem |
 * | alguém entrou no chamado | `info` | atribuído |
 * | terminou bem | `success` | resolvido |
 * | pede atenção | `warning` | aviso de SLA, pesquisa de satisfação |
 * | deu errado | `danger` | SLA violado |
 * | não pede nada | `muted` | encerrado, sistema |
 *
 * Dois tipos dividirem a cor é o mesmo caso dos dois "aguardando" do
 * `lib/status.ts`: a cor é **reforço**, e o rótulo carrega a distinção — e o
 * rótulo está escrito dentro do selo, em toda ocorrência. Qual grupo cada tipo
 * ocupa é decisão de desenho, e está relatada como tal.
 *
 * **Exportada para que o teste a prenda literal.** O agrupamento é decisão, não
 * dedução: nada no código o deriva, e sem um caso comparando a tabela inteira
 * por igualdade, trocar `danger` por `muted` no SLA violado é uma edição de uma
 * palavra que nenhum outro caso reprova — a tela continua renderizando, o selo
 * continua dizendo "SLA violado", e só a cor muda, que é justamente o que o
 * ambiente de teste não vê. É a mesma razão pela qual `SLOT_DE_STATUS` é
 * comparada literal, e não derivada.
 *
 * O `react-refresh` reclama que um arquivo com componente não deveria exportar
 * mais nada. A queixa é legítima e o remédio dela — arquivo próprio em
 * `src/lib/` — está fora do escopo desta fase, que pode escrever só nesta tela
 * e no teste dela. Fica silenciado AQUI, na linha, e não na configuração:
 * quando a tabela virar módulo, o silêncio sai junto com ela.
 */
// eslint-disable-next-line react-refresh/only-export-components
export const TIPO: Record<
  NotificationType,
  { rotulo: string; icone: IconName; variante: VarianteStatus }
> = {
  ticket_created: {
    rotulo: "Chamado criado",
    icone: "ticket",
    variante: "primary",
  },
  ticket_assigned: {
    rotulo: "Chamado atribuído",
    icone: "user",
    variante: "info",
  },
  ticket_updated: {
    rotulo: "Chamado atualizado",
    icone: "refresh",
    variante: "primary",
  },
  ticket_resolved: {
    rotulo: "Chamado resolvido",
    icone: "check",
    variante: "success",
  },
  // Mesmo ícone do resolvido, e de propósito: o desenho antigo era um "certo"
  // sem círculo, e a E21 unificou os dois traçados de "certo" num nome só. O
  // que separa os dois tipos é a variante e o rótulo, não o glifo.
  ticket_closed: {
    rotulo: "Chamado encerrado",
    icone: "check",
    variante: "muted",
  },
  sla_warning: { rotulo: "Aviso SLA", icone: "clock", variante: "warning" },
  sla_breached: { rotulo: "SLA violado", icone: "warning", variante: "danger" },
  chat_message: {
    rotulo: "Nova mensagem",
    icone: "chat",
    variante: "primary",
  },
  satisfaction_survey: {
    rotulo: "Pesquisa de satisfação",
    icone: "star",
    variante: "warning",
  },
  system: { rotulo: "Sistema", icone: "settings", variante: "muted" },
};

/**
 * Os acessores recuam, e não derrubam a tela.
 *
 * O dado vem da REDE: um tipo novo no backend que o front ainda não conheça não
 * pode virar "cannot read properties of undefined". É o mesmo recuo que
 * `varianteDeStatus` e `varianteDePrioridade` já fazem. O rótulo recua para o
 * valor cru, que ao menos diz à pessoa o que aconteceu; o ícone recua para o
 * sino, que é o desenho da própria tela; e a variante recua para o neutro,
 * porque tipo desconhecido é ausência de informação — pintar de vermelho
 * afirmaria algo que não se sabe.
 */
function rotuloDeTipo(t: string): string {
  return TIPO[t as NotificationType]?.rotulo ?? t;
}

function iconeDeTipo(t: string): IconName {
  return TIPO[t as NotificationType]?.icone ?? "bell";
}

function varianteDeTipo(t: string): VarianteStatus {
  return TIPO[t as NotificationType]?.variante ?? "muted";
}

/**
 * As duas abas, com o rótulo escrito e não derivado de booleano.
 *
 * `String(tab.value)` continua sendo a chave da lista, mas o que a pessoa lê
 * vem daqui — e é o que o teste procura.
 */
const ABAS = [
  { rotulo: "Todas", apenasNaoLidas: false },
  { rotulo: "Não lidas", apenasNaoLidas: true },
];

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "agora";
  if (mins < 60) return `há ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `há ${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "ontem";
  if (days < 7) return `há ${days} dias`;
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

// ── NotificationsPage ─────────────────────────────────────────

export default function NotificationsPage() {
  const navigate = useNavigate();

  const [items, setItems] = useState<Notification[]>([]);
  const [total, setTotal] = useState(0);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [markingAll, setMarkingAll] = useState(false);

  function load(p = page, unreadOnlyFilter = unreadOnly) {
    setLoading(true);
    setError(null);
    getNotifications({ limit: PAGE_SIZE, offset: (p - 1) * PAGE_SIZE, unread_only: unreadOnlyFilter })
      .then((res) => { setItems(res.items); setTotal(res.total); setUnread(res.unread); })
      .catch(() => setError("Não foi possível carregar as notificações."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, unreadOnly]);

  async function handleMarkRead(notif: Notification) {
    if (!notif.read) {
      await markRead(notif.id);
      setItems((prev) => prev.map((n) => (n.id === notif.id ? { ...n, read: true } : n)));
      setUnread((u) => Math.max(0, u - 1));
    }
    if (notif.data?.ticket_id) navigate(`/tickets/${notif.data.ticket_id}`);
  }

  /**
   * Remove a notificacao, e so entao a tira da lista.
   *
   * Mesmo defeito e mesmo conserto do `handleDeleteComment` da
   * `KBArticlePage`: o `await` estava solto, e a lista era filtrada antes de a
   * rede confirmar. Falha silenciosa que AFIRMA remocao — o contrario do
   * defeito da tela de auditoria, que afirma ausencia.
   *
   * A contagem do cabecalho continua descontando de `total` e nao de `unread`,
   * que e outro defeito, registrado a parte: apagar uma notificacao POR LER
   * deixa o cabecalho com um numero a mais. Nao se conserta aqui.
   */
  async function handleDelete(id: string) {
    try {
      await deleteNotification(id);
      setItems((prev) => prev.filter((n) => n.id !== id));
      setTotal((t) => t - 1);
    } catch (err) {
      toastApiError(err, "Não foi possível remover a notificação.");
    }
  }

  async function handleMarkAllRead() {
    setMarkingAll(true);
    try {
      await markAllRead();
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnread(0);
    } finally {
      setMarkingAll(false);
    }
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-conteudo-heading">Notificações</h1>
          <p className="text-sm text-conteudo-muted mt-0.5">
            {unread > 0 ? (
              <span>
                {/* O número era `text-primary` — o degrau de MARCA — sobre o
                    fundo da página, o que dá 3,66:1 e reprova AA. Não é link,
                    então o degrau de link também não serve: quem o lê pensaria
                    que dá para clicar. A ênfase passou para o degrau de título
                    mais o peso, que é contraste e não cor. */}
                <span className="text-conteudo-heading font-semibold">{unread}</span> não {unread === 1 ? "lida" : "lidas"}
              </span>
            ) : (
              "Todas lidas"
            )}
          </p>
        </div>

        {unread > 0 && (
          <Button variant="secondary" size="sm" loading={markingAll} onClick={handleMarkAllRead}>
            Marcar todas como lidas
          </Button>
        )}
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1">
        {ABAS.map((aba) => {
          const ativa = unreadOnly === aba.apenasNaoLidas;
          return (
            <button
              key={String(aba.apenasNaoLidas)}
              type="button"
              // Qual aba está valendo era dito **só pela cor de fundo**. Um
              // botão que liga e desliga é um botão de alternância, e a árvore
              // de acessibilidade tem palavra para isso: `aria-pressed`. Sem
              // ele, quem navega por leitor de tela ouve dois botões iguais.
              aria-pressed={ativa}
              onClick={() => { setUnreadOnly(aba.apenasNaoLidas); setPage(1); }}
              className={cn(
                "px-3 py-1.5 text-sm rounded-lg font-medium transition-colors",
                // `bg-action` + `text-on-primary`, e NÃO `bg-primary` +
                // `text-white`: o segundo par dá 3,83:1, e o branco cravado dá
                // 2,69:1 no escuro, onde o par do fundo de ação é navy.
                ativa
                  ? "bg-action text-on-primary"
                  : "text-conteudo-muted hover:bg-surface-elevated hover:text-conteudo-heading",
              )}
            >
              {aba.rotulo}
              {aba.apenasNaoLidas && unread > 0 && (
                <span
                  className={cn(
                    "ml-1.5 text-xs rounded-full px-1.5 py-0.5 font-medium",
                    // A contagem desenhava `bg-white/20 text-white` SEMPRE —
                    // inclusive com a aba desligada, onde não há fundo escuro
                    // por baixo e o número ficava branco sobre a página. Agora
                    // ela acompanha o estado: sobre o fundo de ação vai o
                    // degrau de hover (mais escuro no claro, mais claro no
                    // escuro — nos dois casos MAIS contraste que o par base);
                    // fora dele, o par tinta/par-da-tinta do `Badge`.
                    ativa
                      ? "bg-action-hover text-on-primary"
                      : "bg-tint-primary text-on-tint-primary",
                  )}
                >
                  {unread}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      {/* Feed */}
      {loading ? (
        <div className="flex h-48 items-center justify-center">
          <Spinner size="lg" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl bg-surface border border-borda py-16 flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-surface-elevated flex items-center justify-center text-conteudo-muted">
            {/* `conteudo-faint` sobre a superfície elevada dá 2,34:1 — não é
                par, e vale para o traço de um ícone como vale para texto. */}
            <Icon name="bell" size={24} strokeWidth={1.5} />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-conteudo">
              {unreadOnly ? "Nenhuma notificação não lida" : "Nenhuma notificação"}
            </p>
            <p className="text-xs text-conteudo-muted mt-0.5">
              {unreadOnly ? "Você está em dia com tudo!" : "As notificações aparecerão aqui"}
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-xl bg-surface border border-borda overflow-hidden divide-y divide-borda">
          {items.map((n) => {
            const tom = TOM_STATUS[varianteDeTipo(n.type)];
            return (
              <div
                key={n.id}
                role="button"
                tabIndex={0}
                onClick={() => handleMarkRead(n)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleMarkRead(n); }}
                className={cn(
                  "group relative flex items-start gap-4 px-5 py-4 cursor-pointer transition-colors",
                  "hover:bg-surface-elevated",
                  // Era `bg-primary/[0.03] dark:bg-primary/[0.05]` — dois
                  // valores de opacidade escolhidos à mão, um por tema. O
                  // `--action-tint` é o realce de ação do pacote e resolve por
                  // tema sozinho; no escuro ele é visível, que os 5% não eram.
                  !n.read && "bg-action-tint",
                )}
              >
                {/* Unread left border */}
                {!n.read && (
                  <div
                    aria-hidden="true"
                    className="absolute left-0 top-0 bottom-0 w-0.5 bg-action rounded-r"
                  />
                )}

                {/* Type icon */}
                <div className={cn(
                  "w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5",
                  tom.fundo,
                  tom.texto,
                )}>
                  <Icon name={iconeDeTipo(n.type)} size={16} strokeWidth={2} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-3">
                    <p className={cn(
                      "text-sm leading-snug",
                      n.read ? "text-conteudo-muted" : "font-semibold text-conteudo-heading",
                    )}>
                      {/* "Não lida" era dito por três coisas que um leitor de
                          tela não vê: a barrinha da esquerda, o fundo levemente
                          azul e o peso da fonte. Nenhuma delas chega à árvore
                          de acessibilidade, então o estado simplesmente não
                          existia para quem não enxerga a tela. */}
                      {!n.read && <span className="sr-only">Não lida. </span>}
                      {n.title}
                    </p>
                    <span className="text-xs text-conteudo-muted shrink-0 mt-0.5">{timeAgo(n.created_at)}</span>
                  </div>
                  {n.message && (
                    <p className="text-xs text-conteudo-muted mt-0.5 line-clamp-2">{n.message}</p>
                  )}
                  {/* O tipo é o `Badge`, e não uma pílula à mão: mesmo raio,
                      mesma altura, e o par tinta/par-da-tinta medido pela E8. */}
                  <Badge variant={varianteDeTipo(n.type)} className="mt-2">
                    {rotuloDeTipo(n.type)}
                  </Badge>
                </div>

                {/* Delete button */}
                <button
                  type="button"
                  aria-label="Remover notificação"
                  onClick={(e) => { e.stopPropagation(); handleDelete(n.id); }}
                  // `focus-visible:opacity-100` porque o botão só aparecia no
                  // hover do mouse: quem chegava nele pelo teclado recebia o
                  // foco num controle invisível.
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 shrink-0 mt-0.5 w-7 h-7 rounded-lg flex items-center justify-center text-conteudo-muted hover:text-on-tint-danger hover:bg-tint-danger transition-all"
                >
                  <Icon name="close" size={16} strokeWidth={2} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {!loading && total > PAGE_SIZE && (
        <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
      )}
    </div>
  );
}
