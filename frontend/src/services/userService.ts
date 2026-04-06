import { api } from "./api";

export interface UserSummary {
  id: string;
  name: string;
  email: string;
  role: "admin" | "technician" | "client";
  status: "active" | "inactive" | "suspended" | "anonymized";
  phone: string | null;
  department: string | null;
  avatar_url: string | null;
  last_login: string | null;
  lgpd_consent: boolean;
  lgpd_consent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserListResponse {
  items: UserSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface UserFilters {
  role?: string;
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface UserCreatePayload {
  name: string;
  email: string;
  password: string;
  role: "admin" | "technician" | "client";
  phone?: string;
  department?: string;
  lgpd_consent: boolean;
}

export interface UserUpdatePayload {
  name?: string;
  phone?: string | null;
  department?: string | null;
  role?: "admin" | "technician" | "client";
}

export async function getUsers(
  filters: UserFilters = {},
): Promise<UserListResponse> {
  const params = new URLSearchParams();
  if (filters.role) params.set("role", filters.role);
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined)
    params.set("offset", String(filters.offset));

  const { data } = await api.get<UserListResponse>(
    `/users?${params.toString()}`,
  );
  return data;
}

export async function createUser(
  payload: UserCreatePayload,
): Promise<UserSummary> {
  const { data } = await api.post<UserSummary>("/users", payload);
  return data;
}

export async function updateUser(
  id: string,
  payload: UserUpdatePayload,
): Promise<UserSummary> {
  const { data } = await api.patch<UserSummary>(`/users/${id}`, payload);
  return data;
}

export async function setUserStatus(
  id: string,
  status: "active" | "inactive" | "suspended",
): Promise<UserSummary> {
  const { data } = await api.patch<UserSummary>(`/users/${id}/status`, {
    status,
  });
  return data;
}

export async function anonymizeUser(id: string): Promise<UserSummary> {
  const { data } = await api.post<UserSummary>(`/users/${id}/anonymize`);
  return data;
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/users/${id}`);
}

export async function updateLGPDConsent(
  consent: boolean,
): Promise<UserSummary> {
  const { data } = await api.patch<UserSummary>("/users/me/lgpd-consent", {
    lgpd_consent: consent,
  });
  return data;
}

export async function getTechnicians(): Promise<UserSummary[]> {
  const { data } = await api.get<UserListResponse>(
    "/users?role=technician&status=active&limit=100",
  );
  return data.items;
}
