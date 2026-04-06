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

export async function getProducts(): Promise<Product[]> {
  const { data } = await api.get<{ items: Product[] }>(
    "/products?is_active=true&limit=100",
  );
  return data.items;
}

export async function getEquipments(productId: string): Promise<Equipment[]> {
  const { data } = await api.get<{ items: Equipment[] }>(
    `/products/${productId}/equipments?is_active=true&limit=100`,
  );
  return data.items;
}
