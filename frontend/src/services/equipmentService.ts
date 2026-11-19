import { api } from "./api";

export interface Equipment {
  id: string;
  product_id: string;
  owner_id: string | null;
  name: string;
  serial_number: string | null;
  model: string | null;
  description: string | null;
  location: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /**
   * ECE-01. `true`: o equipamento é de quem está logado. `false`: é da empresa
   * dele, cadastrado por um colega — e aí `owner_id` vem nulo, porque o cliente
   * não fica sabendo quem é o responsável.
   *
   * Quem decide é o backend. Opcional porque uma API anterior ao campo não o
   * manda; ver `ehDoProprioCliente` em `lib/equipamento.ts`.
   */
  is_mine?: boolean | null;
}

export interface EquipmentListResponse {
  items: Equipment[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateEquipmentPayload {
  name: string;
  serial_number?: string | null;
  model?: string | null;
  location?: string | null;
  description?: string | null;
}

export interface CnpjInfo {
  cnpj: string;
  company_name: string;
  trade_name: string;
  city: string;
  state: string;
}

export async function createMyEquipment(
  productId: string,
  payload: CreateEquipmentPayload,
): Promise<Equipment> {
  const { data } = await api.post<Equipment>(
    `/equipment/my?product_id=${productId}`,
    payload,
  );
  return data;
}

export async function getMyEquipment(isActive?: boolean): Promise<Equipment[]> {
  const params = isActive !== undefined ? `?is_active=${isActive}` : "";
  const { data } = await api.get<EquipmentListResponse>(
    `/equipment/my${params}`,
  );
  return data.items;
}

export async function deleteMyEquipment(id: string): Promise<void> {
  await api.delete(`/equipment/my/${id}`);
}

export interface UpdateMyEquipmentPayload {
  name?: string;
  serial_number?: string | null;
  location?: string | null;
  is_active?: boolean;
}

export async function updateMyEquipment(
  id: string,
  payload: UpdateMyEquipmentPayload,
): Promise<Equipment> {
  const { data } = await api.patch<Equipment>(`/equipment/my/${id}`, payload);
  return data;
}

export async function lookupCnpj(cnpj: string): Promise<CnpjInfo> {
  const clean = cnpj.replace(/\D/g, "");
  const { data } = await api.get<CnpjInfo>(`/auth/cnpj/${clean}`);
  return data;
}

export interface CepInfo {
  cep: string;
  address: string;
  neighborhood: string;
  city: string;
  state: string;
}

export async function lookupCep(cep: string): Promise<CepInfo> {
  const clean = cep.replace(/\D/g, "");
  const { data } = await api.get<CepInfo>(`/auth/cep/${clean}`);
  return data;
}
