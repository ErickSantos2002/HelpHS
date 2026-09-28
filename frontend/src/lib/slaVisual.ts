/**
 * A cor da barra de SLA — decidida pelo limiar CONFIGURADO, não por números
 * fixos no código.
 *
 * ── O que isto conserta ───────────────────────────────────────────────
 *
 * O `TicketListPage` decidia cor com `pct >= 80` e `pct >= 60` escritos aqui
 * dentro, enquanto `sla_configs.warning_threshold` — configurável POR
 * PRIORIDADE, editável na tela de SLA, com default 80 — não era lido por
 * caminho de produção nenhum.
 *
 * A Fase 2A fez o aviso por e-mail respeitar o campo. Sem esta fase, um
 * administrador que baixasse o limiar do nível crítico para 60 receberia
 * e-mail em 60% e veria a barra ficar vermelha só em 80%: a tela discordando
 * do aviso que a equipe acabou de receber, sem nada explicando por quê.
 *
 * ── A régua ───────────────────────────────────────────────────────────
 *
 *     vermelho  pct >= limiar
 *     âmbar     pct >= limiar * 0,75  e  pct < limiar
 *     verde     abaixo disso
 *     vencido   sempre vermelho
 *
 * Com o default de 80 ela reproduz **exatamente** o visual anterior — âmbar em
 * 60, vermelho em 80 —, e é por isso que a fração é 0,75 e não outra: ela foi
 * escolhida para que ligar a configuração não mudasse nada para quem não a
 * configurou.
 *
 * ── O que NÃO mora aqui ───────────────────────────────────────────────
 *
 * O percentual. Quem o calcula é o backend, em minutos ÚTEIS
 * (`sla_resolve_total_min` e `sla_resolve_restante_min`), com a mesma função
 * que o aviso de SLA consome. Recalcular aqui criaria a terceira régua — e a
 * segunda já era o problema.
 */

/** O default da coluna `sla_configs.warning_threshold`. */
export const LIMIAR_PADRAO = 80;

/** A fração do limiar em que a barra começa a avisar. */
const FRACAO_DE_ATENCAO = 0.75;

export type EstadoVisualDoSla = "verde" | "ambar" | "vermelho";

/**
 * O ponto em que a barra sai do verde.
 *
 * **Não arredonda.** Com limiar 70 o valor é 52,5, e arredondar para 53
 * pintaria de verde um chamado que já devia estar âmbar em 52,6. Arredondar é
 * coisa de apresentação, não de decisão.
 */
export function limiarDeAtencao(limiar: number): number {
  return limiar * FRACAO_DE_ATENCAO;
}

/**
 * A cor da barra para este chamado.
 *
 * `limiar` nulo ou ausente cai no {@link LIMIAR_PADRAO}: acontece em chamado
 * sem prioridade — que nasce assim, esperando triagem — e quando não há
 * `SLAConfig` ativa para o nível. O fallback é o default da COLUNA, e não uma
 * escolha nova, para que o chamado sem configuração seja pintado como sempre
 * foi. Verde esconderia urgência; vermelho gritaria sem motivo.
 *
 * Valor fora do domínio (zero, negativo) também cai no default. O banco tem
 * `CHECK (warning_threshold BETWEEN 1 AND 100)`, mas a tela não pode depender
 * dele para não transformar um dado ruim numa página inteira de barras
 * vermelhas.
 */
export function getSlaVisualState(
  pct: number,
  limiar: number | null | undefined,
  vencido: boolean,
): EstadoVisualDoSla {
  if (vencido) return "vermelho";

  const alerta = limiar != null && limiar > 0 ? limiar : LIMIAR_PADRAO;
  if (pct >= alerta) return "vermelho";
  if (pct >= limiarDeAtencao(alerta)) return "ambar";
  return "verde";
}
