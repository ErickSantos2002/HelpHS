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
  company_name: string | null;
  cnpj: string | null;
  company_city: string | null;
  company_state: string | null;
  onboarding_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface OnboardingPayload {
  company_name: string;
  cnpj: string | null;
  company_city: string | null;
  company_state: string | null;
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
  const { data } = await api.get<UserListResponse>("/users/technicians");
  return data.items;
}

export async function getMe(): Promise<UserSummary> {
  const { data } = await api.get<UserSummary>("/users/me");
  return data;
}

export async function updateMe(
  payload: Pick<UserUpdatePayload, "name" | "phone" | "department">,
): Promise<UserSummary> {
  const { data } = await api.patch<UserSummary>("/users/me", payload);
  return data;
}

export async function completeOnboarding(
  payload: OnboardingPayload,
): Promise<UserSummary> {
  const { data } = await api.patch<UserSummary>(
    "/users/me/onboarding",
    payload,
  );
  return data;
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await api.post("/users/me/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}
