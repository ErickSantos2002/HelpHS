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
