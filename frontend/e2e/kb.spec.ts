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
    await page.getByLabel(/título/i).fill(title);
    await page
      .getByLabel(/conteúdo/i)
      .fill("Conteúdo de teste criado por E2E.");

    await page.getByRole("button", { name: /publicar/i }).click();

    // Should redirect to article detail
    await expect(page).toHaveURL(/\/kb\/[^/]+$/, { timeout: 10_000 });
    await expect(page.getByText(title)).toBeVisible();
  });
});
