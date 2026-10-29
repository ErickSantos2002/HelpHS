import { describe, it, expect } from "vitest";
import { getApiError, getApiErrorParts, getRetryAfterSeconds } from "../../lib/apiError";

describe("getApiError", () => {
  it("usa o detail quando vem como string", () => {
    const err = { response: { status: 403, data: { detail: "Motivo específico." } } };
    expect(getApiError(err)).toBe("Motivo específico.");
  });

  it("traduz mensagens técnicas que ainda chegam em inglês", () => {
    const err = { response: { status: 404, data: { detail: "Ticket not found" } } };
    expect(getApiError(err)).toContain("não encontrado");
  });

  it("traduz o 404 de anexo — o que o cliente vê para anexo alheio", () => {
    // Desde que a recusa de chamado alheio virou 404 indistinguível do id
    // inexistente, "Attachment not found" é o que chega ao cliente ao pedir
    // anexo de chamado que não é dele — e ao pedir anexo que não existe.
    // Sem a tradução, o toast mostrava a string crua em inglês, que foi
    // exatamente o bug que o 2db8dfa consertou para equipamento.
    const err = { response: { status: 404, data: { detail: "Attachment not found" } } };
    expect(getApiError(err)).toBe("Anexo não encontrado. Ele pode ter sido excluído.");
  });

  it("traduz o 404 de equipamento — o que o cliente vê para equipamento alheio", () => {
    // Desde que a recusa por dono virou 404 indistinguível do id inexistente,
    // "Equipment not found" é a mensagem que chega ao cliente nesse caso.
    // Sem a tradução, o toast mostrava a string crua em inglês.
    const err = { response: { status: 404, data: { detail: "Equipment not found" } } };
    expect(getApiError(err)).toBe("Equipamento não encontrado. Ele pode ter sido excluído.");
  });

  it("extrai a mensagem de erro de validação do FastAPI", () => {
    const err = {
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ["body", "cnpj"], msg: "O CNPJ deve conter 14 dígitos.", type: "value_error" },
          ],
        },
      },
    };
    expect(getApiError(err)).toContain("O CNPJ deve conter 14 dígitos.");
  });

  it("junta múltiplos erros de validação", () => {
    const err = {
      response: {
        status: 422,
        data: {
          detail: [
            { loc: ["body", "cnpj"], msg: "CNPJ inválido." },
            { loc: ["body", "company_cep"], msg: "CEP inválido." },
          ],
        },
      },
    };
    const msg = getApiError(err);
    expect(msg).toContain("CNPJ inválido.");
    expect(msg).toContain("CEP inválido.");
  });

  it("avisa quando o servidor não respondeu", () => {
    const err = { request: {}, message: "Network Error" };
    expect(getApiError(err)).toContain("conexão");
  });

  it("usa mensagem própria para 500 sem detail", () => {
    const err = { response: { status: 500, data: {} } };
    expect(getApiError(err)).toContain("servidor");
  });

  it("usa mensagem própria para 409 sem detail", () => {
    const err = { response: { status: 409, data: {} } };
    expect(getApiError(err)).toContain("conflita");
  });

  it("cai no fallback quando não há nada aproveitável", () => {
    expect(getApiError({}, "Falha ao salvar.")).toBe("Falha ao salvar.");
  });

  it("ignora detail vazio", () => {
    const err = { response: { status: 400, data: { detail: "   " } } };
    expect(getApiError(err, "Falha ao salvar.")).not.toBe("   ");
  });
});

describe("getApiErrorParts", () => {
  it("separa a ação que falhou do motivo", () => {
    const err = {
      response: { status: 403, data: { detail: "Apenas o responsável pode alterar." } },
    };
    const { title, description } = getApiErrorParts(err, "Não foi possível atribuir o ticket.");
    expect(title).toBe("Não foi possível atribuir o ticket.");
    expect(description).toBe("Apenas o responsável pode alterar.");
  });

  it("fica sem descrição quando não há motivo conhecido", () => {
    const { title, description } = getApiErrorParts({}, "Não foi possível atribuir o ticket.");
    expect(title).toBe("Não foi possível atribuir o ticket.");
    expect(description).toBeUndefined();
  });
});

/**
 * O 429 traz o header Retry-After com o tempo real da janela (calculado pelo
 * backend a partir do estado do limiter). Com ele, a mensagem diz quantos
 * minutos faltam; sem ele, vale o detail do backend — nunca um chute.
 */
describe("getApiError — 429 com Retry-After", () => {
  it("mostra os minutos exatos quando o header vem", () => {
    const err = {
      response: {
        status: 429,
        headers: { "retry-after": "720" },
        data: { detail: "Muitas tentativas. Aguarde alguns minutos e tente novamente." },
      },
    };
    expect(getApiError(err)).toBe("Muitas tentativas. Aguarde 12 minutos e tente novamente.");
  });

  it("arredonda para cima e usa o singular quando falta menos de um minuto", () => {
    const err = { response: { status: 429, headers: { "retry-after": "45" }, data: {} } };
    expect(getApiError(err)).toBe("Muitas tentativas. Aguarde 1 minuto e tente novamente.");
  });

  it("sem o header, mantém a mensagem do backend", () => {
    const err = {
      response: {
        status: 429,
        headers: {},
        data: { detail: "Muitas tentativas. Aguarde alguns minutos e tente novamente." },
      },
    };
    expect(getApiError(err)).toBe("Muitas tentativas. Aguarde alguns minutos e tente novamente.");
  });
});

