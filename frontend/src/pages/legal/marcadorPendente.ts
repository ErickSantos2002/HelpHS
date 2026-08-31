/**
 * Detecta se um documento legal ainda tem trechos em definição pela qualidade
 * — marcadores como `[validar prazos de retenção]` ou `[nome do Encarregado]`.
 *
 * Existe porque a Política de Privacidade é linkada da tela de cadastro, ao
 * lado da caixa em que a pessoa declara ter lido o texto. Publicar com um
 * marcador aberto seria pedir aceite de documento jurídico incompleto.
 *
 * A checagem olha o conteúdo real em vez de uma flag manual: flag alguém
 * esquece de virar, enquanto o marcador desaparece sozinho quando o texto é
 * fechado.
 */

// O `(?!\()` exclui link markdown — `[texto](url)`. Sem ele, um link cujo texto
// começasse por uma destas palavras marcaria o documento como rascunho para
// sempre, e um aviso que nunca sai da tela deixa de ser lido.
const MARCADOR_PENDENTE =
  /\[(?:validar|definir|confirmar|nome|e-mail|endereço|elaborado|aprovado)[^\]]*\](?!\()/i;

export function contemMarcadorPendente(texto: string): boolean {
  return MARCADOR_PENDENTE.test(texto);
}
