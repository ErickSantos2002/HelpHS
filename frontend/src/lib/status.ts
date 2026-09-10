/**
 * O status do chamado, numa fonte só.
 *
 * Existia espalhado: o `Badge` tinha rótulo e variante, o quadro kanban da
 * lista tinha um mapa próprio com a paleta CRUA do Tailwind — sky, indigo,
 * amber, violet, emerald, slate, mais seis hexadecimais cravados —, e o rótulo
 * divergia entre eles ("Ag. Técnico" contra "Aguardando técnico").
 *
 * ── Por que dois status compartilham a mesma cor ──────────────────────
 *
 * `awaiting_client` e `awaiting_technical` são os dois `warning`, e isso é da
 * §16, não descuido. Eles são o mesmo estado do ponto de vista de quem olha o
 * quadro — o chamado está parado esperando alguém — e o que os distingue é
 * **quem**, que é informação de texto.
 *
 * O quadro anterior os pintava de âmbar e violeta, o que dava a impressão de
 * dois estados diferentes. E a medição da E18 mostrou que nem daria para
 * mantê-los distintos com rigor: no tema claro, dois degraus de `warning` que
 * passem 3:1 nas três superfícies ficam a **12,2** de ΔE, contra um piso de 20.
 * A cor não consegue carregar essa distinção; o rótulo carrega.
 *
 * ── O que este módulo NÃO faz ─────────────────────────────────────────
 *
 * Não dá cor de **gráfico**. Gráfico de status usa `--chart-*`, pela E18, com
 * tabela fixa — porque sete séries simultâneas não cabem nas rampas
 * semânticas. Aqui é interface: um elemento de cada vez, com o rótulo do lado.
 */

/** Os sete status que o backend usa. */
export type TicketStatus =
  | "open"
  | "in_progress"
  | "awaiting_client"
  | "awaiting_technical"
  | "resolved"
  | "closed"
  | "cancelled";

/** Variante do `Badge` — mantida em sincronia com `ui/Badge.tsx`. */
export type VarianteStatus =
  | "info"
  | "primary"
  | "warning"
  | "success"
  | "muted"
  | "danger";

export interface Status {
  /** O nome por extenso. É o que o selo mostra. */
  rotulo: string;
  /** A forma curta, para a coluna de 268px do quadro. */
  curto: string;
  /** O que o estado significa, para quem não conhece o fluxo. */
  descricao: string;
  variante: VarianteStatus;
  /**
   * A ordem das COLUNAS do quadro, e só dela.
   *
   * **Não é a ordem da tabela da E18**, e a diferença é real: aqui
   * `awaiting_technical` vem antes de `awaiting_client`, porque é a ordem que o
   * quadro sempre teve; a E18 segue o `STATUS` do `Badge.jsx` do pacote, que
   * lista o cliente primeiro.
   *
   * As duas são legítimas e servem a coisas diferentes — uma é leitura de
   * quadro, a outra é contrato compartilhado com o outro produto. Derivar uma
   * da outra faria a cor de um status mudar entre os dois repositórios, que é
   * exatamente o que a tabela fixa existe para impedir.
   *
   * O comentário anterior dizia que esta ordem era "a das colunas E a da
   * tabela da E18". Era falso, e o caso de teste da tabela pegou.
   */
  ordem: number;
  /** Estado final: o chamado não anda mais a partir daqui. */
  terminal: boolean;
}

export const STATUS: Record<TicketStatus, Status> = {
  open: {
    rotulo: "Aberto",
    curto: "Aberto",
    descricao: "Aguardando atendimento",
    variante: "info",
    ordem: 0,
    terminal: false,
  },
  in_progress: {
    rotulo: "Em andamento",
    curto: "Em andamento",
    descricao: "Técnico vinculado",
    variante: "primary",
    ordem: 1,
    terminal: false,
  },
  awaiting_technical: {
    rotulo: "Aguardando técnico",
    curto: "Ag. técnico",
    descricao: "Aguardando resposta técnica",
    variante: "warning",
    ordem: 2,
    terminal: false,
  },
  awaiting_client: {
    rotulo: "Aguardando cliente",
    curto: "Ag. cliente",
    descricao: "Aguardando resposta do cliente",
    variante: "warning",
    ordem: 3,
    terminal: false,
  },
  resolved: {
    rotulo: "Resolvido",
    curto: "Resolvido",
    descricao: "Finalizado com sucesso",
    variante: "success",
    ordem: 4,
    terminal: true,
  },
  closed: {
    rotulo: "Fechado",
    curto: "Fechado",
    descricao: "Encerrado",
    variante: "muted",
    ordem: 5,
    terminal: true,
  },
  cancelled: {
    rotulo: "Cancelado",
    curto: "Cancelado",
    descricao: "Encerrado sem resolução",
    variante: "danger",
    ordem: 6,
    terminal: true,
  },
};

