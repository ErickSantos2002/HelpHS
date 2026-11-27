import { describe, expect, it } from "vitest";
import { errosDeCampo, pareceInterno } from "../../lib/errosDeCampo";

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

describe("pareceInterno", () => {
  it.each([
    "Traceback (most recent call last): boom",
    'File "/app/app/main.py", line 12, in handler',
    "SELECT id FROM tickets WHERE category = 'other'",
    "UPDATE users SET role = 'admin'",
    "sqlalchemy.exc.IntegrityError",
    "erro no asyncpg ao executar",
    "KeyError: 'category'",
    "ValidationError: 1 validation error",
    "<html><body>502</body></html>",
    "<!DOCTYPE html>",
    "postgresql+asyncpg://user:senha@db:5432/helphs",
    "redis://cache:6379/0",
    "https://usuario:token@interno.exemplo",
    "falha ao falar com 10.0.0.5",
  ])("reconhece texto técnico: %s", (texto) => {
    expect(pareceInterno(texto)).toBe(true);
  });

  it.each([
    "Valor inválido. Opções: hardware, software, network, access, email, security, general",
    "Este chamado já foi encerrado e não aceita alterações. Abra um novo chamado.",
    "Deve ter no máximo 200 caractere(s)",
    "Ative a verificação em duas etapas para continuar.",
    "Só é possível vincular equipamentos que pertencem a você ou à sua empresa.",
    "Selecione onde o problema acontece, de 1 a 3 opções.",
    "Atualize a página e tente de novo.",
    "Data inválida. Use o formato AAAA-MM-DD",
    "Versão 1.23.2 publicada.",
  ])("deixa passar mensagem legítima: %s", (texto) => {
    expect(pareceInterno(texto)).toBe(false);
  });
});
