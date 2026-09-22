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

  test("filtro por prioridade atualiza a lista", async ({ page }) => {
    await page.goto("/tickets");
    // O nome do caso dizia "status", e a barra de /tickets NUNCA teve filtro
    // de status: o primeiro campo sempre foi o de prioridade, e "open" jamais
    // esteve entre os valores dele. O gesto novo vai no filtro que existe —
    // gatilho pelo nome acessível (o rótulo `sr-only` "Prioridade") e escolha
    // pelo RÓTULO da opção —, e o nome do caso passou a dizer isso.
    await page.getByRole("combobox", { name: "Prioridade" }).click();
    await page.getByRole("option", { name: "Alta" }).click();
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

    // A PRIORIDADE NÃO SE ESCOLHE AQUI desde 22/09/2026: quem abre descreve o
    // problema, e quem classifica a urgência é a triagem. O passo que clicava
    // em "Média" saiu junto com o grupo de rádio que ele procurava.
    //
    // A Categoria continua sendo ficha de rádio (`RadioCards`), e não campo de
    // lista: o rádio de verdade fica `sr-only` atrás da ficha, então o clique
    // vai no rótulo visível, dentro do grupo que o `fieldset`/`legend` nomeia.
    await page
      .getByRole("group", { name: "Categoria" })
      .getByText("Software", { exact: true })
      .click();

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
