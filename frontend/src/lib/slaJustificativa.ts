import type { AxiosError } from "axios";

/**
 * Justificativa de SLA violado (`105878d`): o backend recusa com 422 resolver
 * chamado fora do prazo sem `sla_breach_justification`.
 *
 * O front pede o motivo só quando o SERVIDOR tem certeza de que ele é exigido:
 * marca de violação ligada — que ele sempre respeita — ou o próprio 422. Prever
 * pela data foi recusado: o front não recebe a pausa acumulada
 * (`sla_total_paused_ms`), então acharia vencido o que não está, e o relatório
 * de SLA violado filtra pela PRESENÇA da justificativa — um falso positivo põe
 * no relatório um chamado que não violou nada. Desenho em
 * `docs/superpowers/specs/2026-09-11-justificativa-de-sla-na-tela-design.md`.
 */

/** O nome do campo na API. É por ele que o 422 da justificativa se reconhece. */
export const CAMPO_JUSTIFICATIVA = "sla_breach_justification";

/** O `max_length` dos dois schemas de entrada do backend (`schemas/ticket.py`). */
export const LIMITE_JUSTIFICATIVA = 2000;

// Os nomes que o backend dá aos prazos, na ordem em que ele os junta.
const PRAZO_RESPOSTA = "o de primeira resposta";
const PRAZO_RESOLUCAO = "o de resolução";

/** Os prazos que as marcas de violação do chamado dão como estourados. */
export function prazosPelasMarcas(marcas: {
  sla_response_breach?: boolean | null;
  sla_resolve_breach?: boolean | null;
}): string[] {
  const prazos: string[] = [];
  if (marcas.sla_response_breach) prazos.push(PRAZO_RESPOSTA);
  if (marcas.sla_resolve_breach) prazos.push(PRAZO_RESOLUCAO);
  return prazos;
}

/**
 * `null` quando o erro NÃO é o 422 da justificativa. Quando é, os prazos que o
 * servidor disse que passaram — lista vazia se ele não disse quais, e o campo
 * continua exigido do mesmo jeito.
 *
 * O 422 de validação (texto acima do limite) vem com `detail` em lista e não
 * entra aqui: não é pedido de justificativa, é a justificativa passando da
 * conta, e segue para o toast.
 */
export function prazosDoErro(err: unknown): string[] | null {
  const resposta = (err as AxiosError<{ detail?: unknown }> | undefined)?.response;
  const detail = resposta?.data?.detail;
  if (resposta?.status !== 422 || typeof detail !== "string") return null;
  if (!detail.includes(CAMPO_JUSTIFICATIVA)) return null;

  const trecho = detail.match(/passou do prazo \(([^)]*)\)/)?.[1];
  if (!trecho) return [];
  return trecho
    .split(" e ")
    .map((prazo) => prazo.trim())
    .filter(Boolean);
}

/** A frase do aviso acima do campo. Sem saber qual prazo, não inventa um. */
export function avisoDePrazo(prazos: string[]): string {
  const quais = prazos.length > 0 ? ` (${prazos.join(" e ")})` : "";
  return `Este chamado passou do prazo${quais}, e o motivo do atraso é obrigatório.`;
}
