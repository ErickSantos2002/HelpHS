import { api } from "./api";

export interface UserSummary {
  id: string;
  name: string;
  email: string;
  role: "admin" | "technician" | "client";
  is_active: boolean;
}

export async function getTechnicians(): Promise<UserSummary[]> {
  const { data } = await api.get<{ items: UserSummary[] }>(
    "/users?role=technician&is_active=true&limit=100",
  );
  return data.items;
}
