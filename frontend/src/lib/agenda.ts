/**
 * O relógio da agenda: em que dia e em que hora um evento cai.
 *
 * Existe porque a agenda passou a ter hora (backend #16), e com hora há duas
 * naturezas de evento que NÃO se leem do mesmo jeito — a API também as separa:
 *
 * ── Dia inteiro é data FLUTUANTE ──────────────────────────────────────
 *
 * Vale a data em UTC, e o fuso de quem olha não a desloca. É o modelo do
 * `VALUE=DATE` do iCalendar. A razão é concreta: todo evento que já existia foi
 * gravado `00:00:00Z`–`23:59:59Z` pela tela que só tinha data. Lido como
 * instante, cada um começaria às 21:00 do dia ANTERIOR em Recife, e a agenda
 * inteira andaria um dia para trás sem ninguém ter editado nada.
 *
 * ── Evento com hora é um INSTANTE ─────────────────────────────────────
 *
 * Cai no dia e na hora de quem olha. 22:00 do dia 31 em Recife é `01:00Z` do dia
 * 1º — e para quem está em Recife ele é do dia 31.
 *
 * ── O fuso é sempre parâmetro ─────────────────────────────────────────
 *
 * Nenhuma função daqui lê o fuso da máquina com `getDate()` ou `getHours()`.
 * Tudo passa por `Intl.DateTimeFormat` com `timeZone` explícito, e quem decide
 * o fuso é `fusoDoNavegador()`, uma vez, na tela. Sem isso os testes passariam
 * em Recife e reprovariam no CI, que roda em UTC — três horas por dia.
 */

/** Os campos de evento que decidem onde ele cai. */
export interface Faixa {
  start_date: string;
  end_date: string;
  all_day: boolean;
}

/**
 * O fuso de quem olha, como o navegador o informa.
 *
 * O padrão é o mesmo da API (`America/Recife`), para o caso raro de um navegador
 * que não responda: cair em UTC seria escolher o fuso de ninguém.
 */
export function fusoDoNavegador(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Recife";
  } catch {
    return "America/Recife";
  }
}

// ── Chaves de dia ─────────────────────────────────────────────

