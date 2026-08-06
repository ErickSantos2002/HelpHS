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
  avatar_url?: string | null;
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

// ── Confirmação de e-mail e recuperação de senha ──────────────

interface MessageResponse {
  message: string;
}

/** Confirma o cadastro a partir do link recebido por e-mail. */
export async function verifyEmailApi(token: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/verify-email", { token });
  return data.message;
}

/** Reenvia o link de confirmação. */
export async function resendVerificationApi(email: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/resend-verification", { email });
  return data.message;
}

/**
 * Pede o link de redefinição de senha.
 *
 * A resposta é sempre a mesma, mesmo para e-mail que não existe — é assim de
 * propósito, para não revelar quem tem conta no sistema.
 */
export async function forgotPasswordApi(email: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/forgot-password", { email });
  return data.message;
}

/** Grava a nova senha usando o link recebido por e-mail. */
export async function resetPasswordApi(token: string, password: string): Promise<string> {
  const { data } = await api.post<MessageResponse>("/auth/reset-password", { token, password });
  return data.message;
}
