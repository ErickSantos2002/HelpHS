import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider, useTheme } from "../../contexts/ThemeContext";

/**
 * Tema da aplicação.
 *
 * O valor mora em dois lugares que precisam concordar: a classe `dark` no
 * `<html>` — que é o que o Tailwind lê — e a chave `helphs-theme` no
 * localStorage, que é o que sobrevive ao recarregar. Um sem o outro dá o bug
 * clássico de escolher claro, dar F5 e voltar escuro.
 *
 * Quem nunca escolheu recebe a preferência do SISTEMA OPERACIONAL
 * (`prefers-color-scheme`); quem já escolheu manda, contra o sistema
 * inclusive. Por isso a preferência só é gravada quando alguém alterna: se
 * fosse gravada na primeira montagem, o valor do SO ficaria congelado ali e o
 * "seguir o sistema" valeria por uma visita só.
 */

const CHAVE = "helphs-theme";

function Consumidor() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="tema">{theme}</span>
      <button type="button" onClick={toggleTheme}>
        Alternar
      </button>
    </div>
  );
}

function renderComProvider() {
  return render(
    <ThemeProvider>
      <Consumidor />
    </ThemeProvider>,
  );
}

/**
 * Finge a preferência do SO. happy-dom não traz `matchMedia`, e sem stub o
 * provider cairia sempre no mesmo ramo — o teste passaria sem testar nada.
 */
function sistemaPrefere(modo: "light" | "dark" | "sem-suporte") {
  if (modo === "sem-suporte") {
    // @ts-expect-error — simula navegador/ambiente sem matchMedia
    window.matchMedia = undefined;
    return;
  }
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("light") === (modo === "light"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  sistemaPrefere("dark");
});

describe("ThemeProvider — o que vale na primeira visita", () => {
  it("sem nada salvo, segue o sistema operacional no claro", () => {
    sistemaPrefere("light");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("sem nada salvo, segue o sistema operacional no escuro", () => {
    sistemaPrefere("dark");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");
  });

  it("valor salvo estragado não conta como escolha — vale o sistema", () => {
    // Chave escrita por uma versão antiga, ou mexida na mão pelo DevTools.
    sistemaPrefere("light");
    localStorage.setItem(CHAVE, "solarized");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
  });

  it("sem matchMedia no ambiente, cai no escuro", () => {
    // Navegador antigo, ou renderização fora do browser: não dá para perguntar
    // a preferência, e o escuro é o visual de casa do HelpHS.
    sistemaPrefere("sem-suporte");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
  });

  it("não grava nada antes de o usuário escolher", () => {
    // Gravar na montagem congelaria o valor do SO daquele dia: quem trocasse o
    // tema do sistema depois nunca mais veria a mudança refletida, e "seguir o
    // sistema" valeria por uma visita só.
    sistemaPrefere("light");

    renderComProvider();

    expect(localStorage.getItem(CHAVE)).toBeNull();
  });
});

describe("ThemeProvider — a preferência sobrevive ao recarregar", () => {
  it("com 'light' salvo, monta no claro e tira a classe do html", () => {
    document.documentElement.classList.add("dark"); // como o index.html entrega
    localStorage.setItem(CHAVE, "light");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("a escolha salva manda contra o sistema — nos dois sentidos", () => {
    // O SO é o palpite inicial, não uma ordem: quem já escolheu não é
    // sobrescrito por causa do relógio do computador virando a noite.
    sistemaPrefere("dark");
    localStorage.setItem(CHAVE, "light");
    const claro = renderComProvider();
    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    claro.unmount();

    sistemaPrefere("light");
    localStorage.setItem(CHAVE, "dark");
    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
  });

  it("alternar grava a escolha nova", async () => {
    renderComProvider();

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(localStorage.getItem(CHAVE)).toBe("light");
  });

  it("o que foi gravado é o que a próxima montagem lê", async () => {
    // Este é o teste que fecha o ciclo: escolher, sair, voltar. O SO fica no
    // escuro de propósito — se a escolha não fosse gravada, a volta cairia
    // nele e o teste passaria pelo motivo errado.
    sistemaPrefere("dark");
    const { unmount } = renderComProvider();
    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));
    unmount();

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });
});

describe("ThemeProvider — alternar", () => {
  it("vai e volta entre escuro e claro", async () => {
    renderComProvider();

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));
    expect(document.documentElement).not.toHaveClass("dark");

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(screen.getByTestId("tema")).toHaveTextContent("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(CHAVE)).toBe("dark");
  });
});

describe("useTheme fora do provider", () => {
  it("estoura com mensagem clara em vez de devolver undefined", () => {
    const silencio = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<Consumidor />)).toThrow(/useTheme must be used within ThemeProvider/);

    silencio.mockRestore();
  });
});

/**
 * Um segundo leitor do tema. Existe para provar que o valor vem do CONTEXTO:
 * se `useTheme` guardasse um estado local, cada consumidor teria o seu e a
 * troca feita num não apareceria no outro — e todos os testes de um consumidor
 * só continuariam passando.
 */
function ConsumidorEspelho() {
  const { theme } = useTheme();
  return <span data-testid="tema-espelho">{theme}</span>;
}

describe("ThemeProvider — um estado só para a árvore inteira", () => {
  it("a troca feita em um consumidor chega ao outro", async () => {
    render(
      <ThemeProvider>
        <Consumidor />
        <ConsumidorEspelho />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("tema-espelho")).toHaveTextContent("dark");

    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(screen.getByTestId("tema-espelho")).toHaveTextContent("light");
  });
});

