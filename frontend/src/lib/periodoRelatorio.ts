/**
 * Os períodos dos relatórios: que dias cada opção do seletor cobre (F1-B-03b).
 *
 * ── O contrato é o da API (F1-B-03a) ──────────────────────────────────
 *
 * A tela manda `start_date` e `end_date`, `AAAA-MM-DD`, e o backend os lê como
 * DIAS DO CALENDÁRIO de `America/Recife`: do início de `start_date` até o fim
 * de `end_date`, inclusive. A tela não manda mais "N dias contados de agora" —
 * era assim que "Ontem" virava as últimas 48 horas e "Mês passado" os últimos
 * 60 dias. Ver `docs/decisoes-e-regras.md`, "Contrato dos períodos dos
 * relatórios".
 *
 * ── "Hoje" é o dia de Recife, não o do navegador ──────────────────────
 *
 * Nada aqui usa `getDate()` nem `toISOString().slice(0, 10)`. O primeiro lê o
 * fuso da máquina de quem olha; o segundo, o dia em UTC — e às 21:00 em Recife
 * o dia em UTC já é amanhã, e a API recusaria o pedido como "data final no
 * futuro". O dia sai de `chaveCivil(agora, FUSO_DOS_RELATORIOS)`, com o fuso
 * explícito, como na agenda.
 *
 * Depois do dia achado, a conta é de calendário puro (somar dias, achar o dia
 * 1º): uma data civil não tem fuso, e a aritmética é feita em UTC só para não
 * pegar o fuso da máquina por acidente.
 */

import { chaveCivil, chaveDoDia, diasNoMes } from "./agenda";

/** O mesmo fuso do backend (`app/utils/periodo_relatorio.py`). */
export const FUSO_DOS_RELATORIOS = "America/Recife";

/** O limite da API: um intervalo de até 366 dias. */
export const INTERVALO_MAXIMO_DIAS = 366;

export type PresetDePeriodo =
  | "hoje"
  | "ontem"
  | "7-dias"
  | "30-dias"
  | "este-mes"
  | "mes-passado"
  | "personalizado";

/** As opções do seletor, na ordem em que aparecem (decisão D1). */
export const OPCOES_DE_PERIODO: { value: PresetDePeriodo; label: string }[] = [
  { value: "hoje",          label: "Hoje" },
  { value: "ontem",         label: "Ontem" },
  { value: "7-dias",        label: "Últimos 7 dias" },
  { value: "30-dias",       label: "Últimos 30 dias" },
  { value: "este-mes",      label: "Este mês" },
  { value: "mes-passado",   label: "Mês passado" },
  { value: "personalizado", label: "Personalizado" },
];

/** O período com que as telas abrem. */
export const PRESET_PADRAO: PresetDePeriodo = "30-dias";

export interface IntervaloDeDatas {
  /** `AAAA-MM-DD`, dia de Recife, incluído. */
  start_date: string;
  /** `AAAA-MM-DD`, dia de Recife, incluído. */
  end_date: string;
}

// ── Aritmética de calendário ──────────────────────────────────

const FORMATO_DIA = /^(\d{4})-(\d{2})-(\d{2})$/;

function partesDoDia(chave: string): [number, number, number] {
  const [ano, mes, dia] = chave.split("-").map(Number);
  return [ano, mes - 1, dia];
}

/** `chave` é um dia que existe no calendário (30/02 não é). */
export function ehDiaValido(chave: string): boolean {
  const m = FORMATO_DIA.exec(chave);
  if (!m) return false;
  const [ano, mes, dia] = [Number(m[1]), Number(m[2]) - 1, Number(m[3])];
  if (mes < 0 || mes > 11 || dia < 1) return false;
  return dia <= diasNoMes(ano, mes);
}

