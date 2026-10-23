import type { ExibicaoDaFoto } from "../services/userService";

/**
 * O que o perfil e o aviso de lançamento da foto para outras pessoas dividem.
 *
 * ⚠️ Nada aqui é a autorização. A escolha mora no servidor
 * (`PUT /users/me/avatar/exibicao`); o que fica no navegador é só se a pessoa
 * já fechou o AVISO — e fechar o aviso não autoriza nada.
 */

/** Disparado pelo perfil quando o servidor confirma uma escolha nova. */
export const EVENTO_EXIBICAO_DA_FOTO = "helphs:exibicao-da-foto";

export function avisaQueAExibicaoMudou(estado: ExibicaoDaFoto): void {
  window.dispatchEvent(new CustomEvent<ExibicaoDaFoto>(EVENTO_EXIBICAO_DA_FOTO, { detail: estado }));
}

/**
 * Por pessoa E por versão do texto: um texto novo é novidade de novo, e quem
 * divide o computador não esconde o aviso do outro.
 */
function chave(userId: string, versao: string): string {
  return `helphs:aviso-foto-terceiros:${versao}:${userId}`;
}

/**
 * `localStorage` pode não existir ou recusar (aba privada, dados bloqueados).
 * Aí o aviso simplesmente volta a aparecer — nunca some por erro, e nunca
 * derruba a tela.
 */
export function avisoFoiDispensado(userId: string, versao: string): boolean {
  try {
    return window.localStorage.getItem(chave(userId, versao)) === "1";
  } catch {
    return false;
  }
}

export function dispensaAviso(userId: string, versao: string): void {
  try {
    window.localStorage.setItem(chave(userId, versao), "1");
  } catch {
    // Sem armazenamento, o aviso fecha só nesta visita.
  }
}
