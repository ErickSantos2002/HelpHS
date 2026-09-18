/**
 * Telefone: máscara de tela e forma canônica de envio.
 *
 * Espelha `backend/app/utils/telefone.py`, que é a autoridade — **as duas
 * pontas precisam concordar**, e é por isso que aqui é um módulo e não uma
 * cópia por formulário. Antes da Fase 1A havia quatro comportamentos
 * diferentes para o mesmo campo, e dois placeholders que ensinavam formatos
 * divergentes: `(11) 99999-9999` no cadastro e no perfil, `(11) 9 9999-9999`
 * na tela de usuários.
 *
 * O que sai daqui para o backend é **E.164** (`+5581999999999`), a
 * representação canônica interna do HelpHS. A pontuação é coisa de tela,
 * nunca de armazenamento — mesma regra do CNPJ em `documents.ts`.
 *
 * Esta validação existe para o usuário saber o que errou **antes** de enviar.
 * A barreira de verdade é o backend: o front é UX, não segurança.
 */

import { onlyDigits } from "./documents";

/** Máscara PROGRESSIVA, para o `onChange` do campo. Trava no 11º dígito. */
export function maskPhoneInput(value: string): string {
  const d = onlyDigits(value).slice(0, 11);
  if (d.length <= 2) return d;
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
}

/**
 * Máscara para EXIBIÇÃO de um valor já guardado.
 *
 * Aceita E.164 e também o formato antigo, porque até um saneamento rodar
 * ainda existe linha fora do padrão. O que não for reconhecido volta como
 * veio: inventar máscara em cima de dado torto esconde o problema.
 */
export function formatPhone(value: string | null | undefined): string {
  if (!value) return "";
  let d = onlyDigits(value);
  if (d.length === 13 && d.startsWith("55")) d = d.slice(2);
  if (d.length === 12 && d.startsWith("55")) d = d.slice(2);
  if (d.length === 10 || d.length === 11) return maskPhoneInput(d);
  return value;
}

/** Espelha `_valida_nacional_brasileiro` do backend. */
function nacionalBrasileiroValido(nacional: string): boolean {
  if (nacional.length !== 10 && nacional.length !== 11) return false;
  if (nacional[0] === "0" || nacional[1] === "0") return false;
  const primeiroDoAssinante = nacional[2];
  if (nacional.length === 11) return primeiroDoAssinante === "9";
  return "2345".includes(primeiroDoAssinante);
}

/**
 * Converte para E.164, ou devolve `null` quando não dá para normalizar.
 *
 * Não adivinha DDI: sem `+`, só aceita o que é reconhecível como brasileiro.
 * Chutar `+55` em cima de número curto gravaria algo indiscável com cara de
 * telefone bom.
 */
export function toE164(value: string | null | undefined): string | null {
  if (!value) return null;
  const texto = value.trim();
  if (!texto) return null;
  const d = onlyDigits(texto);

  if (texto.startsWith("+")) {
    if (d.length < 8 || d.length > 15 || d.startsWith("0")) return null;
    if (d.startsWith("55") && !nacionalBrasileiroValido(d.slice(2))) return null;
    return `+${d}`;
  }
  if (d.length === 10 || d.length === 11) {
    return nacionalBrasileiroValido(d) ? `+55${d}` : null;
  }
  if ((d.length === 12 || d.length === 13) && d.startsWith("55")) {
    return nacionalBrasileiroValido(d.slice(2)) ? `+${d}` : null;
  }
  return null;
}

/** `true` quando o valor vira um E.164 válido. Campo vazio não é "inválido". */
export function isValidPhone(value: string | null | undefined): boolean {
  return toE164(value) !== null;
}

/** Mensagem única — as três telas diziam coisas diferentes para o mesmo erro. */
export const ERRO_TELEFONE =
  "Informe um telefone válido com DDD, por exemplo (81) 99999-9999.";

export const PLACEHOLDER_TELEFONE = "(81) 99999-9999";
