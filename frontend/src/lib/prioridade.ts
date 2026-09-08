/**
 * A prioridade do chamado, numa fonte só.
 *
 * Existia em **cinco mapas divergentes**, um por tela — `PRIORITY_DOT`,
 * `PRIORITY_COLORS`, `PRIORITY_CFG`, `PRIORITY_CONFIG`, `PRIORITY_LABEL` —
 * mais o canônico dentro do `Badge`. Seis fontes para o mesmo dado, e já
 * discordavam: "médio" era `indigo-400` numa tela, `#3b82f6` noutra,
 * `bg-primary` numa terceira, `info` na quarta e `yellow-400` na quinta.
 *
 * A palavra também divergia: o `Badge` dizia "Alto" e o detalhe do chamado
 * dizia "Alta", no mesmo sistema. A **emenda E17** fixou o feminino no pacote,
 * que concorda com "prioridade"; este módulo é o lado do HelpHS dela.
 *
 * ── As quatro formas de mostrar prioridade, e o que cada uma consome ──
 *
 * | onde | consome |
 * |---|---|
 * | selo (`PriorityBadge`) | `variante` + `rotulo` |
 * | ponto da lista | `ponto` + `rotulo` (ver abaixo) |
 * | gráfico de prioridade | `grafico` |
 * | seletor e histórico | `rotulo` |
 *
 * ── Por que o gráfico de prioridade NÃO usa `--chart-*` ───────────────
 *
 * A paleta `--chart-*` da **E16** é categórica: serve a séries que não têm
 * significado próprio (categorias, produtos, meses). Prioridade **tem**
 * significado, e ele já está pintado na interface inteira — um gráfico de
 * prioridade com cores de categoria diria que "crítico" é uma categoria
 * qualquer, e obrigaria a pessoa a consultar a legenda para algo que o resto do
 * sistema ensina pela cor.
 *
 * ── O ponto, e por que ele precisa do rótulo junto ────────────────────
 *
 * O ponto de 6px era, na lista de chamados, **a única fonte da prioridade**:
 * um `<div>` colorido, sem texto, sem nome acessível. Quem não distingue a cor
 * — ou não a vê — não tinha a informação de forma alguma.
 *
 * Isso tem duas consequências que se resolvem juntas. Enquanto a cor é o único
 * portador, ela precisa de **3:1** (WCAG 1.4.11) — e `--color-warning-500`
 * reprova no tema claro, com **1,96:1** contra a superfície. Com o rótulo em
 * texto ao lado, a cor passa a ser **reforço**, o piso deixa de se aplicar, e a
 * informação existe para todo mundo.
 *
 * Por isso `ponto` nunca deve ser usado sozinho: quem o renderiza põe o
 * `rotulo` junto, visível ou em `sr-only`.
 */

/** As quatro prioridades que o backend usa. Definida AQUI e nao no `Badge`:
 *  este modulo e a fonte, e o selo e um dos consumidores. */
export type TicketPriority = "critical" | "high" | "medium" | "low";

/** Variante do `Badge` — mantida em sincronia com `ui/Badge.tsx`. */
type Variante = "danger" | "warning" | "info" | "muted";

export interface Prioridade {
  /** O texto, no feminino: concorda com "prioridade". Emenda E17. */
  rotulo: string;
  /** Variante do selo. */
  variante: Variante;
  /** Classe de fundo do ponto: a cor cheia 500 da mesma variante. */
  ponto: string;
  /** Preenchimento de série num gráfico DE PRIORIDADE. Não é `--chart-*`. */
  grafico: string;
  /** Ordem de urgência, do mais crítico ao menos. Serve à ordenação. */
  ordem: number;
}

export const PRIORIDADE: Record<TicketPriority, Prioridade> = {
  critical: {
    rotulo: "Crítica",
    variante: "danger",
    ponto: "bg-danger",
    grafico: "var(--color-danger-500)",
    ordem: 0,
  },
  high: {
    rotulo: "Alta",
    variante: "warning",
    ponto: "bg-warning",
    // `--fill-warning`, e NAO `--color-warning-500`: o 500 reprova como
    // preenchimento no tema claro, com 1,96:1 contra a superficie elevada
    // (piso 3:1, WCAG 1.4.11). E o mesmo numero que a E16 registrou, e a mesma
    // causa: amarelo e claro por natureza e degrau fixo nao inverte por tema.
    // O token local resolve como `--border-control` resolve para o neutro.
    grafico: "var(--fill-warning)",
    ordem: 1,
  },
  medium: {
    rotulo: "Média",
    variante: "info",
    ponto: "bg-info",
    grafico: "var(--color-info-500)",
    ordem: 2,
  },
  low: {
    rotulo: "Baixa",
    variante: "muted",
    // `--border-control` e não um degrau fixo: ele **inverte por tema**
    // (slate-500 no claro, slate-400 no escuro). Os degraus fixos falham em um
    // dos dois — slate-400 dá 2,34 no claro e slate-500 dá 2,85 no escuro.
    ponto: "bg-borda-control",
    grafico: "var(--border-control)",
    ordem: 3,
  },
};

/** As quatro, da mais urgente para a menos. */
export const PRIORIDADES = (
  Object.keys(PRIORIDADE) as TicketPriority[]
).sort((a, b) => PRIORIDADE[a].ordem - PRIORIDADE[b].ordem);

/** O rótulo, com recuo para o valor cru quando o backend manda algo novo. */
export function rotuloDePrioridade(p: string): string {
  return PRIORIDADE[p as TicketPriority]?.rotulo ?? p;
}

/**
 * As classes de cada variante, **escritas por extenso**.
 *
 * Por extenso porque o Tailwind gera utilitário varrendo o TEXTO dos arquivos:
 * `"bg-fill-" + variante` some da varredura, a regra não nasce, o elemento fica
 * sem cor, e não há erro nem aviso.
 *
 * Usam os `--fill-*` e não os degraus 500 da rampa. O 500 de `warning` reprova
 * 1,96:1 como preenchimento no tema claro, e a faixa da esquerda do cartão é
 * preenchimento — 4px de cor, sem texto por cima.
 */
export const TOM_PRIORIDADE: Record<Variante, { borda: string; ponto: string }> = {
  danger: { borda: "border-l-fill-danger", ponto: "bg-fill-danger" },
  warning: { borda: "border-l-fill-warning", ponto: "bg-fill-warning" },
  info: { borda: "border-l-fill-info", ponto: "bg-fill-info" },
  muted: { borda: "border-l-borda-control", ponto: "bg-borda-control" },
};

/** A variante do selo, com recuo para o neutro. */
export function varianteDePrioridade(p: string): Variante {
  return PRIORIDADE[p as TicketPriority]?.variante ?? "muted";
}

/**
 * O preenchimento de série, com recuo para o neutro.
 *
 * O recuo é `--border-control` e não uma cor de aviso: prioridade desconhecida
 * é ausência de informação, e pintá-la de vermelho ou âmbar afirmaria algo que
 * não se sabe. O neutro já é medido nas três superfícies dos dois temas.
 */
export function graficoDePrioridade(p: string): string {
  return PRIORIDADE[p as TicketPriority]?.grafico ?? "var(--border-control)";
}
