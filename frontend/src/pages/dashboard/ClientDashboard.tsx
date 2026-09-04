import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  CardTitle,
  Icon,
  KpiCard,
  Pagination,
  PriorityBadge,
  Spinner,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui";
import { useAuth } from "../../contexts/AuthContext";
import { getTickets, type Ticket } from "../../services/ticketService";

const PAGE_SIZE = 10;

/**
 * Uma linha da lista de chamados.
 *
 * ── O que era, e por que mudou ────────────────────────────────────────
 *
 * A lista **parecia** uma tabela e não era nenhuma: o cabeçalho eram quatro
 * `<span>` numa grade CSS e cada linha era um `<button>`. Quem enxerga lê
 * "Protocolo | Título | Prioridade | Status" no topo e alinha a coluna com o
 * olho; quem usa leitor de tela ouvia **dez botões** cujo nome era a costura de
 * tudo — "HS-2024-0031 Impressora não imprime Alta Aberto" —, sem "linha 3 de
 * 10", sem nome de coluna e sem saber quantas colunas existem.
 *
 * ── O link esticado, e por que a área de clique não se perdeu ─────────
 *
 * Navegação é link (regra registrada no `DECISOES.md`), e um `<tr>` não pode
 * ser um link. O acionável vai **dentro** da linha — aqui o título — e um
 * pseudo-elemento `after:absolute after:inset-0` o estica sobre a linha inteira.
 *
 * Medido no navegador antes de escolher: o pseudo-elemento cobre o `<tr>`
 * exatamente (400×61 contra 400×61), porque a linha é `relative`. Onde isso
 * falhar, o link continua funcionando — só cobre a própria célula. Degradação
 * limpa, não quebra.
 *
 * O nome do link é o **título do chamado**, e não "Ver detalhes": dez links
 * chamados "Ver detalhes" produzem uma lista em que nenhum diz para onde vai.
 */
function LinhaDeChamado({ ticket }: { ticket: Ticket }) {
  return (
    <TableRow className="relative">
      <TableCell className="hidden font-mono text-xs text-conteudo-muted sm:table-cell">
        {ticket.protocol}
      </TableCell>

      <TableCell>
        {/* O protocolo reaparece aqui no telefone, onde a coluna própria some. */}
        <span className="mb-0.5 block font-mono text-xs text-conteudo-muted sm:hidden">
          {ticket.protocol}
        </span>
        <Link
          to={`/tickets/${ticket.id}`}
          className="truncate text-conteudo after:absolute after:inset-0 hover:text-conteudo-link hover:underline"
        >
          {ticket.title}
        </Link>
      </TableCell>

      <TableCell>
        <PriorityBadge priority={ticket.priority} />
      </TableCell>
      <TableCell>
        <StatusBadge status={ticket.status} />
      </TableCell>
    </TableRow>
  );
}

export default function ClientDashboard() {
  const { user } = useAuth();

  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [listLoading, setListLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [kpiOpen, setKpiOpen] = useState(0);
  const [kpiResolved, setKpiResolved] = useState(0);
  const [kpiTotal, setKpiTotal] = useState(0);

  // Os três indicadores, numa chamada só.
  //
  // PENDÊNCIA REGISTRADA, e ela não é do sistema de design: só o "Total" vem do
  // servidor (`data.total`); os outros dois são contados no cliente sobre os
  // 500 itens trazidos. Passando de 500 chamados a tela mostra três números que
  // não fecham, sem nenhum sinal de truncamento. Entra na Fase 16 com o
  // serviço, não aqui.
  useEffect(() => {
    if (!user) return;
    getTickets({ creator_id: user.id, limit: 500 })
      .then((data) => {
        setKpiTotal(data.total);
        setKpiOpen(
          data.items.filter((t) => t.status === "open" || t.status === "in_progress")
            .length,
        );
        setKpiResolved(
          data.items.filter((t) => t.status === "resolved" || t.status === "closed")
            .length,
        );
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    setListLoading(true);
    getTickets({
      creator_id: user.id,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
      .then((data) => {
        setTickets(data.items);
        setTotal(data.total);
      })
      .catch(() => setError("Não foi possível carregar seus tickets."))
      .finally(() => setListLoading(false));
  }, [user, page]);

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    // `live` fica ligado: este aviso aparece por FALHA de uma ação, não faz
    // parte da página desde o início. Emenda E12.
    return <Alert variant="danger">{error}</Alert>;
  }

  return (
    <div className="space-y-5 pb-10">
      <div className="flex flex-col gap-4 rounded-2xl border border-borda/40 bg-surface px-5 py-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="text-center sm:text-left">
          <h1 className="text-xl font-extrabold text-conteudo-heading">Meus Tickets</h1>
          <p className="mt-0.5 text-sm text-conteudo-muted">
            Olá,{" "}
            <span className="font-semibold text-conteudo">
              {user?.name?.split(" ")[0]}
            </span>
            ! Acompanhe seus chamados abaixo.
          </p>
        </div>
        <div className="flex justify-center sm:justify-end">
          {/* Era `<button onClick={() => navigate(...)}>` com `bg-primary
              text-white` — 3,83:1, a família da emenda E1. O primitivo resolve
              as duas coisas: a cor sai do par medido e o `to` faz dele um link. */}
          <Button to="/tickets/new" icon={<Icon name="plus" size={16} strokeWidth={2.5} />}>
            Abrir chamado
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard label="Total de chamados" value={kpiTotal} sub="Todos os status" />
        <KpiCard
          label="Em andamento"
          value={kpiOpen}
          sub="Abertos + em progresso"
          tone={kpiOpen > 0 ? "info" : "neutral"}
        />
        <KpiCard
          label="Resolvidos"
          value={kpiResolved}
          sub="Resolvidos + fechados"
          tone={kpiResolved > 0 ? "primary" : "neutral"}
        />
      </div>

      <Card padding="none">
        <div className="border-b border-borda px-4 py-3">
          <CardTitle>Chamados recentes</CardTitle>
        </div>

        {listLoading ? (
          <div className="flex items-center justify-center py-10">
            <Spinner size="md" />
          </div>
        ) : tickets.length === 0 ? (
          <div className="space-y-3 px-4 py-12 text-center">
            <p className="text-sm text-conteudo-muted">
              Você ainda não abriu nenhum chamado.
            </p>
            <Button variant="secondary" to="/tickets/new">
              Abrir primeiro chamado
            </Button>
          </div>
        ) : (
          <>
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell className="hidden sm:table-cell">
                    Protocolo
                  </TableHeaderCell>
                  <TableHeaderCell>Título</TableHeaderCell>
                  <TableHeaderCell>Prioridade</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tickets.map((t) => (
                  <LinhaDeChamado key={t.id} ticket={t} />
                ))}
              </TableBody>
            </Table>

            <div className="px-4 pb-4">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={total}
                onPageChange={setPage}
                itemLabel="chamados"
              />
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
