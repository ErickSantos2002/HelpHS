/**
 * Telefone no front: máscara, forma canônica e o acordo com o backend.
 *
 * O ponto destes testes não é só "a função funciona": é que `toE164` aqui e
 * `normaliza_telefone` em `backend/app/utils/telefone.py` precisam concordar.
 * Quando divergem, o front deixa passar o que o backend recusa — e o usuário
 * leva um 422 sem entender por quê, que é exatamente o defeito que a Fase 1A
 * veio fechar.
 *
 * Os casos abaixo são os MESMOS de `backend/tests/test_telefone.py`, de
 * propósito: se alguém mudar uma ponta, a outra fica vermelha.
 */

import { describe, expect, it } from "vitest";

import {
  ERRO_TELEFONE,
  formatPhone,
  isValidPhone,
  maskPhoneInput,
  toE164,
} from "../../lib/telefone";

describe("toE164 — acordo com o backend", () => {
  it.each([
    ["81999999999", "+5581999999999"],
    ["5581999999999", "+5581999999999"],
    ["+5581999999999", "+5581999999999"],
    ["(81) 99999-9999", "+5581999999999"],
    ["8133334444", "+558133334444"],
    ["(81) 3333-4444", "+558133334444"],
    ["558133334444", "+558133334444"],
    ["+55 (81) 99999-9999", "+5581999999999"],
    ["81 99999 9999", "+5581999999999"],
    ["81.99999.9999", "+5581999999999"],
  ])("normaliza %s", (entrada, esperado) => {
    expect(toE164(entrada)).toBe(esperado);
  });

  it("é idempotente", () => {
    const umaVez = toE164("(81) 99999-9999");
    expect(toE164(umaVez)).toBe(umaVez);
  });

  it("aceita internacional com DDI explícito", () => {
    expect(toE164("+351912345678")).toBe("+351912345678");
    expect(toE164("+1 415 555 2671")).toBe("+14155552671");
  });

  it.each([
    ["abc", "letra pura"],
    ["9999", "curto demais"],
    ["999999999", "9 dígitos: nem fixo com DDD, nem celular"],
    ["123456789012", "12 dígitos que não começam com 55"],
    ["+0581999999999", "E.164 não começa com zero"],
    ["+55819999999999999", "passa dos 15 dígitos"],
    ["+55", "só o DDI"],
    ["0081999999999", "prefixo discado, não E.164"],
    ["01999999999", "DDD não pode ter zero"],
    ["81899999999", "celular que não começa com 9"],
    ["8199999999", "celular antigo de 8 dígitos"],
    ["+55819999", "com +55, mas nacional curto demais"],
    ["+558199999999999", "com +55, mas nacional longo demais"],
  ])("recusa %s (%s)", (entrada) => {
    expect(toE164(entrada)).toBeNull();
    expect(isValidPhone(entrada)).toBe(false);
  });

  it("trata ausência como ausência, não como erro de formato", () => {
    expect(toE164("")).toBeNull();
    expect(toE164("   ")).toBeNull();
    expect(toE164(null)).toBeNull();
    expect(toE164(undefined)).toBeNull();
  });

  it("aceita número de dígito repetido — é o exemplo do próprio produto", () => {
    expect(toE164("(81) 99999-9999")).toBe("+5581999999999");
  });

  // O campo se chama `phone`, não `mobile`: recusar o celular antigo de oito
  // dígitos não pode ter levado o fixo junto. Os dois têm dez dígitos, e a
  // diferença está só no primeiro dígito do assinante.
  it.each([
    ["(81) 3333-1234", "+558133331234"],
    ["8133331234", "+558133331234"],
    ["+558133331234", "+558133331234"],
    ["5581 3333-1234", "+558133331234"],
    ["(81) 2222-1234", "+558122221234"],
    ["(81) 4444-1234", "+558144441234"],
    ["(81) 5555-1234", "+558155551234"],
  ])("aceita fixo brasileiro %s", (entrada, esperado) => {
    expect(toE164(entrada)).toBe(esperado);
  });

  it.each(["(81) 9999-9999", "8199999999", "(81) 8888-9999"])(
    "recusa celular antigo de 8 dígitos %s",
    (entrada) => {
      expect(toE164(entrada)).toBeNull();
    },
  );
});

describe("maskPhoneInput", () => {
  it("vai pontuando conforme se digita", () => {
    expect(maskPhoneInput("8")).toBe("8");
    expect(maskPhoneInput("81")).toBe("81");
    expect(maskPhoneInput("819")).toBe("(81) 9");
    expect(maskPhoneInput("819999")).toBe("(81) 9999");
    expect(maskPhoneInput("8133334444")).toBe("(81) 3333-4444");
    expect(maskPhoneInput("81999999999")).toBe("(81) 99999-9999");
  });

  it("trava no 11º dígito", () => {
    expect(maskPhoneInput("81999999999999")).toBe("(81) 99999-9999");
  });

  it("é idempotente sobre o próprio resultado", () => {
    const uma = maskPhoneInput("81999999999");
    expect(maskPhoneInput(uma)).toBe(uma);
  });
});

describe("formatPhone", () => {
  it("exibe E.164 com máscara brasileira", () => {
    expect(formatPhone("+5581999999999")).toBe("(81) 99999-9999");
    expect(formatPhone("+558133334444")).toBe("(81) 3333-4444");
  });

  it("devolve vazio para ausência", () => {
    expect(formatPhone(null)).toBe("");
    expect(formatPhone(undefined)).toBe("");
    expect(formatPhone("")).toBe("");
  });

  it("devolve o valor cru quando não reconhece — não inventa máscara", () => {
    // Linha legada fora do padrão: mascarar por cima esconderia o problema.
    expect(formatPhone("ramal 4")).toBe("ramal 4");
    expect(formatPhone("+351912345678")).toBe("+351912345678");
  });
});

describe("mensagem", () => {
  it("é única — as três telas diziam coisas diferentes", () => {
    expect(ERRO_TELEFONE).toContain("(81) 99999-9999");
  });
});
