import { api } from "./api";

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

export async function getAttachmentUrl(id: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/attachments/${id}`);
  return data.url;
}

export async function deleteAttachment(id: string): Promise<void> {
  await api.delete(`/attachments/${id}`);
}
