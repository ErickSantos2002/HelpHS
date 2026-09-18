import { describe, expect, it } from "vitest";
import {
  CATEGORIAS,
  descricaoDeCategoria,
  rotuloDeCategoria,
} from "../../lib/categoria";

/**
 * A fonte única de categoria.
 *
 * O rótulo e o ícone já moravam aqui; a descrição entrou em 18/09/2026, ditada
 * pelo operador. Ela não é enfeite da `TicketFormPage`: é parte do que a
 * categoria É, e por isso vem do mesmo lugar que o nome — a tela só desenha.
 *
 * Os textos estão presos palavra por palavra de propósito. Quem quiser trocar
 * um deles troca o teste junto, e aí a mudança aparece no `diff` em vez de
 * escorregar.
 */

const ESPERADO = [
  ["hardware", "Hardware", "Algum problema físico detectado."],
  [
    "software",
    "Software",
    "Plataforma com erro, software de registro ou de extração.",
  ],
  ["network", "Rede", "Dificuldade de conexão."],
  ["access", "Acesso", "Senha."],
  ["email", "E-mail", "Alteração de e-mail."],
  [
    "security",
    "Segurança",
    "Sua senha vazou ou está sendo usada por terceiros (LGPD).",
  ],
  [
    "general",
    "Geral",
    "Qualquer ocorrência que não se encaixe nas demais, ou quando não sabe dizer.",
  ],
] as const;

describe("categoria — a descrição", () => {
  it.each(ESPERADO)("%s (%s) descreve o que abrange", (valor, _rotulo, frase) => {
    expect(descricaoDeCategoria(valor)).toBe(frase);
  });

  it("toda frase é sentença: começa em maiúscula e termina em ponto", () => {
    for (const c of CATEGORIAS) {
      if (!c.descricao) continue;
      expect(c.descricao[0]).toBe(c.descricao[0].toUpperCase());
      expect(c.descricao.endsWith(".")).toBe(true);
    }
  });

  it("'Outro' não tem descrição, e é o único sem", () => {
    // Não é esquecimento: ele se sobrepõe a "Geral", e a decisão de tirá-lo do
    // formulário é do operador. Inventar frase aqui seria inventar diferença
    // entre duas opções que não diferem.
    expect(descricaoDeCategoria("other")).toBeUndefined();

    const semDescricao = CATEGORIAS.filter((c) => !c.descricao).map((c) => c.value);
    expect(semDescricao).toEqual(["other"]);
  });

  it("valor que esta lista não conhece não inventa frase", () => {
    // O rótulo recua para o valor cru; a descrição cala. Mostrar o nome sem
    // significado é honesto; escolher a frase de outra categoria, não.
    expect(descricaoDeCategoria("billing")).toBeUndefined();
    expect(rotuloDeCategoria("billing")).toBe("billing");
  });

  it("as oito categorias continuam as mesmas, na mesma ordem", () => {
    // A descrição entrou sem mexer no que o backend recebe: o `value` é o enum
    // `TicketCategory`, e a ordem é a que a grade de fichas desenha.
    expect(CATEGORIAS.map((c) => c.value)).toEqual([
      "hardware",
      "software",
      "network",
      "access",
      "email",
      "security",
      "general",
      "other",
    ]);
  });
});
