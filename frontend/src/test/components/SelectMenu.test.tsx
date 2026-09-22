import { createRef } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SelectMenu } from "../../components/ui/SelectMenu";
import { AA, contraste } from "../helpers/contraste";

/**
 * O substituto do `<select>` nativo, no desenho do `SelectMenu` do HS Growth.
 *
 * O nativo resolvia de graça o que um painel suspenso tem de provar à mão:
 * papel de campo, teclado, fechar sem escolher. Este arquivo prova cada uma
 * dessas coisas, porque trocar o nativo por um painel e perder o teclado é
 * trocar aparência por acesso — o defeito que o `Selector` já pagou na Fase 8.
 *
 * O gatilho tem `role="combobox"`, o mesmo papel implícito do `<select>`: as
 * telas e os testes que acham o campo por `getByRole("combobox", { name })`
 * continuam achando. O que muda é só a interação — abrir e clicar na opção, no
 * lugar de `selectOptions`.
 */

const SITUACOES = [
  { value: "open", label: "Aberto" },
  { value: "closed", label: "Fechado" },
  { value: "frozen", label: "Congelado" },
];

/** Piso da WCAG 1.4.11 para indicador não textual: borda, anel de foco. */
const NAO_TEXTO = 3;

function montar(props: Partial<React.ComponentProps<typeof SelectMenu>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <SelectMenu
      value=""
      onChange={onChange}
      options={SITUACOES}
      label="Situação"
      {...props}
    />,
  );
  return { ...utils, onChange };
}

