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
    await page.locator("select").first().selectOption("open");
    // The count subtitle updates with the result
    await expect(page.getByText(/chamados? encontrados?/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("abre formulário de novo ticket", async ({ page }) => {
    await page.goto("/tickets");
    await page.getByRole("button", { name: "Abrir chamado" }).click();
    await expect(page).toHaveURL("/tickets/new");
    // Heading is "Abrir chamado" on the form page
    await expect(
      page.getByRole("heading", { name: /abrir chamado/i }),
    ).toBeVisible({ timeout: 5_000 });
  });

  test("cria novo ticket com sucesso", async ({ page }) => {
    await page.goto("/tickets/new");
    // Wait for products to load and form to render
    await expect(
      page.getByRole("heading", { name: /abrir chamado/i }),
    ).toBeVisible({ timeout: 10_000 });

    const title = `Teste E2E ${Date.now()}`;
    await page.getByPlaceholder("Descreva o problema brevemente").fill(title);
    await page
      .getByPlaceholder(/descreva o problema com detalhes/i)
      .fill("Descrição criada por teste automatizado.");

    // Priority and category selects (1st = priority, 2nd = category)
    await page.locator("select").first().selectOption("medium");
    await page.locator("select").nth(1).selectOption("software");

    // Submit goes to preview step first
    await page.getByRole("button", { name: /revisar e enviar/i }).click();
    // Confirm on preview step
    await page.getByRole("button", { name: /confirmar e enviar/i }).click();

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
    await expect(page.getByText(/HS-/).first()).toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByRole("heading", { name: "Descrição" }),
    ).toBeVisible();
  });

  test("botão voltar retorna para lista de tickets", async ({ page }) => {
    await page.goto("/tickets");
    await page.locator("tbody tr").first().click();
    await page.getByRole("button", { name: /voltar/i }).click();
    await expect(page).toHaveURL("/tickets");
  });
});
