import { api } from "./api";

export interface Tag {
  id: string;
  name: string;
  color: string;
  created_by: string | null;
  created_at: string;
}

export interface TagListResponse {
  items: Tag[];
  total: number;
}

export async function getTags(): Promise<Tag[]> {
  const res = await api.get<TagListResponse>("/tags");
  return res.data.items;
}

export async function createTag(data: {
  name: string;
  color: string;
}): Promise<Tag> {
  const res = await api.post<Tag>("/tags", data);
  return res.data;
}

export async function updateTag(
  id: string,
  data: { name?: string; color?: string },
): Promise<Tag> {
  const res = await api.patch<Tag>(`/tags/${id}`, data);
  return res.data;
}

export async function deleteTag(id: string): Promise<void> {
  await api.delete(`/tags/${id}`);
}

export async function setTicketTags(
  ticketId: string,
  tagIds: string[],
): Promise<Tag[]> {
  const res = await api.put<Tag[]>(`/tickets/${ticketId}/tags`, {
    tag_ids: tagIds,
  });
  return res.data;
}
