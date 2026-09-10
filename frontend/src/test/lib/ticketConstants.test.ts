import { describe, it, expect } from "vitest";
import { TICKET_TRANSITIONS } from "../../lib/ticketConstants";

// TICKET_TRANSITIONS é a máquina de estados que a tela de chamado consome
// direto: TicketDetailPage.tsx faz `TICKET_TRANSITIONS[ticket.status] ?? []` e
// mapeia o array em opções do select, na ordem em que ele está escrito. Logo o
// CONJUNTO de destinos e a ORDEM deles são observáveis pelo usuário — e por
// isso o primeiro bloco fixa o conteúdo exato das sete listas, com ordem, uma
// asserção por chave. É o único jeito de reprovar mutações como "tirar resolved
// de in_progress" ou "acrescentar closed em awaiting_client", que nenhuma
// invariante estrutural pega: o grafo continua bem formado depois delas.
//
// O segundo bloco cobra as invariantes do grafo e o terceiro as regras que
// precisam continuar valendo para qualquer estado que venha a ser criado.
// Esses dois sobrevivem a uma atualização legítima do bloco de conteúdo — é
// isso que os torna úteis, e não redundantes: eles pegam a classe "estado novo
// mal ligado", que a comparação literal, uma vez atualizada, deixaria passar.
//
// ⚠️ DIVERGÊNCIA CONHECIDA COM O BACKEND — decisão em aberto, não é defeito de
// teste e não deve ser "consertada" aqui.
// backend/app/routers/tickets.py, dicionário _TRANSITIONS, aceita o salto
// direto entre as duas esperas:
//   awaiting_client    -> {in_progress, awaiting_technical, resolved, cancelled}
//   awaiting_technical -> {in_progress, awaiting_client,    resolved, cancelled}
// O front NÃO oferece esse salto: para trocar de espera é preciso passar por
// in_progress. Ou seja, neste ponto o front é MAIS RESTRITIVO que o backend —
// ele esconde uma transição que a API aceitaria. Os testes abaixo travam o
// comportamento de HOJE, que é o do front. Se a decisão for alinhar os dois,
// este arquivo muda junto, de propósito e não por acidente.

const estados = Object.keys(TICKET_TRANSITIONS);

/** Estados sem saída: de onde o chamado não anda mais. */
const terminais = estados.filter(
  (estado) => TICKET_TRANSITIONS[estado].length === 0,
);

/** Tudo que dá para alcançar a partir de `origem`, em qualquer número de saltos. */
function alcancaveis(origem: string): Set<string> {
  const vistos = new Set<string>();
  let fronteira = TICKET_TRANSITIONS[origem] ?? [];
  while (fronteira.length > 0) {
    const proxima: string[] = [];
    for (const destino of fronteira) {
      if (vistos.has(destino)) continue;
      vistos.add(destino);
      proxima.push(...(TICKET_TRANSITIONS[destino] ?? []));
    }
    fronteira = proxima;
  }
  return vistos;
}

describe("TICKET_TRANSITIONS — conteúdo exato de cada estado", () => {
  it("o mapa cobre exatamente os sete estados do domínio", () => {
    // A ordem das CHAVES não é observável (a tela só lê a lista da chave em que
    // o chamado está), então comparo ordenado. Estado novo — ou estado que
    // sumiu — reprova aqui e obriga a decidir as listas dele conscientemente.
    expect([...estados].sort()).toEqual([
      "awaiting_client",
      "awaiting_technical",
      "cancelled",
      "closed",
      "in_progress",
      "open",
      "resolved",
    ]);
  });

  it("open oferece, nesta ordem: in_progress, cancelled", () => {
    // Aberto não pula para resolved nem para closed: o caminho até resolver
    // passa obrigatoriamente por in_progress. E não oferece espera nenhuma —
    // o backend recusaria open -> awaiting_client com 400.
    expect(TICKET_TRANSITIONS.open).toEqual(["in_progress", "cancelled"]);
  });

  it("in_progress oferece, nesta ordem: awaiting_client, awaiting_technical, resolved, cancelled", () => {
    // "resolved" aqui é a ação mais usada pelo técnico; perdê-la é a mutação
    // mais grave do arquivo, e é esta linha que a reprova.
    expect(TICKET_TRANSITIONS.in_progress).toEqual([
      "awaiting_client",
      "awaiting_technical",
      "resolved",
      "cancelled",
    ]);
  });

  it("awaiting_client oferece, nesta ordem: in_progress, resolved, cancelled", () => {
    // Sem awaiting_technical: é a divergência com o backend anotada no topo.
    expect(TICKET_TRANSITIONS.awaiting_client).toEqual([
      "in_progress",
      "resolved",
      "cancelled",
    ]);
  });

  it("awaiting_technical oferece, nesta ordem: in_progress, resolved, cancelled", () => {
    // Idem: sem awaiting_client. As duas listas são iguais hoje, mas cada uma
    // é cobrada contra o literal — comparar uma com a outra não provaria nada.
    expect(TICKET_TRANSITIONS.awaiting_technical).toEqual([
      "in_progress",
      "resolved",
      "cancelled",
    ]);
  });

  it("resolved oferece só closed", () => {
    // Depois de resolvido a saída é fechar, não cancelar.
    expect(TICKET_TRANSITIONS.resolved).toEqual(["closed"]);
  });

  it("closed e cancelled não oferecem saída nenhuma", () => {
    expect(TICKET_TRANSITIONS.closed).toEqual([]);
    expect(TICKET_TRANSITIONS.cancelled).toEqual([]);
  });
});

