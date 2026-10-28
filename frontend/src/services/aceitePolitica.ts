/**
 * O aviso de que falta aceitar a revisão vigente da Política de Privacidade.
 *
 * Com `LGPD_EXIGE_REACEITE` ligado, o backend recusa toda rota autenticada
 * fora da lista da tela de re-aceite com HTTP 428 e `code`
 * "aceite_politica_pendente", e o chat fecha com 4428. Os dois caminhos
 * chegam aqui e viram o MESMO evento, que o `ReaceiteGuard` escuta para
 * trocar a tela pelo aceite — de qualquer página, sem recarregar.
 *
 * O contrato é o `code` (e o 4428), nunca o texto do `detail`.
 */
import { isAxiosError } from "axios";

export const CODIGO_ACEITE_POLITICA_PENDENTE = "aceite_politica_pendente";
export const WS_ACEITE_POLITICA_PENDENTE = 4428;

const EVENTO = "helphs:aceite-politica-pendente";

/** O 428 do aceite, e só ele: outro 428, ou um 401/403/409, não é. */
export function ehAceitePoliticaPendente(erro: unknown): boolean {
  if (!isAxiosError(erro) || erro.response?.status !== 428) return false;
  const corpo = erro.response.data as { code?: unknown } | undefined;
  return corpo?.code === CODIGO_ACEITE_POLITICA_PENDENTE;
}

export function avisaAceitePoliticaPendente(): void {
  window.dispatchEvent(new Event(EVENTO));
}

/** Escuta o aviso; devolve a função que para de escutar. */
export function aoAceitePoliticaPendente(fn: () => void): () => void {
  window.addEventListener(EVENTO, fn);
  return () => window.removeEventListener(EVENTO, fn);
}
