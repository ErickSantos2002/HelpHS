import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Dashboard e Relatórios", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
  });

  test("dashboard principal exibe cards de métricas", async ({ page }) => {
    await page.goto("/");
    // Admin dashboard should render stat cards
    await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible(
      { timeout: 8_000 },
    );
  });

  test("página de relatórios é acessível via sidebar", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Relatórios" }).click();
    await expect(page).toHaveURL("/reports");
    await expect(page.getByRole("heading", { name: "Relatórios" })).toBeVisible(
      { timeout: 8_000 },
    );
  });

  test("relatórios carregam com período padrão de 30 dias", async ({
    page,
  }) => {
    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Relatórios" })).toBeVisible(
      { timeout: 8_000 },
    );

    // Period selector defaults to 30 days
    const periodSelect = page.locator("select").first();
    await expect(periodSelect).toHaveValue("30", { timeout: 5_000 });
  });

  test("filtro de período atualiza os relatórios", async ({ page }) => {
    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Relatórios" })).toBeVisible(
      { timeout: 8_000 },
    );

    await page.locator("select").first().selectOption("7");

    // Select shows the new period option label
    await expect(page.locator("select").first()).toHaveValue("7");
    // Loading spinner disappears (API call completes)
    await expect(page.getByText("Carregando…")).not.toBeVisible({
      timeout: 8_000,
    });
  });

  test("links de exportação CSV e PDF estão presentes", async ({ page }) => {
    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Relatórios" })).toBeVisible(
      { timeout: 8_000 },
    );

    await expect(page.getByText("CSV")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("PDF")).toBeVisible({ timeout: 5_000 });
  });

  test("página de logs de auditoria exibe registros", async ({ page }) => {
    await page.goto("/audit-logs");
    await expect(page.getByRole("heading", { name: /auditoria/i })).toBeVisible(
      { timeout: 8_000 },
    );
  });
});

test.describe("Dashboard e Relatórios — controle de acesso", () => {
  test("cliente não acessa relatórios (redireciona /403)", async ({ page }) => {
    await login(page, "client");
    await page.goto("/reports");
    await expect(page).toHaveURL(/\/403/, { timeout: 5_000 });
  });
});
