import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../services/auditService", () => ({
  getAuditLogs: vi.fn(),
}));

import AuditLogsPage, { ACAO } from "../../pages/audit/AuditLogsPage";
import * as auditService from "../../services/auditService";
import type { AuditLog } from "../../services/auditService";

/**
 * O que esta tela tinha, e que estes casos prendem.
 *
 * **Duas tabelas para a mesma ação de auditoria**, sem regra dizendo qual
 * valia: `ACTION_OPTIONS` nomeava o filtro e `ACTION_BADGE` nomeava o selo, e
 * as duas já discordavam em `status_change` e `password_change`. **Dez cores
 * cruas do Tailwind**, uma por ação, nenhuma medida contra superfície nenhuma.
 * E **sete `<svg>` soltos** num objeto local, com um relógio e um funil
 * redesenhados à mão.
 *
 * Os casos abaixo não olham classe nenhuma — o ambiente de teste não aplica
 * CSS, então afirmar `toHaveClass` provaria só que a string está escrita.
 * Eles olham o que a pessoa alcança: o nome que ela lê no selo, o nome
 * acessível de cada campo, o que o modal abre.
 */

/**
 * O `<select>` nativo dos dois filtros (D9.2) desenha TODAS as opções na
 * árvore, o tempo todo — ao contrário do painel do `FilterSelect`, que só
 * existia enquanto aberto. Como as opções de ação carregam o rótulo LONGO,
 * um `queryByText("Mudança de status")` passa a achá-lo dentro do filtro.
 *
 * Estes casos falam do que a pessoa lê **na lista**, então a opção sai da
 * busca — e sai por `ignore`, e não por `getAllByText(...)[0]`, que continuaria
 * passando se o texto da lista sumisse.
 */
const FORA_DO_FILTRO = { ignore: "script, style, option" } as const;

const AGORA = "2026-09-08T13:45:00Z";

function log(over: Partial<AuditLog> = {}): AuditLog {
  return {
    id: "l1",
    user_id: "11111111-2222-3333-4444-555555555555",
    user_name: "Rickelme",
    action: "create",
    entity_type: "ticket",
    entity_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    old_data: null,
    new_data: null,
    ip_address: "10.0.0.7",
    user_agent: "Mozilla/5.0",
    created_at: AGORA,
    ...over,
  } as AuditLog;
}

async function montar(items: AuditLog[], total = items.length) {
  vi.mocked(auditService.getAuditLogs).mockResolvedValue({
    items,
    total,
    limit: 20,
    offset: 0,
  });
  render(<AuditLogsPage />);
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Logs de Auditoria" }),
    ).toBeInTheDocument(),
  );
  // A lista desenha as duas formas — celular e mesa — e o ambiente de teste
  // não esconde nenhuma das duas, porque não há CSS. Esperar o selo garante
  // que a promessa já resolveu antes de qualquer asserção.
  await waitFor(() =>
    expect(vi.mocked(auditService.getAuditLogs)).toHaveBeenCalled(),
  );
}