describe("ThemeProvider — a conversa com o sistema operacional", () => {
  it("pergunta exatamente a query que o index.html repete à mão", () => {
    // O script anti-flash do index.html refaz esta mesma pergunta antes do
    // bundle. Perguntar por outra coisa aqui reabre o flash entre as duas.
    sistemaPrefere("light");
    const consulta = vi.mocked(window.matchMedia);

    renderComProvider();

    expect(consulta).toHaveBeenCalledWith("(prefers-color-scheme: light)");
  });

  it("com escolha salva, nem chega a perguntar ao sistema", () => {
    // O `??` curto-circuita: quem já escolheu não precisa do palpite do SO, e
    // consultar mesmo assim seria a porta para o SO acabar vencendo.
    localStorage.setItem(CHAVE, "light");
    sistemaPrefere("dark");
    const consulta = vi.mocked(window.matchMedia);

    renderComProvider();

    expect(consulta).not.toHaveBeenCalled();
    expect(screen.getByTestId("tema")).toHaveTextContent("light");
  });

  it("a escolha salva vale mesmo sem matchMedia no ambiente", () => {
    // Cruzamento dos dois ramos: ambiente sem como perguntar, mas com escolha
    // gravada. O escuro é o padrão da AUSÊNCIA de escolha, não um atropelo.
    sistemaPrefere("sem-suporte");
    localStorage.setItem(CHAVE, "light");

    renderComProvider();

    expect(screen.getByTestId("tema")).toHaveTextContent("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });
});

describe("ThemeProvider — o que a troca não pode atropelar", () => {
  it("alternar mexe só na classe 'dark' do <html>", async () => {
    // O provider escreve na mesma tag que carrega as classes de base do app.
    // Trocar `classList.toggle` por uma atribuição de `className` passaria em
    // todos os outros testes e varreria o resto do <html>.
    document.documentElement.classList.add("h-full");

    renderComProvider();
    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(document.documentElement).not.toHaveClass("dark");
    expect(document.documentElement).toHaveClass("h-full");
    document.documentElement.classList.remove("h-full");
  });

  it("alternar não encosta nas outras chaves do localStorage", async () => {
    // O token da sessão mora no mesmo localStorage. Um `clear()` no caminho da
    // gravação deslogaria o usuário toda vez que ele trocasse o tema.
    localStorage.setItem("helphs-token", "token-da-sessao");

    renderComProvider();
    await userEvent.click(screen.getByRole("button", { name: "Alternar" }));

    expect(localStorage.getItem("helphs-token")).toBe("token-da-sessao");
    expect(localStorage.getItem(CHAVE)).toBe("light");
  });
});

/**
 * Substitui o localStorage global por um que estoura no método pedido, como
 * faz um navegador com armazenamento bloqueado ou cota estourada. O alvo é o
 * `globalThis` porque o código de produção diz `localStorage` sem qualificar;
 * espionar `Storage.prototype` não pega — o happy-dom não passa por lá.
 * Devolve a função que põe o armazenamento real de volta.
 */
function armazenamentoQueEstouraEm(metodo: "getItem" | "setItem", erro: string) {
  const real = globalThis.localStorage;
  const descritor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const estoura = () => {
    throw new Error(erro);
  };
  const falso: Storage = {
    length: real.length,
    clear: () => real.clear(),
    key: (i: number) => real.key(i),
    removeItem: (chave: string) => real.removeItem(chave),
    getItem: metodo === "getItem" ? estoura : (chave: string) => real.getItem(chave),
    setItem:
      metodo === "setItem" ? estoura : (chave: string, valor: string) => real.setItem(chave, valor),
  };

  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: falso });

  return function devolveOReal() {
    if (descritor) Object.defineProperty(globalThis, "localStorage", descritor);
    else delete (globalThis as { localStorage?: Storage }).localStorage;
  };
}

describe("ThemeProvider — quando o localStorage recusa", () => {
  it("hoje, leitura bloqueada derruba a montagem do provider", () => {
    // Navegador com cookies/armazenamento bloqueados (Safari em modo restrito)
    // faz o próprio ACESSO ao localStorage estourar. Como `escolhaSalva()` lê
    // sem proteção e o provider embrulha o app inteiro, o erro sobe até a
    // raiz: tela branca, não um tema errado. Este teste registra o
    // comportamento de HOJE — veja "problemas" no relatório da fase.
    const silencio = vi.spyOn(console, "error").mockImplementation(() => {});
    const devolveOReal = armazenamentoQueEstouraEm(
      "getItem",
      "SecurityError: acesso ao armazenamento negado",
    );

    try {
      expect(() => renderComProvider()).toThrow(/SecurityError/);
    } finally {
      devolveOReal();
      silencio.mockRestore();
    }
  });

  it("hoje, gravação recusada deixa a tela travada no tema antigo", async () => {
    // Cota estourada / modo privado: `setItem` estoura ANTES do `setTheme`, e
    // o clique não muda nada — nem o texto, nem a classe do <html>. O usuário
    // aperta o botão e não acontece nada, sem aviso nenhum.
    renderComProvider();
    const silencio = vi.spyOn(console, "error").mockImplementation(() => {});
    const devolveOReal = armazenamentoQueEstouraEm("setItem", "QuotaExceededError");

    try {
      await userEvent.click(screen.getByRole("button", { name: "Alternar" })).catch(() => {});

      expect(screen.getByTestId("tema")).toHaveTextContent("dark");
      expect(document.documentElement).toHaveClass("dark");
    } finally {
      devolveOReal();
      silencio.mockRestore();
    }
  });
});
