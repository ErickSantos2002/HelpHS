import { test, expect } from "@playwright/test";
import { login, logout, CREDENTIALS } from "./helpers";

test.describe("Autenticação", () => {
  test("redireciona para /login quando não autenticado", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("exibe erro com credenciais inválidas", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("E-mail").fill("wrong@example.com");
    await page.getByLabel("Senha").fill("wrongpassword");
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByText(/E-mail ou senha incorretos/i)).toBeVisible({
      timeout: 8_000,
    });
  });

  test("login admin com sucesso e exibe dashboard", async ({ page }) => {
    await login(page, "admin");
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible(
      { timeout: 8_000 },
    );
  });

  test("logout redireciona para /login", async ({ page }) => {
    await login(page, "admin");
    await logout(page);
    await expect(page).toHaveURL(/\/login/);
  });

  test("após login não acessa /login novamente (redireciona para /)", async ({
    page,
  }) => {
    await login(page, "admin");
    await page.goto("/login");
    await expect(page).toHaveURL("/");
  });
});
