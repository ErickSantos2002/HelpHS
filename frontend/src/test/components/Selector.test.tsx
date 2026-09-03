import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Selector } from "../../components/ui/Selector";
import { AA, contraste } from "../helpers/contraste";

/**
 * O seletor único da Fase 8, e o que ele passou a fazer.
 *
 * Os três testes de contrato — `FilterSelect`, `FormDropdown`, `SearchSelect` —
 * provam que os invólucros não mudaram o que as telas já faziam. Este arquivo
 * prova o que **não existia em nenhum dos três**: teclado, papéis de widget,
 * anel de foco e tokens no lugar das 45 cores cravadas.
 *
 * Por que isso importa mais do que parece: o `SearchSelect` já declarava
 * `role="listbox"` e `role="option"` **sem teclado nenhum**. Declarar o papel
 * promete o contrato do widget a quem usa leitor de tela — setas andam, `Enter`
 * escolhe, `Escape` fecha. Prometer e não cumprir é pior que não declarar: a
 * pessoa fica esperando um comportamento que nunca vem.
 */

const SITUACOES = [
  { value: "open", label: "Aberto", dot: "#22c55e" },
  { value: "closed", label: "Fechado", dot: "#64748b" },
];

/** Piso da WCAG 1.4.11 para indicador não textual: borda, anel de foco. */
const NAO_TEXTO = 3;

function montar(props: Partial<React.ComponentProps<typeof Selector>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <Selector value={null} onChange={onChange} options={SITUACOES} {...props} />,
  );
  return { ...utils, onChange };
}

const gatilho = () => screen.getAllByRole("button")[0];

describe("Selector — os papéis que o widget promete", () => {
  it("o gatilho anuncia que abre uma lista, e se está aberta", async () => {
    montar();

    expect(gatilho()).toHaveAttribute("aria-haspopup", "listbox");
    expect(gatilho()).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(gatilho());

    expect(gatilho()).toHaveAttribute("aria-expanded", "true");
  });

  it("o gatilho aponta para o painel que abriu", async () => {
    montar();
    await userEvent.click(gatilho());

    const alvo = gatilho().getAttribute("aria-controls");
    expect(alvo).toBeTruthy();
    expect(screen.getByRole("listbox").id).toBe(alvo);
  });

  it("as opções são opções, e dizem qual está escolhida", async () => {
    montar({ value: "open" });
    await userEvent.click(gatilho());

    expect(screen.getByRole("option", { name: "Aberto" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("option", { name: "Fechado" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });
});

describe("Selector — o teclado, que não existia", () => {
  it("a seta para baixo abre a lista fechada", async () => {
    montar();
    gatilho().focus();

    await userEvent.keyboard("{ArrowDown}");

    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("as setas andam e o Enter escolhe a opção em que se parou", async () => {
    const { onChange } = montar();

    await userEvent.click(gatilho());
    // O índice 0 é a linha que limpa; a primeira opção é o passo seguinte.
    await userEvent.keyboard("{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("open", SITUACOES[0]);
  });

  it("duas setas param na segunda opção, e não passam do fim", async () => {
    const { onChange } = montar();

    await userEvent.click(gatilho());
    await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}{Enter}");

    // Só há duas opções: as setas extras não podem escolher nada além delas.
    expect(onChange).toHaveBeenCalledWith("closed", SITUACOES[1]);
  });

  it("o End vai à última e o Home volta à linha que limpa", async () => {
    const { onChange } = montar({ value: "open" });

    await userEvent.click(gatilho());
    await userEvent.keyboard("{End}{Home}{Enter}");

    expect(onChange).toHaveBeenCalledWith(null, null);
  });

  it("o Escape fecha sem escolher, e devolve o foco ao gatilho", async () => {
    const { onChange } = montar();

    await userEvent.click(gatilho());
    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(gatilho()).toHaveFocus();
  });
});

describe("Selector — o foco, que estava ausente", () => {
  it("o gatilho tem anel de foco, e ele sai do degrau de AÇÃO", () => {
    // Os dois seletores de formulário traziam `focus:outline-none` e **nada**
    // no lugar: quem navegava por teclado não via onde estava. É o mesmo
    // defeito que a emenda E9 consertou no `Checkbox` e no `Switch`.
    montar();

    const c = gatilho().className;
    expect(c).toContain("focus-visible:ring-2");
    expect(c).toContain("focus-visible:ring-action");
    expect(c).not.toContain("focus:ring-primary");
  });
});

describe("Selector — os tokens no lugar do slate cravado", () => {
  it("não sobra cor cravada em nenhuma das duas variantes", async () => {
    for (const variant of ["filter", "form"] as const) {
      const { container, unmount } = render(
        <Selector
          value="open"
          onChange={vi.fn()}
          options={SITUACOES}
          variant={variant}
          label="Situação"
        />,
      );
      await userEvent.click(screen.getAllByRole("button")[0]);

      // O painel do filtro vai para o `body` por portal, então olhar só o
      // `container` deixaria metade do componente de fora.
      const html = container.innerHTML + document.body.innerHTML;
      expect(html).not.toMatch(/slate-\d/);
      expect(html).not.toMatch(/background-surface|background-elevated/);

      unmount();
    }
  });

  it("a borda de repouso é contorno de controle, não separador", () => {
    // `--border-control`, da E7. Antes era `border-border/60`, que é a linha de
    // cabelo entre superfícies — 1,23:1.
    montar();

    expect(gatilho().className).toContain("border-borda-control");
  });

  it("o rótulo usa token de texto, e não o slate-300 do tema escuro", () => {
    // O `FormDropdown` e o `SearchSelect` pintavam o rótulo com `text-slate-300`
    // **sem `dark:`** — eram escritos só para o tema escuro. No claro, o rótulo
    // ficava slate-300 sobre fundo claro.
    render(
      <Selector value={null} onChange={vi.fn()} options={SITUACOES} label="Situação" />,
    );

    expect(screen.getByText("Situação").className).toContain("text-conteudo");
  });
});

describe("Selector — contraste", () => {
  it.each(["claro", "escuro"] as const)(
    "borda de repouso e anel de foco passam o piso de componente, tema %s",
    (tema) => {
      expect(
        contraste("--surface", "--border-control", tema),
      ).toBeGreaterThanOrEqual(NAO_TEXTO);
      expect(contraste("--surface", "--action", tema)).toBeGreaterThanOrEqual(
        NAO_TEXTO,
      );
    },
  );

  it.each(["claro", "escuro"] as const)(
    "rótulo, opção e linha secundária são texto, tema %s",
    (tema) => {
      expect(contraste("--surface", "--text-body", tema)).toBeGreaterThanOrEqual(AA);
      expect(contraste("--surface", "--text-muted", tema)).toBeGreaterThanOrEqual(AA);
      expect(
        contraste("--surface", "--text-heading", tema),
      ).toBeGreaterThanOrEqual(AA);
    },
  );

  it.each(["claro", "escuro"] as const)(
    "a opção escolhida usa o par medido da tinta, tema %s",
    (tema) => {
      // `bg-tint-primary` + `text-on-tint-primary`, o mesmo par do `Badge`. O
      // original usava `bg-primary/10 text-primary`, e `--color-primary-500`
      // como texto sobre `--bg-base` dá 3,66:1 — reprova, e opção é texto.
      expect(
        contraste("--tint-primary", "--on-tint-primary", tema),
      ).toBeGreaterThanOrEqual(AA);
    },
  );
});
