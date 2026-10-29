import { Component, type ErrorInfo, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "./ui";

/**
 * Última rede para erro de RENDERIZAÇÃO (F1-B-02).
 *
 * Sem ela, qualquer exceção ao desenhar — um `detail` em lista dentro de um
 * `<Alert>`, por exemplo — apagava a aplicação inteira: tela em branco. Erro
 * de HTTP não é assunto daqui: esses têm mensagem própria pelo `getApiError`
 * e nunca deveriam chegar a esta barreira.
 *
 * A pessoa vê só uma mensagem e as saídas; a mensagem do erro e a pilha vão
 * para o console do navegador e para nenhum outro lugar.
 */

type Props = {
  children: ReactNode;
  /** Quando muda (a rota, na raiz), a barreira tenta desenhar os filhos de novo. */
  chaveDeReinicio?: unknown;
  /** Saída para o início; a raiz passa a navegação do roteador. */
  aoIrParaInicio?: () => void;
};

type State = { falhou: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { falhou: false };

  static getDerivedStateFromError(): State {
    return { falhou: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  componentDidUpdate(anteriores: Props) {
    if (this.state.falhou && anteriores.chaveDeReinicio !== this.props.chaveDeReinicio) {
      this.setState({ falhou: false });
    }
  }

  private tentarDeNovo = () => this.setState({ falhou: false });

  private irParaInicio = () => {
    this.setState({ falhou: false });
    this.props.aoIrParaInicio?.();
  };

  render() {
    if (!this.state.falhou) return this.props.children;

    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-base px-4">
        <div role="alert" className="max-w-md text-center space-y-4">
          <h1 className="text-xl font-semibold text-conteudo-heading">
            Algo deu errado nesta tela
          </h1>
          <p className="text-conteudo-muted">
            Não foi possível mostrar esta parte do sistema. Tente de novo; se continuar,
            recarregue a página.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button onClick={this.tentarDeNovo}>Tentar novamente</Button>
            {this.props.aoIrParaInicio && (
              <Button variant="secondary" onClick={this.irParaInicio}>
                Ir para o início
              </Button>
            )}
            <Button variant="ghost" onClick={() => window.location.reload()}>
              Recarregar a página
            </Button>
          </div>
        </div>
      </div>
    );
  }
}

/**
 * A barreira da raiz, dentro do roteador: trocar de rota limpa o erro, e a
 * saída "Ir para o início" navega sem recarregar.
 */
export function ProtecaoDaRaiz({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  return (
    <ErrorBoundary chaveDeReinicio={pathname} aoIrParaInicio={() => navigate("/")}>
      {children}
    </ErrorBoundary>
  );
}
