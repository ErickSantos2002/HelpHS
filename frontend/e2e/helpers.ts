import { Page } from "@playwright/test";

export const CREDENTIALS = {
  admin: {
    email: process.env.ADMIN_EMAIL ?? "admin@helphs.dev",
    password: process.env.ADMIN_PASSWORD ?? "Admin@1234",
  },
  technician: {
    email: process.env.TECH_EMAIL ?? "tech@helphs.dev",
    password: process.env.TECH_PASSWORD ?? "Tech@1234",
  },
  client: {
    email: process.env.CLIENT_EMAIL ?? "client@helphs.dev",
    password: process.env.CLIENT_PASSWORD ?? "Client@1234",
  },
};

export async function login(
  page: Page,
  role: keyof typeof CREDENTIALS = "admin",
) {
  const { email, password } = CREDENTIALS[role];
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.includes("/login"), {
    timeout: 10_000,
  });
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: /Menu do usuário/i }).click();
  await page.getByRole("button", { name: "Sair" }).click();
  await page.waitForURL("**/login");
}
