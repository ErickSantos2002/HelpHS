import { toast } from "sonner";
import { getApiErrorParts } from "./apiError";

/**
 * Mostra o erro da API em duas linhas: o título diz qual ação falhou e a
 * descrição explica o motivo devolvido pelo servidor.
 *
 *   toastApiError(err, "Não foi possível atribuir o ticket.");
 *   → "Não foi possível atribuir o ticket."
 *     "Este ticket está fechado e não pode ser reatribuído."
 */
export function toastApiError(err: unknown, fallback: string): void {
  const { title, description } = getApiErrorParts(err, fallback);
  toast.error(title, description ? { description } : undefined);
}
