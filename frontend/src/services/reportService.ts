import { isAxiosError } from "axios";

import { api } from "./api";
import {
  avisaAceitePoliticaPendente,
  ehAceitePoliticaPendente,
} from "./aceitePolitica";
import type { IntervaloDeDatas } from "../lib/periodoRelatorio";

export interface DailyCount {
  date: string;
  count: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface SLAComplianceItem {
  priority: string;
  total: number;
  breached: number;
  compliance_rate: number;
}

export interface CSATDistributionItem {
  rating: number;
  count: number;
}

export interface AvgResolutionItem {
  priority: string;
  avg_hours: number | null;
}

export interface CsatDailyItem {
  date: string;
  avg_rating: number | null;
  count: number;
}

export interface WeekdayCount {
  weekday: number; // 1 = Seg … 7 = Dom
  count: number;
}

export interface AvgFirstResponseItem {
  priority: string;
  avg_hours: number | null;
}

export interface ProductCount {
  product_name: string;
  count: number;
}

export interface HourlyCount {
  hour: number;
  count: number;
}

export interface TechnicianDistItem {
  technician_name: string;
  total: number;
  resolved: number;
  open_count: number;
}

export interface OldestTicketItem {
  ticket_id: string;
  protocol: string;
  title: string;
  /** Nulo enquanto o chamado nao foi triado. */
  priority: string | null;
  category: string;
  status: string;
  age_hours: number;
  sla_breached: boolean;
  assignee_name: string | null;
}

/**
 * Chamado resolvido fora do prazo, com o motivo que quem resolveu escreveu.
 *
 * O relatório de SLA só tinha número agregado: sabia-se QUANTOS estouraram,
 * nunca POR QUÊ. A contagem responde à auditoria; o motivo é o que permite
 * corrigir a causa.
 *
 * A lista vem do servidor pela PRESENÇA da justificativa, e não por uma conta
 * de datas feita na tela — é a mesma razão pela qual o front nunca decide se o
 * SLA estourou: ele não recebe a pausa acumulada (`sla_total_paused_ms`), então
 * acharia vencido o que não está.
 */
export interface SlaJustificationItem {
  ticket_id: string;
  protocol: string;
  title: string;
  priority: string | null;
  resolved_at: string | null;
  assignee_name: string | null;
  justification: string;
}

export interface ReportComparison {
  /** Os dias do período comparado (F1-B-03a). Ausentes num backend antigo. */
  start_date?: string | null;
  end_date?: string | null;
  total_tickets: number;
  csat_average: number | null;
  sla_compliance: SLAComplianceItem[];
}

export interface ReportData {
  period_days: number;
  /**
   * Os dias que o servidor de fato aplicou, e o fuso em que os leu (F1-B-03a).
   * Opcionais: um backend anterior à F1-B-03a não os manda.
   */
  start_date?: string | null;
  end_date?: string | null;
  timezone?: string | null;
  total_tickets: number;
  tickets_by_day: DailyCount[];
  tickets_by_category: CategoryCount[];
  sla_compliance: SLAComplianceItem[];
  csat_distribution: CSATDistributionItem[];
  csat_average: number | null;
  /** Média da nota "o quanto recomendaria a empresa"; null se ninguém respondeu. */
  recommend_average: number | null;
  avg_resolution_by_priority: AvgResolutionItem[];
  avg_first_response_by_priority: AvgFirstResponseItem[];
  csat_by_day: CsatDailyItem[];
  tickets_by_product: ProductCount[];
  tickets_by_weekday: WeekdayCount[];
  tickets_by_hour: HourlyCount[];
  oldest_open_tickets: OldestTicketItem[];
  technicians_dist: TechnicianDistItem[];
  reopened_count: number;
  reopen_rate: number;
  sla_justifications: SlaJustificationItem[];
  comparison: ReportComparison | null;
}

export interface TechnicianSummary {
  technician_id: string;
  technician_name: string;
  total_assigned: number;
  resolved: number;
  open_count: number;
  sla_breached: number;
  sla_compliance_rate: number;
  avg_resolution_hours: number | null;
  csat_average: number | null;
  csat_count: number;
}

export interface TechnicianListReport {
  period_days: number;
  /**
   * Os dias que o servidor de fato aplicou, e o fuso em que os leu (F1-B-03a).
   * Opcionais: um backend anterior à F1-B-03a não os manda.
   */
  start_date?: string | null;
  end_date?: string | null;
  timezone?: string | null;
  technicians: TechnicianSummary[];
}

export interface TechnicianDetailReport {
  period_days: number;
  /**
   * Os dias que o servidor de fato aplicou, e o fuso em que os leu (F1-B-03a).
   * Opcionais: um backend anterior à F1-B-03a não os manda.
   */
  start_date?: string | null;
  end_date?: string | null;
  timezone?: string | null;
  technician_id: string;
  technician_name: string;
  total_assigned: number;
  resolved: number;
  in_progress: number;
  open_count: number;
  sla_breached: number;
  sla_compliance_rate: number;
  avg_resolution_hours: number | null;
  csat_average: number | null;
  csat_count: number;
  tickets_by_day: DailyCount[];
}

export interface ReportFilters {
  period?: number;
  category?: string;
  priority?: string;
  start_date?: string;
  end_date?: string;
}

export async function getReports(filters: ReportFilters = {}): Promise<ReportData> {
  const { data } = await api.get<ReportData>("/dashboard/reports", {
    params: {
      ...(filters.period   !== undefined && { period:     filters.period   }),
      ...(filters.category !== undefined && { category:   filters.category }),
      ...(filters.priority !== undefined && { priority:   filters.priority }),
      ...(filters.start_date             && { start_date: filters.start_date }),
      ...(filters.end_date               && { end_date:   filters.end_date   }),
    },
  });
  return data;
}

/**
 * O recorte de tempo dos relatórios de técnico: as datas do calendário
 * (F1-B-03a) ou, por compatibilidade, o `period` legado em dias.
 *
 * As telas mandam as datas. O número continua aceito para quem ainda o usa, e
 * com o mesmo significado de antes: N dias contados de agora para trás.
 */
export type RecorteDeTempo = number | IntervaloDeDatas;

function paramsDoRecorte(recorte: RecorteDeTempo): Record<string, string | number> {
  return typeof recorte === "number"
    ? { period: recorte }
    : { start_date: recorte.start_date, end_date: recorte.end_date };
}

export async function getTechnicianListReport(
  recorte: RecorteDeTempo = 30,
): Promise<TechnicianListReport> {
  const { data } = await api.get<TechnicianListReport>(
    "/dashboard/reports/technicians",
    { params: paramsDoRecorte(recorte) },
  );
  return data;
}

export async function getTechnicianDetailReport(
  recorte: RecorteDeTempo = 30,
  technicianId?: string,
): Promise<TechnicianDetailReport> {
  const { data } = await api.get<TechnicianDetailReport>(
    "/dashboard/reports/technician",
    {
      params: {
        ...paramsDoRecorte(recorte),
        ...(technicianId ? { technician_id: technicianId } : {}),
      },
    },
  );
  return data;
}

// ── Exportação (F1-C-01a) ─────────────────────────────────────
//
// Até aqui a exportação era um `<a href="/api/v1/...">`. Dois defeitos, cada
// um suficiente para não baixar nada: o caminho relativo ia ao domínio do
// FRONT, cujo nginx devolve o `index.html` da SPA para qualquer rota (200
// text/html), e o link não leva o `Authorization` — a API, no outro domínio,
// responde 401. Agora o pedido sai pelo `api`: a base é a `VITE_API_URL` e o
// token vai pelo interceptor, nunca na query.

export type FormatoDeExportacao = "csv" | "pdf";

const TIPO_DO_FORMATO: Record<FormatoDeExportacao, string> = {
  csv: "text/csv",
  pdf: "application/pdf",
};

/**
 * O que veio com 2xx mas não é o relatório pedido — o caso típico é o
 * `index.html` da SPA. Não vira arquivo, e a tela não mostra o conteúdo.
 */
export class ArquivoDeRelatorioInvalido extends Error {
  constructor(formato: FormatoDeExportacao) {
    super(`A resposta não é um relatório ${formato.toUpperCase()}.`);
    this.name = "ArquivoDeRelatorioInvalido";
  }
}

/**
 * Os parâmetros da exportação. O intervalo de datas vence o `period` legado,
 * e só vale com as DUAS pontas — a mesma regra da URL que existia antes.
 */
export function paramsDaExportacao(filters: ReportFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (filters.start_date && filters.end_date) {
    params.start_date = filters.start_date;
    params.end_date = filters.end_date;
  } else if (filters.period !== undefined) {
    params.period = String(filters.period);
  }
  if (filters.category) params.category = filters.category;
  if (filters.priority) params.priority = filters.priority;
  return params;
}

/** Só letra, dígito e hífen: o nome do arquivo não carrega o que vier do filtro. */
function trechoDoNome(valor: string): string {
  return valor.replace(/[^a-z0-9-]/gi, "");
}

/**
 * O nome do arquivo, montado aqui: o CORS da API não expõe o
 * `Content-Disposition`, então o nome que o backend escolhe não chega ao JS.
 *
 * Com intervalo, o nome diz o intervalo — que é o que distingue dois arquivos
 * baixados no mesmo dia. Com o `period` legado, a data de hoje e os dias.
 */
export function nomeDoArquivoDoRelatorio(
  formato: FormatoDeExportacao,
  filters: ReportFilters,
  hoje: Date = new Date(),
): string {
  const partes = ["relatorio_helphs"];
  if (filters.start_date && filters.end_date) {
    partes.push(`${trechoDoNome(filters.start_date)}_a_${trechoDoNome(filters.end_date)}`);
  } else {
    partes.push(hoje.toISOString().slice(0, 10));
    if (filters.period !== undefined) partes.push(`${filters.period}d`);
  }
  if (filters.category) partes.push(trechoDoNome(filters.category));
  if (filters.priority) partes.push(trechoDoNome(filters.priority));
  return `${partes.filter(Boolean).join("_")}.${formato}`;
}

async function inicioDoArquivo(blob: Blob, bytes: number): Promise<string> {
  const pedaco = await blob.slice(0, bytes).arrayBuffer();
  // O `TextDecoder` já descarta o BOM do início (ignoreBOM = false).
  return new TextDecoder().decode(pedaco);
}

/**
 * Confere que o corpo é do formato pedido, pelo tipo E pelo conteúdo: o tipo
 * sozinho não basta contra um proxy que rotule errado, e o conteúdo sozinho
 * não distingue CSV de texto qualquer.
 */
async function confereFormato(
  formato: FormatoDeExportacao,
  blob: Blob,
  contentType: string,
): Promise<void> {
  const tipo = (contentType || blob.type).toLowerCase();
  if (!tipo.includes(TIPO_DO_FORMATO[formato]) || blob.size === 0) {
    throw new ArquivoDeRelatorioInvalido(formato);
  }
  const inicio = await inicioDoArquivo(blob, 16);
  const valido =
    formato === "pdf" ? inicio.startsWith("%PDF") : !/^\s*</.test(inicio);
  if (!valido) throw new ArquivoDeRelatorioInvalido(formato);
}

/**
 * Com `responseType: "blob"` o corpo do ERRO também chega como Blob, e quem lê
 * `data.detail` (o `apiError`) ou `data.code` (o 428 do aceite) não acha
 * nada. Aqui o Blob volta a ser o JSON que o backend mandou; o que não for
 * JSON — uma página HTML de proxy, por exemplo — vira corpo vazio, para a tela
 * cair na mensagem do status em vez de desenhar HTML.
 */
async function desembrulhaCorpoDoErro(erro: unknown): Promise<void> {
  if (!isAxiosError(erro) || !erro.response) return;
  const corpo: unknown = erro.response.data;
  if (!(corpo instanceof Blob)) return;
  try {
    erro.response.data = JSON.parse(await corpo.text());
  } catch {
    erro.response.data = undefined;
  }
}

/** Entrega o arquivo ao navegador e libera a URL temporária. */
function entregaAoNavegador(blob: Blob, nome: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    // No próximo tique, não no mesmo: revogar antes de o navegador começar o
    // download cancela o arquivo em alguns navegadores.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

/**
 * Baixa o relatório em CSV ou PDF.
 *
 * Erros saem como o `AxiosError` de sempre, com o corpo já legível pelo
 * `apiError`. O 401 passa pelo interceptor (renova e repete, ou manda para o
 * login) antes de chegar aqui. O 428 do aceite da Política o interceptor não
 * reconhece com corpo Blob — por isso o aviso é disparado aqui, depois de
 * desembrulhar, e o `ReaceiteGuard` troca a tela como em qualquer outra rota.
 */
export async function baixarRelatorio(
  formato: FormatoDeExportacao,
  filters: ReportFilters,
): Promise<void> {
  let resposta;
  try {
    resposta = await api.get<Blob>(`/dashboard/reports/export/${formato}`, {
      params: paramsDaExportacao(filters),
      responseType: "blob",
    });
  } catch (erro) {
    await desembrulhaCorpoDoErro(erro);
    if (ehAceitePoliticaPendente(erro)) avisaAceitePoliticaPendente();
    throw erro;
  }

  const blob = resposta.data;
  if (!(blob instanceof Blob)) throw new ArquivoDeRelatorioInvalido(formato);
  await confereFormato(formato, blob, String(resposta.headers?.["content-type"] ?? ""));

  entregaAoNavegador(
    new Blob([blob], { type: TIPO_DO_FORMATO[formato] }),
    nomeDoArquivoDoRelatorio(formato, filters),
  );
}
