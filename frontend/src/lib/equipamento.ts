/**
 * Equipamento compartilhado por empresa (ECE-01) — o que a tela lê da API.
 *
 * Nada aqui decide permissão. O backend é quem diz de quem é o equipamento
 * (`is_mine`), de que empresa ele é e quem pode alterá-lo; estas funções só
 * traduzem a resposta em "o que mostrar".
 */

/**
 * O equipamento é de quem está logado?
 *
 * Só `false` EXPLÍCITO diz que não. Campo ausente ou nulo é a resposta de uma
 * API anterior à ECE-01, em que `/equipment/my` só devolvia os próprios — tratar
 * ausência como "de colega" esconderia editar e excluir de quem é dono.
 *
 * Isto decide o que a tela OFERECE, não o que a pessoa pode: editar ou excluir
 * equipamento de colega volta 404 do backend, com ou sem botão.
 */
export function ehDoProprioCliente(e: { is_mine?: boolean | null }): boolean {
  return e.is_mine !== false;
}

/** Os campos de empresa que a equipe recebe em cada equipamento. */
export interface EmpresasDoEquipamento {
  owner_id?: string | null;
  /** Empresa OFICIAL do responsável (vínculo feito na tela de Grupos). */
  linked_company_id?: string | null;
  linked_company_name?: string | null;
  /** Empresa DO EQUIPAMENTO (`equipments.company_id`). */
  equipment_company_id?: string | null;
  equipment_company_name?: string | null;
  /** A equipe deixou o equipamento sem empresa de propósito. */
  no_company_by_decision?: boolean | null;
}

/**
 * A API já manda a empresa do equipamento?
 *
 * `undefined` é campo AUSENTE — backend anterior à ECE-01. `null` é a resposta
 * nova dizendo "sem empresa". A diferença importa: sem ela, a tela nova sobre
 * uma API antiga diria "Sem empresa" para o parque inteiro.
 */
export function conheceEmpresaDoEquipamento(e: EmpresasDoEquipamento): boolean {
  return e.equipment_company_id !== undefined;
}

export type SituacaoDeEmpresa = "classificado" | "sem_empresa_por_decisao" | "a_classificar";

export function situacaoDeEmpresa(e: EmpresasDoEquipamento): SituacaoDeEmpresa {
  if (e.equipment_company_id) return "classificado";
  return e.no_company_by_decision ? "sem_empresa_por_decisao" : "a_classificar";
}

/**
 * A empresa do equipamento e a do responsável dizem coisas diferentes?
 *
 * Só há divergência quando existe responsável: equipamento sem responsável não
 * tem com o que divergir. E "sem empresa por decisão" não é divergência — é a
 * equipe dizendo que sabe, e que é assim mesmo.
 *
 * A tela só APONTA. Não corrige, não sugere empresa e não infere qual das duas
 * está certa: quem classifica é a equipe, equipamento por equipamento.
 */
export function empresasDivergem(e: EmpresasDoEquipamento): boolean {
  if (!conheceEmpresaDoEquipamento(e) || !e.owner_id) return false;
  if (situacaoDeEmpresa(e) === "sem_empresa_por_decisao") return false;
  return (e.equipment_company_id ?? null) !== (e.linked_company_id ?? null);
}
