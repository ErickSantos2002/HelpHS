import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Base de Conhecimento", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
  });

  test("lista de artigos é acessível via sidebar", async ({ page }) => {
    await page.getByRole("link", { name: "Base de Conhecimento" }).click();
    await expect(page).toHaveURL("/kb");
    await expect(
      page.getByRole("heading", { name: /base de conhecimento/i }),
    ).toBeVisible();
  });

  test("filtro de pesquisa filtra artigos", async ({ page }) => {
    await page.goto("/kb");
    await page.getByPlaceholder(/buscar/i).fill("xyz_inexistente_abc");
    await expect(page.getByText(/nenhum artigo encontrado/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("formulário de novo artigo é acessível", async ({ page }) => {
    await page.goto("/kb");
    await page.getByRole("link", { name: /novo artigo/i }).click();
    await expect(page).toHaveURL("/kb/new");
    await expect(
      page.getByRole("heading", { name: /novo artigo/i }),
    ).toBeVisible();
  });

  test("cria e visualiza novo artigo KB", async ({ page }) => {
    await page.goto("/kb/new");

    const title = `Artigo E2E ${Date.now()}`;
    // KBFormPage uses raw <label> without htmlFor — use placeholder instead
    await page.getByPlaceholder("Título do artigo").fill(title);
    await page
      .getByPlaceholder(/escreva o conteúdo/i)
      .fill("Conteúdo de teste criado por E2E.");

    // Set status to "published" so the detail page can find the article
    // Status is the 2nd select (1st is category)
    await page.locator("select").nth(1).selectOption("published");

    await page.getByRole("button", { name: /criar artigo/i }).click();

    // Should redirect to article detail with the new article's ID
    await expect(page).toHaveURL(/\/kb\/[^/]+$/, { timeout: 10_000 });
    // Article page loaded (title shown in heading or page body)
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({
      timeout: 5_000,
    });
  });
});
