import { api } from "./api";

export interface Product {
  id: string;
  name: string;
  description: string | null;
  version: string | null;
  is_active: boolean;
}

export interface Equipment {
  id: string;
  product_id: string;
  name: string;
  serial_number: string | null;
  model: string | null;
  description: string | null;
  is_active: boolean;
  location?: string | null;
  created_at?: string;
  updated_at?: string;
  // Owner info (populated by list endpoint)
  owner_id?: string | null;
  owner_name?: string | null;
  owner_email?: string | null;
  /** Empresa DECLARADA: o que o responsável digitou no cadastro. Não é vínculo. */
  company_name?: string | null;
  company_cnpj?: string | null;
  /** Só para a equipe. */
  product_name?: string | null;
  /** Empresa OFICIAL: o vínculo feito por um admin na tela de Grupos. Só para a equipe. */
  linked_company_id?: string | null;
  linked_company_name?: string | null;
  /**
   * ECE-01, só para a equipe. Empresa DO EQUIPAMENTO (`equipments.company_id`),
   * ao lado da do responsável acima: as duas juntas mostram a divergência.
   * Ausente (`undefined`) = API anterior ao campo; `null` = sem empresa.
   */
  equipment_company_id?: string | null;
  equipment_company_name?: string | null;
  /** A equipe deixou o equipamento sem empresa de propósito — não é lacuna. */
  no_company_by_decision?: boolean | null;
}

/**
 * A empresa do equipamento, como a equipe a informa (ECE-01). São TRÊS estados,
 * e o campo ausente não é o mesmo que o campo nulo:
 *
 *   - `undefined` (campo fora do corpo): na edição, não mexe; no cadastro,
 *     o backend herda a empresa oficial do responsável;
 *   - `"<id>"`: atribui a empresa e limpa a marca de "sem empresa por decisão";
 *   - `null`: tira a empresa e MARCA que foi decisão da equipe.
 *
 * `JSON.stringify` descarta chave com `undefined` e mantém a com `null`, então
 * o tipo já é o contrato: quem monta o corpo não pode trocar um pelo outro.
 */
export type EmpresaDoEquipamentoNoCorpo = string | null | undefined;

export interface ProductListResponse {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
}

export interface EquipmentListResponse {
  items: Equipment[];
  total: number;
  limit: number;
  offset: number;
}

// ── Products ──────────────────────────────────────────────────

export async function getProducts(
  params: {
    search?: string;
    is_active?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<ProductListResponse> {
  const p = new URLSearchParams();
  if (params.search) p.set("search", params.search);
  if (params.is_active !== undefined)
    p.set("is_active", String(params.is_active));
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  const { data } = await api.get<ProductListResponse>(`/products?${p}`);
  return data;
}

export async function createProduct(payload: {
  name: string;
  description?: string;
  version?: string;
}): Promise<Product> {
  const { data } = await api.post<Product>("/products", payload);
  return data;
}

export async function updateProduct(
  id: string,
  payload: {
    name?: string;
    description?: string | null;
    version?: string | null;
  },
): Promise<Product> {
  const { data } = await api.patch<Product>(`/products/${id}`, payload);
  return data;
}

export async function setProductActive(
  id: string,
  is_active: boolean,
): Promise<Product> {
  const { data } = await api.patch<Product>(`/products/${id}`, { is_active });
  return data;
}

// ── Equipments ────────────────────────────────────────────────

/**
 * `without_owner` é o filtro de órfãos: equipamento cadastrado sem dono, que
 * o staff precisa achar para atribuir. Vai como parâmetro porque a listagem é
 * paginada no servidor — peneirar o array recebido acharia só o órfão que por
 * acaso caiu na página aberta.
 *
 * Só é mandado quando ligado: `false` teria o mesmo efeito, mas apareceria na
 * URL de toda listagem normal.
 */
export async function getEquipments(
  productId: string,
  params: {
    search?: string;
    is_active?: boolean;
    without_owner?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<EquipmentListResponse> {
  const p = new URLSearchParams();
  if (params.without_owner) p.set("without_owner", "true");
  if (params.search) p.set("search", params.search);
  if (params.is_active !== undefined)
    p.set("is_active", String(params.is_active));
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  const { data } = await api.get<EquipmentListResponse>(
    `/products/${productId}/equipments?${p}`,
  );
  return data;
}

/**
 * O parque inteiro, de todos os produtos — só para a equipe (`GET /equipments`).
 *
 * O backend recusa cliente com 403; a rota da tela é a segunda tranca, não a
 * primeira. A empresa declarada não entra em filtro.
 *
 * `company_id` é interpretado pelo BACKEND conforme o modo dele: com o
 * compartilhamento por empresa desligado, casa o vínculo oficial do
 * responsável; ligado, casa a empresa do equipamento. O front manda o mesmo
 * parâmetro nos dois modos e não tenta adivinhar qual está valendo.
 *
 * `without_company` (ECE-01) traz os equipamentos sem empresa própria — os que
 * falta classificar e os deixados sem empresa por decisão. Vale nos dois modos.
 */
export async function listAllEquipments(
  params: {
    search?: string;
    product_id?: string;
    is_active?: boolean;
    company_id?: string;
    without_owner?: boolean;
    without_company?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<EquipmentListResponse> {
  const p = new URLSearchParams();
  if (params.search) p.set("search", params.search);
  if (params.product_id) p.set("product_id", params.product_id);
  if (params.is_active !== undefined)
    p.set("is_active", String(params.is_active));
  if (params.company_id) p.set("company_id", params.company_id);
  if (params.without_owner) p.set("without_owner", "true");
  if (params.without_company) p.set("without_company", "true");
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  const { data } = await api.get<EquipmentListResponse>(`/equipments?${p}`);
  return data;
}

/**
 * Cadastro de equipamento pela tela de Produtos (staff).
 *
 * `owner_id` é o que impede o equipamento de nascer órfão: sem dono ele não
 * aparece para cliente nenhum, não vira chamado e nem pode ser recadastrado,
 * porque o número de série já está tomado. O campo é opcional, e só existe
 * aqui — os `/equipment/my*` do cliente não o aceitam, de propósito.
 */
export async function createEquipment(
  productId: string,
  payload: {
    name: string;
    serial_number?: string;
    model?: string;
    description?: string;
    owner_id?: string | null;
    company_id?: EmpresaDoEquipamentoNoCorpo;
  },
): Promise<Equipment> {
  const { data } = await api.post<Equipment>(
    `/products/${productId}/equipments`,
    payload,
  );
  return data;
}

/**
 * Edição pela tela de Produtos (staff).
 *
 * É por aqui que se conserta o equipamento cadastrado sem dono. `owner_id`
 * ausente deixa o vínculo como está; `null` explícito desvincula.
 */
export async function updateEquipment(
  id: string,
  payload: {
    name?: string;
    serial_number?: string | null;
    model?: string | null;
    description?: string | null;
    owner_id?: string | null;
    company_id?: EmpresaDoEquipamentoNoCorpo;
  },
): Promise<Equipment> {
  const { data } = await api.patch<Equipment>(`/equipments/${id}`, payload);
  return data;
}

export async function setEquipmentActive(
  id: string,
  is_active: boolean,
): Promise<Equipment> {
  const { data } = await api.patch<Equipment>(`/equipments/${id}`, {
    is_active,
  });
  return data;
}
