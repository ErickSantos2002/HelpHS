import { describe, expect, it } from "vitest";
import {
  OPCOES_DE_PAPEL,
  PAPEIS,
  PAPEL,
  rotuloDePapel,
  varianteDePapel,
} from "../../lib/papel";

/**
 * O módulo nasceu de **cinco** cópias das mesmas três linhas, e o que estes
 * casos prendem é o que impede a sexta.
 */
describe("papel — a fonte única", () => {
  it("os três papéis têm rótulo em português, e nenhum devolve o valor cru", () => {
    // O defeito que o `ProfilePage` relatou na tela vizinha: o estado da conta
    // mostrava "inactive" e "anonymized" em inglês, porque não havia tabela.
    expect(rotuloDePapel("admin")).toBe("Administrador");
    expect(rotuloDePapel("technician")).toBe("Técnico");
    expect(rotuloDePapel("client")).toBe("Cliente");
  });

  it("a ordem é de PRIVILÉGIO, não alfabética", () => {
    // "Administrador, Técnico, Cliente" é uma escada que se entende sozinha.
    // Em ordem alfabética viraria "Administrador, Cliente, Técnico", que não
    // diz nada — e é o que sai de um `Object.keys` mal ordenado.
    expect(PAPEIS).toEqual(["admin", "technician", "client"]);
  });

  it("as opções do seletor são DERIVADAS da tabela, na mesma ordem", () => {
    // Era exatamente aqui que o `UsersPage` guardava duas das suas três cópias:
    // as opções do formulário e as do filtro, cada uma escrita à parte.
    expect(OPCOES_DE_PAPEL).toEqual([
      { value: "admin", label: "Administrador" },
      { value: "technician", label: "Técnico" },
      { value: "client", label: "Cliente" },
    ]);
    expect(OPCOES_DE_PAPEL).toHaveLength(Object.keys(PAPEL).length);
  });

  it("o papel neutro é `muted`, e não `secondary`", () => {
    // As duas cópias divergiam aqui, e a divergência não pintou diferente por
    // acaso: `secondary` e `muted` são classes IDÊNTICAS no `Badge`. Dois nomes
    // para uma aparência só escondem a divergência em vez de mostrá-la.
    expect(varianteDePapel("client")).toBe("muted");
    expect(Object.values(PAPEL).map((p) => p.variante)).not.toContain(
      "secondary",
    );
  });

  it("papel desconhecido recua sem derrubar a tela", () => {
    // O dado vem da REDE: um papel novo no backend não pode quebrar nada.
    expect(rotuloDePapel("auditor")).toBe("auditor");
    expect(varianteDePapel("auditor")).toBe("muted");
  });

  it("cada papel tem uma variante própria — dois papéis iguais não seriam três", () => {
    const variantes = Object.values(PAPEL).map((p) => p.variante);
    expect(new Set(variantes).size).toBe(variantes.length);
  });
});