describe("TICKET_TRANSITIONS — invariantes da máquina de estados", () => {
  it("todo destino também existe como chave do mapa", () => {
    // Destino órfão significa mover o chamado para um estado sobre o qual a
    // UI não saberia oferecer nada depois: TICKET_TRANSITIONS[status] ?? [].
    const orfaos = estados
      .flatMap((origem) => TICKET_TRANSITIONS[origem])
      .filter((destino) => !(destino in TICKET_TRANSITIONS));
    expect(orfaos).toEqual([]);
  });

  it("nenhum estado transiciona para si mesmo", () => {
    // Um self-loop viraria "mudar para o status em que já estou" no select.
    const comLaco = estados.filter((estado) =>
      TICKET_TRANSITIONS[estado].includes(estado),
    );
    expect(comLaco).toEqual([]);
  });

  it("nenhuma lista de destinos tem estado repetido", () => {
    const comRepetido = estados.filter(
      (estado) =>
        new Set(TICKET_TRANSITIONS[estado]).size !==
        TICKET_TRANSITIONS[estado].length,
    );
    expect(comRepetido).toEqual([]);
  });

  it("os únicos estados terminais são closed e cancelled", () => {
    expect([...terminais].sort()).toEqual(["cancelled", "closed"]);
  });

  it("open é a entrada: alcança todos os outros e ninguém volta para ele", () => {
    // Estado que ninguém alcança seria linha morta no mapa; e uma transição
    // de volta para open reabriria chamado por caminho não previsto aqui.
    const daEntrada = alcancaveis("open");
    const inalcancaveis = estados.filter(
      (estado) => estado !== "open" && !daEntrada.has(estado),
    );
    expect(inalcancaveis).toEqual([]);
    expect(
      estados.filter((estado) => TICKET_TRANSITIONS[estado].includes("open")),
    ).toEqual([]);
  });

  it("de todo estado não-terminal dá para chegar a um terminal", () => {
    // DOCUMENTAÇÃO EXECUTÁVEL, e assumido como tal: com o mapa de hoje este
    // teste nunca falha sozinho — qualquer laço preso que ele pegaria já é
    // pego pelo conteúdo exato ou pela regra de "cancelar em todo estado
    // ativo". Fica porque enuncia a propriedade que ninguém pode quebrar:
    // chamado que nunca fecha nem cancela, só circulando entre estados ativos.
    const presos = estados
      .filter((estado) => !terminais.includes(estado))
      .filter(
        (estado) =>
          ![...alcancaveis(estado)].some((destino) =>
            terminais.includes(destino),
          ),
      );
    expect(presos).toEqual([]);
  });
});

describe("TICKET_TRANSITIONS — regras que valem para qualquer estado novo", () => {
  it("cancelar está disponível em todo estado ativo, menos em resolvido", () => {
    const ativos = estados.filter((estado) => !terminais.includes(estado));
    const semCancelar = ativos.filter(
      (estado) => !TICKET_TRANSITIONS[estado].includes("cancelled"),
    );
    expect(semCancelar).toEqual(["resolved"]);
  });

  it("closed só é oferecido a partir de resolved", () => {
    // Fechar direto de in_progress ou de uma das esperas é a classe de mutação
    // que o backend recusaria com 400 — não existe esse par no _TRANSITIONS de
    // lá. Cobrado sobre todos os estados, e não só sobre os quatro de hoje.
    const oferecemFechar = estados.filter((estado) =>
      TICKET_TRANSITIONS[estado].includes("closed"),
    );
    expect(oferecemFechar).toEqual(["resolved"]);
  });
});
