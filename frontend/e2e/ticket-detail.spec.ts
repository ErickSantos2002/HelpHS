import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Ticket Detail — Interações", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
  });

  // Helper: creates a ticket and returns to its detail page URL
  async function createAndOpenTicket(page: Parameters<typeof login>[0]) {
    await page.goto("/tickets/new");
    await expect(
      page.getByRole("heading", { name: /abrir chamado/i }),
    ).toBeVisible({ timeout: 10_000 });

    const title = `Detail E2E ${Date.now()}`;
    await page.getByPlaceholder("Descreva o problema brevemente").fill(title);
    await page
      .getByPlaceholder(/descreva o problema com detalhes/i)
      .fill("Descrição para teste de detalhe do chamado.");
    await page.locator("select").first().selectOption("medium");
    await page.locator("select").nth(1).selectOption("software");

    await page.getByRole("button", { name: /revisar e enviar/i }).click();
    await page.getByRole("button", { name: /confirmar e enviar/i }).click();

    await expect(page).toHaveURL(/\/tickets\/[^/]+$/, { timeout: 10_000 });
    return title;
  }

  test("exibe seções principais do detalhe (protocolo, descrição, chat)", async ({
    page,
  }) => {
    await createAndOpenTicket(page);

    await expect(page.getByText(/HS-/).first()).toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByRole("heading", { name: "Descrição" }),
    ).toBeVisible();
    await expect(page.getByPlaceholder(/escreva uma mensagem/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  test("abre modal de alteração de status e confirma novo status", async ({
    page,
  }) => {
    await createAndOpenTicket(page);

    // Staff sidebar should show "Alterar status"
    await page.getByRole("button", { name: "Alterar status" }).click();

    // Modal opens
    await expect(
      page.getByRole("heading", { name: "Alterar status" }),
    ).toBeVisible({ timeout: 5_000 });

    // Select first available transition (in_progress for an open ticket)
    const statusSelect = page.getByLabel("Novo status");
    await statusSelect.selectOption({ index: 1 });

    await page.getByRole("button", { name: "Confirmar" }).click();

    // Modal closes after successful status change
    await expect(
      page.getByRole("heading", { name: "Alterar status" }),
    ).not.toBeVisible({ timeout: 8_000 });
  });

  test("abre modal de atribuição de técnico", async ({ page }) => {
    await createAndOpenTicket(page);

    await page.getByRole("button", { name: /atribuir técnico/i }).click();

    await expect(
      page.getByRole("heading", { name: /atribuir técnico/i }),
    ).toBeVisible({ timeout: 5_000 });

    // Cancel without assigning
    await page.getByRole("button", { name: "Cancelar" }).click();
    await expect(
      page.getByRole("heading", { name: /atribuir técnico/i }),
    ).not.toBeVisible();
  });

  test("exibe painel de chat com textarea de mensagem", async ({ page }) => {
    await createAndOpenTicket(page);

    const chatInput = page.getByPlaceholder(/escreva uma mensagem/i);
    await expect(chatInput).toBeVisible({ timeout: 5_000 });

    await chatInput.fill("Mensagem de teste E2E");
    await expect(chatInput).toHaveValue("Mensagem de teste E2E");
  });

  test("botão editar ticket navega para /tickets/:id/edit", async ({
    page,
  }) => {
    await createAndOpenTicket(page);

    await page.getByRole("button", { name: "Editar ticket" }).click();
    await expect(page).toHaveURL(/\/tickets\/[^/]+\/edit$/, {
      timeout: 5_000,
    });
  });
});
