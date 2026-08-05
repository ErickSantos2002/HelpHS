import { api } from "./api";
import { resolveFileUrl } from "../lib/fileUrl";

export interface Attachment {
  id: string;
  ticket_id: string;
  uploaded_by: string;
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

/** Formatos que o navegador abre sem baixar (o backend valida o mesmo conjunto). */
const VIEWABLE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "pdf", "txt"];

export function canPreview(filename: string): boolean {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  return VIEWABLE_EXTENSIONS.includes(ext);
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

export async function deleteAttachment(id: string): Promise<void> {
  await api.delete(`/attachments/${id}`);
}
