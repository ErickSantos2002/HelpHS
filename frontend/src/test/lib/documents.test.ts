import { describe, it, expect } from "vitest";
import { isValidCnpj, isValidCep, onlyDigits, formatCnpj, maskCnpjInput } from "../../lib/documents";

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

describe("formatCnpj", () => {
  it("mascara os 14 dígitos crus que vêm do banco", () => {
    expect(formatCnpj("08857492000148")).toBe("08.857.492/0001-48");
  });

  it("mascara valor que ainda chega com pontuação (linha antiga do banco)", () => {
    expect(formatCnpj("08.857.492/0001-48")).toBe("08.857.492/0001-48");
  });

  it("devolve vazio para nulo, indefinido ou vazio", () => {
    expect(formatCnpj(null)).toBe("");
    expect(formatCnpj(undefined)).toBe("");
    expect(formatCnpj("")).toBe("");
  });

  it("devolve o valor original quando não são 14 dígitos, sem inventar máscara", () => {
    expect(formatCnpj("123")).toBe("123");
  });
});

describe("maskCnpjInput", () => {
  it("mascara progressivamente enquanto se digita", () => {
    expect(maskCnpjInput("08")).toBe("08");
    expect(maskCnpjInput("088")).toBe("08.8");
    expect(maskCnpjInput("08857492000148")).toBe("08.857.492/0001-48");
  });

  it("para de aceitar depois do 14o digito", () => {
    expect(maskCnpjInput("088574920001489999")).toBe("08.857.492/0001-48");
  });

  it("ignora o que nao for digito", () => {
    expect(maskCnpjInput("08abc857")).toBe("08.857");
  });

  it("devolve vazio para entrada vazia", () => {
    expect(maskCnpjInput("")).toBe("");
  });
});
