import { useEffect, useState } from "react";
import { Input, Pagination, Select } from "../../components/ui";
import {
  getAuditLogs,
  type AuditAction,
  type AuditLog,
} from "../../services/auditService";

const PAGE_SIZE = 50;

const ACTION_OPTIONS = [
  { value: "create", label: "Criação" },
  { value: "update", label: "Atualização" },
  { value: "delete", label: "Exclusão" },
  { value: "login", label: "Login" },
  { value: "logout", label: "Logout" },
  { value: "export", label: "Exportação" },
  { value: "assign", label: "Atribuição" },
  { value: "status_change", label: "Mudança de status" },
  { value: "password_change", label: "Troca de senha" },
  { value: "anonymize", label: "Anonimização" },
];

const ENTITY_OPTIONS = [
  { value: "user", label: "Usuário" },
  { value: "ticket", label: "Ticket" },
  { value: "attachment", label: "Anexo" },
  { value: "kb_article", label: "Artigo KB" },
];

const ACTION_BADGE: Record<AuditAction, { label: string; color: string }> = {
  create: { label: "Criação", color: "text-green-400 bg-green-400/10" },
  update: { label: "Atualização", color: "text-blue-400 bg-blue-400/10" },
  delete: { label: "Exclusão", color: "text-red-400 bg-red-400/10" },
  login: { label: "Login", color: "text-primary bg-primary/10" },
  logout: { label: "Logout", color: "text-slate-400 bg-slate-400/10" },
  export: { label: "Exportação", color: "text-yellow-400 bg-yellow-400/10" },
  assign: { label: "Atribuição", color: "text-cyan-400 bg-cyan-400/10" },
  status_change: {
    label: "Status",
    color: "text-orange-400 bg-orange-400/10",
  },
  password_change: { label: "Senha", color: "text-pink-400 bg-pink-400/10" },
  anonymize: {
    label: "Anonimização",
    color: "text-purple-400 bg-purple-400/10",
  },
};

function ActionBadge({ action }: { action: AuditAction }) {
  const badge = ACTION_BADGE[action] ?? {
    label: action,
    color: "text-slate-400 bg-slate-400/10",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${badge.color}`}
    >
      {badge.label}
    </span>
  );
}

function DataCell({ data }: { data: Record<string, unknown> | null }) {
  const [open, setOpen] = useState(false);
  if (!data || Object.keys(data).length === 0)
    return <span className="text-slate-600 text-xs">—</span>;
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-primary hover:underline"
      >
        {open ? "Ocultar" : "Ver dados"}
      </button>
      {open && (
        <pre className="mt-1 text-xs text-slate-400 bg-background-elevated rounded p-2 max-w-xs overflow-auto whitespace-pre-wrap break-all">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const [actionFilter, setActionFilter] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [userIdFilter, setUserIdFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  useEffect(() => {
    setPage(1);
  }, [actionFilter, entityFilter, userIdFilter, dateFrom, dateTo]);

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
      .then((res) => {
        setLogs(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  }, [actionFilter, entityFilter, userIdFilter, dateFrom, dateTo, page]);

  const hasFilters =
    actionFilter || entityFilter || userIdFilter || dateFrom || dateTo;

  function clearFilters() {
    setActionFilter("");
    setEntityFilter("");
    setUserIdFilter("");
    setDateFrom("");
    setDateTo("");
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Logs de Auditoria</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          Registro completo de operações — conformidade LGPD
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end">
        <Select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          options={ACTION_OPTIONS}
          placeholder="Ação"
          className="w-44"
        />
        <Select
          value={entityFilter}
          onChange={(e) => setEntityFilter(e.target.value)}
          options={ENTITY_OPTIONS}
          placeholder="Entidade"
          className="w-36"
        />
        <div className="flex-1 min-w-48">
          <Input
            placeholder="User ID (UUID)"
            value={userIdFilter}
            onChange={(e) => setUserIdFilter(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="rounded-lg border border-border bg-background-surface px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <span className="text-slate-500 text-sm">até</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="rounded-lg border border-border bg-background-surface px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        {hasFilters && (
          <button
            onClick={clearFilters}
            className="text-sm text-slate-400 hover:text-slate-200 transition-colors px-2"
          >
            Limpar
          </button>
        )}
      </div>

      {/* Summary */}
      <p className="text-xs text-slate-500">
        {loading
          ? "Carregando…"
          : `${total} registro${total !== 1 ? "s" : ""} encontrado${total !== 1 ? "s" : ""}`}
      </p>

      {/* Table */}
      <div className="rounded-xl border border-border bg-background-surface overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 w-40">
                Data / Hora
              </th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 w-32">
                Ação
              </th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 w-28">
                Entidade
              </th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500">
                ID Entidade
              </th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500">
                Usuário
              </th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 w-24">
                IP
              </th>
              <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 w-24">
                Dados
              </th>
            </tr>
          </thead>
          <tbody>
            {!loading && logs.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="text-center py-12 text-slate-500 text-sm"
                >
                  Nenhum registro encontrado.
                </td>
              </tr>
            )}
            {logs.map((log, i) => (
              <tr
                key={log.id}
                className={`border-b border-border/50 hover:bg-background-elevated transition-colors ${
                  i % 2 === 0 ? "" : "bg-background-elevated/30"
                }`}
              >
                <td className="px-4 py-2.5 text-xs text-slate-400 whitespace-nowrap">
                  {formatDate(log.created_at)}
                </td>
                <td className="px-4 py-2.5">
                  <ActionBadge action={log.action} />
                </td>
                <td className="px-4 py-2.5 text-xs text-slate-300 capitalize">
                  {log.entity_type}
                </td>
                <td className="px-4 py-2.5 text-xs text-slate-500 font-mono">
                  {log.entity_id ? log.entity_id.slice(0, 8) + "…" : "—"}
                </td>
                <td className="px-4 py-2.5 text-xs text-slate-500 font-mono">
                  {log.user_id ? log.user_id.slice(0, 8) + "…" : "—"}
                </td>
                <td className="px-4 py-2.5 text-xs text-slate-500">
                  {log.ip_address ?? "—"}
                </td>
                <td className="px-4 py-2.5">
                  <DataCell data={log.new_data ?? log.old_data} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!loading && total > PAGE_SIZE && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={setPage}
        />
      )}
    </div>
  );
}
