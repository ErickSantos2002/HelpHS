import { Link } from "react-router-dom";
import logoFull from "../../assets/Logo HelpHS.png";

/**
 * Moldura das telas de conta que não são o login (confirmar e-mail, esqueci a
 * senha, redefinir senha). Mantém a mesma identidade visual sem repetir o
 * painel de apresentação do login.
 *
 * O fundo é escuro FIXO, nos dois temas — por isso a raiz carrega a classe
 * `dark`: os tokens do tema escuro estão em `.dark { }` e passam a valer
 * daqui para dentro, seja qual for o tema do `<html>`. Sem ela, no tema claro
 * o rótulo do `Input` e as tintas do `Alert` saíam nas cores de fundo claro,
 * sobre este fundo (AUTH-UI-01: rótulo 1,24:1, aviso de erro 2,45:1).
 *
 * Pelo mesmo motivo aqui não se escreve `text-slate-*`: o `index.css` inverte
 * essas classes pelo `<html>`, e o escopo não alcança essa regra.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="dark min-h-screen flex flex-col items-center justify-center bg-[#0D1623] px-6 py-12">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex items-center justify-center">
          <Link to="/login">
            <img src={logoFull} alt="HelpHS" className="h-12 w-auto object-contain" />
          </Link>
        </div>

        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-bold text-conteudo-heading">{title}</h1>
          {subtitle && <p className="text-sm text-conteudo-muted">{subtitle}</p>}
        </div>

        {children}

        {/* O link do rodapé vem de cada tela, com 18px de altura; os 24px de
            área de toque são dados aqui, uma vez, para todas. */}
        {footer && (
          <div className="text-center text-sm text-conteudo-muted [&_a]:inline-block [&_a]:py-1">
            {footer}
          </div>
        )}
      </div>

      <p className="mt-10 text-xs text-conteudo-muted">
        © {new Date().getFullYear()} HelpHS — Health &amp; Safety Tech
      </p>
    </div>
  );
}
