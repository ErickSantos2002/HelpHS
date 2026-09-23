/**
 * O tempo ÚTIL que falta num prazo de SLA, como a tela o mostra.
 *
 * ── O defeito que isto conserta ───────────────────────────────────────
 *
 * O chip fazia `new Date(dueAt) - Date.now()`: tempo CORRIDO. Um prazo de 12h
 * ÚTEIS carimbado às 09:11 aparecia como **27h**, porque a subtração contava
 * também as 15 horas entre 17:00 e 08:00, em que ninguém atende. O mesmo erro
 * estava na barra da lista — e lá em três lugares: o texto, o percentual e a
 * decisão de pintar de vermelho.
 *
 * ── Por que o calendário NÃO mora aqui ────────────────────────────────
 *
 * Dia útil, neste sistema, não é "segunda a sexta". É a jornada 08:00–17:00
 * mais os dez feriados nacionais, mais Carnaval e Cinzas derivados da Páscoa,
 * mais uma tabela manual de decretos — tudo em `backend/app/utils/feriados.py`.
 * Reimplementar isso aqui criaria uma segunda verdade que diverge no primeiro
 * ano em que alguém atualizar só um dos lados.
 *
 * Então o backend manda o que já sabe:
 *
 * | campo | o que é |
 * |---|---|
 * | `restanteMin` | minutos ÚTEIS que faltavam quando a resposta foi montada |
 * | `venceEm` | o prazo EFETIVO — com a pausa somada, o mesmo que decide violação |
 * | `expediente.agora` | o relógio do SERVIDOR naquele instante |
 * | `expediente.aberto` | o relógio está correndo? |
 * | `expediente.proxima_virada` | quando esse estado muda |
 * | `expediente.fuso` | em que fuso a jornada é definida |
 *
 * E este módulo só faz aritmética: desconta o tempo que passou enquanto a
 * janela está aberta, e congela quando ela fecha.
 *
 * ── Por que o tempo decorrido é medido LOCALMENTE ─────────────────────
 *
 * `decorridoMs` é medido do instante em que a resposta chegou, e não por
 * `Date.now() - expediente.agora`. Essa subtração mistura dois relógios: o do
 * servidor e o da máquina de quem olha. Um desvio de dez minutos no relógio do
 * usuário — que é comum — apareceria como dez minutos a mais ou a menos no
 * contador, sem nada na tela explicando de onde vieram.
 *
 * A duração da janela (`proxima_virada - agora`) é subtração de DOIS instantes
 * do servidor, então ela não sofre do problema e serve de teto.
 */

/** O relógio do servidor, como a API o entrega. */
export interface Expediente {
  agora: string;
  aberto: boolean;
  proxima_virada: string;
  fuso: string;
}

/** Quanto da janela atual ainda cabe, em milissegundos. Sem relógio local. */
function janelaMs(expediente: Expediente): number {
  return (
    new Date(expediente.proxima_virada).getTime() -
    new Date(expediente.agora).getTime()
  );
}

/**
 * Os minutos úteis que faltam AGORA.
 *
 * Com o expediente fechado o valor não se mexe — é isso que "congela após
 * 17:00" quer dizer. Com ele aberto, desconta o tempo decorrido, mas nunca
 * além do fim da janela: passado esse ponto o dado está velho, e quem decide o
 * que fazer é `precisaRecarregar`.
 */
export function restanteUtil(
  restanteMin: number,
  expediente: Expediente,
  decorridoMs: number,
): number {
  if (!expediente.aberto) return restanteMin;
  const efetivoMs = Math.min(Math.max(0, decorridoMs), Math.max(0, janelaMs(expediente)));
  return Math.max(0, restanteMin - Math.floor(efetivoMs / 60_000));
}

/**
 * O dado envelheceu: a janela virou desde que a resposta chegou.
 *
 * É o gatilho para buscar de novo — e é o que faz o contador **voltar a
 * diminuir** quando a jornada seguinte começa, sem a tela precisar saber que
 * horas a jornada começa.
 */
export function precisaRecarregar(expediente: Expediente, decorridoMs: number): boolean {
  return decorridoMs >= janelaMs(expediente);
}

/** `692` → `"11h 32m"`. Zero e negativo não chegam aqui: viram "Vencido". */
export function formataUtil(minutos: number): string {
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/**
 * `"Vence em 24/09/2026 às 12:11"`, no fuso em que a jornada é definida.
 *
 * O fuso vem do backend (`expediente.fuso`) e não de um literal daqui: o
 * horário do vencimento só faz sentido na jornada que o produziu, e quem abre
 * a tela de outro fuso veria um horário que não corresponde a jornada nenhuma.
 */
export function textoDoVencimento(venceEm: string, fuso: string): string {
  const d = new Date(venceEm);
  const data = d.toLocaleDateString("pt-BR", {
    timeZone: fuso,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
  const hora = d.toLocaleTimeString("pt-BR", {
    timeZone: fuso,
    hour: "2-digit",
    minute: "2-digit",
  });
  return `Vence em ${data} às ${hora}`;
}
