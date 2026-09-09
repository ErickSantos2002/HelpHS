import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Tooltip } from "../../components/ui/Tooltip";

/**
 * O que estes casos prendem é o **desvio** do original, mais que o porte.
 *
 * A pastilha é decoração: ela repete um nome que o disparador já carrega. Se um
 * dia alguém tirar o `aria-hidden` "para o leitor de tela também ver", a dica
 * passa a ser lida solta, e o nome do controle vira dois.
 */
describe("Tooltip", () => {
  it("a pastilha é invisível para o leitor de tela, sempre", () => {
    // O `role="tooltip"` do original é inerte — só significa alguma coisa se
    // alguém o referenciar por `aria-describedby`. Aqui a pastilha é decoração
    // declarada, e quem dispara carrega o próprio nome.
    render(
      <Tooltip label="Chamados">
        <button aria-label="Chamados">•</button>
      </Tooltip>,
    );
    // Um nome acessível só: o do botão. A pastilha não acrescenta um segundo.
    expect(screen.getAllByRole("button", { name: "Chamados" })).toHaveLength(1);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("o texto continua no DOM, e é a opacidade que o mostra", () => {
    // Não é `display: none`: a pastilha transita, e um elemento que entra e sai
    // do DOM não transita. Quem confere isto por `queryByText` se confunde.
    const { container } = render(
      <Tooltip label="Relatórios">
        <button aria-label="Relatórios">•</button>
      </Tooltip>,
    );
    const pastilha = container.querySelector("[aria-hidden='true']");
    expect(pastilha).toHaveTextContent("Relatórios");
    expect(pastilha?.className).toContain("opacity-0");
  });

  it("o TECLADO abre a dica, e não só o ponteiro", () => {
    // O motivo de o original ter `onFocus`/`onBlur`, e o que o mantém
    // utilizável: quem navega por teclado alcança o disparador e precisa ver a
    // dica pelo mesmo motivo que quem passa o mouse.
    const { container } = render(
      <Tooltip label="Agenda">
        <button aria-label="Agenda">•</button>
      </Tooltip>,
    );
    const pastilha = () => container.querySelector("[aria-hidden='true']");
    expect(pastilha()?.className).toContain("opacity-0");

    fireEvent.focus(screen.getByRole("button"));
    expect(pastilha()?.className).toContain("opacity-100");

    fireEvent.blur(screen.getByRole("button"));
    expect(pastilha()?.className).toContain("opacity-0");
  });

  it("o ponteiro abre e fecha", () => {
    const { container } = render(
      <Tooltip label="Equipe">
        <button aria-label="Equipe">•</button>
      </Tooltip>,
    );
    const alvo = container.firstElementChild as HTMLElement;
    const pastilha = () => container.querySelector("[aria-hidden='true']");

    fireEvent.mouseEnter(alvo);
    expect(pastilha()?.className).toContain("opacity-100");

    fireEvent.mouseLeave(alvo);
    expect(pastilha()?.className).toContain("opacity-0");
  });

  it("a pastilha não intercepta o clique do que está embaixo", () => {
    // `pointer-events-none`. Sem isso a dica, que nasce colada ao disparador,
    // rouba o clique dele no exato momento em que aparece.
    const { container } = render(
      <Tooltip label="Base">
        <button aria-label="Base">•</button>
      </Tooltip>,
    );
    expect(
      container.querySelector("[aria-hidden='true']")?.className,
    ).toContain("pointer-events-none");
  });

  it("a cor sai do TOKEN, e não da paleta do Tailwind", () => {
    // `bg-slate-900` pegaria o slate do Tailwind, não o do pacote — e seria
    // paleta crua, que a catraca conta. A rampa `slate` não tem mapa no
    // `tailwind.config.js`; só a `primary` tem.
    const { container } = render(
      <Tooltip label="x">
        <button aria-label="x">•</button>
      </Tooltip>,
    );
    const cls = container.querySelector("[aria-hidden='true']")?.className ?? "";
    expect(cls).toContain("bg-[var(--color-slate-900)]");
    expect(cls).toContain("text-[var(--color-white)]");
    expect(cls).not.toMatch(/(?<![\w-[])(bg|text)-slate-\d/);
  });
});
