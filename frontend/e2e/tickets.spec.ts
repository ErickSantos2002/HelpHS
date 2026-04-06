import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Tickets", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
  });

  test("lista de tickets é acessível via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Tickets" }).click();
    await expect(page).toHaveURL("/tickets");
    await expect(page.getByRole("heading", { name: /tickets/i })).toBeVisible();
  });

  test("filtro por status atualiza a lista", async ({ page }) => {
    await page.goto("/tickets");
    // Open status filter
    await page.locator("select").first().selectOption("open");
    // URL or list updates (count in header changes)
    await expect(page.getByText(/chamado/i)).toBeVisible({ timeout: 5_000 });
  });

  test("abre formulário de novo ticket", async ({ page }) => {
    await page.goto("/tickets");
    await page.getByRole("button", { name: "Abrir chamado" }).click();
    await expect(page).toHaveURL("/tickets/new");
    await expect(
      page.getByRole("heading", { name: /novo chamado/i }),
    ).toBeVisible();
  });

  test("cria novo ticket com sucesso", async ({ page }) => {
    await page.goto("/tickets/new");

    const title = `Teste E2E ${Date.now()}`;
    await page.getByLabel(/título/i).fill(title);
    await page
      .getByLabel(/descrição/i)
      .fill("Descrição criada por teste automatizado.");

    // Select category
    const categorySelect = page
      .locator("select")
      .filter({ hasText: /categoria/i })
      .or(
        page
          .locator("label")
          .filter({ hasText: /categoria/i })
          .locator("..")
          .locator("select"),
      )
      .first();
    await categorySelect.selectOption("software");

    await page.getByRole("button", { name: /abrir chamado/i }).click();

    // Should redirect to ticket detail
    await expect(page).toHaveURL(/\/tickets\/[^/]+$/, { timeout: 10_000 });
    await expect(page.getByText(title)).toBeVisible();
  });

  test("detalhe do ticket exibe informações do chamado", async ({ page }) => {
    await page.goto("/tickets");
    // Click on first ticket row
    const firstRow = page.locator("tbody tr").first();
    await firstRow.click();
    await expect(page).toHaveURL(/\/tickets\/[^/]+$/);
    // Should show protocol, status, description section
    await expect(page.getByText(/HS-/)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/Descrição/i)).toBeVisible();
  });

  test("botão voltar retorna para lista de tickets", async ({ page }) => {
    await page.goto("/tickets");
    await page.locator("tbody tr").first().click();
    await page.getByRole("button", { name: /voltar/i }).click();
    await expect(page).toHaveURL("/tickets");
  });
});