/** Os sete, na ordem do ciclo de vida. */
export const STATUS_ORDEM = (Object.keys(STATUS) as TicketStatus[]).sort(
  (a, b) => STATUS[a].ordem - STATUS[b].ordem,
);

/**
 * As classes de cada variante, **escritas por extenso**.
 *
 * Nada aqui pode ser montado por concatenação: o Tailwind gera utilitário
 * varrendo o texto dos arquivos, e `"bg-tint-" + variante` some da varredura.
 * A regra não nasce, o elemento fica sem fundo, e não há erro nem aviso.
 */
export const TOM_STATUS: Record<
  VarianteStatus,
  { fundo: string; texto: string; ponto: string }
> = {
  info: {
    fundo: "bg-tint-info",
    texto: "text-on-tint-info",
    ponto: "bg-fill-info",
  },
  primary: {
    fundo: "bg-tint-primary",
    texto: "text-on-tint-primary",
    ponto: "bg-primary",
  },
  warning: {
    fundo: "bg-tint-warning",
    texto: "text-on-tint-warning",
    ponto: "bg-fill-warning",
  },
  success: {
    fundo: "bg-tint-success",
    texto: "text-on-tint-success",
    ponto: "bg-fill-success",
  },
  muted: {
    fundo: "bg-tint-neutral",
    texto: "text-on-tint-neutral",
    ponto: "bg-borda-control",
  },
  danger: {
    fundo: "bg-tint-danger",
    texto: "text-on-tint-danger",
    ponto: "bg-fill-danger",
  },
};

/**
 * O slot da paleta de gráfico, por status — a tabela da emenda **E18**.
 *
 * Fixa, e igual nos dois repositórios. Fixa porque as cores deixaram de
 * significar: com `--chart-*`, o sétimo é pervinca no claro e sálvia no escuro,
 * e nenhuma das duas diz "cancelado". Sem uma ordem combinada, "Resolvidos"
 * mudaria de cor entre o painel e o relatório.
 *
 * A ordem é a do `STATUS` do `Badge.jsx` do PACOTE, que é o que a emenda cita.
 * Ela **não** é a mesma do campo `ordem` acima: lá `awaiting_technical` vem
 * antes, porque é a ordem do quadro. Escrita à mão, e não derivada, justamente
 * por isso — e o caso de teste a compara literal.
 *
 * ── Por que gráfico de status NÃO usa a §16 ───────────────────────────
 *
 * Porque não cabe. Medido na E18: escolher dentro das rampas semânticas, com
 * 3:1 nas três superfícies e ΔE ≥ 20 entre todos os pares nas quatro visões,
 * **não tem solução no tema claro** — sete séries param em 12,16 e seis em
 * 15,67, contra um piso de 20. A capacidade do claro é de cinco matizes.
 *
 * O par que trava não são as duas azuis: é `success` × `danger` em protanopia,
 * verde e vermelho, com os dois obrigados a escurecer para passar 3:1 no
 * branco.
 *
 * ── A legenda deixa de ser conveniência ───────────────────────────────
 *
 * Enquanto o status pintava com a cor da §16, quem conhecia o sistema lia
 * "vermelho = cancelado" sem consultar nada. Com `--chart-*` isso acabou:
 * **gráfico de status leva legenda com o nome de cada série, sempre.**
 */
export const SLOT_DE_STATUS: Record<TicketStatus, string> = {
  open: "var(--chart-1)",
  in_progress: "var(--chart-2)",
  awaiting_client: "var(--chart-3)",
  awaiting_technical: "var(--chart-4)",
  resolved: "var(--chart-5)",
  closed: "var(--chart-6)",
  cancelled: "var(--chart-7)",
};

/**
 * O preenchimento de série para um status, com recuo para o neutro.
 *
 * Recuo neutro, e não uma das sete: status desconhecido é ausência de
 * informação, e emprestar o slot de outro faria duas séries diferentes
 * pintarem igual — que é exatamente o que a paleta existe para impedir.
 */
export function slotDeStatus(s: string): string {
  return SLOT_DE_STATUS[s as TicketStatus] ?? "var(--border-control)";
}

/** O rótulo, com recuo para o valor cru quando o backend manda algo novo. */
export function rotuloDeStatus(s: string): string {
  return STATUS[s as TicketStatus]?.rotulo ?? s;
}

/** A variante, com recuo para o neutro. */
export function varianteDeStatus(s: string): VarianteStatus {
  return STATUS[s as TicketStatus]?.variante ?? "muted";
}

/** Se o chamado ainda anda. Desconhecido conta como NÃO terminal. */
export function ehTerminal(s: string): boolean {
  return STATUS[s as TicketStatus]?.terminal ?? false;
}
