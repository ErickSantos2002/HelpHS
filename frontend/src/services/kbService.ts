import { api } from "./api";

export type KBArticleStatus = "draft" | "published" | "archived";

export interface KBArticle {
  id: string;
  title: string;
  content: string;
  slug: string;
  category: string;
  tags: string[];
  status: KBArticleStatus;
  author_id: string;
  author_name: string;
  view_count: number;
  helpful: number;
  not_helpful: number;
  created_at: string;
  updated_at: string;
}

export interface KBArticleListResponse {
  items: KBArticle[];
  total: number;
  limit: number;
  offset: number;
}

export interface KBArticleFilters {
  search?: string;
  category?: string;
  status?: KBArticleStatus;
  offset?: number;
  limit?: number;
}

export interface KBArticleCreatePayload {
  title: string;
  content: string;
  category: string;
  tags: string[];
  status: KBArticleStatus;
}

export interface KBArticleUpdatePayload {
  title?: string;
  content?: string;
  category?: string;
  tags?: string[];
  status?: KBArticleStatus;
}

export async function getKBArticles(
  filters: KBArticleFilters = {},
): Promise<KBArticleListResponse> {
  const p = new URLSearchParams();
  if (filters.search) p.set("search", filters.search);
  if (filters.category) p.set("category", filters.category);
  if (filters.status) p.set("status", filters.status);
  if (filters.offset !== undefined) p.set("offset", String(filters.offset));
  if (filters.limit !== undefined) p.set("limit", String(filters.limit));
  const { data } = await api.get<KBArticleListResponse>(`/kb/articles?${p}`);
  return data;
}

export async function getKBArticle(id: string): Promise<KBArticle> {
  const { data } = await api.get<KBArticle>(`/kb/articles/${id}`);
  return data;
}

export async function createKBArticle(
  payload: KBArticleCreatePayload,
): Promise<KBArticle> {
  const { data } = await api.post<KBArticle>("/kb/articles", payload);
  return data;
}

export async function updateKBArticle(
  id: string,
  payload: KBArticleUpdatePayload,
): Promise<KBArticle> {
  const { data } = await api.patch<KBArticle>(`/kb/articles/${id}`, payload);
  return data;
}

export async function deleteKBArticle(id: string): Promise<void> {
  await api.delete(`/kb/articles/${id}`);
}

export async function submitKBFeedback(
  id: string,
  helpful: boolean,
): Promise<void> {
  await api.post(`/kb/articles/${id}/feedback`, { helpful });
}

export async function suggestArticlesForTicket(
  ticketId: string,
  limit = 5,
): Promise<KBArticle[]> {
  const { data } = await api.get<KBArticleListResponse>(
    `/kb/articles/suggestions?ticket_id=${ticketId}&limit=${limit}`,
  );
  return data.items;
}
