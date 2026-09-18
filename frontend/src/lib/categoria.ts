import type { IconName } from "../components/ui/Icon";

/**
 * A categoria do chamado, numa fonte só.
 *
 * Existia em **três** cópias: `TicketFormPage` (com os ícones),
 * `TicketDetailPage` e `ReportsPage`. As três diziam a mesma coisa hoje — e é
 * exatamente por isso que valia unificar antes de divergirem, que foi o que
 * aconteceu com prioridade em dez mapas e com status em três.
 *
 * ── Categoria NÃO tem cor semântica ───────────────────────────────────
 *
 * Ao contrário de status e prioridade, categoria não significa nada em si:
 * "Hardware" não é melhor nem pior que "Rede". É o caso puro de série
 * categórica, e num gráfico ela usa `--chart-*` — a paleta que a E16-b mediu
 * justamente para séries sem significado próprio.
 *
 * Por isso aqui não há campo de cor. Quem precisar de cor de série pega o slot
 * pela posição na lista, e a legenda carrega o nome.
 */
export interface Categoria {
  value: string;
  label: string;
  /** Desenho, não significado: o rótulo é que informa. */
  icon: IconName;
}

export const CATEGORIAS: readonly Categoria[] = [
  { value: "hardware", label: "Hardware", icon: "server" },
  { value: "software", label: "Software", icon: "code" },
  { value: "network", label: "Rede", icon: "network" },
  { value: "access", label: "Acesso", icon: "key" },
  { value: "email", label: "E-mail", icon: "mail" },
  { value: "security", label: "Segurança", icon: "shield" },
  { value: "general", label: "Geral", icon: "help" },
  { value: "other", label: "Outro", icon: "ellipsis" },
] as const;

/** O rótulo, com recuo para o valor cru quando o backend manda algo novo. */
export function rotuloDeCategoria(valor: string): string {
  return CATEGORIAS.find((c) => c.value === valor)?.label ?? valor;
}
