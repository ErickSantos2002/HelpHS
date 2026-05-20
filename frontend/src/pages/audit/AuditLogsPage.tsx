import { useEffect, useState } from "react";
import { Card, FilterSelect, Input, Modal, Pagination, Spinner } from "../../components/ui";
import {
  getAuditLogs,
  type AuditAction,
  type AuditLog,
} from "../../services/auditService";

// ── Constants ─────────────────────────────────────────────────

const PAGE_SIZE = 20;

const ACTION_OPTIONS = [
  { value: "create",          label: "Criação" },
  { value: "update",          label: "Atualização" },
  { value: "delete",          label: "Exclusão" },
  { value: "login",           label: "Login" },
  { value: "logout",          label: "Logout" },
  { value: "export",          label: "Exportação" },
  { value: "assign",          label: "Atribuição" },
  { value: "status_change",   label: "Mudança de status" },
  { value: "password_change", label: "Troca de senha" },
  { value: "anonymize",       label: "Anonimização" },
];

const ENTITY_OPTIONS = [
  { value: "user",       label: "Usuário" },
  { value: "ticket",     label: "Ticket" },
  { value: "attachment", label: "Anexo" },
  { value: "kb_article", label: "Artigo KB" },
  { value: "product",    label: "Produto" },
  { value: "equipment",  label: "Equipamento" },
];

const ACTION_BADGE: Record<AuditAction, { label: string; cls: string }> = {
  create:          { label: "Criação",          cls: "bg-emerald-50 text-emerald-600 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-700/40" },
  update:          { label: "Atualização",       cls: "bg-blue-50 text-blue-600 border border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700/40" },
  delete:          { label: "Exclusão",          cls: "bg-red-50 text-red-600 border border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700/40" },
  login:           { label: "Login",             cls: "bg-primary/10 text-primary border border-primary/30" },
  logout:          { label: "Logout",            cls: "bg-slate-100 text-slate-500 border border-slate-300 dark:bg-slate-800/60 dark:text-slate-400 dark:border-slate-600/40" },
  export:          { label: "Exportação",        cls: "bg-yellow-50 text-yellow-600 border border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-700/40" },
  assign:          { label: "Atribuição",        cls: "bg-cyan-50 text-cyan-600 border border-cyan-200 dark:bg-cyan-900/30 dark:text-cyan-300 dark:border-cyan-700/40" },
  status_change:   { label: "Status",            cls: "bg-orange-50 text-orange-600 border border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-700/40" },
  password_change: { label: "Senha",             cls: "bg-pink-50 text-pink-600 border border-pink-200 dark:bg-pink-900/30 dark:text-pink-300 dark:border-pink-700/40" },
  anonymize:       { label: "Anonimização",      cls: "bg-purple-50 text-purple-600 border border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-700/40" },
};

const ENTITY_LABEL: Record<string, string> = {
  user: "Usuário", ticket: "Ticket", attachment: "Anexo",
  kb_article: "Artigo KB", product: "Produto", equipment: "Equipamento",
};

// ── Icons ─────────────────────────────────────────────────────

