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

  it("toda categoria oferecida tem descrição", () => {
    // "Outro" era a única sem frase, e saiu (INC-01). Categoria nova chega com
    // a frase dela, ou este caso reprova.
    const semDescricao = CATEGORIAS.filter((c) => !c.descricao).map((c) => c.value);
    expect(semDescricao).toEqual([]);
  });

  it("'other' não é oferecido: a API recusa o valor desde 18/09/2026 (INC-01)", () => {
    // O backend tirou `other` do enum no PR #28 e responde 422 a quem o manda.
    // A tela continuou oferecendo "Outro", e quem o escolhia via "Erro ao
    // salvar o chamado" sem saber por quê. "Geral" é o balde que ficou.
    expect(CATEGORIAS.map((c) => c.value)).not.toContain("other");
    expect(CATEGORIAS.map((c) => c.label)).not.toContain("Outro");
    expect(CATEGORIAS.map((c) => c.value)).toContain("general");
  });

  it("valor antigo que chega do servidor ainda ganha nome, sem virar opção", () => {
    // Um registro anterior à remoção, se existir, aparece com o valor cru em
    // vez de quebrar a tela — o mesmo recuo de qualquer valor desconhecido.
    expect(rotuloDeCategoria("other")).toBe("other");
    expect(descricaoDeCategoria("other")).toBeUndefined();
  });

  it("valor que esta lista não conhece não inventa frase", () => {
    // O rótulo recua para o valor cru; a descrição cala. Mostrar o nome sem
    // significado é honesto; escolher a frase de outra categoria, não.
    expect(descricaoDeCategoria("billing")).toBeUndefined();
    expect(rotuloDeCategoria("billing")).toBe("billing");
  });

  it("as sete categorias são as do enum do backend, na mesma ordem", () => {
    // O `value` é o enum `TicketCategory` (backend/app/models/models.py), e a
    // ordem é a que a grade de fichas desenha. O lado do backend confere esta
    // mesma lista em `backend/tests/test_categoria_contrato_front.py`.
    expect(CATEGORIAS.map((c) => c.value)).toEqual([
      "hardware",
      "software",
      "network",
      "access",
      "email",
      "security",
      "general",
    ]);
  });
});
