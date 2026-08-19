import { describe, it, expect } from "vitest";
import { cn } from "../../lib/utils";

// O ramo de string do cn já era exercitado de tabela pelos componentes; os
// ramos de objeto (clsx-style) e de array aninhado estavam sem teste — e são
// exatamente os que erram numa refatoração.
describe("cn", () => {
  it("junta strings e descarta os valores falsy", () => {
    expect(cn("btn", undefined, null, false, "btn-primary")).toBe("btn btn-primary");
  });

  it("aceita objeto clsx-style, mantendo só as chaves com valor verdadeiro", () => {
    expect(cn("base", { ativo: true, oculto: false, marcado: undefined })).toBe("base ativo");
  });

  it("achata arrays aninhados", () => {
    expect(cn("a", ["b", ["c", null], false], "d")).toBe("a b c d");
  });

  it("array que só tem falsy não deixa espaço sobrando", () => {
    // O ramo aninhado só entra no resultado se produzir algo — sem o guard,
    // sairia "a  b" com espaço duplo.
    expect(cn("a", [null, false, undefined], "b")).toBe("a b");
  });

  it("aceita número — útil para classes geradas", () => {
    expect(cn("col-", 2)).toBe("col- 2");
  });

  it("sem argumentos úteis, devolve string vazia", () => {
    expect(cn(undefined, null, false, {})).toBe("");
  });
});
