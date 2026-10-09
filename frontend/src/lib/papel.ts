/**
 * O papel do usuário, numa fonte só.
 *
 * Existia em **cinco** lugares: `ProfilePage`, `Topbar`, e três vezes dentro do
 * `UsersPage` — a tabela, as opções do formulário e as opções do filtro. É o
 * mesmo modo de falha que produziu os dez mapas de prioridade, e ele já tinha
 * começado a render fruto: `client` era `secondary` numa cópia e `muted` na
 * outra.
 *
 * Essa divergência específica não chegou a pintar diferente, e o motivo é
 * instrutivo: `secondary` e `muted` são **classes idênticas** no `Badge`
 * (`bg-tint-neutral text-on-tint-neutral border-borda`). Dois nomes para uma
 * aparência só escondem a divergência em vez de mostrá-la — a próxima, entre
 * dois nomes que pintam diferente, teria aparecido na tela.
 *
 * Aqui fica `muted`, que é o nome que o `lib/status.ts` já usa para o papel
 * neutro. Duas palavras para a mesma cor é assunto do pacote, não desta camada.
 *
 * ── Por que este módulo existe e o `lib/auditoria.ts` não ─────────────
 *
 * A regra que os agentes da Fase 16 vinham aplicando: tabela com **um**
 * consumidor fica local, com a disciplina dos módulos; tabela com **vários**
 * sobe. Ação de auditoria tem um consumidor e ficou lá. Papel tem três telas e
 * cinco cópias, e é isto.
 */

import type { VarianteStatus } from "./status";

/** Os três papéis que o backend usa. */
export type PapelUsuario = "admin" | "technician" | "client";

/** Variante do `Badge`, emprestada do módulo de status: é o mesmo vocabulário. */
export type VariantePapel = Extract<
  VarianteStatus,
  "primary" | "info" | "muted"
>;

export interface Papel {
  /** O nome por extenso. É o que o selo e o menu mostram. */
  rotulo: string;
  variante: VariantePapel;
  /**
   * Ordem de privilégio, do maior para o menor.
   *
   * Serve à lista de opções, e é a ordem em que as três aparecem em todo
   * seletor de papel do sistema. Não é ordem alfabética de propósito: quem lê
   * "Administrador, Técnico, Cliente" entende a escada; quem lê "Administrador,
   * Cliente, Técnico" não entende nada.
   */
  ordem: number;
}

export const PAPEL: Record<PapelUsuario, Papel> = {
  admin: { rotulo: "Administrador", variante: "primary", ordem: 0 },
  technician: { rotulo: "Técnico", variante: "info", ordem: 1 },
  client: { rotulo: "Cliente", variante: "muted", ordem: 2 },
};

/** Os três, na ordem de privilégio. */
export const PAPEIS = (Object.keys(PAPEL) as PapelUsuario[]).sort(
  (a, b) => PAPEL[a].ordem - PAPEL[b].ordem,
);

/**
 * As opções de um seletor de papel.
 *
 * Derivada, e não escrita à mão: era assim que o `UsersPage` tinha três cópias
 * em vez de uma — a tabela, as opções do formulário e as do filtro, cada uma
 * mantida à parte.
 */
export const OPCOES_DE_PAPEL = PAPEIS.map((p) => ({
  value: p,
  label: PAPEL[p].rotulo,
}));

/** O rótulo, com recuo para o valor cru quando o backend manda algo novo. */
export function rotuloDePapel(p: string): string {
  return PAPEL[p as PapelUsuario]?.rotulo ?? p;
}

/** A variante, com recuo para o neutro. */
export function varianteDePapel(p: string): VariantePapel {
  return PAPEL[p as PapelUsuario]?.variante ?? "muted";
}
