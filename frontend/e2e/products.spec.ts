import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Produtos e Equipamentos", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
    await page.goto("/products");
  });

  test("página de produtos é acessível via sidebar", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Produtos" }).click();
    await expect(page).toHaveURL("/products");
    await expect(page.getByText(/produtos/i).first()).toBeVisible({
      timeout: 5_000,
    });
  });

  test("exibe lista de produtos com campo de busca", async ({ page }) => {
    await expect(page.getByPlaceholder("Buscar produto…")).toBeVisible({
      timeout: 8_000,
    });
  });

  test("abre modal de criação de produto", async ({ page }) => {
    await expect(page.getByPlaceholder("Buscar produto…")).toBeVisible({
      timeout: 8_000,
    });

    await page.getByRole("button", { name: "+ Produto" }).click();

    await expect(
      page.getByRole("heading", { name: "Novo produto" }),
    ).toBeVisible({ timeout: 5_000 });
    await expect(page.getByLabel("Nome *")).toBeVisible();
  });

  test("cria novo produto com sucesso", async ({ page }) => {
    await expect(page.getByPlaceholder("Buscar produto…")).toBeVisible({
      timeout: 8_000,
    });

    await page.getByRole("button", { name: "+ Produto" }).click();
    await expect(
      page.getByRole("heading", { name: "Novo produto" }),
    ).toBeVisible({ timeout: 5_000 });

    const productName = `Produto E2E ${Date.now()}`;
    await page.getByLabel("Nome *").fill(productName);
    await page.getByLabel("Versão").fill("1.0.0");

    await page.getByRole("button", { name: "Criar" }).click();

    // Modal closes after creation
    await expect(
      page.getByRole("heading", { name: "Novo produto" }),
    ).not.toBeVisible({ timeout: 8_000 });

    // Product appears in the list
    await expect(page.getByText(productName)).toBeVisible({ timeout: 5_000 });
  });

  test("cancela criação de produto sem salvar", async ({ page }) => {
    await expect(page.getByPlaceholder("Buscar produto…")).toBeVisible({
      timeout: 8_000,
    });

    await page.getByRole("button", { name: "+ Produto" }).click();
    await expect(
      page.getByRole("heading", { name: "Novo produto" }),
    ).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: "Cancelar" }).click();

    await expect(
      page.getByRole("heading", { name: "Novo produto" }),
    ).not.toBeVisible();
  });

  test("busca produto por nome filtra a lista", async ({ page }) => {
    await expect(page.getByPlaceholder("Buscar produto…")).toBeVisible({
      timeout: 8_000,
    });

    await page
      .getByPlaceholder("Buscar produto…")
      .fill("xyz_inexistente_12345");
    // List clears or shows empty state — no product should match
    await expect(page.getByText(/nenhum produto/i)).toBeVisible({
      timeout: 5_000,
    });
  });
});