/**
 * O relógio da tela de login precisa dos segundos crus, não da frase pronta —
 * este extrator é a fonte única do Retry-After no front.
 */
describe("getRetryAfterSeconds", () => {
  it("devolve os segundos quando o header vem", () => {
    const err = { response: { status: 429, headers: { "retry-after": "90" } } };
    expect(getRetryAfterSeconds(err)).toBe(90);
  });

  it("devolve null sem header, com valor inválido ou zerado", () => {
    expect(getRetryAfterSeconds({ response: { status: 429, headers: {} } })).toBeNull();
    expect(
      getRetryAfterSeconds({ response: { status: 429, headers: { "retry-after": "abc" } } }),
    ).toBeNull();
    expect(
      getRetryAfterSeconds({ response: { status: 429, headers: { "retry-after": "0" } } }),
    ).toBeNull();
    expect(getRetryAfterSeconds(new Error("rede"))).toBeNull();
  });
});

/**
 * O contrato real do 422 (backend/app/core/exceptions.py): `detail` é uma
 * lista de `{field, message}`. O front lia `msg`, que o backend nunca manda —
 * toda validação caía na mensagem genérica (auditoria F1-B-02). `{loc, msg}`
 * continua aceito por compatibilidade.
 */
describe("getApiError — contrato do 422 {field, message}", () => {
  const erro422 = (detail: unknown) => ({ response: { status: 422, data: { detail } } });

  it("lê o message do formato que o backend devolve", () => {
    const err = erro422([{ field: "new_password", message: "Deve ter no mínimo 8 caractere(s)" }]);
    expect(getApiError(err)).toBe("Deve ter no mínimo 8 caractere(s)");
  });

  it("junta vários erros e não repete a mesma mensagem", () => {
    const err = erro422([
      { field: "name", message: "Campo obrigatório" },
      { field: "email", message: "E-mail inválido" },
      { field: "phone", message: "Campo obrigatório" },
    ]);
    expect(getApiError(err)).toBe("Campo obrigatório E-mail inválido");
  });

  it("aceita item misto: message primeiro, msg como reserva", () => {
    const err = erro422([
      { field: "cnpj", message: "CNPJ inválido." },
      { loc: ["body", "cep"], msg: "CEP inválido." },
    ]);
    expect(getApiError(err)).toBe("CNPJ inválido. CEP inválido.");
  });

  it("aceita lista de textos soltos", () => {
    expect(getApiError(erro422(["Primeiro motivo.", "Segundo motivo."]))).toBe(
      "Primeiro motivo. Segundo motivo.",
    );
  });

  it("ignora itens que não trazem texto e cai na mensagem do status", () => {
    const err = erro422([null, 7, { field: "x" }, { message: { aninhado: true } }, { msg: "" }]);
    expect(getApiError(err)).toBe("Alguns campos não foram preenchidos corretamente.");
  });

  it("detail em objeto usa o message dele, se for texto", () => {
    expect(getApiError(erro422({ message: "Motivo do objeto." }))).toBe("Motivo do objeto.");
    expect(getApiError(erro422({ code: "x", outro: 1 }))).toBe(
      "Alguns campos não foram preenchidos corretamente.",
    );
  });

  it.each([
    ["lista", [{ field: "a", message: "ok" }]],
    ["objeto", { message: "ok" }],
    ["número", 42],
    ["booleano", true],
    ["lista aninhada", [[{ message: "dentro" }]]],
    ["null", null],
  ])("nunca devolve outra coisa que texto (detail %s)", (_nome, detail) => {
    expect(typeof getApiError(erro422(detail))).toBe("string");
    expect(typeof getApiErrorParts(erro422(detail), "Falhou.").title).toBe("string");
  });
});

describe("getApiError — respostas inesperadas e dados internos", () => {
  it("página HTML no lugar do JSON não vai para a tela", () => {
    const err = { response: { status: 502, data: "<html><body>Bad Gateway</body></html>" } };
    expect(getApiError(err)).toBe(
      "O servidor está indisponível no momento. Tente novamente em instantes.",
    );
  });

  it("traceback no detail não vai para a tela", () => {
    const err = {
      response: {
        status: 500,
        data: { detail: 'Traceback (most recent call last):\n  File "/app/x.py", line 1' },
      },
    };
    expect(getApiError(err)).toBe("Erro interno no servidor. Tente novamente em instantes.");
  });

  it.each([
    [401, "Sua sessão expirou"],
    [403, "permissão"],
    [404, "não foi encontrado"],
    [409, "conflita"],
    [422, "Alguns campos"],
  ])("sem detail, o %i mantém a mensagem própria do status", (status, trecho) => {
    expect(getApiError({ response: { status, data: {} } })).toContain(trecho);
  });

  it.each([401, 403, 404, 409])("com detail em texto, o %i mostra o texto do backend", (status) => {
    const err = { response: { status, data: { detail: "Motivo do servidor." } } };
    expect(getApiError(err)).toBe("Motivo do servidor.");
  });
});
