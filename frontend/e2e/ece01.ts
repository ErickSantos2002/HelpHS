import { expect, type Locator, type Page } from "@playwright/test";

/**
 * O que os specs `ece01-*.spec.ts` têm em comum: o cenário semeado por
 * `python -m app.seeds_e2e --ece01` e o modo em que o backend está rodando.
 *
 * Os nomes e as credenciais são os de `backend/app/seeds_e2e.py`; há teste no
 * backend garantindo que os dois lados batem.
 */

/**
 * `E2E_ECE01` diz em que modo o backend DESTA execução subiu — `ligada` ou
 * `desligada`, espelhando `EQUIPAMENTO_POR_EMPRESA`. A tela não conhece a
 * flag, e o spec não tem como descobri-la sozinho: quem sobe o backend é quem
 * sabe.
 *
 * Sem a variável, os três specs se pulam inteiros. É o que mantém a suíte
 * geral (`npx playwright test`, sem o seed `--ece01`) do jeito que estava.
 */
export const MODO_ECE01 = process.env.E2E_ECE01 as
  "ligada" | "desligada" | undefined;

export const MOTIVO_DO_SKIP =
  "specs da ECE-01 só rodam com E2E_ECE01=ligada|desligada e o seed --ece01";

export const ECE01 = {
  produto: "ECE01 Produto",
  alfa: "ECE01 Alfa Ltda",
  beta: "ECE01 Beta Ltda",
  ana: {
    nome: "Ana ECE01",
    email: "ana.ece01.e2e@healthsafety.com",
    password: "AnaEce01@123",
  },
  bruno: {
    nome: "Bruno ECE01",
    email: "bruno.ece01.e2e@healthsafety.com",
    password: "BrunoEce01@123",
  },
  aparelhoDaAna: "ECE01 Aparelho da Ana",
  aparelhoDoBruno: "ECE01 Aparelho do Bruno",
  aparelhoDivergente: "ECE01 Aparelho divergente",
  aparelhoAClassificar: "ECE01 Aparelho a classificar",
};

/** O mesmo caminho do `login` de `helpers.ts`, para uma conta qualquer. */
export async function entrar(
  page: Page,
  conta: { email: string; password: string },
) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(conta.email);
  await page.getByLabel("Senha", { exact: true }).fill(conta.password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), {
    timeout: 10_000,
  });
}

/**
 * O campo do detalhe do equipamento: o rótulo e o valor moram no mesmo bloco,
 * e o rótulo é o que a pessoa lê para saber de qual empresa se trata.
 */
export function campoDoDetalhe(dialogo: Locator, rotulo: string): Locator {
  return dialogo.getByText(rotulo, { exact: true }).locator("..");
}

/** Abre a tela de Produtos já com os equipamentos do produto da ECE-01. */
export async function abrirEquipamentosDoProduto(page: Page) {
  await page.goto("/products");
  await page.getByPlaceholder("Buscar produto…").fill(ECE01.produto);
  await page.getByText(ECE01.produto, { exact: true }).first().click();
  await expect(page.getByPlaceholder("Buscar equipamento…")).toBeVisible();
}

/**
 * A linha do equipamento na tela de Produtos. Busca antes: a lista é paginada,
 * e cada execução acrescenta um aparelho ao mesmo produto.
 */
export async function linhaDoEquipamento(
  page: Page,
  nome: string,
): Promise<Locator> {
  await page.getByPlaceholder("Buscar equipamento…").fill(nome);
  const linha = page
    .getByText(nome, { exact: true })
    .locator("xpath=ancestor::div[contains(@class,'cursor-pointer')][1]");
  await expect(linha).toBeVisible();
  return linha;
}

/** A linha do equipamento em "Meus equipamentos" (a tela do cliente). */
export function linhaDoCliente(page: Page, nome: string): Locator {
  return page
    .getByText(nome, { exact: true })
    .locator("xpath=ancestor::div[contains(@class,'items-center')][1]");
}

/**
 * O campo "Equipamento" do detalhe do chamado. Pelo rótulo, e não pelo nome do
 * aparelho solto na página: o histórico do chamado também escreve nomes, e um
 * aparelho desvinculado continuaria "visível" lá.
 */
export function equipamentoDoChamado(page: Page): Locator {
  // Dentro do `main`: a barra lateral da equipe tem um link "Equipamentos".
  return page
    .getByRole("main")
    .getByText(/^Equipamentos?$/)
    .locator("..")
    .filter({ visible: true })
    .first();
}
