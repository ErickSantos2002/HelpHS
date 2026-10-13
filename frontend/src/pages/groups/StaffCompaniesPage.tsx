import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Card,
  Icon,
  Input,
  Pagination,
  Selector,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui";
import { formatCnpj } from "../../lib/documents";
import {
  listAllCompanies,
  listGroups,
  type CompanyStaffItem,
  type GroupResponse,
} from "../../services/groupService";
import { CompanyDetailModal } from "./GroupsPage";

/**
 * Empresas — a consulta de todas as empresas, de todos os grupos, para a equipe.
 *
 * Até aqui uma empresa só era achada abrindo o grupo certo na tela de Grupos.
 * Esta lista atravessa os grupos e busca por nome ou CNPJ.
 *
 * **É só consulta.** Criar, editar, excluir, vincular cliente e notas
 * continuam na tela de Grupos; o detalhe abre o mesmo modal de lá, no modo
 * somente leitura. A rota é de admin e técnico, mas a tranca de verdade é o
 * backend: `GET /companies` recusa cliente com 403.
 *
 * "Clientes vinculados" e "Equipamentos" contam só o vínculo OFICIAL
 * (`users.company_id`, feito por um admin). O nome de empresa que o cliente
 * digitou no cadastro não entra em conta nenhuma.
 */

const PAGE_SIZE = 20;

export default function StaffCompaniesPage() {
  const [empresas, setEmpresas] = useState<CompanyStaffItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [grupos, setGrupos] = useState<GroupResponse[]>([]);
  const [search, setSearch] = useState("");
  const [grupo, setGrupo] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const [detalhe, setDetalhe] = useState<CompanyStaffItem | null>(null);

  // A busca dispara a cada tecla: a resposta velha não pode pintar por cima.
  const ultimaRequisicao = useRef(0);

  useEffect(() => {
    listGroups()
      .then(setGrupos)
      .catch(() => setGrupos([]));
  }, []);

  useEffect(() => {
    const esta = ++ultimaRequisicao.current;
    setLoading(true);
    setError(null);
    listAllCompanies({
      search: search || undefined,
      group_id: grupo ?? undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
      .then((res) => {
        if (esta !== ultimaRequisicao.current) return;
        setEmpresas(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        if (esta !== ultimaRequisicao.current) return;
        setError("Não foi possível carregar as empresas.");
      })
      .finally(() => {
        if (esta === ultimaRequisicao.current) setLoading(false);
      });
  }, [search, grupo, page]);

  const hasFilters = !!(search || grupo);

  return (
    <div className="space-y-5">
      <div className="text-center sm:text-left">
        <h1 className="text-2xl font-bold text-conteudo-heading">Empresas</h1>
        <p className="text-conteudo-muted text-sm mt-0.5">
          {total} {total === 1 ? "empresa" : "empresas"}
        </p>
      </div>

      <div className="flex flex-col md:flex-row md:items-center gap-2">
        <div className="relative md:flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 z-10 text-conteudo-muted pointer-events-none">
            <Icon name="search" size={16} strokeWidth={2} />
          </span>
          <Input
            aria-label="Buscar empresas"
            className="pl-9"
            placeholder="Buscar por nome ou CNPJ…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <div className="flex flex-wrap gap-2 items-center justify-center sm:justify-start">
          {/* D9.2: os grupos vêm da rede e crescem com o cadastro — `Selector`. */}
          <Selector
            variant="filter"
            label="Grupo"
            value={grupo}
            onChange={(v) => { setGrupo(v); setPage(1); }}
            options={grupos.map((g) => ({ value: g.id, label: g.name }))}
            placeholder="Todos os grupos"
          />
          {hasFilters && (
            <button
              type="button"
              onClick={() => { setSearch(""); setGrupo(null); setPage(1); }}
              className="text-xs text-conteudo-muted hover:text-conteudo transition-colors px-2 py-1.5 rounded-lg hover:bg-surface-elevated cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
            >
              Limpar filtros
            </button>
          )}
        </div>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      <Card padding="none">
        <div className="px-4 py-3 border-b border-borda">
          <p className="text-sm font-semibold text-conteudo-heading">Empresas de todos os grupos</p>
          <p className="text-xs text-conteudo-muted mt-0.5">
            Consulta. Para cadastrar, editar ou vincular clientes, use a tela de Grupos.
          </p>
        </div>

        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <Spinner size="lg" />
          </div>
        ) : error ? null : empresas.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-surface-elevated border border-borda flex items-center justify-center text-conteudo-muted mb-3">
              <Icon name="building" size={20} strokeWidth={2} />
            </div>
            <p className="text-sm text-conteudo-muted">
              {hasFilters ? "Nenhuma empresa encontrada para esses filtros." : "Nenhuma empresa cadastrada."}
            </p>
          </div>
        ) : (
          <>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Empresa</TableHeaderCell>
                  <TableHeaderCell className="hidden sm:table-cell">CNPJ</TableHeaderCell>
                  <TableHeaderCell className="hidden md:table-cell">Grupo</TableHeaderCell>
                  <TableHeaderCell className="text-right">Clientes vinculados</TableHeaderCell>
                  <TableHeaderCell className="hidden sm:table-cell text-right">Equipamentos</TableHeaderCell>
                  <TableHeaderCell className="hidden sm:table-cell text-right">Ações</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {empresas.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      {/* O nome abre o detalhe: no celular a coluna de ações some. */}
                      <button
                        type="button"
                        onClick={() => setDetalhe(c)}
                        className="text-left font-medium text-conteudo-heading hover:text-conteudo-link transition-colors cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
                      >
                        {c.name}
                      </button>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell font-mono text-xs">
                      {c.cnpj ? formatCnpj(c.cnpj) : <span className="text-conteudo-muted">—</span>}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">{c.group_name}</TableCell>
                    <TableCell className="text-right tabular-nums">{c.client_count}</TableCell>
                    <TableCell className="hidden sm:table-cell text-right tabular-nums">{c.equipment_count}</TableCell>
                    <TableCell className="hidden sm:table-cell text-right">
                      <button
                        type="button"
                        onClick={() => setDetalhe(c)}
                        title="Ver detalhes"
                        aria-label={`Ver detalhes de ${c.name}`}
                        className="p-1.5 rounded-lg text-conteudo-muted hover:text-conteudo-link hover:bg-action-tint transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
                      >
                        <Icon name="eye" size={16} strokeWidth={2} />
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <div className="px-4 py-2 border-t border-borda">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={total}
                onPageChange={setPage}
                itemLabel="empresas"
              />
            </div>
          </>
        )}
      </Card>

      {detalhe && (
        <CompanyDetailModal
          groupId={detalhe.group_id}
          company={detalhe}
          onClose={() => setDetalhe(null)}
          onUpdated={() => {}}
          somenteLeitura
        />
      )}
    </div>
  );
}