describe("AuditLogsPage", () => {
  it("o selo diz a ação por escrito — a cor é reforço, não a informação", async () => {
    await montar([
      log({ id: "a", action: "create" }),
      log({ id: "b", action: "delete" }),
      log({ id: "c", action: "export" }),
      log({ id: "d", action: "anonymize" }),
    ]);

    // Quatro ações, e `delete`/`anonymize` compartilham a variante `danger`
    // enquanto `export` compartilha `warning` com a troca de senha. Quem não
    // distingue a cor continua tendo a informação inteira, porque ela está
    // escrita dentro do selo.
    for (const nome of ["Criação", "Exclusão", "Exportação", "Anonimização"]) {
      expect(screen.getAllByText(nome).length).toBeGreaterThan(0);
    }
  });

  it("ação que o front não conhece não derruba a tela, e aparece crua", async () => {
    // O dado vem da REDE: uma ação nova no backend não pode virar tela branca.
    await montar([log({ action: "merge" as AuditLog["action"] })]);

    expect(screen.getAllByText("merge").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", { name: "Logs de Auditoria" }),
    ).toBeInTheDocument();
  });

  it("entidade que o front não conhece também aparece crua", async () => {
    await montar([log({ entity_type: "invoice" })]);

    expect(screen.getAllByText("invoice").length).toBeGreaterThan(0);
  });

  it("a lista abrevia a ação, e o modal a diz por extenso", async () => {
    // As duas formas saem da MESMA linha da tabela: `curto` cabe na coluna de
    // 110px, `rotulo` é o nome completo. Antes eram duas tabelas soltas, e é
    // exatamente aqui que elas divergiam.
    await montar([log({ action: "status_change", new_data: { status: "closed" } })]);

    expect(screen.getAllByText("Status", FORA_DO_FILTRO).length).toBeGreaterThan(0);
    expect(
      screen.queryByText("Mudança de status", FORA_DO_FILTRO),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: "Ver detalhes" })[0]);

    const modal = await screen.findByRole("dialog");
    expect(within(modal).getByText("Mudança de status")).toBeInTheDocument();
  });

  it("cada filtro tem nome próprio, e não se anuncia pelo valor escolhido", async () => {
    // O defeito que a D9.2 fecha. O `FilterSelect` não repassava `label`, e os
    // dois filtros desta barra se anunciavam pelo VALOR — numa barra com dois,
    // quem usa leitor de tela ouvia "Criação" e "Ticket" sem saber de que
    // filtro cada um era.
    await montar([log()]);

    expect(screen.getByRole("combobox", { name: "Ação" })).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: "Entidade" }),
    ).toBeInTheDocument();
  });

  it("o filtro de ação lista as dez ações da tabela, e o filtro de entidade as seis", async () => {
    // As opções saem de `ACAO` e de `ENTIDADE`, e não de uma lista paralela —
    // é a mesma afirmação de antes, agora lida do `<select>` nativo.
    await montar([log()]);

    const acao = screen.getByRole("combobox", { name: "Ação" });
    const rotulos = within(acao)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(rotulos).toContain("Todas as ações");
    expect(rotulos).toContain("Mudança de status");
    expect(rotulos).toContain("Anonimização");
    expect(rotulos).toHaveLength(Object.keys(ACAO).length + 1);
  });

  it("escolher no filtro pede ao serviço aquele filtro, e não outro", async () => {
    await montar([log()]);

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Entidade" }),
      "kb_article",
    );

    await waitFor(() =>
      expect(auditService.getAuditLogs).toHaveBeenLastCalledWith(
        expect.objectContaining({ entity_type: "kb_article" }),
      ),
    );
  });

  it("cada campo de data tem nome acessível próprio", async () => {
    // O "De" e o "até" ao lado nunca foram `<label>` de coisa nenhuma: quem
    // navega por leitor de tela ouvia dois campos de data sem nome, e sem como
    // saber qual era o início do intervalo.
    await montar([log()]);

    expect(screen.getByLabelText("Data inicial")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("Data final")).toHaveAttribute("type", "date");
  });

  it("a busca não depende do texto de dentro do campo para se nomear", async () => {
    await montar([log()]);

    // O `placeholder` some assim que a pessoa digita a primeira letra.
    expect(screen.getByLabelText("Buscar por User ID")).toBeInTheDocument();
  });

  it("sem registro, diz que não há — e não oferece limpar filtro que não existe", async () => {
    await montar([], 0);

    expect(screen.getByText("Nenhum registro encontrado.")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Limpar filtros" }),
    ).not.toBeInTheDocument();
  });

  it("filtrar faz aparecer o Limpar filtros, e ele devolve o campo ao vazio", async () => {
    await montar([log()]);

    const busca = screen.getByLabelText("Buscar por User ID");
    await userEvent.type(busca, "abc");

    const limpar = await screen.findAllByRole("button", { name: /Limpar filtros/ });
    await userEvent.click(limpar[0]);

    await waitFor(() => expect(busca).toHaveValue(""));
  });

  it("a contagem acompanha o total, e o singular é singular", async () => {
    await montar([log({ id: "a" }), log({ id: "b" }), log({ id: "c" })], 3);
    expect(screen.getByText("3 registros")).toBeInTheDocument();
  });

  it("um único registro é contado no singular", async () => {
    await montar([log()], 1);
    expect(screen.getByText("1 registro")).toBeInTheDocument();
  });

  it("a tabela ACAO é esta, literal — as dez ações e as seis variantes", () => {
    // Comparada LITERAL, e não derivada, pelo mesmo motivo que
    // `SLOT_DE_STATUS` é: **nada no código deduz este agrupamento**. Dez ações
    // couberam em seis variantes porque alguém decidiu que exclusão e
    // anonimização são o mesmo grau de gravidade para quem audita, e que
    // exportação e troca de senha são outro. É decisão de desenho, aprovada
    // fora daqui.
    //
    // Sem este caso, trocar `danger` por `muted` na exclusão é uma edição de
    // uma palavra que nenhum outro caso reprova: a tela continua renderizando,
    // o selo continua dizendo "Exclusão", e só a cor muda — que é justamente o
    // que o ambiente de teste não vê. O mesmo vale para o rótulo longo de uma
    // ação cujo modal nenhum caso abre.
    expect(ACAO).toEqual({
      create: { rotulo: "Criação", curto: "Criação", variante: "success" },
      update: { rotulo: "Atualização", curto: "Atualização", variante: "info" },
      delete: { rotulo: "Exclusão", curto: "Exclusão", variante: "danger" },
      login: { rotulo: "Login", curto: "Login", variante: "primary" },
      logout: { rotulo: "Logout", curto: "Logout", variante: "muted" },
      export: { rotulo: "Exportação", curto: "Exportação", variante: "warning" },
      assign: { rotulo: "Atribuição", curto: "Atribuição", variante: "info" },
      status_change: {
        rotulo: "Mudança de status",
        curto: "Status",
        variante: "info",
      },
      password_change: {
        rotulo: "Troca de senha",
        curto: "Senha",
        variante: "warning",
      },
      anonymize: {
        rotulo: "Anonimização",
        curto: "Anonimização",
        variante: "danger",
      },
    });
  });

  it("as duas ações destrutivas dividem a variante, e as duas de exposição também", () => {
    // O agrupamento não é uma lista de dez escolhas soltas: é a afirmação de
    // que certos pares são o MESMO grau. Se um dia exclusão e anonimização
    // deixarem de pintar igual, o agrupamento registrado na ficha deixou de
    // valer — e isso tem de reprovar aqui, não ser descoberto na tela.
    expect(ACAO.delete.variante).toBe(ACAO.anonymize.variante);
    expect(ACAO.export.variante).toBe(ACAO.password_change.variante);
    expect(ACAO.update.variante).toBe(ACAO.assign.variante);
    expect(ACAO.update.variante).toBe(ACAO.status_change.variante);

    // E que login e logout NÃO são o mesmo grau: abrir sessão é o degrau de
    // ação, encerrar é o neutro.
    expect(ACAO.login.variante).not.toBe(ACAO.logout.variante);
  });

  it("onde as duas formas diferem, a lista usa a curta e o modal a completa", async () => {
    // A regra, e não o caso particular: as duas ações em que `rotulo` e
    // `curto` divergem são as mesmas duas em que as tabelas antigas
    // discordavam. Percorrer a tabela em vez de cravar uma ação impede que o
    // caso continue passando por acidente se a divergência mudar de linha.
    const divergentes = (Object.keys(ACAO) as (keyof typeof ACAO)[]).filter(
      (a) => ACAO[a].rotulo !== ACAO[a].curto,
    );
    expect(divergentes.length).toBeGreaterThan(0);

    for (const acao of divergentes) {
      const { rotulo, curto } = ACAO[acao];

      await montar([log({ action: acao, new_data: { x: 1 } })]);

      // Na lista, só a curta.
      expect(screen.getAllByText(curto, FORA_DO_FILTRO).length).toBeGreaterThan(0);
      expect(screen.queryByText(rotulo, FORA_DO_FILTRO)).not.toBeInTheDocument();

      // No modal, só a completa.
      await userEvent.click(
        screen.getAllByRole("button", { name: "Ver detalhes" })[0],
      );
      const modal = await screen.findByRole("dialog");
      expect(within(modal).getByText(rotulo)).toBeInTheDocument();
      expect(within(modal).queryByText(curto)).not.toBeInTheDocument();

      cleanup();
    }
  });
});
