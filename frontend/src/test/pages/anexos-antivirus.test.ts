import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Os três estados do antivírus, e a garantia de que continuam visíveis.
 *
 * Lê o arquivo em vez de montar a `TicketDetailPage`, que tem mais de duas mil
 * linhas e arrasta roteador, sessão, chat e sugestões da base de conhecimento
 * para prender um selo — mesma escolha dos testes do link de pular e do botão
 * de sair.
 *
 * ── Os três estados, e por que só um vira selo ────────────────────────
 *
 * A varredura do ClamAV é **síncrona**, feita antes de persistir
 * (`backend/app/routers/attachments.py`). Então:
 *
 * | Estado | No banco | Onde o usuário vê |
 * |---|---|---|
 * | verificado e limpo | `virus_scanned = true` | sem selo — é o esperado |
 * | **não verificado** | `virus_scanned = false` | **selo de aviso** |
 * | rejeitado | não vira linha | 422 com o motivo, no `toastApiError` |
 *
 * O rejeitado nunca chega a ser um anexo: `scan_bytes` devolve
 * `(False, "Virus: …")`, o router levanta 422 com
 * `detail: "File 'X' rejected: …"`, e o arquivo não é gravado. Quem mostra o
 * motivo é a tela de envio.
 *
 * O **não verificado** é o que este teste guarda, e é o que estava invisível: o
 * `virus_scanned` existe no tipo e no schema desde sempre, e **nenhuma tela o
 * lia**. Um arquivo gravado sem exame parecia idêntico a um examinado.
 */
const TELA = readFileSync(
  resolve(process.cwd(), "src/pages/tickets/TicketDetailPage.tsx"),
  "utf-8",
);

const SERVICO = readFileSync(
  resolve(process.cwd(), "src/services/attachmentService.ts"),
  "utf-8",
);

describe("estado do antivírus nos anexos", () => {
  it("o anexo não verificado ganha selo de aviso", () => {
    expect(TELA).toMatch(/!attachment\.virus_scanned/);
    expect(TELA).toMatch(/não verificado/);
  });

  it("o selo explica o motivo, e não só rotula", () => {
    // "não verificado" sozinho não diz o que aconteceu nem o que fazer. O
    // título carrega a causa: o antivírus estava fora quando o arquivo subiu.
    expect(TELA).toMatch(/antivírus estava indisponível/i);
  });

  it("o anexo verificado NÃO ganha selo", () => {
    // Carimbar "verificado" em todo anexo viraria ruído e ensinaria a ignorar
    // o selo — que é justamente o oposto do que ele existe para fazer. O selo
    // só aparece no estado que pede atenção.
    const trecho = TELA.slice(
      TELA.indexOf("function AttachmentItem"),
      TELA.indexOf("function AttachmentItem") + 3000,
    );
    expect(trecho).not.toMatch(/variant="success"/);
  });

  it("o campo continua no contrato do serviço", () => {
    // Se o backend parar de mandar `virus_scanned`, o selo some em silêncio e
    // todo anexo passa a parecer verificado. Este teste é o que faz a remoção
    // aparecer aqui em vez de na tela.
    expect(SERVICO).toMatch(/virus_scanned:\s*boolean/);
    expect(SERVICO).toMatch(/virus_clean:\s*boolean/);
  });

  it("o motivo da rejeição chega pelo toast, e o serviço não o engole", () => {
    // O 422 do antivírus tem que subir do serviço para a tela: é lá que o
    // `toastApiError` mostra o `detail` como descrição.
    expect(TELA).toMatch(/toastApiError\(err, "Falha no upload/);
  });
});
