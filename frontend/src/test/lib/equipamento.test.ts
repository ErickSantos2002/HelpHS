import { describe, expect, it } from "vitest";
import {
  conheceEmpresaDoEquipamento,
  ehDoProprioCliente,
  empresasDivergem,
  situacaoDeEmpresa,
} from "../../lib/equipamento";

/**
 * A leitura que as telas fazem dos campos da ECE-01.
 *
 * Nenhuma destas funções decide permissão — o backend decide. O que elas
 * prendem é a diferença entre campo AUSENTE (API anterior ao campo) e campo
 * NULO (a resposta nova dizendo "não"), que é onde uma tela nova sobre uma API
 * antiga erraria calada.
 */

describe("ehDoProprioCliente", () => {
  it("só `false` explícito diz que o equipamento é de colega", () => {
    expect(ehDoProprioCliente({ is_mine: false })).toBe(false);
  });

  it.each([[true], [null], [undefined]])("is_mine=%s é tratado como próprio", (is_mine) => {
    expect(ehDoProprioCliente({ is_mine })).toBe(true);
  });

  it("resposta sem o campo (API anterior) é própria — não esconde editar de quem é dono", () => {
    expect(ehDoProprioCliente({})).toBe(true);
  });
});

describe("conheceEmpresaDoEquipamento", () => {
  it("campo ausente é API antiga; nulo é a API nova dizendo 'sem empresa'", () => {
    expect(conheceEmpresaDoEquipamento({})).toBe(false);
    expect(conheceEmpresaDoEquipamento({ equipment_company_id: null })).toBe(true);
    expect(conheceEmpresaDoEquipamento({ equipment_company_id: "c1" })).toBe(true);
  });
});

describe("situacaoDeEmpresa", () => {
  it("com empresa, está classificado", () => {
    expect(situacaoDeEmpresa({ equipment_company_id: "c1" })).toBe("classificado");
  });

  it("sem empresa e com a marca, foi decisão da equipe", () => {
    expect(
      situacaoDeEmpresa({ equipment_company_id: null, no_company_by_decision: true }),
    ).toBe("sem_empresa_por_decisao");
  });

  it.each([[false], [null], [undefined]])(
    "sem empresa e marca=%s, falta classificar",
    (no_company_by_decision) => {
      expect(situacaoDeEmpresa({ equipment_company_id: null, no_company_by_decision })).toBe(
        "a_classificar",
      );
    },
  );
});

describe("empresasDivergem", () => {
  const COM_RESPONSAVEL = { owner_id: "u1" };

  it("mesma empresa nos dois lados não diverge", () => {
    expect(
      empresasDivergem({ ...COM_RESPONSAVEL, equipment_company_id: "c1", linked_company_id: "c1" }),
    ).toBe(false);
  });

  it("empresas diferentes divergem", () => {
    expect(
      empresasDivergem({ ...COM_RESPONSAVEL, equipment_company_id: "c1", linked_company_id: "c2" }),
    ).toBe(true);
  });

  it("equipamento classificado com responsável sem vínculo diverge", () => {
    expect(
      empresasDivergem({ ...COM_RESPONSAVEL, equipment_company_id: "c1", linked_company_id: null }),
    ).toBe(true);
  });

  it("equipamento a classificar com responsável vinculado diverge", () => {
    expect(
      empresasDivergem({ ...COM_RESPONSAVEL, equipment_company_id: null, linked_company_id: "c2" }),
    ).toBe(true);
  });

  it("nenhum dos dois tem empresa: não há o que divergir", () => {
    expect(
      empresasDivergem({ ...COM_RESPONSAVEL, equipment_company_id: null, linked_company_id: null }),
    ).toBe(false);
  });

  it("sem empresa POR DECISÃO não é divergência — a equipe já sabe", () => {
    expect(
      empresasDivergem({
        ...COM_RESPONSAVEL,
        equipment_company_id: null,
        no_company_by_decision: true,
        linked_company_id: "c2",
      }),
    ).toBe(false);
  });

  it("sem responsável não há com o que divergir", () => {
    expect(
      empresasDivergem({ owner_id: null, equipment_company_id: "c1", linked_company_id: null }),
    ).toBe(false);
  });

  it("API antiga (campo ausente) nunca acusa divergência", () => {
    expect(empresasDivergem({ ...COM_RESPONSAVEL, linked_company_id: "c2" })).toBe(false);
  });
});
