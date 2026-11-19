import { test, expect } from "@playwright/test";
import { login } from "./helpers";
import {
  ECE01,
  MODO_ECE01,
  MOTIVO_DO_SKIP,
  abrirEquipamentosDoProduto,
  campoDoDetalhe,
  linhaDoEquipamento,
} from "./ece01";

/**
 * A equipe classifica o equipamento — vale igual com o compartilhamento ligado
 * ou desligado, e por isso este spec roda nos dois modos.
 *
 * Os passos são em série e dividem um aparelho: cada um parte do estado que o
 * anterior deixou. O nome leva o relógio para a repetição do CI (`retries: 1`)
 * não esbarrar no aparelho da tentativa anterior.
 */
test.describe.serial("ECE-01 — classificação pela equipe", () => {
  test.skip(!MODO_ECE01, MOTIVO_DO_SKIP);

  const aparelho = `ECE01 Classificado ${Date.now()}`;

  test.beforeEach(async ({ page }) => {
    await login(page, "admin");
  });

  test("cadastra com empresa e a tela mostra a empresa sem recarregar", async ({
    page,
  }) => {
    await abrirEquipamentosDoProduto(page);
    await page.getByRole("button", { name: /Equipamento$/ }).click();

    const formulario = page.getByRole("dialog", { name: "Novo equipamento" });
    await formulario.getByLabel("Nome *").fill(aparelho);

    // Responsável: a Ana, que é da Alfa.
    await formulario.getByRole("button", { name: /Dono/ }).click();
    await page
      .getByPlaceholder("Buscar cliente por nome ou e-mail…")
      .fill(ECE01.ana.email);
    await page.getByRole("option", { name: new RegExp(ECE01.ana.nome) }).click();

    // Empresa do equipamento: a Beta — de propósito outra que não a da Ana.
    await formulario
      .getByRole("combobox", { name: "Empresa do equipamento" })
      .click();
    await page.getByRole("option", { name: "Definir a empresa…" }).click();
    await formulario.getByRole("button", { name: /^Empresa/ }).click();
    await page
      .getByPlaceholder("Buscar empresa por nome ou CNPJ…")
      .fill(ECE01.beta);
    await page.getByRole("option", { name: new RegExp(ECE01.beta) }).click();

    await formulario.getByRole("button", { name: "Criar equipamento" }).click();
    await expect(formulario).not.toBeVisible();

    // SEM recarregar: a linha que a tela mostra agora é a resposta do salvar.
    // Era aqui que o aparelho recém-classificado aparecia "sem empresa".
    const linha = page
      .getByText(aparelho, { exact: true })
      .locator("xpath=ancestor::div[contains(@class,'cursor-pointer')][1]");
    await linha.getByTitle("Visualizar").click();

    const detalhe = page.getByRole("dialog", { name: aparelho });
    await expect(
      campoDoDetalhe(detalhe, "Empresa do equipamento"),
    ).toContainText(ECE01.beta);
    await expect(
      campoDoDetalhe(detalhe, "Empresa do responsável"),
    ).toContainText(ECE01.alfa);
    await expect(
      detalhe.getByText("Diferente da empresa do responsável."),
    ).toBeVisible();
  });

  test("a consulta da equipe aponta a divergência com a empresa do responsável", async ({
    page,
  }) => {
    await page.goto("/equipamentos");
    await page.getByLabel("Buscar equipamentos").fill(aparelho);

    const linha = page.getByRole("row", { name: new RegExp(aparelho) });
    await expect(linha).toContainText(ECE01.beta);
    await expect(linha).toContainText(
      `Diverge do responsável: ${ECE01.alfa}`,
    );
  });

  test("inativar o equipamento mantém a classificação", async ({ page }) => {
    await abrirEquipamentosDoProduto(page);
    const linha = await linhaDoEquipamento(page, aparelho);

    await linha.getByTitle("Clique para desativar").click();
    await expect(linha.getByTitle("Clique para ativar")).toBeVisible();

    // De novo sem recarregar: a linha é a resposta do PATCH só com `is_active`.
    await linha.getByTitle("Visualizar").click();
    const detalhe = page.getByRole("dialog", { name: aparelho });
    await expect(
      campoDoDetalhe(detalhe, "Empresa do equipamento"),
    ).toContainText(ECE01.beta);
    await detalhe.getByRole("button", { name: "Fechar" }).first().click();

    // E o banco concorda: reativa, recarrega e a empresa continua lá.
    await linha.getByTitle("Clique para ativar").click();
    await expect(linha.getByTitle("Clique para desativar")).toBeVisible();
    await page.reload();
    await abrirEquipamentosDoProduto(page);
    const depois = await linhaDoEquipamento(page, aparelho);
    await depois.getByTitle("Visualizar").click();
    await expect(
      campoDoDetalhe(
        page.getByRole("dialog", { name: aparelho }),
        "Empresa do equipamento",
      ),
    ).toContainText(ECE01.beta);
  });

  test("editar para sem empresa por decisão", async ({ page }) => {
    await abrirEquipamentosDoProduto(page);
    const linha = await linhaDoEquipamento(page, aparelho);
    await linha.getByTitle("Editar").click();

    const formulario = page.getByRole("dialog", { name: "Editar equipamento" });
    await expect(formulario.getByText(`Hoje: ${ECE01.beta}.`)).toBeVisible();
    await formulario
      .getByRole("combobox", { name: "Empresa do equipamento" })
      .click();
    await page.getByRole("option", { name: "Sem empresa (por decisão)" }).click();
    await formulario.getByRole("button", { name: "Salvar" }).click();
    await expect(formulario).not.toBeVisible();

    await linha.getByTitle("Visualizar").click();
    const detalhe = page.getByRole("dialog", { name: aparelho });
    await expect(
      campoDoDetalhe(detalhe, "Empresa do equipamento"),
    ).toContainText("Sem empresa (por decisão)");
    // Decisão da equipe não é divergência.
    await expect(
      detalhe.getByText("Diferente da empresa do responsável."),
    ).not.toBeVisible();
  });

  test("o filtro Sem empresa traz o que falta classificar e o que ficou sem por decisão", async ({
    page,
  }) => {
    await page.goto("/equipamentos");
    await page.getByLabel("Sem empresa", { exact: true }).check();

    // O semeado sem empresa nenhuma: falta classificar.
    await page
      .getByLabel("Buscar equipamentos")
      .fill(ECE01.aparelhoAClassificar);
    const aClassificar = page.getByRole("row", {
      name: new RegExp(ECE01.aparelhoAClassificar),
    });
    await expect(aClassificar).toBeVisible();
    await expect(aClassificar).not.toContainText("por decisão");

    // O do passo anterior: sem empresa, e a linha diz que foi decisão.
    await page.getByLabel("Buscar equipamentos").fill(aparelho);
    await expect(
      page.getByRole("row", { name: new RegExp(aparelho) }),
    ).toContainText("Sem empresa (por decisão)");

    // Quem tem empresa fica de fora.
    await page.getByLabel("Buscar equipamentos").fill(ECE01.aparelhoDaAna);
    await expect(
      page.getByText("Nenhum equipamento encontrado para esses filtros."),
    ).toBeVisible();
  });

  test("o equipamento semeado em outra empresa aparece como divergente", async ({
    page,
  }) => {
    await page.goto("/equipamentos");
    await page.getByLabel("Buscar equipamentos").fill(ECE01.aparelhoDivergente);

    const linha = page.getByRole("row", {
      name: new RegExp(ECE01.aparelhoDivergente),
    });
    await expect(linha).toContainText(ECE01.beta);
    await expect(linha).toContainText(
      `Diverge do responsável: ${ECE01.alfa}`,
    );
  });
});