const gatilho = () => screen.getByRole("combobox");
const opcao = (nome: string) => screen.getByRole("option", { name: nome });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SelectMenu — o campo que o nativo era", () => {
  it("o gatilho é um combobox com o nome do rótulo, como o <select>", () => {
    montar();

    expect(screen.getByRole("combobox", { name: "Situação" })).toBeInTheDocument();
  });

  it("o rótulo aponta para o gatilho: clicar nele foca o campo", async () => {
    montar();

    await userEvent.click(screen.getByText("Situação"));

    expect(gatilho()).toHaveFocus();
  });

  it("o nome é só o rótulo — o valor é o conteúdo, não entra no nome", () => {
    montar({ value: "open" });

    expect(gatilho()).toHaveAccessibleName("Situação");
    expect(gatilho()).toHaveTextContent("Aberto");
  });

  it("aceita aria-label quando não há rótulo visível", () => {
    montar({ label: undefined, "aria-label": "Filtrar por situação" });

    expect(
      screen.getByRole("combobox", { name: "Filtrar por situação" }),
    ).toBeInTheDocument();
  });

  it("aceita aria-labelledby apontando para um rótulo da tela", () => {
    render(
      <>
        <span id="rotulo-de-fora">Situação do chamado</span>
        <SelectMenu
          value=""
          onChange={vi.fn()}
          options={SITUACOES}
          aria-labelledby="rotulo-de-fora"
        />
      </>,
    );

    expect(
      screen.getByRole("combobox", { name: "Situação do chamado" }),
    ).toBeInTheDocument();
  });

  it("sem rótulo nenhum, não inventa apontamento", () => {
    montar({ label: undefined });

    expect(gatilho()).not.toHaveAttribute("aria-labelledby");
  });

  it("o id passado por quem chama vai para o gatilho", () => {
    montar({ id: "filtro-status" });

    expect(gatilho().id).toBe("filtro-status");
  });

  it("dois campos com o mesmo rótulo não compartilham id", () => {
    render(
      <>
        <SelectMenu value="" onChange={vi.fn()} options={SITUACOES} label="Situação" />
        <SelectMenu value="" onChange={vi.fn()} options={SITUACOES} label="Situação" />
      </>,
    );

    const [a, b] = screen.getAllByRole("combobox", { name: "Situação" });
    expect(a.id).toBeTruthy();
    expect(a.id).not.toBe(b.id);
  });

  it("o ref chega ao gatilho, para o formulário poder focar o campo recusado", () => {
    const ref = createRef<HTMLButtonElement>();
    render(
      <SelectMenu ref={ref} value="" onChange={vi.fn()} options={SITUACOES} label="Situação" />,
    );

    expect(ref.current).toBe(gatilho());
    ref.current!.focus();
    expect(gatilho()).toHaveFocus();
  });

  it("não é botão de envio: dentro de <form>, abrir não submete", async () => {
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <SelectMenu value="" onChange={vi.fn()} options={SITUACOES} label="Situação" />
      </form>,
    );

    await userEvent.click(gatilho());
    await userEvent.click(opcao("Fechado"));

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("SelectMenu — o que o gatilho mostra", () => {
  it("mostra o rótulo da opção escolhida", () => {
    montar({ value: "closed" });

    expect(gatilho()).toHaveTextContent("Fechado");
  });

  it("sem escolha, mostra o placeholder em tom apagado", () => {
    montar({ placeholder: "Todos os status" });

    const texto = screen.getByText("Todos os status");
    expect(texto.className).toContain("text-conteudo-muted");
  });

  it("com escolha, o texto sai do tom de conteúdo", () => {
    montar({ value: "open" });

    const texto = screen.getByText("Aberto");
    expect(texto.className).toContain("text-conteudo");
    expect(texto.className).not.toContain("text-conteudo-muted");
  });

  it("sem escolha e sem placeholder, diz 'Selecione'", () => {
    montar();

    expect(gatilho()).toHaveTextContent("Selecione");
  });

  it("texto longo é truncado no gatilho", () => {
    montar({ value: "open" });

    expect(screen.getByText("Aberto").className).toContain("truncate");
  });

  it("a seta gira 180 graus quando o menu abre", async () => {
    montar();
    const seta = () => gatilho().querySelector("svg")!;

    expect(seta().getAttribute("class")).not.toContain("rotate-180");

    await userEvent.click(gatilho());

    expect(seta().getAttribute("class")).toContain("rotate-180");
  });
});

describe("SelectMenu — clique", () => {
  it("clicar no campo abre, clicar de novo fecha", async () => {
    montar();

    expect(gatilho()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    await userEvent.click(gatilho());
    expect(gatilho()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await userEvent.click(gatilho());
    expect(gatilho()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("clicar numa opção chama onChange com o valor e fecha", async () => {
    const { onChange } = montar();

    await userEvent.click(gatilho());
    await userEvent.click(opcao("Fechado"));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("closed");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("reescolher a opção já escolhida fecha e NÃO avisa — como o nativo", async () => {
    // O `<select>` nativo não dispara `change` sem troca de valor, e as telas
    // contam com isso: nos filtros da `UsersPage` o `onChange` roda
    // `setPage(1)`. Avisar aqui mudaria o comportamento do filtro.
    const { onChange } = montar({ value: "open" });

    await userEvent.click(gatilho());
    await userEvent.click(opcao("Aberto"));

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("reescolher o placeholder com o filtro já vazio também não avisa", async () => {
    const { onChange } = montar({ value: "", placeholder: "Todos os status" });

    await userEvent.click(gatilho());
    await userEvent.click(opcao("Todos os status"));

    expect(onChange).not.toHaveBeenCalled();
  });

  it("o placeholder é uma opção de valor vazio, como no Select nativo", async () => {
    // O `<Select>` de hoje desenha o placeholder como `<option value="">`, e
    // as barras de filtro dependem disso para LIMPAR o filtro ("Todos os
    // status"). Tirar a linha trocaria a regra do filtro.
    const { onChange } = montar({ value: "open", placeholder: "Todos os status" });

    await userEvent.click(gatilho());
    await userEvent.click(opcao("Todos os status"));

    expect(onChange).toHaveBeenCalledWith("");
  });

  it("clicar fora fecha sem escolher", async () => {
    const onChange = vi.fn();
    render(
      <>
        <p>fora</p>
        <SelectMenu value="" onChange={onChange} options={SITUACOES} label="Situação" />
      </>,
    );

    await userEvent.click(gatilho());
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await userEvent.click(screen.getByText("fora"));

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("o clique fora fecha mesmo quando o foco não se move", async () => {
    // Quem fecha aqui é o ouvinte de `mousedown` no `document`, e só ele: um
    // clique num trecho não focável (um parágrafo, o fundo de um cartão) não
    // tira o foco do gatilho, então o `onBlur` não entra. Este caso existe
    // porque, sem ele, apagar o ouvinte não derrubava teste nenhum.
    const { onChange } = montar();
    await userEvent.click(gatilho());
    expect(gatilho()).toHaveFocus();

    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(gatilho()).toHaveFocus();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("o toque fora também fecha (celular)", async () => {
    montar();
    await userEvent.click(gatilho());

    fireEvent.touchStart(document.body);

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("apertar numa opção não tira o foco do gatilho", async () => {
    // O painel mora num portal, fora do gatilho. Sem `preventDefault` no
    // `mousedown`, o foco sairia do campo a cada clique numa opção — e quem
    // estava no teclado voltaria ao começo da página.
    montar();
    await userEvent.click(gatilho());

    const aceito = fireEvent.mouseDown(opcao("Fechado"));

    expect(aceito).toBe(false);
  });

  it("desabilitado, não abre", async () => {
    const { onChange } = montar({ disabled: true });

    expect(gatilho()).toBeDisabled();
    await userEvent.click(gatilho());

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("SelectMenu — os papéis da lista", () => {
  it("o gatilho anuncia que abre uma lista e aponta para ela", async () => {
    montar();

    expect(gatilho()).toHaveAttribute("aria-haspopup", "listbox");
    expect(gatilho()).not.toHaveAttribute("aria-controls");

    await userEvent.click(gatilho());

    const alvo = gatilho().getAttribute("aria-controls");
    expect(alvo).toBeTruthy();
    expect(screen.getByRole("listbox").id).toBe(alvo);
  });

  it("a lista leva o nome do campo", async () => {
    montar();
    await userEvent.click(gatilho());

    expect(screen.getByRole("listbox", { name: "Situação" })).toBeInTheDocument();
  });

  it("as opções dizem qual está escolhida", async () => {
    montar({ value: "closed" });
    await userEvent.click(gatilho());

    expect(opcao("Fechado")).toHaveAttribute("aria-selected", "true");
    expect(opcao("Aberto")).toHaveAttribute("aria-selected", "false");
  });

  it("as opções não entram na ordem de tabulação", async () => {
    // O foco fica no gatilho o tempo todo, e a opção em destaque é anunciada
    // por `aria-activedescendant`. Opção focável num portal no fim do `body`
    // seria parada de Tab fora de ordem.
    montar();
    await userEvent.click(gatilho());

    for (const o of screen.getAllByRole("option")) {
      expect(o.tabIndex).toBe(-1);
    }
  });
});

describe("SelectMenu — teclado", () => {
  it("a seta para baixo abre, em destaque a opção escolhida", async () => {
    montar({ value: "closed" });
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}");

    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(gatilho()).toHaveAttribute(
      "aria-activedescendant",
      opcao("Fechado").id,
    );
  });

  it("Enter e Espaço também abrem", async () => {
    montar();
    gatilho().focus();

    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    await userEvent.keyboard(" ");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("as setas andam e o Enter escolhe a opção em que se parou", async () => {
    const { onChange } = montar({ value: "open" });
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("closed");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("as setas não passam das pontas", async () => {
    // Medido no destaque, e não no aviso: reescolher o valor que já está
    // escolhido não chama `onChange` nenhum (paridade com o nativo).
    montar({ value: "open" });
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}{ArrowUp}{ArrowUp}{ArrowUp}");
    expect(gatilho()).toHaveAttribute("aria-activedescendant", opcao("Aberto").id);

    await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}");
    expect(gatilho()).toHaveAttribute("aria-activedescendant", opcao("Congelado").id);
  });

  it("End vai à última e Home volta à primeira", async () => {
    const { onChange } = montar({ value: "closed" });
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}{End}");
    expect(gatilho()).toHaveAttribute(
      "aria-activedescendant",
      opcao("Congelado").id,
    );

    await userEvent.keyboard("{Home}{Enter}");
    expect(onChange).toHaveBeenCalledWith("open");
  });

  it("Espaço escolhe com a lista aberta", async () => {
    const { onChange } = montar({ value: "open" });
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}{ArrowDown} ");

    expect(onChange).toHaveBeenCalledWith("closed");
    // O botão dispara clique no keyup do Espaço. Se o keydown não o impedir,
    // esse clique reabre o menu logo depois de escolher.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("digitar uma letra leva à opção que começa com ela, sem acento", async () => {
    // O nativo faz isso de graça, e quem usa teclado conta com isso.
    const { onChange } = montar({
      value: "",
      options: [
        { value: "a", label: "Aberto" },
        { value: "t", label: "Técnico" },
        { value: "f", label: "Fechado" },
      ],
    });
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}t{Enter}");

    expect(onChange).toHaveBeenCalledWith("t");
  });

  it("Escape fecha sem escolher e o foco fica no gatilho", async () => {
    const { onChange } = montar();
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}{ArrowDown}{Escape}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(gatilho()).toHaveFocus();
  });

  it("o Escape que fecha o menu não chega ao document — não fecha o Modal junto", async () => {
    // O `Modal` escuta Escape em `document`. Sem conter o evento aqui, fechar
    // o menu dentro de uma modal fecharia a modal e jogaria fora o formulário.
    const noDocumento = vi.fn();
    document.addEventListener("keydown", noDocumento);
    try {
      montar();
      gatilho().focus();
      await userEvent.keyboard("{ArrowDown}");

      await userEvent.keyboard("{Escape}");

      expect(noDocumento.mock.calls.some(([e]) => e.key === "Escape")).toBe(false);
    } finally {
      document.removeEventListener("keydown", noDocumento);
    }
  });

  it("com o menu FECHADO, o Escape segue o caminho normal", async () => {
    // A contenção é só de quem o menu consumiu. Com ele fechado, o Escape é da
    // modal — engolir aqui prenderia a pessoa dentro dela.
    const noDocumento = vi.fn();
    document.addEventListener("keydown", noDocumento);
    try {
      montar();
      gatilho().focus();

      await userEvent.keyboard("{Escape}");

      expect(noDocumento.mock.calls.some(([e]) => e.key === "Escape")).toBe(true);
    } finally {
      document.removeEventListener("keydown", noDocumento);
    }
  });

  it("Tab fecha sem escolher", async () => {
    const { onChange } = montar();
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    await userEvent.tab();

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("perder o foco avisa quem chamou (onBlur), como o campo nativo", async () => {
    const onBlur = vi.fn();
    render(
      <>
        <SelectMenu
          value=""
          onChange={vi.fn()}
          onBlur={onBlur}
          options={SITUACOES}
          label="Situação"
        />
        <button type="button">depois</button>
      </>,
    );
    gatilho().focus();

    await userEvent.tab();

    expect(onBlur).toHaveBeenCalledTimes(1);
  });
});

describe("SelectMenu — o painel não fica preso atrás de cartão, tabela ou modal", () => {
  function comRetangulo(r: Partial<DOMRect>) {
    const cheio = {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      bottom: 0,
      right: 0,
      width: 0,
      height: 0,
      toJSON: () => ({}),
      ...r,
    } as DOMRect;
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(cheio);
  }

  it("o painel vai para o body, fora de qualquer overflow da tela", async () => {
    const { container } = render(
      <div style={{ overflow: "hidden" }}>
        <SelectMenu value="" onChange={vi.fn()} options={SITUACOES} label="Situação" />
      </div>,
    );

    await userEvent.click(gatilho());

    const lista = screen.getByRole("listbox");
    expect(container.contains(lista)).toBe(false);
    expect(document.body.contains(lista)).toBe(true);
  });

  it("o painel fica acima da modal (z-[200])", async () => {
    montar();
    await userEvent.click(gatilho());

    const painel = screen.getByRole("listbox");
    expect(Number(painel.style.zIndex)).toBeGreaterThan(200);
    expect(painel.style.position).toBe("fixed");
  });

  it("o painel nunca é mais estreito que o campo, e nasce logo abaixo dele", async () => {
    // Largura CRAVADA no campo seria o defeito oposto: o `<select>` nativo
    // media pela opção mais longa, e um botão mede pelo texto exibido — um
    // painel de 240px truncaria "Administrador" num filtro que mostra
    // "Perfil". Piso no campo, teto na borda da tela.
    comRetangulo({ top: 100, bottom: 138, left: 40, right: 280, width: 240, height: 38 });
    montar();

    await userEvent.click(gatilho());

    const painel = screen.getByRole("listbox");
    expect(painel.style.minWidth).toBe("240px");
    expect(painel.style.width).toBe("max-content");
    expect(painel.style.left).toBe("40px");
    expect(parseFloat(painel.style.top)).toBeGreaterThan(138);
  });

  it("o painel não passa da borda direita da tela", async () => {
    // Celular de 390px, campo começando em 200: o painel pode crescer até a
    // borda menos a folga, e não além.
    comRetangulo({ top: 100, bottom: 138, left: 200, right: 360, width: 160, height: 38 });
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(390);
    montar({ options: [{ value: "x", label: "Um rótulo bem comprido de verdade" }] });

    await userEvent.click(gatilho());

    const painel = screen.getByRole("listbox");
    expect(parseFloat(painel.style.maxWidth)).toBe(390 - 200 - 8);
  });

  it("sem espaço embaixo, abre para cima", async () => {
    // No celular o campo perto do fim da tela abriria o painel para fora dela.
    comRetangulo({ top: 700, bottom: 738, left: 16, right: 374, width: 358, height: 38 });
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(760);
    montar();

    await userEvent.click(gatilho());

    const painel = screen.getByRole("listbox");
    expect(painel.style.top).toBe("");
    expect(parseFloat(painel.style.bottom)).toBeGreaterThan(760 - 700);
  });

  it("lista longa rola dentro do painel, sem estourar a tela", async () => {
    const muitas = Array.from({ length: 40 }, (_, i) => ({
      value: String(i),
      label: "Opção " + String(i),
    }));
    montar({ options: muitas });

    await userEvent.click(gatilho());

    const painel = screen.getByRole("listbox");
    expect(painel.className).toContain("overflow-y-auto");
    expect(painel.style.maxHeight).not.toBe("");
  });

  it("fecha quando o campo sai de cena (desmonta com o menu aberto)", async () => {
    const { unmount } = montar();
    await userEvent.click(gatilho());

    unmount();

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});

describe("SelectMenu — o desenho do HS Growth, nos tokens do pacote", () => {
  it("gatilho: flex, entre as pontas, rounded-lg, px-4 py-2, texto pequeno", () => {
    montar();

    const c = gatilho().className;
    for (const classe of [
      "flex",
      "w-full",
      "items-center",
      "justify-between",
      "gap-3",
      "rounded-lg",
      "border",
      "px-4",
      "py-2",
      "text-sm",
    ]) {
      expect(c.split(/\s+/)).toContain(classe);
    }
  });

  it("gatilho: o anel de foco sai do degrau de AÇÃO, sem o contorno padrão", () => {
    montar();

    const c = gatilho().className;
    expect(c).toContain("focus:outline-none");
    expect(c).toContain("focus:ring-2");
    expect(c).toContain("focus:ring-action");
  });

  it("gatilho: a borda de repouso é contorno de controle (E7), não separador", () => {
    montar();

    expect(gatilho().className).toContain("border-borda-control");
  });

  it("com erro, a borda e o anel viram de perigo", () => {
    montar({ error: "Escolha a situação" });

    expect(gatilho().className).toContain("border-danger");
    expect(gatilho().className).toContain("focus:ring-danger");
    expect(gatilho().className).not.toContain("border-borda-control");
  });

  it("painel: rounded-lg, borda, sombra, fundo de superfície", async () => {
    montar();
    await userEvent.click(gatilho());

    const c = screen.getByRole("listbox").className.split(/\s+/);
    for (const classe of ["rounded-lg", "border", "border-borda", "bg-surface", "shadow-lg"]) {
      expect(c).toContain(classe);
    }
  });

  it("opção: largura cheia, à esquerda, px-4 py-2, com hover", async () => {
    montar();
    await userEvent.click(gatilho());

    const c = opcao("Fechado").className.split(/\s+/);
    for (const classe of [
      "w-full",
      "text-left",
      "px-4",
      "py-2",
      "text-sm",
      "truncate",
      "hover:bg-surface-elevated",
    ]) {
      expect(c).toContain(classe);
    }
  });

  it("a opção escolhida tem destaque próprio", async () => {
    montar({ value: "closed" });
    await userEvent.click(gatilho());
    // O cursor do teclado nasce na escolhida; tira-o de lá para medir só o
    // destaque de seleção na outra.
    await userEvent.hover(opcao("Aberto"));

    expect(opcao("Fechado").className).toContain("bg-surface-elevated");
    expect(opcao("Fechado").className).toContain("font-medium");
    expect(opcao("Congelado").className).not.toContain("font-medium");
  });

  it("não sobra cor cravada do Growth (slate, gray, emerald, white)", async () => {
    const { container } = montar({ value: "open", placeholder: "Todos" });
    await userEvent.click(gatilho());

    // O painel vai para o `body` por portal; olhar só o `container` deixaria
    // metade do componente de fora.
    const html = container.innerHTML + document.body.innerHTML;
    expect(html).not.toMatch(/\b(?:slate|gray|emerald)-\d/);
    expect(html).not.toMatch(/\b(?:bg|text|border)-white\b/);
  });
});

describe("SelectMenu — contraste dos tokens que ele usa", () => {
  it.each(["claro", "escuro"] as const)(
    "borda de repouso e anel de foco passam o piso de componente, tema %s",
    (tema) => {
      expect(contraste("--surface", "--border-control", tema)).toBeGreaterThanOrEqual(
        NAO_TEXTO,
      );
      expect(contraste("--surface", "--action", tema)).toBeGreaterThanOrEqual(
        NAO_TEXTO,
      );
    },
  );

  it.each(["claro", "escuro"] as const)(
    "valor, placeholder e seta são legíveis no gatilho e na lista, tema %s",
    (tema) => {
      expect(contraste("--surface", "--text-body", tema)).toBeGreaterThanOrEqual(AA);
      expect(contraste("--surface", "--text-muted", tema)).toBeGreaterThanOrEqual(AA);
    },
  );

  it.each(["claro", "escuro"] as const)(
    "a opção em destaque e a escolhida continuam legíveis, tema %s",
    (tema) => {
      expect(
        contraste("--surface-elevated", "--text-body", tema),
      ).toBeGreaterThanOrEqual(AA);
      expect(
        contraste("--surface-elevated", "--text-heading", tema),
      ).toBeGreaterThanOrEqual(AA);
      expect(
        contraste("--surface-elevated", "--text-muted", tema),
      ).toBeGreaterThanOrEqual(AA);
    },
  );
});
