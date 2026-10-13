import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Card,
  Checkbox,
  Icon,
  Input,
  Pagination,
  SelectMenu,
  Selector,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "../../components/ui";
import { EquipmentDetailModal } from "../../components/equipment/EquipmentDetailModal";
import {
  getProducts,
  listAllEquipments,
  type Equipment,
  type Product,
} from "../../services/productService";
import {
  getCompanyById,
  listAllCompanies,
  type CompanyStaffItem,
} from "../../services/groupService";

/**
 * Equipamentos — a consulta do parque inteiro, para a equipe.
 *
 * Antes, achar o aparelho de um cliente exigia abrir a tela de Produtos e
 * percorrer produto por produto. Aqui a lista atravessa todos os produtos, e a
 * busca alcança nome, série, modelo e o nome ou e-mail do responsável.
 *
 * **É só consulta.** Criar, editar e ativar continuam na tela de Produtos; o
 * detalhe abre o mesmo modal de lá, sem o botão de editar. A rota é de admin e
 * técnico, mas a tranca de verdade é o backend: `GET /equipments` recusa
 * cliente com 403.
 *
 * **Empresa é só a oficial.** As opções do filtro vêm de `GET /companies` —
 * empresas cadastradas pela equipe — e o filtro manda `company_id`, que casa o
 * vínculo do responsável. O nome que o cliente digitou nunca vira opção. A URL
 * aceita `?empresa=<id>`: é por ela que o detalhe da empresa traz para cá.
 */

const PAGE_SIZE = 20;

const OPCOES_DE_STATUS = [
  { value: "true", label: "Ativos" },
  { value: "false", label: "Inativos" },
];

/** Vinculada é a oficial; a declarada vem marcada, e nunca no lugar dela. */
function CelulaEmpresa({ equip }: { equip: Equipment }) {
  return (
    <div className="flex flex-col min-w-0">
      {equip.linked_company_name ? (
        <span className="truncate">{equip.linked_company_name}</span>
      ) : (
        <span className="text-conteudo-muted">Sem empresa vinculada</span>
      )}
      {equip.company_name && (
        <span className="text-xs text-conteudo-muted truncate">Declarada: {equip.company_name}</span>
      )}
    </div>
  );
}

