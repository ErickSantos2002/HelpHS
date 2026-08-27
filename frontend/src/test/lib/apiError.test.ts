import { describe, it, expect } from "vitest";
import { getApiError, getApiErrorParts } from "../../lib/apiError";

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