const IC = {
  Search: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>,
  X:      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>,
  Filter: <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" /></svg>,
  Clock:  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><circle cx="12" cy="12" r="10" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2" /></svg>,
  User:   <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>,
  Eye:    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>,
  Globe:  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9" /></svg>,
};

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
  const badge = ACTION_BADGE[log.action] ?? { label: log.action, cls: "bg-slate-100 text-slate-500 border border-slate-300 dark:bg-slate-800/60 dark:text-slate-400 dark:border-slate-600/40" };
  const hasOld = log.old_data && Object.keys(log.old_data).length > 0;
  const hasNew = log.new_data && Object.keys(log.new_data).length > 0;

  return (
    <Modal open onClose={onClose} title="Detalhes do log">
      <div className="space-y-4 text-sm">

        {/* Action + Entity */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${badge.cls}`}>
            {badge.label}
          </span>
          <span className="text-slate-500 dark:text-slate-400">
            {ENTITY_LABEL[log.entity_type] ?? log.entity_type}
          </span>
        </div>

        {/* Info grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-background-elevated border border-border/40 p-3 space-y-0.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-wide">Data / Hora</p>
            <p className="text-slate-700 dark:text-slate-200 text-xs font-mono">{formatDate(log.created_at)}</p>
          </div>
          <div className="rounded-lg bg-background-elevated border border-border/40 p-3 space-y-0.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-wide">IP</p>
            <p className="text-slate-700 dark:text-slate-200 text-xs font-mono">{log.ip_address ?? "—"}</p>
          </div>
          <div className="rounded-lg bg-background-elevated border border-border/40 p-3 space-y-0.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-wide">Usuário</p>
            <p className="text-slate-700 dark:text-slate-200 text-xs">{log.user_name ?? "—"}</p>
            {log.user_id && <p className="text-slate-400 dark:text-slate-600 text-[10px] font-mono">{log.user_id}</p>}
          </div>
          <div className="rounded-lg bg-background-elevated border border-border/40 p-3 space-y-0.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-wide">ID Entidade</p>
            <p className="text-slate-700 dark:text-slate-200 text-[10px] font-mono break-all">{log.entity_id ?? "—"}</p>
          </div>
        </div>

        {/* User agent */}
        {log.user_agent && (
          <div className="rounded-lg bg-background-elevated border border-border/40 p-3 space-y-0.5">
            <p className="text-[10px] text-slate-500 uppercase tracking-wide">User Agent</p>
            <p className="text-slate-500 dark:text-slate-400 text-xs break-all">{log.user_agent}</p>
          </div>
        )}

        {/* Data diff */}
        {(hasOld || hasNew) && (
          <div className={`grid gap-3 ${hasOld && hasNew ? "grid-cols-2" : "grid-cols-1"}`}>
            {hasOld && (
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-1.5">Dados anteriores</p>
                <pre className="text-xs text-red-600 bg-red-50 border border-red-200 dark:text-red-300/80 dark:bg-red-900/10 dark:border-red-800/20 rounded-lg p-3 overflow-auto max-h-48 whitespace-pre-wrap break-all">
                  {JSON.stringify(log.old_data, null, 2)}
                </pre>
              </div>
            )}
            {hasNew && (
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wide mb-1.5">Dados novos</p>
                <pre className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 dark:text-emerald-300/80 dark:bg-emerald-900/10 dark:border-emerald-800/20 rounded-lg p-3 overflow-auto max-h-48 whitespace-pre-wrap break-all">
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

  const dateInputCls = "rounded-lg border border-border/60 bg-background-elevated px-3 py-[7px] text-sm text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary transition-colors [color-scheme:light] dark:[color-scheme:dark]";

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="text-center sm:text-left">
          <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Logs de Auditoria</h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-0.5">Registro completo de operações — conformidade LGPD</p>
        </div>
        {!loading && (
          <span className="self-center sm:self-auto text-xs text-slate-500 bg-background-elevated border border-border/60 px-3 py-1.5 rounded-full">
            {total} {total === 1 ? "registro" : "registros"}
          </span>
        )}
      </div>

      {/* Filters */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <span className="text-slate-500">{IC.Filter}</span>
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Filtros</p>
          {hasFilters && (
            <button onClick={clearFilters} className="ml-auto inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors cursor-pointer">
              {IC.X} Limpar filtros
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
            <span className="text-xs text-slate-500 shrink-0">De</span>
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={`${dateInputCls} flex-1 min-w-[130px]`} />
            <span className="text-xs text-slate-500 shrink-0">até</span>
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={`${dateInputCls} flex-1 min-w-[130px]`} />
          </div>
          {/* User ID search */}
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none">{IC.Search}</span>
            <Input
              className="pl-9 w-full"
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
        <div className="hidden lg:grid grid-cols-[1fr_110px_110px_160px_100px_44px] px-4 py-2.5 border-b border-border bg-background-elevated/30">
          {["Evento", "Entidade", "Ação", "Usuário", "IP", ""].map((h, i) => (
            <span key={i} className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">{h}</span>
          ))}
        </div>

        {loading ? (
          <div className="flex h-48 items-center justify-center"><Spinner /></div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-10 h-10 rounded-full bg-background-elevated border border-border flex items-center justify-center text-slate-600 mb-3">{IC.Filter}</div>
            <p className="text-sm text-slate-400">Nenhum registro encontrado.</p>
            {hasFilters && (
              <button onClick={clearFilters} className="mt-2 text-sm text-primary hover:text-primary/80 transition-colors cursor-pointer">Limpar filtros</button>
            )}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {logs.map((log) => {
              const badge = ACTION_BADGE[log.action] ?? { label: log.action, cls: "bg-slate-100 text-slate-500 border border-slate-300 dark:bg-slate-800/60 dark:text-slate-400 dark:border-slate-600/40" };
              const hasData = (log.old_data && Object.keys(log.old_data).length > 0) || (log.new_data && Object.keys(log.new_data).length > 0);
              return (
                <div key={log.id}>
                  {/* Mobile layout */}
                  <div
                    className="lg:hidden flex items-start justify-between gap-3 px-4 py-3 hover:bg-background-elevated/40 transition-colors cursor-pointer"
                    onClick={() => setDetail(log)}
                  >
                    <div className="flex-1 min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${badge.cls}`}>{badge.label}</span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">{ENTITY_LABEL[log.entity_type] ?? log.entity_type}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                        <span className="shrink-0">{IC.Clock}</span>
                        <span>{formatDate(log.created_at)}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 truncate">
                        <span className="shrink-0">{IC.User}</span>
                        <span className="truncate">{log.user_name ?? "—"}</span>
                        {log.ip_address && <span className="font-mono text-slate-400 ml-1">· {log.ip_address}</span>}
                      </div>
                    </div>
                    <button
                      title="Ver detalhes"
                      className={`shrink-0 p-1.5 rounded-lg transition-colors cursor-pointer ${hasData ? "text-primary hover:bg-primary/10" : "text-slate-400 hover:bg-background-elevated"}`}
                      onClick={(e) => { e.stopPropagation(); setDetail(log); }}
                    >
                      {IC.Eye}
                    </button>
                  </div>

                  {/* Desktop layout */}
                  <div className="hidden lg:grid grid-cols-[1fr_110px_110px_160px_100px_44px] items-center px-4 py-3 hover:bg-background-elevated/40 transition-colors">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                        <span className="text-slate-400 dark:text-slate-600 shrink-0">{IC.Clock}</span>
                        <span className="whitespace-nowrap">{formatDate(log.created_at)}</span>
                      </div>
                      <p className="text-[11px] text-slate-400 dark:text-slate-600 font-mono mt-0.5">
                        {log.entity_id ? shortUuid(log.entity_id) : "—"}
                      </p>
                    </div>
                    <span className="text-xs text-slate-600 dark:text-slate-300">{ENTITY_LABEL[log.entity_type] ?? log.entity_type}</span>
                    <div>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${badge.cls}`}>{badge.label}</span>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1 text-xs text-slate-600 dark:text-slate-300 truncate">
                        <span className="text-slate-400 dark:text-slate-600 shrink-0">{IC.User}</span>
                        <span className="truncate">{log.user_name ?? "—"}</span>
                      </div>
                      {log.user_id && <p className="text-[11px] text-slate-400 dark:text-slate-600 font-mono mt-0.5">{shortUuid(log.user_id)}</p>}
                    </div>
                    <span className="text-xs text-slate-500 font-mono">{log.ip_address ?? "—"}</span>
                    <button
                      onClick={() => setDetail(log)}
                      title="Ver detalhes"
                      className={`p-1.5 rounded-lg transition-colors cursor-pointer ${hasData ? "text-primary hover:bg-primary/10" : "text-slate-400 dark:text-slate-600 hover:text-slate-600 dark:hover:text-slate-400 hover:bg-background-elevated"}`}
                    >
                      {IC.Eye}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!loading && total > 0 && (
          <div className="px-4 py-2 border-t border-border">
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} itemLabel="registros" />
          </div>
        )}
      </Card>

      {detail && <DetailModal log={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
