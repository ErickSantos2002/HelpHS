import type { Page } from "@playwright/test";

// O admin vem de `app.seeds` (os mesmos seeds do boot). O cliente vem de
// `app.seeds_e2e`, que só o workflow de e2e roda — e que se recusa a rodar em
// produção. Há um teste no backend garantindo que os valores daqui e de lá
// são os mesmos.
//
// Não existe técnico: nenhum spec loga como técnico, e manter credencial de
// uma conta que nenhum seed cria é armadilha para o próximo que usar.
export const CREDENTIALS = {
  admin: {
    email: process.env.ADMIN_EMAIL ?? "admin@healthsafety.com",
    password: process.env.ADMIN_PASSWORD ?? "Admin@123456",
  },
  client: {
    email: process.env.CLIENT_EMAIL ?? "client.e2e@healthsafety.com",
    password: process.env.CLIENT_PASSWORD ?? "ClientE2E@123",
  },
};

/**
 * O que vai para o campo "Senha" no lugar da senha. Não é credencial de nada:
 * é o texto que o relatório, o trace e a fotografia da página podem guardar à
 * vontade.
 */
const NO_LUGAR_DA_SENHA = "senha-fora-do-relatorio";

/**
 * Entra pela tela de login sem que a senha passe pela página.
 *
 * Tudo o que o Playwright vê da página ele pode guardar: o valor de um `fill`
 * vira título de passo no relatório HTML, o argumento de um `evaluate` e o
 * corpo das requisições vão para o trace, e o valor dos campos sai na
 * fotografia que acompanha o teste que falha. O relatório é artefato do
 * workflow — e mascarar o log do GitHub não alcança artefato.
 *
 * Por isso a senha não é digitada. O formulário recebe um texto qualquer, e a
 * troca acontece fora da página, na interceptação da própria chamada de login:
 * o corpo que o navegador montou segue para o backend com a senha de verdade
 * no lugar. O backend autentica como sempre — nada é pulado, e senha errada
 * continua sendo recusada —, e o que fica registrado é o que a página enviou.
 *
 * A interceptação vale para UMA chamada de `/auth/login` e só troca o corpo
 * que traz o texto combinado; qualquer outro passa intacto.
 */
export async function entrarSemExporASenha(
  page: Page,
  email: string,
  senha: string,
) {
  await page.route(
    "**/auth/login",
    async (rota) => {
      const corpo = rota.request().postDataJSON() as {
        password?: unknown;
      } | null;
      if (corpo?.password !== NO_LUGAR_DA_SENHA) {
        await rota.continue();
        return;
      }
      await rota.continue({
        postData: JSON.stringify({ ...corpo, password: senha }),
      });
    },
    { times: 1 },
  );

  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  // `exact` porque a tela de login tem DOIS elementos rotulados com "senha": o
  // campo (label "Senha") e o botão do olho de revelar (aria-label "Mostrar
  // senha" / "Ocultar senha", que entrou na v1.10.0). `getByLabel` casa por
  // substring e sem diferenciar caixa, então sem isto o seletor é ambíguo e o
  // Playwright recusa com "strict mode violation" — foi o que derrubou 45 dos
  // 46 testes da suíte.
  await page.getByLabel("Senha", { exact: true }).fill(NO_LUGAR_DA_SENHA);
  await page.getByRole("button", { name: "Entrar" }).click();
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.includes("/login"), {
    timeout: 10_000,
  });
}

export async function login(
  page: Page,
  role: keyof typeof CREDENTIALS = "admin",
) {
  const { email, password } = CREDENTIALS[role];
  await entrarSemExporASenha(page, email, password);
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: /Menu do usuário/i }).click();
  await page.getByRole("button", { name: "Sair" }).click();
  await page.waitForURL("**/login");
}
