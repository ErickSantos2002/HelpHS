import { Link } from "react-router-dom";
import logoFull from "../../assets/Logo HelpHS.png";

/**
 * Moldura das telas de conta que não são o login (confirmar e-mail, esqueci a
 * senha, redefinir senha). Mantém a mesma identidade visual sem repetir o
 * painel de apresentação do login.
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
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#0D1623] px-6 py-12">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex items-center justify-center">
          <Link to="/login">
            <img src={logoFull} alt="HelpHS" className="h-12 w-auto object-contain" />
          </Link>
        </div>

        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-bold text-slate-100">{title}</h1>
          {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
        </div>

        {children}

        {footer && <div className="text-center text-sm text-slate-500">{footer}</div>}
      </div>

      <p className="mt-10 text-xs text-slate-600">
        © {new Date().getFullYear()} HelpHS — Health &amp; Safety Tech
      </p>
    </div>
  );
}
