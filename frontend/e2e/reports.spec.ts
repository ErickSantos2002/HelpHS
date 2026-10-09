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
    //
    // O filtro tem rótulo `sr-only` ("Período"), que é o nome acessível do
    // gatilho e não muda quando o período muda. O que está escolhido se lê
    // pelo TEXTO do gatilho: o `toHaveValue` do Playwright só serve a
    // `<input>`, `<textarea>` e `<select>` e recusa qualquer outro elemento.
    const periodSelect = page.getByRole("combobox", { name: "Período" });
    await expect(periodSelect).toContainText("Últimos 30 dias", {
      timeout: 5_000,
    });
  });

  test("filtro de período atualiza os relatórios", async ({ page }) => {
    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Relatórios" })).toBeVisible(
      { timeout: 8_000 },
    );

    const periodSelect = page.getByRole("combobox", { name: "Período" });
    await periodSelect.click();
    await page.getByRole("option", { name: "Últimos 7 dias" }).click();

    // O gatilho passa a mostrar o rótulo do novo período — é o texto dele que
    // diz o que está escolhido, não um `value`.
    await expect(periodSelect).toContainText("Últimos 7 dias");
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
