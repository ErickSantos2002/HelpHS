import { api } from "./api";

export interface Product {
  id: string;
  name: string;
  description: string | null;
  version: string | null;
  is_active: boolean;
}

export interface Equipment {
  id: string;
  product_id: string;
  name: string;
  serial_number: string | null;
  model: string | null;
  description: string | null;
  is_active: boolean;
}

export interface ProductListResponse {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
}

export interface EquipmentListResponse {
  items: Equipment[];
  total: number;
  limit: number;
  offset: number;
}

// ── Products ──────────────────────────────────────────────────

export async function getProducts(
  params: {
    search?: string;
    is_active?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<ProductListResponse> {
  const p = new URLSearchParams();
  if (params.search) p.set("search", params.search);
  if (params.is_active !== undefined)
    p.set("is_active", String(params.is_active));
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  const { data } = await api.get<ProductListResponse>(`/products?${p}`);
  return data;
}

export async function createProduct(payload: {
  name: string;
  description?: string;
  version?: string;
}): Promise<Product> {
  const { data } = await api.post<Product>("/products", payload);
  return data;
}

export async function updateProduct(
  id: string,
  payload: {
    name?: string;
    description?: string | null;
    version?: string | null;
  },
): Promise<Product> {
  const { data } = await api.patch<Product>(`/products/${id}`, payload);
  return data;
}

export async function setProductActive(
  id: string,
  is_active: boolean,
): Promise<Product> {
  const { data } = await api.patch<Product>(`/products/${id}`, { is_active });
  return data;
}

// ── Equipments ────────────────────────────────────────────────

export async function getEquipments(
  productId: string,
  params: { is_active?: boolean; limit?: number; offset?: number } = {},
): Promise<EquipmentListResponse> {
  const p = new URLSearchParams();
  if (params.is_active !== undefined)
    p.set("is_active", String(params.is_active));
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  const { data } = await api.get<EquipmentListResponse>(
    `/products/${productId}/equipments?${p}`,
  );
  return data;
}

export async function createEquipment(
  productId: string,
  payload: {
    name: string;
    serial_number?: string;
    model?: string;
    description?: string;
  },
): Promise<Equipment> {
  const { data } = await api.post<Equipment>(
    `/products/${productId}/equipments`,
    payload,
  );
  return data;
}

export async function updateEquipment(
  id: string,
  payload: {
    name?: string;
    serial_number?: string | null;
    model?: string | null;
    description?: string | null;
  },
): Promise<Equipment> {
  const { data } = await api.patch<Equipment>(`/equipments/${id}`, payload);
  return data;
}

export async function setEquipmentActive(
  id: string,
  is_active: boolean,
): Promise<Equipment> {
  const { data } = await api.patch<Equipment>(`/equipments/${id}`, {
    is_active,
  });
  return data;
}
