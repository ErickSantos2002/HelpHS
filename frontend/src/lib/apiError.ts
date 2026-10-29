import type { AxiosError } from "axios";

import { plural } from "./utils";

/**
 * Traduz o erro da API numa mensagem que o usuário entenda.
 *
 * Cobre os formatos que o backend devolve:
 *   - `detail` em string (caso comum do FastAPI)
 *   - `detail` em lista: o 422 de validação, `[{field, message}]`
 *     (backend/app/core/exceptions.py). `{loc, msg}`, o formato cru do
 *     FastAPI, segue aceito por compatibilidade
 *   - resposta sem corpo útil (usa uma mensagem por status HTTP)
 *   - nenhuma resposta (rede caiu, servidor fora do ar, timeout)
 *
 * O resultado é SEMPRE texto: uma tela que desenhasse `detail` cru recebia uma
 * lista no 422 e derrubava o React (F1-B-02). Quem mostra erro da API usa
 * `getApiError`, nunca `response.data.detail` direto.
 */

/** Item do 422: `message` é o contrato; `msg` é o formato antigo/cru. */
interface ValidationItem {
  field?: unknown;
  message?: unknown;
  loc?: unknown;
  msg?: unknown;
}

type ApiErrorBody = { detail?: unknown };

const STATUS_FALLBACKS: Record<number, string> = {
  400: "Os dados enviados não são válidos. Revise o formulário e tente de novo.",
  401: "Sua sessão expirou. Entre novamente para continuar.",
  403: "Você não tem permissão para realizar esta ação.",
  404: "O item que você tentou acessar não foi encontrado. Ele pode ter sido excluído.",
  409: "Esta ação conflita com o estado atual do registro. Atualize a página e tente de novo.",
  413: "O arquivo enviado é grande demais.",
  422: "Alguns campos não foram preenchidos corretamente.",
  429: "Muitas tentativas em pouco tempo. Aguarde alguns instantes e tente de novo.",
  500: "Erro interno no servidor. Tente novamente em instantes.",
  502: "O servidor está indisponível no momento. Tente novamente em instantes.",
  503: "O servidor está indisponível no momento. Tente novamente em instantes.",
  504: "O servidor demorou demais para responder. Tente novamente em instantes.",
};

/** Mensagens técnicas que ainda chegam em inglês de alguns endpoints. */
const TRANSLATIONS: Record<string, string> = {
  "Ticket not found": "Ticket não encontrado. Ele pode ter sido excluído.",
  "Access denied": "Você não tem permissão para realizar esta ação.",
  "Assignee not found": "O técnico selecionado não existe mais no sistema.",
  "User not found": "Usuário não encontrado.",
  "Article not found": "Artigo não encontrado.",
  // Também é o que o cliente recebe ao tentar equipamento de outro dono: a
  // recusa sai como 404 indistinguível do id inexistente, de propósito.
  "Equipment not found": "Equipamento não encontrado. Ele pode ter sido excluído.",
  // Mesma história para anexo: pedir o anexo de um chamado que não é seu
  // responde igual a pedir um anexo que não existe.
  "Attachment not found": "Anexo não encontrado. Ele pode ter sido excluído.",
  "Comment not found": "Comentário não encontrado.",
  "Event not found": "Evento não encontrado.",
  "Notification not found": "Notificação não encontrada.",
  "Tag not found": "Etiqueta não encontrada.",
  "Tag name already exists": "Já existe uma etiqueta com esse nome.",
  "Product name already exists": "Já existe um produto com esse nome.",
  "Serial number already in use": "Este número de série já está em uso.",
  "Email already registered": "Este e-mail já está cadastrado.",
  "Invalid credentials": "E-mail ou senha incorretos.",
  "User account is inactive": "Esta conta está inativa. Fale com um administrador.",
  "Only admins can change roles": "Apenas administradores podem alterar o tipo de usuário.",
  "Not your equipment": "Este equipamento não está vinculado ao seu cadastro.",
  "Cannot edit observation on a closed or cancelled ticket":
    "Não é possível editar a observação de um ticket fechado ou cancelado.",
};

/** O texto de um item do 422, ou `null` se ele não trouxer texto. */
function textoDoItem(item: unknown): string | null {
  if (typeof item === "string") return item.trim() || null;
  if (!item || typeof item !== "object" || Array.isArray(item)) return null;
  const { message, msg } = item as ValidationItem;
  for (const candidato of [message, msg]) {
    if (typeof candidato === "string" && candidato.trim()) return candidato.trim();
  }
  return null;
}

/**
 * Texto que é diagnóstico do servidor, não mensagem para a pessoa: o backend
 * não manda isso hoje, mas um traceback vazado não pode chegar à tela.
 */
function pareceInterno(texto: string): boolean {
  return texto.includes("Traceback (most recent call last)");
}

function describeError(err: unknown): string | null {
  const axiosErr = err as AxiosError<ApiErrorBody>;

  // Pedido saiu mas não voltou resposta: rede, DNS, servidor fora do ar ou timeout
  if (axiosErr?.request && !axiosErr?.response) {
    return "Não foi possível falar com o servidor. Verifique sua conexão e tente de novo.";
  }

  // 429 com Retry-After: o backend calcula o tempo real da janela do rate
  // limit — quando ele vem, os minutos exatos valem mais que o detail vago.
  // Sem o header (storage indisponível, por exemplo), o fluxo normal segue.
  if (axiosErr?.response?.status === 429) {
    const segundos = getRetryAfterSeconds(err);
    if (segundos !== null) {
      const minutos = Math.ceil(segundos / 60);
      return `Muitas tentativas. Aguarde ${minutos} ${plural(minutos, "minuto", "minutos")} e tente novamente.`;
    }
  }

  const data = axiosErr?.response?.data;
  const detail = data && typeof data === "object" ? data.detail : undefined;

  if (typeof detail === "string" && detail.trim()) {
    const clean = detail.trim();
    if (!pareceInterno(clean)) return TRANSLATIONS[clean] ?? clean;
  }

  if (Array.isArray(detail)) {
    // Sem repetir: três campos obrigatórios não viram "Campo obrigatório" três vezes
    const messages = [...new Set(detail.map(textoDoItem).filter((m): m is string => m !== null))];
    if (messages.length > 0) return messages.join(" ");
  } else if (detail && typeof detail === "object") {
    const message = textoDoItem(detail);
    if (message) return message;
  }

  const status = axiosErr?.response?.status;
  if (status && STATUS_FALLBACKS[status]) return STATUS_FALLBACKS[status];

  return null;
}

/**
 * Segundos do header Retry-After, quando o servidor informou um valor
 * utilizável. É a fonte única do tempo de bloqueio no front — o relógio da
 * tela de login conta a partir daqui.
 */
export function getRetryAfterSeconds(err: unknown): number | null {
  const axiosErr = err as AxiosError;
  const bruto = axiosErr?.response?.headers?.["retry-after"];
  const segundos = Number(bruto);
  return Number.isFinite(segundos) && segundos > 0 ? Math.ceil(segundos) : null;
}

/** Mensagem única e legível para o erro da API. */
export function getApiError(err: unknown, fallback = "Ocorreu um erro inesperado."): string {
  return describeError(err) ?? fallback;
}

/**
 * Divide o erro em duas partes para o toast: o título diz qual ação falhou e a
 * descrição explica o motivo. Sem motivo conhecido, devolve só o título.
 */
export function getApiErrorParts(
  err: unknown,
  fallback = "Ocorreu um erro inesperado.",
): { title: string; description?: string } {
  const description = describeError(err);
  return description ? { title: fallback, description } : { title: fallback };
}
