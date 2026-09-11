import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  CAMPO_JUSTIFICATIVA,
  LIMITE_JUSTIFICATIVA,
  avisoDePrazo,
  prazosDoErro,
  prazosPelasMarcas,
} from "../../lib/slaJustificativa";

/** O `detail` que o backend devolve, com o trecho do prazo variando. */
const DETAIL = (quais: string) =>
  `Este chamado passou do prazo (${quais}). Informe 'sla_breach_justification' com o motivo do atraso para resolvê-lo.`;

const erro = (status: number, detail: unknown) => ({
  response: { status, data: { detail } },
});

describe("prazosPelasMarcas", () => {
  it("sem marca ligada, nenhum prazo", () => {
    expect(
      prazosPelasMarcas({ sla_response_breach: false, sla_resolve_breach: false }),
    ).toEqual([]);
  });

  it("cada marca ligada nomeia o seu prazo, na ordem em que o backend nomeia", () => {
    expect(
      prazosPelasMarcas({ sla_response_breach: true, sla_resolve_breach: false }),
    ).toEqual(["o de primeira resposta"]);
    expect(
      prazosPelasMarcas({ sla_response_breach: false, sla_resolve_breach: true }),
    ).toEqual(["o de resolução"]);
    expect(
      prazosPelasMarcas({ sla_response_breach: true, sla_resolve_breach: true }),
    ).toEqual(["o de primeira resposta", "o de resolução"]);
  });
});

describe("prazosDoErro", () => {
  it("reconhece o 422 da justificativa e diz qual prazo passou", () => {
    expect(prazosDoErro(erro(422, DETAIL("o de resolução")))).toEqual([
      "o de resolução",
    ]);
    expect(
      prazosDoErro(erro(422, DETAIL("o de primeira resposta e o de resolução"))),
    ).toEqual(["o de primeira resposta", "o de resolução"]);
  });

  it("reconhece pelo nome do campo, mesmo sem saber qual prazo", () => {
    // A frase do prazo é cortesia; o nome do campo é o contrato. Sem a frase,
    // o campo ainda tem de aparecer — só sem dizer qual prazo passou.
    expect(prazosDoErro(erro(422, "Informe 'sla_breach_justification'."))).toEqual([]);
  });

  it("não confunde com outro 422", () => {
    expect(prazosDoErro(erro(422, "Alguma outra regra do chamado."))).toBeNull();
    // Texto longo demais cai na validação do Pydantic, que responde em LISTA.
    // Isso não é pedido de justificativa: é a justificativa passando do limite.
    expect(
      prazosDoErro(
        erro(422, [
          {
            loc: ["body", CAMPO_JUSTIFICATIVA],
            msg: "String should have at most 2000 characters",
          },
        ]),
      ),
    ).toBeNull();
  });

  it("não confunde com outro status que por acaso cite o campo", () => {
    expect(prazosDoErro(erro(409, DETAIL("o de resolução")))).toBeNull();
  });

  it("erro sem resposta não é pedido de justificativa", () => {
    expect(prazosDoErro(new Error("rede caiu"))).toBeNull();
    expect(prazosDoErro(undefined)).toBeNull();
  });
});

describe("avisoDePrazo", () => {
  it("nomeia os prazos quando sabe quais", () => {
    expect(avisoDePrazo(["o de resolução"])).toBe(
      "Este chamado passou do prazo (o de resolução), e o motivo do atraso é obrigatório.",
    );
    expect(avisoDePrazo(["o de primeira resposta", "o de resolução"])).toBe(
      "Este chamado passou do prazo (o de primeira resposta e o de resolução), e o motivo do atraso é obrigatório.",
    );
  });

  it("sem saber qual, não inventa", () => {
    expect(avisoDePrazo([])).toBe(
      "Este chamado passou do prazo, e o motivo do atraso é obrigatório.",
    );
  });
});

describe("contrato com o backend", () => {
  // O front reconhece o 422 pelo nome do campo no `detail` e lê dele qual
  // prazo passou. Se o backend mudar a mensagem, nada quebra no build: o campo
  // simplesmente deixa de aparecer, e o 422 volta a ser um toast sem saída —
  // o defeito que este trabalho fechou. Por isso os casos leem a fonte, e não
  // uma cópia da frase.
  //
  // O vitest roda com o cwd em `frontend/` (e o CI também), então o backend
  // fica um nível acima — o mesmo idioma do `userService.test.ts`.
  const ler = (relativo: string) => {
    const caminho = path.resolve(process.cwd(), "..", relativo);
    expect(fs.existsSync(caminho), `não encontrei ${caminho}`).toBe(true);
    return fs.readFileSync(caminho, "utf-8");
  };

  it("a recusa ainda é um 422 que cita o campo e diz qual prazo passou", () => {
    const fonte = ler("backend/app/routers/tickets.py");
    const inicio = fonte.indexOf("def _justificativa_de_sla(");
    expect(inicio, "não achei _justificativa_de_sla em tickets.py").toBeGreaterThan(-1);
    // A primeira versão cortava no próximo `\ndef ` — e depois desta função
    // só há `async def`: o corte ia até o fim do arquivo, e o `HTTP_422` de
    // outro endpoint fazia o caso passar pelo motivo errado. Mutar o status da
    // recusa para 409 não derrubava nada. Agora o corte para no próximo item de
    // topo, e o status é conferido COLADO na frase da recusa.
    const fim = fonte.slice(inicio + 1).search(/\n(@|async def |def |class |# ═)/);
    expect(fim, "não achei onde _justificativa_de_sla termina").toBeGreaterThan(0);
    const corpo = fonte.slice(inicio, inicio + 1 + fim);

    expect(corpo).toMatch(/HTTP_422\w*,\s*detail=\(\s*f"Este chamado passou do prazo/);
    expect(corpo).toContain(`'${CAMPO_JUSTIFICATIVA}'`);
    expect(corpo).toContain("passou do prazo ({' e '.join(quais)})");
    for (const prazo of prazosPelasMarcas({
      sla_response_breach: true,
      sla_resolve_breach: true,
    })) {
      expect(corpo, `o backend não nomeia mais "${prazo}"`).toContain(`"${prazo}"`);
    }
    // E a regra ainda vale nos DOIS caminhos que resolvem: a definição e as
    // chamadas no PATCH de status e no POST de resolver.
    expect(
      (fonte.match(/_justificativa_de_sla\(/g) ?? []).length,
      "o PATCH de status e o POST de resolver deixaram de passar pela regra",
    ).toBeGreaterThanOrEqual(3);
  });

  it("o limite do campo é o dos dois schemas de entrada", () => {
    // Acima do limite o backend responde 422 de VALIDAÇÃO, que não é pedido de
    // justificativa e cai no toast. O `maxLength` do campo impede chegar lá.
    const schema = ler("backend/app/schemas/ticket.py");
    const limites = [
      ...schema.matchAll(/sla_breach_justification:[^\n]*max_length=(\d+)/g),
    ].map((m) => Number(m[1]));

    expect(limites, "TicketStatusUpdate e TicketResolve declaram o campo").toHaveLength(2);
    for (const limite of limites) expect(limite).toBe(LIMITE_JUSTIFICATIVA);
  });
});