/** O dia `n` dias depois (ou antes, com `n` negativo). */
export function somaDias(chave: string, n: number): string {
  const [ano, mes, dia] = partesDoDia(chave);
  const d = new Date(Date.UTC(ano, mes, dia + n));
  return chaveDoDia(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

/** Quantos dias o intervalo cobre, contando as duas pontas. */
export function diasNoIntervalo(inicio: string, fim: string): number {
  const [a1, m1, d1] = partesDoDia(inicio);
  const [a2, m2, d2] = partesDoDia(fim);
  return Math.round((Date.UTC(a2, m2, d2) - Date.UTC(a1, m1, d1)) / 86_400_000) + 1;
}

/** O dia de hoje em Recife, para o instante dado. */
export function hojeNosRelatorios(agora: Date = new Date()): string {
  return chaveCivil(agora, FUSO_DOS_RELATORIOS);
}

// ── Os presets ────────────────────────────────────────────────

/**
 * Os dias que um preset cobre, a partir do dia de hoje em Recife.
 *
 * - **Hoje / Ontem:** um dia só.
 * - **Últimos 7 / 30 dias:** 7 ou 30 dias de calendário, hoje incluído (D2).
 * - **Este mês:** do dia 1º até hoje.
 * - **Mês passado:** o mês civil anterior inteiro. A comparação da API é, por
 *   isso, com o mês civil antes dele (D6).
 *
 * "Personalizado" não tem dias próprios: quem chama usa as datas escolhidas.
 */
export function intervaloDoPreset(
  preset: Exclude<PresetDePeriodo, "personalizado">,
  agora: Date = new Date(),
): IntervaloDeDatas {
  const hoje = hojeNosRelatorios(agora);
  const [ano, mes] = partesDoDia(hoje);
  switch (preset) {
    case "hoje":
      return { start_date: hoje, end_date: hoje };
    case "ontem": {
      const ontem = somaDias(hoje, -1);
      return { start_date: ontem, end_date: ontem };
    }
    case "7-dias":
      return { start_date: somaDias(hoje, -6), end_date: hoje };
    case "30-dias":
      return { start_date: somaDias(hoje, -29), end_date: hoje };
    case "este-mes":
      return { start_date: chaveDoDia(ano, mes, 1), end_date: hoje };
    case "mes-passado": {
      const ultimo = somaDias(chaveDoDia(ano, mes, 1), -1);
      const [a, m] = partesDoDia(ultimo);
      return { start_date: chaveDoDia(a, m, 1), end_date: ultimo };
    }
  }
}

/** O "Personalizado" abre com os últimos 30 dias preenchidos. */
export function datasPersonalizadasIniciais(agora: Date = new Date()): IntervaloDeDatas {
  return intervaloDoPreset("30-dias", agora);
}

// ── Validação do intervalo personalizado ──────────────────────

/**
 * O motivo de o intervalo ser recusado, ou `null` se ele vale.
 *
 * São as mesmas regras da API, com as mesmas palavras, checadas ANTES de
 * pedir: a tela não manda um pedido que sabe que vai voltar 422.
 */
export function motivoDoIntervaloInvalido(
  inicio: string,
  fim: string,
  agora: Date = new Date(),
): string | null {
  if (!inicio || !fim) return "Informe a data inicial e a data final.";
  if (!ehDiaValido(inicio) || !ehDiaValido(fim)) {
    return "Data inválida. Use o formato AAAA-MM-DD.";
  }
  if (inicio > fim) return "A data inicial não pode ser posterior à data final.";
  if (fim > hojeNosRelatorios(agora)) return "A data final não pode estar no futuro.";
  if (diasNoIntervalo(inicio, fim) > INTERVALO_MAXIMO_DIAS) {
    return `O intervalo pode ter no máximo ${INTERVALO_MAXIMO_DIAS} dias.`;
  }
  return null;
}

export type PeriodoResolvido =
  | { ok: true; intervalo: IntervaloDeDatas }
  | { ok: false; erro: string };

/** O intervalo que a tela vai pedir, ou o motivo de não pedir nada. */
export function resolvePeriodo(
  preset: PresetDePeriodo,
  personalizado: { inicio: string; fim: string },
  agora: Date = new Date(),
): PeriodoResolvido {
  if (preset !== "personalizado") {
    return { ok: true, intervalo: intervaloDoPreset(preset, agora) };
  }
  const erro = motivoDoIntervaloInvalido(personalizado.inicio, personalizado.fim, agora);
  if (erro) return { ok: false, erro };
  return {
    ok: true,
    intervalo: { start_date: personalizado.inicio, end_date: personalizado.fim },
  };
}

/** Uma chave estável do intervalo, para dependência de efeito. */
export function chaveDoIntervalo(intervalo: IntervaloDeDatas | null): string {
  return intervalo ? `${intervalo.start_date}|${intervalo.end_date}` : "";
}

// ── O que a tela escreve ──────────────────────────────────────

/** `29/10`, ou `29/10/2025` quando o ano não é o de `hoje`. */
function diaCurto(chave: string, anoCorrente: string): string {
  const ddmm = `${chave.slice(8, 10)}/${chave.slice(5, 7)}`;
  return chave.slice(0, 4) === anoCorrente ? ddmm : `${ddmm}/${chave.slice(0, 4)}`;
}

/**
 * Os dias do intervalo por extenso curto: `29/10` ou `23/10 – 29/10`.
 *
 * O ano só aparece quando não é o corrente: "Mês passado" em janeiro mostra
 * `01/12/2025 – 31/12/2025`, e sem o ano dezembro pareceria o deste ano.
 */
export function descreveIntervalo(
  intervalo: IntervaloDeDatas,
  agora: Date = new Date(),
): string {
  const ano = hojeNosRelatorios(agora).slice(0, 4);
  const inicio = diaCurto(intervalo.start_date, ano);
  if (intervalo.start_date === intervalo.end_date) return inicio;
  return `${inicio} – ${diaCurto(intervalo.end_date, ano)}`;
}

/** O rótulo de um preset. */
export function rotuloDoPreset(preset: PresetDePeriodo): string {
  return OPCOES_DE_PERIODO.find((o) => o.value === preset)?.label ?? "";
}

/**
 * A nota discreta sobre a comparação do "Hoje".
 *
 * A API compara a janela com a mesma quantidade de dias imediatamente antes.
 * Para "Hoje" isso é o dia de ontem INTEIRO contra o dia de hoje até agora —
 * a variação tende a parecer queda durante o dia. A regra fica como está
 * (não se inventa outro cálculo na tela); a nota diz o que está sendo
 * comparado.
 */
export const NOTA_COMPARACAO_DE_HOJE =
  "Hoje, até agora, comparado com o dia de ontem inteiro.";

/**
 * O que um bloco do período diz enquanto o "Personalizado" está inválido.
 *
 * Com o intervalo inválido a carga fica ociosa — nada é pedido —, e o bloco
 * desenhava o anel de carregando para sempre, esperando uma resposta que não
 * viria. O motivo exato está no seletor; o bloco só diz que espera.
 */
export const AVISO_DE_PERIODO_INVALIDO =
  "Aguardando um período válido — corrija as datas acima.";

/** A versão curta, para o subtítulo de um indicador. */
export const SUBTITULO_DE_PERIODO_INVALIDO = "Período inválido";
