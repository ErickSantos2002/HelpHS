import type { Page } from "@playwright/test";

// O admin vem de `app.seeds` (os mesmos seeds do boot). O cliente vem de
// `app.seeds_e2e`, que só o workflow de e2e roda — e que se recusa a rodar em
// produção. Há um teste no backend garantindo que os valores daqui e de lá
// são os mesmos.
//
// Não existe técnico: nenhum spec loga como técnico, e manter credencial de
// uma conta que nenhum seed cria é armadilha para o próximo que usar.
/**
 * Senha vem SEMPRE do ambiente, sem valor de reserva.
 *
 * O literal que morava aqui tinha de bater com o do `.github/workflows/e2e.yml`
 * — e a duplicação era o próprio defeito: a senha do admin de teste ficava
 * escrita em repositório público, em dois lugares que ninguém garantia iguais.
 * Hoje o workflow gera uma por execução e exporta para os dois lados.
 *
 * Falhar aqui é melhor do que cair num valor de reserva: com reserva, o login
 * erraria lá na frente com "credencial inválida", e o motivo real — a variável
 * não chegou — ficaria escondido atrás de um sintoma que parece outra coisa.
 */
function doAmbiente(nome: string): string {
  const valor = process.env[nome];
  if (!valor) {
    throw new Error(
      `${nome} não está definida. No CI ela é gerada por execução; ` +
        `rodando local, exporte o mesmo valor que você passou em SEED_ADMIN_PASSWORD.`,
    );
  }
  return valor;
}

export const CREDENTIALS = {
  admin: {
    email: process.env.ADMIN_EMAIL ?? "admin@healthsafety.com",
    password: doAmbiente("ADMIN_PASSWORD"),
  },
  client: {
    email: process.env.CLIENT_EMAIL ?? "client.e2e@healthsafety.com",
    password: process.env.CLIENT_PASSWORD ?? "ClientE2E@123",
  },
};

export async function login(
  page: Page,
  role: keyof typeof CREDENTIALS = "admin",
) {
  const { email, password } = CREDENTIALS[role];
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.includes("/login"), {
    timeout: 10_000,
  });
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: /Menu do usuário/i }).click();
  await page.getByRole("button", { name: "Sair" }).click();
  await page.waitForURL("**/login");
}
