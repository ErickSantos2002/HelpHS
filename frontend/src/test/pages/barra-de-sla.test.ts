import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * A barra de prazo da lista de chamados, e a semântica que ela não tinha.
 *
 * Lê o arquivo em vez de montar a `TicketListPage`: a barra é uma função local
 * não exportada, e montar a página arrastaria roteador, sessão, filtros e a
 * chamada de listagem para prender cinco atributos — mesma escolha dos testes
 * do link de pular, do botão de sair e do estado do antivírus.
 *
 * ── De onde isto veio ─────────────────────────────────────────────────
 *
 * O `Progress.jsx` do pacote tem `role="progressbar"` e diz, no próprio
 * arquivo, que nasceu do `SlaProgresso` do ChamadosHS. O pacote **melhorou o
 * que copiou**, e a melhoria nunca voltou para nenhum dos dois consumidores.
 * Achado pela sessão do ChamadosHS ao reler a referência de um componente que
 * ela mesma tinha escrito.
 *
 * É o gêmeo da regra da E5: depois de criar um token, varra quem deveria usá-lo;
 * **e depois de emprestar um componente, releia o que fizeram com ele.**
 *
 * ── Por que só esta barra, e não as cinco ─────────────────────────────
 *
 * O HelpHS tem cinco barras desenhadas à mão, e **duas delas não são
 * progresso**: a de contagem por categoria vai de zero ao maior valor da lista,
 * não a 100, e a empilhada por status é distribuição. Pôr `role="progressbar"`
 * nelas anunciaria um número numa escala que não existe — pior que não pôr
 * papel nenhum.
 *
 * As outras três entram nas Fases 11–16, uma por tela, registradas na §29:
 * conformidade e razão como `meter`; comparação e distribuição sem papel de
 * progresso.
 */
const TELA = readFileSync(
  resolve(process.cwd(), "src/pages/tickets/TicketListPage.tsx"),
  "utf-8",
);

describe("barra de prazo de SLA", () => {
  it("as duas barras são progressbar — a do prazo e a da resposta dada", () => {
    // Duas, e não uma: o estado "primeira resposta já dada" desenha a própria
    // barra cheia, e ficaria muda se só a outra fosse tratada.
    expect(TELA.match(/role="progressbar"/g)).toHaveLength(2);
  });

  it("declara a escala completa, e não só o valor", () => {
    // `aria-valuenow` sozinho não diz nada: sem `min` e `max` o leitor de tela
    // não sabe de que escala o número saiu.
    expect(TELA).toMatch(/aria-valuemin=\{0\}/);
    expect(TELA).toMatch(/aria-valuemax=\{100\}/);
    expect(TELA).toMatch(/aria-valuenow=\{Math\.round\(pct\)\}/);
    expect(TELA).toMatch(/aria-valuenow=\{100\}/);
  });

  it("tem nome acessível, e ele diz de que prazo se trata", () => {
    // "Prazo de 1ª Resposta" ou "Prazo de Resolução" — sem isso a barra é
    // anunciada como "barra de progresso" e nada mais, e há uma por chamado.
    expect(TELA).toMatch(/aria-label=\{`Prazo de \$\{phase\}`\}/);
  });

  it("o anúncio é o tempo que sobra, não a porcentagem", () => {
    // `aria-valuetext` troca "65%" — que não diz nada a quem ouve — por "2h
    // 15m restantes". A porcentagem é a forma; o tempo é a informação.
    expect(TELA).toMatch(/aria-valuetext=\{breached \? "prazo vencido"/);
    expect(TELA).toMatch(/aria-valuetext=\{breach \? "respondida com atraso"/);
  });

  it("as barras de comparação NÃO viraram progressbar", () => {
    // Guarda contra o conserto por analogia: o `AdminDashboard` tem barras que
    // vão de zero ao maior valor da lista, e a `SlaConfigPage` tem uma razão.
    // Nenhuma é progresso, e as três entram nas Fases 11–16 com o papel certo.
    const painel = readFileSync(
      resolve(process.cwd(), "src/pages/dashboard/AdminDashboard.tsx"),
      "utf-8",
    );
    expect(painel).not.toMatch(/role="progressbar"/);
  });
});
