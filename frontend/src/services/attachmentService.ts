import { api } from "./api";
import { resolveFileUrl } from "../lib/fileUrl";

export interface Attachment {
  id: string;
  ticket_id: string;
  uploaded_by: string;
  /** Nome e papel de quem enviou, lidos do cadastro pelo backend na hora. */
  uploaded_by_name: string | null;
  uploaded_by_role: string | null;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  virus_scanned: boolean;
  virus_clean: boolean;
  created_at: string;
}

export interface AttachmentListResponse {
  items: Attachment[];
  total: number;
}

export async function getAttachments(
  ticketId: string,
): Promise<AttachmentListResponse> {
  const { data } = await api.get<AttachmentListResponse>(
    `/tickets/${ticketId}/attachments`,
  );
  return data;
}

export async function uploadAttachments(
  ticketId: string,
  files: File[],
): Promise<Attachment[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const { data } = await api.post<Attachment[]>(
    `/tickets/${ticketId}/attachments`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

/**
 * Como o anexo aparece no visualizador.
 *
 * O conjunto é o mesmo que `files.py` serve inline (`_INLINE_EXTENSIONS`);
 * tudo fora dele o backend entrega como download, e aqui vira "nenhuma" — o
 * modal mostra a alternativa com o botão Baixar. SVG e HTML ficam de fora nos
 * dois lados de propósito: aceitam script.
 */
export type TipoDePrevia = "imagem" | "pdf" | "texto" | "nenhuma";

const PREVIA_POR_EXTENSAO: Record<string, TipoDePrevia> = {
  png: "imagem",
  jpg: "imagem",
  jpeg: "imagem",
  gif: "imagem",
  webp: "imagem",
  pdf: "pdf",
  txt: "texto",
};

export function tipoDePrevia(filename: string): TipoDePrevia {
  const partes = filename.split(".");
  if (partes.length < 2) return "nenhuma";
  return PREVIA_POR_EXTENSAO[partes.pop()!.toLowerCase()] ?? "nenhuma";
}

/** Formatos que o navegador abre sem baixar (o backend valida o mesmo conjunto). */
export function canPreview(filename: string): boolean {
  return tipoDePrevia(filename) !== "nenhuma";
}

export async function getAttachmentUrl(
  id: string,
  options: { download?: boolean } = {},
): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/attachments/${id}`);
  // A API devolve o caminho; o host vem da configuração do frontend
  const url = resolveFileUrl(data.url);
  return options.download ? `${url}&download=true` : url;
}

/**
 * Baixa um anexo: o link é pedido ao backend NA HORA, e é lá que o acesso ao
 * chamado é conferido. Um caminho só para a lista, o modal e o que vier.
 *
 * Abre em aba nova, como sempre abriu: com `download=true` o servidor responde
 * `attachment` e a aba vira download; se o arquivo tiver sumido do disco, o erro
 * aparece na aba nova e a tela do chamado fica onde estava.
 */
export async function downloadAttachment(id: string): Promise<void> {
  const url = await getAttachmentUrl(id, { download: true });
  window.open(url, "_blank");
}

/** O lote pedido para o ZIP: o link e o que precisa ser avisado antes. */
export interface AttachmentArchive {
  url: string;
  expires_in: number;
  total: number;
  /** Gravados com o antivírus fora do ar. Vão no ZIP; a tela avisa antes. */
  nao_verificados: { id: string; original_name: string }[];
}

/**
 * Pede o ZIP de todos os anexos do chamado.
 *
 * O backend confere o acesso, confere que os arquivos estão em disco, congela
 * os ids num token e devolve o link — quem baixa é o navegador, pelo link, e
 * nada passa pela memória da página.
 */
export async function requestAttachmentsArchive(ticketId: string): Promise<AttachmentArchive> {
  const { data } = await api.post<AttachmentArchive>(
    `/tickets/${ticketId}/attachments/archive`,
  );
  return { ...data, url: resolveFileUrl(data.url) };
}

export async function deleteAttachment(id: string): Promise<void> {
  await api.delete(`/attachments/${id}`);
}
