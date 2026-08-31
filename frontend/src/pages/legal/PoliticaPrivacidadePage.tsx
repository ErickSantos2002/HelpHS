import { useNavigate } from "react-router-dom";
import { renderMarkdown } from "../../lib/markdown";
import { Button } from "../../components/ui";
import conteudo from "../../content/politica-privacidade.md?raw";
import { contemMarcadorPendente } from "./marcadorPendente";
import logoFull from "../../assets/Logo HelpHS.png";

/**
 * Política de Privacidade — texto vigente, renderizado do markdown versionado
 * em `src/content/politica-privacidade.md`.
 *
 * O texto vive num arquivo e não neste componente de propósito: cada revisão
 * vira um diff no git. O registro de aceite grava QUAL revisão a pessoa
 * aceitou, e a prova do que aquela revisão dizia é o histórico do arquivo.
 * Texto embutido em JSX não dá essa garantia com a mesma clareza.
 *
 * Passa pelo `renderMarkdown` como todo markdown do sistema — é o ponto único
 * de sanitização. Aqui o conteúdo é nosso e confiável, mas abrir exceção à
 * regra é como ela deixa de valer.
 */

const ESTILO_DOCUMENTO = [
  "max-w-none text-slate-300 leading-relaxed [overflow-wrap:anywhere]",
  "[&_h1]:text-2xl [&_h1]:font-semibold [&_h1]:text-slate-100 [&_h1]:mb-2",
  "[&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-slate-100 [&_h2]:mt-10 [&_h2]:mb-3",
  "[&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-slate-200 [&_h3]:mt-6 [&_h3]:mb-2",
  "[&_p]:my-3",
  "[&_ul]:my-3 [&_ul]:pl-6 [&_ul]:list-disc [&_ol]:my-3 [&_ol]:pl-6 [&_ol]:list-decimal",
  "[&_li]:my-1 [&_li]:marker:text-slate-500",
  "[&_strong]:text-slate-100 [&_strong]:font-semibold",
  "[&_a]:text-primary [&_a]:no-underline hover:[&_a]:underline",
  "[&_hr]:my-8 [&_hr]:border-border",
  // As tabelas são a parte que quebra em telas estreitas: cada uma rola
  // sozinha, sem empurrar a página inteira para o lado.
  // `block` + `overflow-x-auto` faz cada tabela rolar dentro da própria caixa.
  // Sem isso, a tabela de retenção (três colunas de texto corrido) empurra a
  // página inteira para o lado no celular.
  "[&_table]:block [&_table]:overflow-x-auto [&_table]:w-full",
  "[&_table]:my-5 [&_table]:text-sm [&_table]:border-collapse",
  "[&_thead]:bg-background-elevated",
  "[&_th]:border [&_th]:border-border [&_th]:p-2 [&_th]:text-left [&_th]:text-slate-100 [&_th]:font-semibold",
  "[&_td]:border [&_td]:border-border [&_td]:p-2 [&_td]:align-top",
].join(" ");

export default function PoliticaPrivacidadePage() {
  const navigate = useNavigate();
  const html = renderMarkdown(conteudo);
  const emElaboracao = contemMarcadorPendente(conteudo);

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
        <img src={logoFull} alt="HelpHS" className="mb-8 h-8" />

        {emElaboracao && (
          <div
            role="alert"
            className="mb-8 rounded-lg border border-danger bg-danger/10 p-4 text-sm text-slate-200"
          >
            <p className="font-semibold text-slate-100">
              Documento em elaboração — este não é o texto vigente.
            </p>
            <p className="mt-1">
              Trechos entre colchetes ainda estão em definição pelo setor de
              qualidade. Não utilize esta versão como referência.
            </p>
          </div>
        )}

        <div
          className={ESTILO_DOCUMENTO}
          dangerouslySetInnerHTML={{ __html: html }}
        />

        <div className="mt-12 border-t border-border pt-6">
          <Button variant="secondary" onClick={() => navigate(-1)}>
            Voltar
          </Button>
        </div>
      </div>
    </div>
  );
}
