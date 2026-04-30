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

export async function getMyEquipment(): Promise<Equipment[]> {
  const { data } = await api.get<EquipmentListResponse>("/equipment/my");
  return data.items;
}

export async function lookupCnpj(cnpj: string): Promise<CnpjInfo> {
  const clean = cnpj.replace(/\D/g, "");
  const { data } = await api.get<CnpjInfo>(`/auth/cnpj/${clean}`);
  return data;
}
