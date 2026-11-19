import { test, expect } from "@playwright/test";
import { ECE01, MODO_ECE01, MOTIVO_DO_SKIP, entrar } from "./ece01";

/**
 * Compartilhamento DESLIGADO (`EQUIPAMENTO_POR_EMPRESA=false`, o padrão): o
 * cliente vê e usa só o que é dele, mesmo com um colega na mesma empresa e
 * com os equipamentos já classificados.
 *
 * O dado é o mesmo do spec da flag ligada — o que muda é o backend.
 */
test.describe("ECE-01 — cliente com o compartilhamento desligado", () => {
  test.skip(MODO_ECE01 !== "desligada", MOTIVO_DO_SKIP);

  test("a Ana vê os próprios equipamentos e não vê o do colega", async ({
    page,
  }) => {
    await entrar(page, ECE01.ana);
    await page.goto("/equipment");

    await expect(page.getByText(ECE01.aparelhoDaAna)).toBeVisible();
    // Também é dela, ainda que classificado em outra empresa.
    await expect(page.getByText(ECE01.aparelhoDivergente)).toBeVisible();
    await expect(page.getByText(ECE01.aparelhoDoBruno)).not.toBeVisible();
  });

  test("nenhum equipamento leva o selo Da empresa, e todos podem ser alterados", async ({
    page,
  }) => {
    await entrar(page, ECE01.ana);
    await page.goto("/equipment");
    await expect(page.getByText(ECE01.aparelhoDaAna)).toBeVisible();

    await expect(page.getByText("Da empresa", { exact: true })).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: `Editar ${ECE01.aparelhoDaAna}` }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Excluir ${ECE01.aparelhoDaAna}` }),
    ).toBeVisible();
  });

  test("o Bruno também só vê o dele", async ({ page }) => {
    await entrar(page, ECE01.bruno);
    await page.goto("/equipment");

    await expect(page.getByText(ECE01.aparelhoDoBruno)).toBeVisible();
    await expect(page.getByText(ECE01.aparelhoDaAna)).not.toBeVisible();
    await expect(page.getByText("Da empresa", { exact: true })).toHaveCount(0);
  });

  test("o formulário de chamado só oferece os equipamentos do próprio cliente", async ({
    page,
  }) => {
    await entrar(page, ECE01.bruno);
    await page.goto("/tickets/new");

    await page.getByRole("button", { name: /Produto/ }).click();
    await page.getByRole("option", { name: ECE01.produto }).click();

    const equipamentos = page.getByRole("group", { name: "Equipamentos" });
    await expect(
      equipamentos.getByRole("button", { name: ECE01.aparelhoDoBruno }),
    ).toBeVisible();
    await expect(
      equipamentos.getByRole("button", { name: ECE01.aparelhoDaAna }),
    ).toHaveCount(0);
    await expect(equipamentos.getByText("Da empresa")).toHaveCount(0);
  });
});