/** `YYYY-MM-DD`, com mês de 0 a 11 na entrada. Compara como texto. */
export function chaveDoDia(ano: number, mes: number, dia: number): string {
  return `${ano}-${String(mes + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}

function partes(instante: string | number | Date, fuso: string) {
  const formato = new Intl.DateTimeFormat("en-US", {
    timeZone: fuso,
    // `h23` e não o padrão: alguns motores devolvem "24" para meia-noite.
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const valor: Record<string, string> = {};
  for (const p of formato.formatToParts(new Date(instante))) valor[p.type] = p.value;
  return valor;
}

/** O dia civil de um instante, no fuso pedido. */
export function chaveCivil(instante: string | number | Date, fuso: string): string {
  const v = partes(instante, fuso);
  return `${v.year}-${v.month}-${v.day}`;
}

/** `HH:MM` de um instante, no fuso pedido. */
export function horaCivil(instante: string | number | Date, fuso: string): string {
  const v = partes(instante, fuso);
  return `${v.hour}:${v.minute}`;
}

/** A data de um evento de dia inteiro: a parte de data em UTC, sem fuso. */
export function chaveFlutuante(instante: string): string {
  const d = new Date(instante);
  return chaveDoDia(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

// ── Do relógio de quem digita para o instante ─────────────────

/** Quantos ms o relógio do fuso está à frente de UTC naquele instante. */
function deslocamento(instanteMs: number, fuso: string): number {
  const v = partes(instanteMs, fuso);
  const comoSeFosseUtc = Date.UTC(
    Number(v.year), Number(v.month) - 1, Number(v.day),
    Number(v.hour), Number(v.minute), Number(v.second),
  );
  return comoSeFosseUtc - Math.floor(instanteMs / 1000) * 1000;
}

const FORMATO_DIA = /^(\d{4})-(\d{2})-(\d{2})$/;
const FORMATO_HORA = /^(\d{2}):(\d{2})$/;

/**
 * O instante UTC de "dia tal, hora tal" no fuso de quem digitou — ou `null`.
 *
 * **`null` quando a entrada não é dia e hora de verdade.** Apagar um pedaço do
 * `<input type="time">` deixa o valor vazio, e esta conta roda durante a
 * renderização do modal: lançando, ela derrubava a tela inteira (não há
 * ErrorBoundary), com o que a pessoa tinha digitado. Achado da revisão
 * independente, pelas quatro lentes. Quem chama decide o que fazer com o nulo.
 *
 * **Duas passadas.** O deslocamento depende do instante, e o instante é o que se
 * quer descobrir. A primeira acha o deslocamento perto; a segunda corrige quando
 * a primeira caiu do outro lado de uma troca de horário de verão.
 *
 * **Hora que não existe anda para a frente.** No dia em que o relógio pula (02:00
 * vira 03:00), "02:15" não acontece. As duas passadas então não concordam, e a
 * convenção — a do `Temporal`, "compatible" — é ler como 03:15: o maior dos dois
 * candidatos. Sem isso, 02:15 virava 01:15, antes de um início às 01:45.
 *
 * **Hora que se repete fica com a primeira ocorrência** (o relógio volta, e 01:30
 * acontece duas vezes). É a mesma convenção. E é por isso que a tela não
 * recalcula a hora que ninguém mexeu: recalcular trocaria a segunda ocorrência
 * pela primeira.
 *
 * O resultado nunca tem segundos. A pegada do backend (#17) é `23:59:59`
 * cravado, e um campo de hora com segundos a acionaria por acidente.
 */
export function instanteDe(dia: string, hora: string, fuso: string): string | null {
  const d = FORMATO_DIA.exec(dia);
  const h = FORMATO_HORA.exec(hora);
  if (!d || !h) return null;
  const [ano, mes, dd] = [Number(d[1]), Number(d[2]), Number(d[3])];
  const [hh, mm] = [Number(h[1]), Number(h[2])];
  if (hh > 23 || mm > 59) return null;
  // 30/02 não existe: `Date.UTC` o empurraria para março sem avisar.
  const data = new Date(Date.UTC(ano, mes - 1, dd));
  if (data.getUTCMonth() !== mes - 1 || data.getUTCDate() !== dd) return null;

  const relogio = Date.UTC(ano, mes - 1, dd, hh, mm, 0, 0);
  const primeira = relogio - deslocamento(relogio, fuso);
  const segunda = relogio - deslocamento(primeira, fuso);
  if (chaveCivil(segunda, fuso) === dia && horaCivil(segunda, fuso) === hora) {
    return new Date(segunda).toISOString();
  }
  return new Date(Math.max(primeira, segunda)).toISOString();
}

// ── Onde o evento cai ─────────────────────────────────────────

/** O primeiro e o último dia que o evento ocupa, como chaves. */
function diasDoEvento(e: Faixa, fuso: string): { inicio: string; fim: string } {
  if (e.all_day) {
    return { inicio: chaveFlutuante(e.start_date), fim: chaveFlutuante(e.end_date) };
  }
  // Fim EXCLUSIVO: um evento que termina à meia-noite em ponto não ocupa o dia
  // seguinte, onde ele não dura um minuto sequer.
  const fim = new Date(e.end_date).getTime() - 1;
  return { inicio: chaveCivil(e.start_date, fuso), fim: chaveCivil(fim, fuso) };
}

export function ocupaODia(e: Faixa, dia: string, fuso: string): boolean {
  const { inicio, fim } = diasDoEvento(e, fuso);
  return inicio <= dia && dia <= fim;
}

/**
 * Mês de 0 a 11. O mesmo corte da API, com UMA borda de diferença.
 *
 * Aqui o fim do evento com hora é exclusivo: um evento que termina à 00:00 do dia
 * 1º não pertence ao mês que começa. A API (`routers/calendar.py`) compara
 * `end_date >= inicio_local` e o devolve na lista desse mês. A tela não o
 * desenha, porque refiltra por aqui — mas a resposta da API traz um item a mais.
 * Achado da revisão, relatado para conserto no backend.
 */
export function ocupaOMes(e: Faixa, ano: number, mes: number, fuso: string): boolean {
  const { inicio, fim } = diasDoEvento(e, fuso);
  return inicio <= chaveDoDia(ano, mes, diasNoMes(ano, mes)) && fim >= chaveDoDia(ano, mes, 1);
}

/**
 * Dia inteiro termina quando o DIA termina para quem olha — não às 23:59:59Z.
 *
 * Comparado como instante, o treinamento de hoje sumiria da lista de próximos às
 * 21:00 em Recife, que é quando 23:59:59Z acontece.
 */
export function jaTerminou(e: Faixa, agora: Date, fuso: string): boolean {
  if (e.all_day) return chaveFlutuante(e.end_date) < chaveCivil(agora, fuso);
  return new Date(e.end_date).getTime() <= agora.getTime();
}

/**
 * A ordem do calendário, e não a do instante.
 *
 * Pelo instante, o dia inteiro de 15/01 (00:00Z) viria antes da reunião das
 * 22:00 de 14/01 em Recife (01:00Z de 15/01). No mesmo dia, dia inteiro vem antes
 * de qualquer horário — o `0` e o `1` do meio garantem isso até contra 00:00.
 */
export function chaveDeOrdem(e: Faixa, fuso: string): string {
  const { inicio } = diasDoEvento(e, fuso);
  return e.all_day ? `${inicio}|0` : `${inicio}|1|${horaCivil(e.start_date, fuso)}`;
}

// ── O que a tela escreve ──────────────────────────────────────

const ddmm = (chave: string) => `${chave.slice(8, 10)}/${chave.slice(5, 7)}`;

/** O horário, para quem já sabe o dia (o detalhe do dia). */
export function descreveHorario(e: Faixa, fuso: string): string {
  const { inicio, fim } = diasDoEvento(e, fuso);
  if (e.all_day) {
    return inicio === fim ? "Dia inteiro" : `Dia inteiro · ${ddmm(inicio)} → ${ddmm(fim)}`;
  }
  const hIni = horaCivil(e.start_date, fuso);
  const hFim = horaCivil(e.end_date, fuso);
  if (inicio === fim) return `${hIni}–${hFim}`;
  return `${ddmm(inicio)} ${hIni} → ${ddmm(chaveCivil(e.end_date, fuso))} ${hFim}`;
}

/** O horário com a data, para quem não sabe o dia (a lista de próximos). */
export function descreveComData(e: Faixa, fuso: string): string {
  const { inicio, fim } = diasDoEvento(e, fuso);
  if (e.all_day) {
    return inicio === fim
      ? `${ddmm(inicio)} · Dia inteiro`
      : `${ddmm(inicio)} → ${ddmm(fim)} · Dia inteiro`;
  }
  if (inicio === fim) return `${ddmm(inicio)} · ${descreveHorario(e, fuso)}`;
  return descreveHorario(e, fuso);
}

// ── A grade ───────────────────────────────────────────────────

/** 0 = domingo. Aritmética em UTC: uma data civil não tem fuso. */
export function diaDaSemana(chave: string): number {
  const [ano, mes, dia] = chave.split("-").map(Number);
  return new Date(Date.UTC(ano, mes - 1, dia)).getUTCDay();
}

/** Mês de 0 a 11. */
export function diasNoMes(ano: number, mes: number): number {
  return new Date(Date.UTC(ano, mes + 1, 0)).getUTCDate();
}
