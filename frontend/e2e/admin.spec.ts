import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Admin — páginas restritas", () => {
  test("admin acessa /users", async ({ page }) => {
    await login(page, "admin");
    await page.goto("/users");
    await expect(page.getByRole("heading", { name: /usuários/i })).toBeVisible({
      timeout: 8_000,
    });
  });

  test("admin acessa /sla-config", async ({ page }) => {
    await login(page, "admin");
    await page.goto("/sla-config");
    await expect(page.getByRole("heading", { name: /SLA/i })).toBeVisible({
      timeout: 8_000,
    });
  });

  test("admin acessa /audit-logs", async ({ page }) => {
    await login(page, "admin");
    await page.goto("/audit-logs");
    await expect(
      page.getByRole("heading", { name: /logs de auditoria/i }),
    ).toBeVisible({ timeout: 8_000 });
  });

  test("admin acessa /reports", async ({ page }) => {
    await login(page, "admin");
    await page.goto("/reports");
    await expect(
      page.getByRole("heading", { name: /relatórios/i }),
    ).toBeVisible({ timeout: 8_000 });
  });

  test("cliente é redirecionado de /users para /403", async ({ page }) => {
    await login(page, "client");
    await page.goto("/users");
    await expect(page).toHaveURL(/\/403|\/login/, { timeout: 8_000 });
  });
});
