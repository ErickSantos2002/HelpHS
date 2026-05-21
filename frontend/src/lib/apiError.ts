import type { AxiosError } from "axios";

/**
 * Extrai a mensagem legível de um erro da API.
 * Lê `response.data.detail` (padrão FastAPI) e traduz mensagens técnicas
 * para português amigável. Usa `fallback` se não encontrar nada.
 */
export function getApiError(err: unknown, fallback = "Ocorreu um erro inesperado."): string {
  const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail;

  if (!detail) return fallback;

  // Mapeamento de mensagens técnicas → mensagens amigáveis
  const map: Record<string, string> = {
    "Você precisa se atribuir ao ticket antes de enviar mensagens.":
      "Você precisa se atribuir ao ticket antes de enviar mensagens.",
    "Você precisa estar atribuído ao ticket para concluí-lo.":
      "Você precisa estar atribuído ao ticket para concluí-lo.",
    "Ticket not found": "Ticket não encontrado.",
    "Access denied": "Você não tem permissão para realizar esta ação.",
    "Assignee not found": "Técnico não encontrado.",
    "Only admins can change roles": "Apenas administradores podem alterar o tipo de usuário.",
    "Cannot edit observation on a closed or cancelled ticket":
      "Não é possível editar a observação de um ticket fechado ou cancelado.",
    "User not found": "Usuário não encontrado.",
    "Email already registered": "Este e-mail já está cadastrado.",
    "Invalid credentials": "E-mail ou senha incorretos.",
  };

  return map[detail] ?? detail;
}
