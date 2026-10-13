/**
 * Anexo enviado, contado na conversa do chamado.
 *
 * O acontecimento NÃO é mensagem de chat, e de propósito. Uma mensagem de
 * sistema gravada em `chat_messages` congelaria o nome de quem enviou no texto
 * (a anonimização da conta não alcançaria) e encostaria em tudo que lê a
 * conversa: primeira resposta do SLA, a Helô, o resumo da IA. Aqui a fonte é o
 * histórico do chamado — o backend grava uma linha `attachment_added` na mesma
 * transação do anexo — e a conversa só intercala essas linhas na hora de
 * desenhar.
 *
 * Quem pode ler o evento é decidido no backend, junto com o chamado: quem vê o
 * chamado vê todos os anexos dele. Nada aqui filtra por papel.
 */

import type { Attachment } from "../services/attachmentService";
import { rotuloDePapel } from "./papel";
import type { TicketHistory } from "../services/ticketService";

/** O `field` que o backend grava (`app/utils/history.py`). */
export const CAMPO_ANEXO_ADICIONADO = "attachment_added";

export interface EventoDeAnexo {
  /** O id da linha do histórico — estável entre leituras, serve de `key`. */
  id: string;
  created_at: string;
  /** Nome de quem enviou, do cadastro vivo. Nulo: o histórico não tem autor. */
  autor: string | null;
  papel: string | null;
  /** Nulo quando o anexo foi excluído depois: o acontecimento continua. */
  anexo: Attachment | null;
}

/**
 * As linhas de anexo do histórico, ligadas ao anexo pelo id.
 *
 * O `new_value` da linha é o id do anexo, e nada mais — o nome do arquivo vem
 * da lista de anexos, que já passou pela autorização do backend.
 */
export function eventosDeAnexo(
  historico: TicketHistory[],
  anexos: Attachment[],
): EventoDeAnexo[] {
  const porId = new Map(anexos.map((a) => [a.id, a]));
  return historico
    .filter((h) => h.field === CAMPO_ANEXO_ADICIONADO)
    .map((h) => ({
      id: h.id,
      created_at: h.created_at,
      autor: h.user_name,
      papel: h.user_role,
      anexo: (h.new_value && porId.get(h.new_value)) || null,
    }));
}

/**
 * "Enviado por Bruno Lima (Técnico) · 09/10/2026, 14:03".
 *
 * Uma frase só para a aba Anexos e para o visualizador: nome e perfil vêm do
 * backend, lidos do cadastro na hora. Sem nome, não inventa autor.
 */
export function autoriaDoAnexo(anexo: Attachment): string {
  const quando = dataHoraDoAnexo(anexo.created_at);
  if (!anexo.uploaded_by_name) return `Enviado em ${quando}`;
  const papel = anexo.uploaded_by_role ? ` (${rotuloDePapel(anexo.uploaded_by_role)})` : "";
  return `Enviado por ${anexo.uploaded_by_name}${papel} · ${quando}`;
}

/** Data e hora como o resto da tela escreve: "09/10/2026, 14:03". */
export function dataHoraDoAnexo(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
