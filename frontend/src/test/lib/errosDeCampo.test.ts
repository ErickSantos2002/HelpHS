import { describe, expect, it } from "vitest";
import { errosDeCampo } from "../../lib/errosDeCampo";

const resposta = (status: number, data: unknown) => ({ response: { status, data } });

describe("errosDeCampo", () => {
  it("lê o 422 do contrato: `{field, message}`", () => {
    const err = resposta(422, { detail: [{ field: "category", message: "Valor inválido." }] });
    expect(errosDeCampo(err)).toEqual([{ campo: "category", mensagem: "Valor inválido." }]);
  });

  it("campo composto vira o campo do formulário", () => {
    const err = resposta(422, { detail: [{ field: "equipment_ids.0", message: "Id inválido." }] });
    expect(errosDeCampo(err)).toEqual([{ campo: "equipment_ids", mensagem: "Id inválido." }]);
  });

  it("aceita o formato cru do FastAPI, `{loc, msg}`, sem o prefixo `body`", () => {
    const err = resposta(422, { detail: [{ loc: ["body", "title"], msg: "Campo obrigatório" }] });
    expect(errosDeCampo(err)).toEqual([{ campo: "title", mensagem: "Campo obrigatório" }]);
  });

  it("um aviso por campo: o primeiro", () => {
    const err = resposta(422, {
      detail: [
        { field: "title", message: "Curto demais." },
        { field: "title", message: "Outro motivo." },
      ],
    });
    expect(errosDeCampo(err)).toEqual([{ campo: "title", mensagem: "Curto demais." }]);
  });

  it("traceback não vira mensagem de campo", () => {
    const err = resposta(422, {
      detail: [{ field: "title", message: "Traceback (most recent call last): boom" }],
    });
    expect(errosDeCampo(err)).toEqual([]);
  });

  it("o que não é 422 de campos devolve vazio", () => {
    expect(errosDeCampo(resposta(500, "Internal Server Error"))).toEqual([]);
    expect(errosDeCampo(resposta(422, { detail: "texto" }))).toEqual([]);
    expect(errosDeCampo(resposta(400, { detail: [{ field: "x", message: "y" }] }))).toEqual([]);
    expect(errosDeCampo({ request: {} })).toEqual([]);
    expect(errosDeCampo(new Error("x"))).toEqual([]);
    expect(errosDeCampo(undefined)).toEqual([]);
  });
});
