import { describe, it, expect } from "vitest";
import { isValidCnpj, isValidCep, onlyDigits } from "../../lib/documents";

describe("onlyDigits", () => {
  it("remove máscara", () => {
    expect(onlyDigits("08.857.492/0001-48")).toBe("08857492000148");
  });
});

describe("isValidCnpj", () => {
  it("aceita um CNPJ válido com máscara", () => {
    expect(isValidCnpj("08.857.492/0001-48")).toBe(true);
  });

  it("aceita um CNPJ válido sem máscara", () => {
    expect(isValidCnpj("08857492000148")).toBe(true);
  });

  it("rejeita dígito verificador errado", () => {
    expect(isValidCnpj("08857492000149")).toBe(false);
  });

  it("rejeita todos os dígitos iguais", () => {
    expect(isValidCnpj("11111111111111")).toBe(false);
  });

  it("rejeita quantidade de dígitos errada", () => {
    expect(isValidCnpj("123")).toBe(false);
  });

  it("rejeita string vazia", () => {
    expect(isValidCnpj("")).toBe(false);
  });
});

describe("isValidCep", () => {
  it("aceita CEP com máscara", () => {
    expect(isValidCep("50070-000")).toBe(true);
  });

  it("aceita CEP sem máscara", () => {
    expect(isValidCep("50070000")).toBe(true);
  });

  it("rejeita CEP incompleto", () => {
    expect(isValidCep("5007")).toBe(false);
  });

  it("rejeita string vazia", () => {
    expect(isValidCep("")).toBe(false);
  });
});
