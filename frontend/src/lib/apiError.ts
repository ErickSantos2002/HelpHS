import type { AxiosError } from "axios";

/**
 * Traduz o erro da API numa mensagem que o usuário entenda.
 *
 * Cobre os quatro formatos que o backend devolve:
 *   - `detail` em string (caso comum do FastAPI)
 *   - `detail` em lista (erro de validação — sem tratamento viraria "[object Object]")
 *   - resposta sem corpo útil (usa uma mensagem por status HTTP)
 *   - nenhuma resposta (rede caiu, servidor fora do ar, timeout)
 */

interface ValidationItem {
  loc?: (string | number)[];
  msg?: string;
}

type ApiErrorBody = { detail?: string | ValidationItem[] };

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

function describeError(err: unknown): string | null {
  const axiosErr = err as AxiosError<ApiErrorBody>;

  // Pedido saiu mas não voltou resposta: rede, DNS, servidor fora do ar ou timeout
  if (axiosErr?.request && !axiosErr?.response) {
    return "Não foi possível falar com o servidor. Verifique sua conexão e tente de novo.";
  }

  const detail = axiosErr?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    const clean = detail.trim();
    return TRANSLATIONS[clean] ?? clean;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail
      .map((item) => item?.msg?.trim())
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) return messages.join(" ");
  }

  const status = axiosErr?.response?.status;
  if (status && STATUS_FALLBACKS[status]) return STATUS_FALLBACKS[status];

  return null;
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
