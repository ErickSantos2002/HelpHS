import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe("Notificações", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
  });

  test("página de notificações é acessível via sidebar", async ({ page }) => {
    await page.goto("/notifications");
    await expect(
      page.getByRole("heading", { name: /notificações/i }),
    ).toBeVisible();
  });

  test("sino de notificações abre dropdown", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Notificações/i }).click();
    await expect(page.getByText(/Ver todas as notificações/i)).toBeVisible();
  });

  test("'Ver todas' redireciona para /notifications", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Notificações/i }).click();
    await page.getByText(/Ver todas as notificações/i).click();
    await expect(page).toHaveURL("/notifications");
  });
});