export default function StaffEquipmentsPage() {
  const [equipamentos, setEquipamentos] = useState<Equipment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [produtos, setProdutos] = useState<Product[]>([]);
  const [search, setSearch] = useState("");
  const [produto, setProduto] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [empresas, setEmpresas] = useState<CompanyStaffItem[] | null>(null);
  const [empresa, setEmpresa] = useState<string | null>(searchParams.get("empresa"));
  const [status, setStatus] = useState("");
  const [semResponsavel, setSemResponsavel] = useState(false);
  const [page, setPage] = useState(1);

  const [detalhe, setDetalhe] = useState<Equipment | null>(null);

  // A busca dispara a cada tecla. Sem esta contagem, a resposta de "ma"
  // chegando depois da de "maria" pintaria a lista do termo velho.
  const ultimaRequisicao = useRef(0);

  useEffect(() => {
    getProducts({ limit: 100 })
      .then((res) => setProdutos(res.items))
      .catch(() => setProdutos([]));
    listAllCompanies({ limit: 100 })
      .then((res) => setEmpresas(res.items))
      .catch(() => setEmpresas([]));
  }, []);

  // Veio do detalhe da empresa com `?empresa=`, e ela não está entre as cem
  // primeiras: busca o nome dela, senão o filtro ativo apareceria sem rótulo.
  // Só DEPOIS de a lista chegar (`null` = ainda carregando): antes disso toda
  // empresa "não está na lista", e o pedido saía à toa.
  const empresaDaUrl = searchParams.get("empresa");
  useEffect(() => {
    if (!empresaDaUrl || empresas === null || empresas.some((c) => c.id === empresaDaUrl)) return;
    getCompanyById(empresaDaUrl)
      .then((c) =>
        setEmpresas((atual) => (atual?.some((x) => x.id === c.id) ? atual : [c, ...(atual ?? [])])),
      )
      .catch(() => {});
  }, [empresaDaUrl, empresas]);

  function escolherEmpresa(id: string | null) {
    setEmpresa(id);
    setPage(1);
    // A URL acompanha o filtro: voltar e compartilhar o endereço mantêm a empresa.
    const proximos = new URLSearchParams(searchParams);
    if (id) proximos.set("empresa", id);
    else proximos.delete("empresa");
    setSearchParams(proximos, { replace: true });
  }

  useEffect(() => {
    const esta = ++ultimaRequisicao.current;
    setLoading(true);
    setError(null);
    listAllEquipments({
      search: search || undefined,
      product_id: produto ?? undefined,
      company_id: empresa ?? undefined,
      is_active: status === "" ? undefined : status === "true",
      without_owner: semResponsavel || undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
      .then((res) => {
        if (esta !== ultimaRequisicao.current) return;
        setEquipamentos(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        if (esta !== ultimaRequisicao.current) return;
        setError("Não foi possível carregar os equipamentos.");
      })
      .finally(() => {
        if (esta === ultimaRequisicao.current) setLoading(false);
      });
  }, [search, produto, empresa, status, semResponsavel, page]);

  const hasFilters = !!(search || produto || empresa || status || semResponsavel);

  function limparFiltros() {
    setSearch("");
    setProduto(null);
    escolherEmpresa(null);
    setStatus("");
    setSemResponsavel(false);
    setPage(1);
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="text-center sm:text-left">
        <h1 className="text-2xl font-bold text-conteudo-heading">Equipamentos</h1>
        <p className="text-conteudo-muted text-sm mt-0.5">
          {total} {total === 1 ? "equipamento" : "equipamentos"}
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row md:items-center gap-2">
        <div className="relative md:flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 z-10 text-conteudo-muted pointer-events-none">
            <Icon name="search" size={16} strokeWidth={2} />
          </span>
          <Input
            aria-label="Buscar equipamentos"
            className="pl-9"
            placeholder="Buscar por nome, série, modelo ou responsável…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <div className="flex flex-wrap gap-2 items-center justify-center sm:justify-start">
          {/* D9.2: os produtos vêm da rede e crescem com o cadastro — lista
              longa, logo `Selector` com busca. O status é lista fixa no
              código, logo `SelectMenu`. */}
          <Selector
            variant="filter"
            label="Produto"
            value={produto}
            onChange={(v) => { setProduto(v); setPage(1); }}
            options={produtos.map((p) => ({ value: p.id, label: p.name }))}
            placeholder="Todos os produtos"
          />
          <Selector
            variant="filter"
            label="Empresa"
            value={empresa}
            onChange={(v) => escolherEmpresa(v)}
            options={(empresas ?? []).map((c) => ({ value: c.id, label: c.name }))}
            placeholder="Todas as empresas"
          />
          <span id="rotulo-filtro-status-equipamento" className="sr-only">
            Status do equipamento
          </span>
          <SelectMenu
            id="filtro-status-equipamento"
            aria-labelledby="rotulo-filtro-status-equipamento"
            options={OPCOES_DE_STATUS}
            placeholder="Status"
            value={status}
            onChange={(v) => { setStatus(v); setPage(1); }}
          />
          <Checkbox
            checked={semResponsavel}
            onChange={(v) => { setSemResponsavel(v); setPage(1); }}
            label="Sem responsável"
          />
          {hasFilters && (
            <button
              type="button"
              onClick={limparFiltros}
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
          <p className="text-sm font-semibold text-conteudo-heading">Parque de equipamentos</p>
          <p className="text-xs text-conteudo-muted mt-0.5">
            Consulta de todos os produtos. Para cadastrar ou editar, use a tela de Produtos.
          </p>
        </div>

        {loading ? (
          <div className="flex h-48 items-center justify-center">
            <Spinner size="lg" />
          </div>
        ) : error ? null : equipamentos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 rounded-full bg-surface-elevated border border-borda flex items-center justify-center text-conteudo-muted mb-3">
              <Icon name="cpu" size={20} strokeWidth={2} />
            </div>
            <p className="text-sm text-conteudo-muted">
              {hasFilters ? "Nenhum equipamento encontrado para esses filtros." : "Nenhum equipamento cadastrado."}
            </p>
          </div>
        ) : (
          <>
            <Table>
              <TableHead>
                <tr>
                  <TableHeaderCell>Equipamento</TableHeaderCell>
                  <TableHeaderCell className="hidden md:table-cell">Produto</TableHeaderCell>
                  <TableHeaderCell className="hidden sm:table-cell">Série</TableHeaderCell>
                  <TableHeaderCell>Responsável</TableHeaderCell>
                  <TableHeaderCell className="hidden lg:table-cell">Empresa</TableHeaderCell>
                  <TableHeaderCell className="hidden sm:table-cell">Status</TableHeaderCell>
                  <TableHeaderCell className="hidden sm:table-cell text-right">Ações</TableHeaderCell>
                </tr>
              </TableHead>
              <TableBody>
                {equipamentos.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell>
                      {/* O nome abre o detalhe. No celular a coluna de ações
                          some, e a linha só tem nome e responsável: sem isto o
                          detalhe ficava atrás de rolagem lateral da tabela. */}
                      <button
                        type="button"
                        onClick={() => setDetalhe(e)}
                        className="text-left font-medium text-conteudo-heading hover:text-conteudo-link transition-colors cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
                      >
                        {e.name}
                      </button>
                      {e.model && <p className="text-xs text-conteudo-muted">{e.model}</p>}
                    </TableCell>
                    <TableCell className="hidden md:table-cell">{e.product_name ?? "—"}</TableCell>
                    <TableCell className="hidden sm:table-cell font-mono text-xs">
                      {e.serial_number ?? <span className="text-conteudo-muted">—</span>}
                    </TableCell>
                    <TableCell>
                      {e.owner_name ? (
                        <div className="flex flex-col min-w-0">
                          <span className="truncate">{e.owner_name}</span>
                          {e.owner_email && <span className="text-xs text-conteudo-muted truncate">{e.owner_email}</span>}
                        </div>
                      ) : (
                        <span className="text-conteudo-muted">Sem responsável</span>
                      )}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      <CelulaEmpresa equip={e} />
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <Badge variant={e.is_active ? "success" : "muted"}>
                        {e.is_active ? "Ativo" : "Inativo"}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-right">
                      {/* O nome do equipamento no `aria-label`: são N botões
                          por página, e "Ver detalhes" sozinho não diz de qual. */}
                      <button
                        type="button"
                        onClick={() => setDetalhe(e)}
                        title="Ver detalhes"
                        aria-label={`Ver detalhes de ${e.name}`}
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
                itemLabel="equipamentos"
              />
            </div>
          </>
        )}
      </Card>

      {detalhe && <EquipmentDetailModal equip={detalhe} onClose={() => setDetalhe(null)} />}
    </div>
  );
}
