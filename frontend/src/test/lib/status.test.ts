import { describe, expect, it } from "vitest";
import {
  SLOT_DE_STATUS,
  STATUS,
  STATUS_ORDEM,
  slotDeStatus,
  varianteDeStatus,
  rotuloDeStatus,
  ehTerminal,
} from "../../lib/status";

/**
 * A tabela status → slot da emenda **E18**, e o que ela promete.
 *
 * Ela é **fixa e igual nos dois repositórios**, e essa é a única coisa que a faz
 * funcionar: com `--chart-*` a cor deixou de significar — o sétimo slot é
 * pervinca no claro e sálvia no escuro, e nenhuma das duas diz "cancelado". Sem
 * a ordem combinada, "Resolvidos" mudaria de cor entre o painel e o relatório, e
 * ninguém veria: cada tela estaria internamente coerente.
 */
describe("status — a tabela da E18", () => {
  it("os sete status têm slot, e nenhum divide com outro", () => {
    // Dois status no mesmo slot fariam duas séries diferentes pintarem igual —
    // que é exatamente o que a paleta existe para impedir.
    const slots = Object.values(SLOT_DE_STATUS);
    expect(slots).toHaveLength(7);
    expect(new Set(slots).size).toBe(7);
  });

  it("a tabela é a da E18, literal", () => {
    // Comparada LITERAL, e não derivada de `STATUS_ORDEM` — porque as duas
    // ordens são diferentes de propósito, e a primeira versão deste caso
    // reprovou justamente por assumir que eram a mesma.
    //
    // A E18 segue o `STATUS` do `Badge.jsx` do pacote, que lista
    // `awaiting_client` antes de `awaiting_technical`. O campo `ordem` do
    // módulo segue o quadro, que sempre teve o técnico primeiro.
    expect(SLOT_DE_STATUS).toEqual({
      open: "var(--chart-1)",
      in_progress: "var(--chart-2)",
      awaiting_client: "var(--chart-3)",
      awaiting_technical: "var(--chart-4)",
      resolved: "var(--chart-5)",
      closed: "var(--chart-6)",
      cancelled: "var(--chart-7)",
    });
  });

  it("a ordem do QUADRO e a da E18 são diferentes, e isso é deliberado", () => {
    // Sem este caso, alguém "consertaria" a divergência derivando uma da outra
    // — e a cor de um status passaria a mudar entre os dois repositórios, que é
    // exatamente o que a tabela fixa existe para impedir.
    const porColuna = STATUS_ORDEM.map((s) => SLOT_DE_STATUS[s]);
    const porTabela = Object.values(SLOT_DE_STATUS);
    expect(porColuna).not.toEqual(porTabela);
    expect(STATUS.awaiting_technical.ordem).toBeLessThan(
      STATUS.awaiting_client.ordem,
    );
  });

  it("status desconhecido recua para o NEUTRO, e não pega slot emprestado", () => {
    // Emprestar o slot de outro faria duas séries pintarem igual em silêncio.
    expect(slotDeStatus("triagem")).toBe("var(--border-control)");
    expect(Object.values(SLOT_DE_STATUS)).not.toContain(slotDeStatus("triagem"));
  });

  it("os dois `awaiting_*` compartilham a variante, e NÃO o slot", () => {
    // Na interface eles são o mesmo estado — o chamado está parado esperando
    // alguém — e a §16 os pinta igual, com o rótulo separando. No gráfico são
    // duas séries, e séries que pintam igual deixam de ser duas.
    expect(varianteDeStatus("awaiting_client")).toBe("warning");
    expect(varianteDeStatus("awaiting_technical")).toBe("warning");
    expect(SLOT_DE_STATUS.awaiting_client).not.toBe(
      SLOT_DE_STATUS.awaiting_technical,
    );
  });

  it("os acessores recuam sem derrubar a tela", () => {
    // O dado vem da REDE: um status novo no backend não pode quebrar nada.
    expect(rotuloDeStatus("triagem")).toBe("triagem");
    expect(varianteDeStatus("triagem")).toBe("muted");
    expect(ehTerminal("triagem")).toBe(false);
  });

  it("todo status da tabela existe no módulo", () => {
    // As duas tabelas são escritas à mão, lado a lado, e nada além disto
    // impede que uma ganhe uma chave e a outra não.
    expect(Object.keys(SLOT_DE_STATUS).sort()).toEqual(Object.keys(STATUS).sort());
  });
});
