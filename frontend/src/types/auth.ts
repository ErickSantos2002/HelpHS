export type UserRole = "admin" | "technician" | "client";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
}
