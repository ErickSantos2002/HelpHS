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
  /**
   * Uma frase dizendo o que cai nesta categoria, para quem abre o chamado.
   *
   * Mora aqui, e não na tela, pelo mesmo motivo do rótulo e do ícone: a
   * descrição é parte do que a categoria É. A `TicketFormPage` mostra a da
   * escolhida no Resumo; qualquer outra tela que precise explicar categoria
   * pega daqui em vez de reescrever.
   *
   * É opcional porque "Outro" não tem descrição — ver o comentário na lista.
   */
  descricao?: string;
}

export const CATEGORIAS: readonly Categoria[] = [
  {
    value: "hardware",
    label: "Hardware",
    icon: "server",
    descricao: "Algum problema físico detectado.",
  },
  {
    value: "software",
    label: "Software",
    icon: "code",
    descricao: "Plataforma com erro, software de registro ou de extração.",
  },
  {
    value: "network",
    label: "Rede",
    icon: "network",
    descricao: "Dificuldade de conexão.",
  },
  { value: "access", label: "Acesso", icon: "key", descricao: "Senha." },
  {
    value: "email",
    label: "E-mail",
    icon: "mail",
    descricao: "Alteração de e-mail.",
  },
  {
    value: "security",
    label: "Segurança",
    icon: "shield",
    descricao: "Sua senha vazou ou está sendo usada por terceiros (LGPD).",
  },
  {
    value: "general",
    label: "Geral",
    icon: "help",
    descricao:
      "Qualquer ocorrência que não se encaixe nas demais, ou quando não sabe dizer.",
  },
  /*
    "Outro" está sem descrição de propósito, e não por esquecimento: ele se
    sobrepõe a "Geral" — as duas são a mesma ideia com dois nomes —, e a decisão
    de tirá-lo do formulário é do operador, com a contagem de chamados já
    abertos nesta categoria na mesa. Enquanto ele existir, escolher "Outro" não
    mostra frase nenhuma no Resumo; escrever um texto agora seria inventar
    diferença entre duas opções que não diferem.
  */
  { value: "other", label: "Outro", icon: "ellipsis" },
] as const;

/** O rótulo, com recuo para o valor cru quando o backend manda algo novo. */
export function rotuloDeCategoria(valor: string): string {
  return CATEGORIAS.find((c) => c.value === valor)?.label ?? valor;
}

/**
 * A descrição, quando existe.
 *
 * Devolve `undefined` para categoria sem descrição ("Outro") e para valor que
 * esta lista não conhece — o mesmo recuo do rótulo, mas sem inventar frase: a
 * tela mostra o nome e cala sobre o significado, em vez de mentir.
 */
export function descricaoDeCategoria(valor: string): string | undefined {
  return CATEGORIAS.find((c) => c.value === valor)?.descricao;
}
