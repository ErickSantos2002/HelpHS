import { marked } from "marked";
import DOMPurify from "dompurify";

// O conteúdo de artigo da Base de Conhecimento é escrito por admin/técnico e
// renderizado com dangerouslySetInnerHTML. O `marked` NÃO remove HTML embutido
// no markdown, então sem sanitizar um `<img onerror>` ou `<script>` gravado no
// artigo rodaria na sessão de quem abrisse — inclusive um admin, com o token
// exposto no localStorage. DOMPurify remove script, handlers de evento e URLs
// perigosas, mantendo a formatação (títulos, negrito, links, código).

marked.setOptions({ breaks: true });

/**
 * Converte markdown em HTML seguro para injetar via dangerouslySetInnerHTML.
 *
 * Toda renderização de markdown do sistema DEVE passar por aqui — é o ponto
 * único onde a sanitização acontece.
 */
export function renderMarkdown(content: string): string {
  const rawHtml = marked.parse(content) as string;
  return DOMPurify.sanitize(rawHtml);
}
