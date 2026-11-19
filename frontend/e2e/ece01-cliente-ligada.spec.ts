import { test, expect } from "@playwright/test";
import { login } from "./helpers";
import {
  ECE01,
  MODO_ECE01,
  MOTIVO_DO_SKIP,
  entrar,
  equipamentoDoChamado,
  linhaDoCliente,
} from "./ece01";

/**
 * Compartilhamento LIGADO (`EQUIPAMENTO_POR_EMPRESA=true`): Ana e Bruno são
 * clientes ativos da mesma empresa, e cada um passa a ver e a usar em chamado
 * o equipamento do outro — sem poder alterá-lo.
 */
test.describe("ECE-01 — cliente com o compartilhamento ligado", () => {
  test.skip(MODO_ECE01 !== "ligada", MOTIVO_DO_SKIP);

  test("o Bruno vê o equipamento da colega com o selo Da empresa", async ({
    page,
  }) => {
    await entrar(page, ECE01.bruno);
    await page.goto("/equipment");

    await expect(page.getByText(ECE01.aparelhoDoBruno)).toBeVisible();
    const daColega = linhaDoCliente(page, ECE01.aparelhoDaAna);
    await expect(daColega).toBeVisible();
    await expect(daColega.getByText("Da empresa", { exact: true })).toBeVisible();
  });

  test("o equipamento da colega não oferece editar nem excluir; o próprio oferece", async ({
    page,
  }) => {
    await entrar(page, ECE01.bruno);
    await page.goto("/equipment");
    await expect(page.getByText(ECE01.aparelhoDaAna)).toBeVisible();

    await expect(
      page.getByRole("button", { name: `Editar ${ECE01.aparelhoDaAna}` }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: `Excluir ${ECE01.aparelhoDaAna}` }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: `Editar ${ECE01.aparelhoDoBruno}` }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Excluir ${ECE01.aparelhoDoBruno}` }),
    ).toBeVisible();
  });

  test("o equipamento da colega classificado em OUTRA empresa não é compartilhado", async ({
    page,
  }) => {
    // O que decide é a empresa do EQUIPAMENTO, e não a do responsável: a Ana é
    // da Alfa, mas este aparelho dela foi classificado na Beta.
    await entrar(page, ECE01.bruno);
    await page.goto("/equipment");
    await expect(page.getByText(ECE01.aparelhoDaAna)).toBeVisible();

    await expect(page.getByText(ECE01.aparelhoDivergente)).not.toBeVisible();
  });

  test("a dona continua vendo o próprio sem selo e com as ações", async ({
    page,
  }) => {
    await entrar(page, ECE01.ana);
    await page.goto("/equipment");

    const proprio = linhaDoCliente(page, ECE01.aparelhoDaAna);
    await expect(proprio).toBeVisible();
    await expect(proprio.getByText("Da empresa", { exact: true })).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: `Editar ${ECE01.aparelhoDaAna}` }),
    ).toBeVisible();
  });

  test("o Bruno abre chamado com o equipamento da colega, e editar o chamado não o desvincula", async ({
    page,
  }) => {
    const titulo = `ECE01 chamado compartilhado ${Date.now()}`;

    // ── Abre o chamado com o aparelho da Ana ──────────────────
    await entrar(page, ECE01.bruno);
    await page.goto("/tickets/new");
    await page.getByLabel("Título *").fill(titulo);
    // O rádio é `sr-only`: quem recebe o clique é o cartão que o rotula.
    await page.getByText("Hardware", { exact: true }).click();
    await expect(page.getByRole("radio", { name: "Hardware" })).toBeChecked();
    await page.getByRole("button", { name: /Produto/ }).click();
    await page.getByRole("option", { name: ECE01.produto }).click();

    const equipamentos = page.getByRole("group", { name: "Equipamentos" });
    const daColega = equipamentos.getByRole("button", {
      name: new RegExp(ECE01.aparelhoDaAna),
    });
    await expect(daColega).toContainText("Da empresa");
    await daColega.click();
    await expect(daColega).toHaveAttribute("aria-pressed", "true");

    await page
      .getByLabel("Descrição *")
      .fill("Chamado do e2e: o aparelho da colega parou de responder.");
    await page.getByRole("button", { name: "Revisar e enviar" }).click();
    await page.getByRole("button", { name: "Confirmar e enviar" }).click();

    await page.waitForURL(/\/tickets\/[0-9a-f-]{36}$/);
    const urlDoChamado = page.url();
    await expect(equipamentoDoChamado(page)).toContainText(ECE01.aparelhoDaAna);

    // ── A equipe edita o chamado SEM tocar nos equipamentos ───
    // Era aqui o desvínculo acidental: a edição abria com a seleção vazia e o
    // PATCH levava `equipment_ids: []`.
    await page.context().clearCookies();
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await login(page, "admin");
    await page.goto(`${urlDoChamado}/edit`);

    const naEdicao = page
      .getByRole("group", { name: "Equipamentos" })
      .getByRole("button", { name: new RegExp(ECE01.aparelhoDaAna) });
    await expect(naEdicao).toHaveAttribute("aria-pressed", "true");

    await page.getByLabel("Título *").fill(`${titulo} (editado)`);
    // A edição abre com a descrição em branco e a exige de novo.
    await page
      .getByLabel("Descrição *")
      .fill("Chamado do e2e: descrição revista pela equipe.");
    await page.getByRole("button", { name: "Revisar e enviar" }).click();
    await page.getByRole("button", { name: "Confirmar e enviar" }).click();

    await page.waitForURL(urlDoChamado);
    await expect(page.getByText(`${titulo} (editado)`).first()).toBeVisible();
    await expect(equipamentoDoChamado(page)).toContainText(ECE01.aparelhoDaAna);

    // E não é só a tela que guardou: recarregado, o chamado continua com ele.
    await page.reload();
    await expect(equipamentoDoChamado(page)).toContainText(ECE01.aparelhoDaAna);
  });
});
