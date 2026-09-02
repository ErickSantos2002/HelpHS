import { createHash } from "node:crypto";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Icon, ICON_PATHS } from "../../components/ui/Icon";
import type { IconName } from "../../components/ui/Icon";

/** Renderiza e devolve o `<svg>`, que é o primeiro filho. */
function svg(elemento: React.ReactElement): SVGSVGElement | null {
  const { container } = render(elemento);
  return container.querySelector("svg");
}

describe("Icon", () => {
  it("traz os 25 nomes do pacote, nem um a mais", () => {
    expect(Object.keys(ICON_PATHS)).toHaveLength(25);
  });

  it("desenha na grade de 24 do pacote e herda a cor de quem o contém", () => {
    const el = svg(<Icon name="check" />);
    expect(el).toHaveAttribute("viewBox", "0 0 24 24");
    expect(el).toHaveAttribute("stroke", "currentColor");
    expect(el).toHaveAttribute("fill", "none");
  });

  it("é decorativo: sai da árvore de acessibilidade", () => {
    // O rótulo é de quem usa o ícone (o botão, o item de menu), não dele.
    expect(svg(<Icon name="bell" />)).toHaveAttribute("aria-hidden", "true");
  });

  it("nasce com os padrões do pacote — 20px e traço 1,75", () => {
    const el = svg(<Icon name="menu" />);
    expect(el).toHaveAttribute("width", "20");
    expect(el).toHaveAttribute("height", "20");
    expect(el).toHaveAttribute("stroke-width", "1.75");
  });

  it("aceita o tamanho e o peso de traço de cada lugar", () => {
    // 16 em botão, 24 em cabeçalho; peso 2 dentro de botão.
    const el = svg(<Icon name="plus" size={16} strokeWidth={2} />);
    expect(el).toHaveAttribute("width", "16");
    expect(el).toHaveAttribute("stroke-width", "2");
  });

  it("cada nome desenha um traçado diferente, e é o que está na tabela", () => {
    const vistos = new Set<string>();
    for (const nome of Object.keys(ICON_PATHS) as IconName[]) {
      const el = svg(<Icon name={nome} />);
      const d = el?.querySelector("path")?.getAttribute("d") ?? "";
      expect(d, nome).toBe(ICON_PATHS[nome]);
      vistos.add(d);
    }
    expect(vistos.size).toBe(25);
  });

  it("os 25 traçados continuam idênticos aos do pacote", () => {
    // O teste acima compara a tabela consigo mesma: trocar um traçado aqui e no
    // componente passaria verde. Este prende a tabela a um número calculado do
    // `Icon.jsx` do pacote no dia da cópia — a mesma conferência por hash que o
    // `VERSION.md` faz com os sete arquivos de CSS.
    //
    // Se este teste cair, ou alguém editou um traçado à mão, ou o pacote mudou.
    // No segundo caso o conserto é recopiar e trocar o hash, com registro.
    const serial = Object.entries(ICON_PATHS)
      .map(([nome, d]) => `${nome}:${d}`)
      .join("\n");
    const hash = createHash("sha256").update(serial, "utf-8").digest("hex");
    expect(hash.toUpperCase()).toBe(
      "1B07BB04C2632522334663D75DC172FE634F97A33727339CB9183EF97A439C3B",
    );
  });

  it("nome desconhecido não desenha nada, em vez de um quadrado vazio", () => {
    const { container } = render(
      <Icon name={"naoExiste" as IconName} />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("não encolhe dentro de flex, e ainda aceita classe de fora", () => {
    const el = svg(<Icon name="search" className="text-conteudo-muted" />);
    expect(el).toHaveClass("shrink-0");
    expect(el).toHaveClass("text-conteudo-muted");
  });
});
