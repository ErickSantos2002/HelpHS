import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FilterSelect } from "../../components/ui/FilterSelect";

/**
 * Dropdown de filtro das listagens (chamados, produtos, usuários).
 *
 * Duas coisas o separam de um `<select>` nativo e justificam teste próprio:
 * o painel é renderizado em portal no `document.body` — para não ser cortado
 * pelo `overflow` da barra de filtros — e por isso precisa fechar sozinho em
 * clique fora, scroll e resize, já que flutua ancorado a uma posição
 * calculada uma única vez na abertura.
 *
 * A linha do placeholder é o "limpar filtro": devolve `""`, que é o valor que
 * as páginas traduzem para "não mandar o parâmetro".
 */

const SITUACOES = [
  { value: "open", label: "Aberto", dot: "#22c55e" },
  { value: "closed", label: "Fechado", dot: "#64748b" },
];

function renderFiltro(props: Partial<React.ComponentProps<typeof FilterSelect>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <FilterSelect value="" onChange={onChange} options={SITUACOES} {...props} />,
  );
  return { ...utils, onChange };
}

/** O gatilho é o único botão que existe antes de abrir. */
function gatilho() {
  return screen.getAllByRole("button")[0];
}

/** O painel em portal é o `div` posicionado que embrulha as opções. */
function painel() {
  return document.body.querySelector<HTMLDivElement>('div[style*="position: fixed"]');
}

const LARGURA_ORIGINAL = window.innerWidth;

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(window, "innerWidth", { value: LARGURA_ORIGINAL, configurable: true });
});

describe("FilterSelect — o que aparece no gatilho", () => {
  it("sem valor, mostra o placeholder", () => {
    renderFiltro();

    expect(gatilho()).toHaveTextContent("Todos");
  });

  it("com valor, mostra o rótulo da opção escolhida", () => {
    renderFiltro({ value: "open" });

    expect(gatilho()).toHaveTextContent("Aberto");
  });

  it("valor que não existe nas opções cai no placeholder", () => {
    // Acontece de verdade: filtro salvo na URL de uma versão que tinha outra
    // lista de situações. Mostrar o id cru ("cancelled") não diria nada.
    renderFiltro({ value: "cancelled" });

    expect(gatilho()).toHaveTextContent("Todos");
  });

  it("aceita um placeholder próprio", () => {
    renderFiltro({ placeholder: "Todas as prioridades" });

    expect(gatilho()).toHaveTextContent("Todas as prioridades");
  });
});

describe("FilterSelect — abrir e escolher", () => {
  it("o painel só existe depois do clique no gatilho", async () => {
    renderFiltro();

    expect(painel()).toBeNull();

    await userEvent.click(gatilho());

    expect(painel()).not.toBeNull();
    expect(screen.getByRole("button", { name: "Aberto" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fechado" })).toBeInTheDocument();
  });

  it("escolher uma opção devolve o valor e fecha o painel", async () => {
    const { onChange } = renderFiltro();

    await userEvent.click(gatilho());
    await userEvent.click(screen.getByRole("button", { name: "Fechado" }));

    expect(onChange).toHaveBeenCalledWith("closed");
    expect(painel()).toBeNull();
  });

  it("a linha do placeholder limpa o filtro", async () => {
    // "" é o contrato com as páginas: valor vazio significa não filtrar.
    const { onChange } = renderFiltro({ value: "open" });

    await userEvent.click(gatilho());
    await userEvent.click(screen.getByRole("button", { name: "Todos" }));

    expect(onChange).toHaveBeenCalledWith("");
  });

  it("clicar no gatilho de novo fecha sem avisar mudança", async () => {
    const { onChange } = renderFiltro();

    await userEvent.click(gatilho());
    await userEvent.click(gatilho());

    expect(painel()).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("FilterSelect — fechar sozinho", () => {
  it("fecha ao clicar fora", async () => {
    render(
      <div>
        <FilterSelect value="" onChange={vi.fn()} options={SITUACOES} />
        <button type="button">Novo chamado</button>
      </div>,
    );

    await userEvent.click(gatilho());
    expect(painel()).not.toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Novo chamado" }));

    expect(painel()).toBeNull();
  });

  it("fecha ao rolar a página", async () => {
    // A posição é calculada na abertura; sem isso o painel ficaria parado no
    // ar enquanto a listagem rola por baixo.
    renderFiltro();

    await userEvent.click(gatilho());
    expect(painel()).not.toBeNull();

    act(() => document.dispatchEvent(new Event("scroll", { bubbles: true })));

    expect(painel()).toBeNull();
  });

  it("fecha ao redimensionar a janela", async () => {
    renderFiltro();

    await userEvent.click(gatilho());
    expect(painel()).not.toBeNull();

    act(() => window.dispatchEvent(new Event("resize")));

    expect(painel()).toBeNull();
  });
});

describe("FilterSelect — não sair da tela", () => {
  it("perto da borda direita, o painel ancora pela direita", async () => {
    // Filtro no fim da barra: ancorado pela esquerda, o painel passaria da
    // janela e o usuário veria metade das opções cortadas.
    Object.defineProperty(window, "innerWidth", { value: 400, configurable: true });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 100, bottom: 140, left: 320, right: 390, width: 70, height: 40, x: 320, y: 100,
      toJSON: () => ({}),
    } as DOMRect);

    renderFiltro();
    await userEvent.click(gatilho());

    expect(painel()?.style.right).toBe("10px");
    expect(painel()?.style.left).toBe("");
  });

  it("com espaço de sobra, o painel ancora pela esquerda do gatilho", async () => {
    Object.defineProperty(window, "innerWidth", { value: 1280, configurable: true });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 100, bottom: 140, left: 24, right: 94, width: 70, height: 40, x: 24, y: 100,
      toJSON: () => ({}),
    } as DOMRect);

    renderFiltro();
    await userEvent.click(gatilho());

    expect(painel()?.style.left).toBe("24px");
    expect(painel()?.style.right).toBe("");
  });
});
