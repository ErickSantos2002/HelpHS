import { api } from "./api";

export interface GroupResponse {
  id: string;
  name: string;
  description: string | null;
  notes: string | null;
  company_count: number;
  created_at: string;
  updated_at: string;
}

export interface CompanyResponse {
  id: string;
  group_id: string;
  name: string;
  cnpj: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  notes: string | null;
  client_count: number;
  created_at: string;
  updated_at: string;
}

export interface ClientInCompany {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  client_notes: string | null;
}

export interface GroupDetail extends GroupResponse {
  companies: CompanyResponse[];
}

export interface CompanyDetail extends CompanyResponse {
  clients: ClientInCompany[];
}

export interface GroupCreate {
  name: string;
  description?: string;
  notes?: string;
}

export interface GroupUpdate {
  name?: string;
  description?: string;
  notes?: string;
}

export interface CompanyCreate {
  name: string;
  cnpj?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  notes?: string;
}

export interface CompanyUpdate {
  name?: string;
  cnpj?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  notes?: string;
}

// ── Groups ────────────────────────────────────────────────────

export async function listGroups(): Promise<GroupResponse[]> {
  const { data } = await api.get<GroupResponse[]>("/groups");
  return data;
}

export async function getGroup(groupId: string): Promise<GroupDetail> {
  const { data } = await api.get<GroupDetail>(`/groups/${groupId}`);
  return data;
}

export async function createGroup(body: GroupCreate): Promise<GroupResponse> {
  const { data } = await api.post<GroupResponse>("/groups", body);
  return data;
}

export async function updateGroup(groupId: string, body: GroupUpdate): Promise<GroupResponse> {
  const { data } = await api.put<GroupResponse>(`/groups/${groupId}`, body);
  return data;
}

export async function deleteGroup(groupId: string): Promise<void> {
  await api.delete(`/groups/${groupId}`);
}

// ── Companies ─────────────────────────────────────────────────

export async function getCompany(groupId: string, companyId: string): Promise<CompanyDetail> {
  const { data } = await api.get<CompanyDetail>(
    `/groups/${groupId}/companies/${companyId}`,
  );
  return data;
}

export async function createCompany(
  groupId: string,
  body: CompanyCreate,
): Promise<CompanyResponse> {
  const { data } = await api.post<CompanyResponse>(`/groups/${groupId}/companies`, body);
  return data;
}

export async function updateCompany(
  groupId: string,
  companyId: string,
  body: CompanyUpdate,
): Promise<CompanyResponse> {
  const { data } = await api.put<CompanyResponse>(
    `/groups/${groupId}/companies/${companyId}`,
    body,
  );
  return data;
}

export async function deleteCompany(groupId: string, companyId: string): Promise<void> {
  await api.delete(`/groups/${groupId}/companies/${companyId}`);
}

// ── Clients ───────────────────────────────────────────────────

export async function assignClient(
  groupId: string,
  companyId: string,
  userId: string,
): Promise<ClientInCompany> {
  const { data } = await api.post<ClientInCompany>(
    `/groups/${groupId}/companies/${companyId}/clients`,
    { user_id: userId },
  );
  return data;
}

export async function unassignClient(
  groupId: string,
  companyId: string,
  clientId: string,
): Promise<void> {
  await api.delete(
    `/groups/${groupId}/companies/${companyId}/clients/${clientId}`,
  );
}

export async function updateClientNotes(
  groupId: string,
  companyId: string,
  clientId: string,
  notes: string | null,
): Promise<ClientInCompany> {
  const { data } = await api.patch<ClientInCompany>(
    `/groups/${groupId}/companies/${companyId}/clients/${clientId}/notes`,
    { client_notes: notes },
  );
  return data;
}

export async function listUnassignedClients(): Promise<ClientInCompany[]> {
  const { data } = await api.get<ClientInCompany[]>("/clients/unassigned");
  return data;
}
