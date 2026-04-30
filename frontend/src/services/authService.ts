import { api } from "./api";
import type { AuthUser } from "../types/auth";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface MeResponse {
  id: string;
  name: string;
  email: string;
  role: AuthUser["role"];
  onboarding_completed: boolean;
}

export async function loginApi(body: LoginRequest): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>("/auth/login", body);
  return data;
}

export async function getMeApi(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/users/me");
  return data;
}

export async function logoutApi(): Promise<void> {
  await api.post("/auth/logout").catch(() => {
    // Best-effort: ignore errors on logout
  });
}
