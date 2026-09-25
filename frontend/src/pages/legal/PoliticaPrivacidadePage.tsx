import conteudo from "../../content/politica-privacidade.md?raw";
import { DocumentoLegal } from "./DocumentoLegal";

/**
 * Política de Privacidade — texto vigente, renderizado do markdown versionado
 * em `src/content/politica-privacidade.md`. A casca (aviso de rascunho,
 * estilos, Voltar) é comum aos documentos legais e mora em `DocumentoLegal`.
 */
export default function PoliticaPrivacidadePage() {
  return <DocumentoLegal conteudo={conteudo} />;
}
