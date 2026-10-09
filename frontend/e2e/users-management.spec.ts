import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Gestão de Usuários", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
    await page.goto("/users");
  });

  test("página de usuários exibe lista e heading", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Usuários" })).toBeVisible({
      timeout: 5_000,
    });
    // Table should render
    await expect(page.locator("table")).toBeVisible({ timeout: 8_000 });
  });

  test("filtra usuários por perfil", async ({ page }) => {
    await expect(page.locator("table")).toBeVisible({ timeout: 8_000 });

    // O filtro de perfil, agora pelo nome acessível: o gatilho tem rótulo
    // `sr-only` ("Perfil"), que não muda quando o filtro é escolhido — a
    // ordem dos campos na barra deixou de importar. A escolha é pelo RÓTULO
    // da opção ("Administrador"), não pelo valor.
    await page.getByRole("combobox", { name: "Perfil" }).click();
    await page.getByRole("option", { name: "Administrador" }).click();

    // Table updates (any row count is valid, even 0)
    await expect(page.locator("table")).toBeVisible();
  });

  test("abre modal de criação de usuário", async ({ page }) => {
    await page.getByRole("button", { name: "Novo usuário" }).click();

    await expect(
      page.getByRole("heading", { name: "Novo usuário" }),
    ).toBeVisible({ timeout: 5_000 });

    // Form fields are visible
    await expect(page.getByLabel("Nome *")).toBeVisible();
    await expect(page.getByLabel("E-mail *")).toBeVisible();
    await expect(page.getByLabel("Senha *")).toBeVisible();
  });

  test("cria novo usuário com sucesso", async ({ page }) => {
    await page.getByRole("button", { name: "Novo usuário" }).click();
    await expect(
      page.getByRole("heading", { name: "Novo usuário" }),
    ).toBeVisible({ timeout: 5_000 });

    const ts = Date.now();
    const email = `e2e.user.${ts}@test.com`;
    await page.getByLabel("Nome *").fill("Usuário E2E");
    await page.getByLabel("E-mail *").fill(email);
    await page.getByLabel("Senha *").fill("Senha@12345");
    // "Perfil *" é o do modal; o filtro da barra atrás dele se chama só
    // "Perfil", e o asterisco separa os dois.
    await page.getByRole("combobox", { name: "Perfil *" }).click();
    await page.getByRole("option", { name: "Cliente" }).click();

    await page.getByRole("button", { name: "Criar" }).click();

    // Modal closes after successful creation
    await expect(
      page.getByRole("heading", { name: "Novo usuário" }),
    ).not.toBeVisible({ timeout: 8_000 });

    // New user email (unique) appears in the table
    await expect(page.getByText(email)).toBeVisible({ timeout: 10_000 });
  });

  test("cancela criação de usuário sem salvar", async ({ page }) => {
    await page.getByRole("button", { name: "Novo usuário" }).click();
    await expect(
      page.getByRole("heading", { name: "Novo usuário" }),
    ).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: "Cancelar" }).click();

    await expect(
      page.getByRole("heading", { name: "Novo usuário" }),
    ).not.toBeVisible();
  });
});
