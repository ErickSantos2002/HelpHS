import conteudo from "../../content/termos-de-uso.md?raw";
import { DocumentoLegal } from "./DocumentoLegal";

/**
 * Termos de Uso — texto vigente, renderizado do markdown versionado em
 * `src/content/termos-de-uso.md`. Mesma casca da Política de Privacidade.
 */
export default function TermosDeUsoPage() {
  return <DocumentoLegal conteudo={conteudo} />;
}
