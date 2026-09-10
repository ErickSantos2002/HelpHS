import { createHash } from "node:crypto";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  Icon,
  ICON_PATHS,
  ICON_PATHS_LOCAIS,
  ICON_PATHS_PACOTE,
} from "../../components/ui/Icon";
import type { IconName } from "../../components/ui/Icon";

/** Renderiza e devolve o `<svg>`, que é o primeiro filho. */
function svg(elemento: React.ReactElement): SVGSVGElement | null {
  const { container } = render(elemento);
  return container.querySelector("svg");
}

describe("Icon", () => {
  it("traz os 62 nomes do pacote, nem um a mais", () => {
    // Eram 25 até a **E20**, que subiu para o pacote os 21 que viviam numa
    // tabela local do HelpHS, e 62 desde a **E21**, que acrescentou 16 vindos
    // dos 151 `<svg>` soltos das telas internas. O número muda quando o pacote
    // muda, e só então.
    expect(Object.keys(ICON_PATHS_PACOTE)).toHaveLength(62);
  });

  it("a tabela local está vazia — variante local não existe", () => {
    // Decisão do operador em 08/09/2026: ou o desenho já significa o mesmo que
    // um do pacote e se unifica, ou ele entra no pacote com nome próprio, como
    // emenda. A tabela fica declarada e vazia de propósito: é onde um
    // acréscimo apareceria, e uma tabela ausente não tem onde ser conferida.
    expect(Object.keys(ICON_PATHS_LOCAIS)).toEqual([]);
  });

  it("nenhum acréscimo local reescreve um nome do pacote", () => {
    // As duas tabelas se juntam por espalhamento, e a de baixo ganha. Um nome
    // repetido trocaria o desenho de um ícone do pacote em silêncio — e o hash
    // NÃO pegaria, porque ele confere a tabela de cima, que continuaria
    // intacta. É a única costura entre as duas, e é aqui que ela se confere.
    const doPacote = new Set(Object.keys(ICON_PATHS_PACOTE));
    const repetidos = Object.keys(ICON_PATHS_LOCAIS).filter((n) => doPacote.has(n));
    expect(repetidos).toEqual([]);
  });

  it("o conjunto que se desenha é a soma dos dois", () => {
    expect(Object.keys(ICON_PATHS)).toHaveLength(
      Object.keys(ICON_PATHS_PACOTE).length + Object.keys(ICON_PATHS_LOCAIS).length,
    );
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
    // Alguns desenhos têm mais de um traçado — o olho é pupila mais contorno.
    // A comparação é sobre a LISTA, e a unicidade sobre a lista inteira: dois
    // ícones que só coincidam no primeiro traçado continuam sendo dois.
    const vistos = new Set<string>();
    for (const nome of Object.keys(ICON_PATHS) as IconName[]) {
      const el = svg(<Icon name={nome} />);
      const desenhados = Array.from(el?.querySelectorAll("path") ?? []).map(
        (p) => p.getAttribute("d") ?? "",
      );
      const naTabela = ICON_PATHS[nome];
      const esperados = typeof naTabela === "string" ? [naTabela] : [...naTabela];
      expect(desenhados, nome).toEqual(esperados);
      vistos.add(esperados.join("|"));
    }
    expect(vistos.size).toBe(Object.keys(ICON_PATHS).length);
  });

  it("os 62 traçados continuam idênticos aos do pacote", () => {
    // O teste acima compara a tabela consigo mesma: trocar um traçado aqui e no
    // componente passaria verde. Este prende a tabela a um número calculado do
    // `Icon.jsx` do pacote no dia da cópia — a mesma conferência por hash que o
    // `VERSION.md` faz com os sete arquivos de CSS.
    //
    // Se este teste cair, ou alguém editou um traçado à mão, ou o pacote mudou.
    // No segundo caso o conserto é recopiar e trocar o hash, com registro.
    const serial = Object.entries(ICON_PATHS_PACOTE)
      .map(([nome, d]) => `${nome}:${d}`)
      .join("\n");
    const hash = createHash("sha256").update(serial, "utf-8").digest("hex");
    expect(hash.toUpperCase()).toBe(
      // Trocado na E20, na E21 e na E21-b — as três vezes pelo segundo dos dois
      // casos que o comentário acima prevê: o pacote mudou, e a tabela foi
      // REGERADA a partir dele por extração, com os 62 traçados conferidos
      // caractere a caractere dos dois lados antes de o número ser trocado.
      // O primeiro caso (alguém editou à mão) continua sendo motivo para
      // investigar, não para trocar o número.
      //
      // ⚠️ E a E21-b ensinou o limite deste caso: ele passou verde com os dois
      // polegares TROCADOS DE NOME, porque o hash foi calculado sobre a tabela
      // errada. Hash prova que ninguém mexeu depois; não prova que estava certo
      // antes. É por isso que existe o caso da geometria, logo abaixo.
      "42F3A276E0477FFF5DB82069E251117CE1ECAD44575093C07E42B449545650B6",
    );
  });

  it("o polegar de `thumbsUp` aponta para CIMA, e o de `thumbsDown` para baixo", () => {
    // O caso que a **E21-b** comprou com um defeito. Na E21 os dois nasceram
    // com os nomes trocados, e NADA acusou: a contagem estava certa (16 nomes
    // novos), a unicidade estava certa (os traçados eram distintos), e o hash
    // estava certo — porque foi calculado sobre a tabela errada.
    //
    // `ICON_PATHS` é mapa de texto. Nome e desenho não têm relação nenhuma que
    // o TypeScript, o `tsc` ou uma revisão de diff consigam conferir. A troca
    // só produziu sintoma na tela que usa os dois lado a lado, num botão "Sim"
    // e num "Não" — e foi lá que apareceu.
    //
    // O que se mede aqui é a GEOMETRIA, e ela é legível no traçado: o punho é
    // o retângulo do pulso, e o lado da figura em que ele está diz para onde o
    // polegar aponta.
    //
    //   punho ancorado em y=20 (embaixo)  → a mão está acima  → polegar SOBE
    //   punho começando em y≈4 (no alto)  → a mão está abaixo → polegar DESCE
    //
    // Este caso reprova o conserto ingênuo — trocar os nomes de volta "porque
    // parecia errado" —, que é exatamente o risco de um defeito assim.
    expect(ICON_PATHS.thumbsUp).toMatch(/M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2\.5$/);
    expect(ICON_PATHS.thumbsDown).toMatch(/m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2\.5$/);

    // E os dois não podem ser o mesmo desenho, que é o outro jeito de errar.
    expect(ICON_PATHS.thumbsUp).not.toBe(ICON_PATHS.thumbsDown);
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
