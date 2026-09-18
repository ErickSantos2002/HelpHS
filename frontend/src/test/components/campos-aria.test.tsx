import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "../../components/ui/Checkbox";
import { Input } from "../../components/ui/Input";
import { RadioCards } from "../../components/ui/RadioCards";
import { Select } from "../../components/ui/Select";
import { Selector } from "../../components/ui/Selector";
import { Textarea } from "../../components/ui/Textarea";

/**
 * O erro do formulário chegando a quem não o vê.
 *
 * Os campos renderizavam o erro e a dica como `<p>` soltos ao lado do
 * controle. Visualmente ficam juntos; na árvore de acessibilidade **não havia
 * relação nenhuma**. A pessoa ouvia o nome do campo, digitava, o formulário
 * recusava — e ela nunca ouvia por quê.
 *
 * O projeto inteiro tinha **zero ocorrências** de `aria-invalid`,
 * `aria-describedby` e `aria-required` quando este arquivo nasceu. O achado veio
 * da sessão do ChamadosHS, que encontrou o mesmo em treze formulários e resolveu
 * com um componente `Campo`; aqui os primitivos já são donos do rótulo, do erro
 * e da dica, então a ligação mora dentro deles e nenhuma tela muda.
 *
 * ── Por que `aria-required` não aparece aqui ──────────────────────────
 *
 * Os campos com controle nativo recebem `required` pelo espalhamento das props,
 * e o atributo nativo já informa a árvore de acessibilidade. Repetir com
 * `aria-required` declararia duas vezes a mesma coisa — e as duas podem
 * divergir. O `Selector` não tem controle nativo, e por isso é o único que
 * precisaria; hoje ele não tem prop de obrigatoriedade, então não finge ter.
 *
 * ── Três implementadores ficaram de fora, e é a origem da regra ───────
 *
 * A tabela nasceu com `Input` e `Textarea`, e o `Selector` ganhou bloco próprio
 * logo abaixo. Ficaram de fora:
 *
 * - o **`Select`**, o seletor nativo de dezoito chamadas depois da D9.2. Erro e
 *   dica seguiam `<p>` soltos, sem `aria-describedby`, e o campo recusado sem
 *   `aria-invalid`. Quatro casos caíram quando ele entrou;
 * - o **`RadioCards`**, que implementava certo — e ninguém sabia, porque nada
 *   media;
 * - o **`Checkbox`**, que renderizava a dica como `<span>` solto, sem
 *   `aria-describedby`. É o defeito do `Select`, na metade da dica.
 *
 * Três de oito componentes de fora de um contrato que se dizia compartilhado.
 * Nada acusava, porque a única coisa que cobraria era esta tabela — e uma
 * tabela de contrato que não cobre todos os implementadores dá a impressão de
 * contrato e não é.
 *
 * ── A regra que este arquivo passa a obedecer ─────────────────────────
 *
 * 1. **Uma linha por implementador.** Nenhum bloco separado por componente —
 *    era o bloco separado do `Selector` que fazia a tabela parecer completa.
 * 2. **Caso negativo só acompanhado do positivo correspondente.** "Sem erro não
 *    se declara inválido" passa de graça em quem nunca declara erro nenhum; ele
 *    só conta em quem também prova o caso positivo.
 * 3. **Um caso que reprova se um implementador conhecido ficar de fora** — a
 *    guarda, logo abaixo.
 *
 * ── A forma: capacidade DECLARADA, não inferida ───────────────────────
 *
 * Cada linha declara à mão o que suporta: `error`, `hint`, ou os dois. E roda
 * os casos daquela capacidade.
 *
 * **Declaração explícita é contrato. Inferir suporte do comportamento é espelho.**
 * Um caso escrito como "se o componente suportar `error`, então o erro é
 * apontado" pergunta ao componente o que ele faz e depois confere que ele faz
 * aquilo: passa em qualquer implementação, inclusive na que não implementa
 * nada. Por isso a capacidade não sai do componente — ela é escrita na linha.
 *
 * As duas pontas erradas ficam cobertas, e é por isso que a forma funciona:
 *
 * | o que dá errado | o que reprova |
 * |---|---|
 * | declara a capacidade e não implementa | o caso **positivo** daquela capacidade |
 * | implementa e não declara | a **guarda de ausentes** |
 *
 * Nenhuma das duas depende de o teste adivinhar nada. A declaração à mão é o
 * contrato; a varredura de `components/ui/*.tsx` é a conferência cruzada. **As
 * duas juntas** — nenhuma sozinha.
 *
 * ── Por que cada linha traz seu próprio localizador ───────────────────
 *
 * Quem carrega `aria-describedby` não é o mesmo elemento em todos: no `Input`,
 * no `Textarea`, no `Select` e no `Checkbox` é o controle nativo; no `Selector`
 * é o `<button>` do gatilho; no `RadioCards` é o `<fieldset>`, enquanto o
 * `aria-invalid` fica nos rádios. Um montador único não daria conta — e é
 * exatamente por não dar conta que o `Selector` acabou num bloco à parte, que é
 * como ele saiu do alcance da tabela sem que ninguém notasse.
 */

// ─────────────────────────────────────────────────────────────────────
// A guarda: quem implementa o contrato sai do disco, não daqui
// ─────────────────────────────────────────────────────────────────────

/**
 * Descobre os implementadores lendo `src/components/ui/*.tsx`.
 *
 * A lista **não pode** ser escrita à mão ao lado da tabela: seria a mesma lista
 * com o mesmo defeito, e um componente novo continuaria entrando sem que nada
 * cobrasse. Ela sai de propriedade observável do código.
 *
 * **O critério.** É implementador de um atributo quem o declara na interface de
 * props do componente **e não o repassa** a outro componente. As duas metades
 * importam:
 *
 * - *Declarar na interface de props*, e não em qualquer lugar do arquivo. O
 *   `SelectorOption` e o `SearchSelectOption` têm um campo `hint` que é a linha
 *   secundária **de cada opção da lista** — nada a ver com a dica do campo. Uma
 *   busca de texto solta marcaria o `Selector` como implementador de `hint`, a
 *   tabela passaria a cobrar dele um contrato que ele nunca prometeu, e a
 *   guarda dispararia em quem está certo. Por isso só conta o que está dentro
 *   de `interface …Props`. Pelo mesmo motivo ficam de fora o `ICON_PATHS` do
 *   `Icon` (que tem uma chave `error`) e o mapa de estilos do `AppToaster`.
 * - *Não repassar*. Delegação se reconhece por `error={error}` / `hint={hint}`
 *   no JSX, e hoje existem exatamente dois casos, ambos invólucros finos e
 *   ambos `@deprecated`:
 *
 *       FormDropdown.tsx:  <Selector … label={label} error={error} … />
 *       SearchSelect.tsx:  <Selector … label={label} error={error} … />
 *
 *   Os dois declaram `error` e nenhum dos dois desenha erro nenhum — quem
 *   desenha é o `Selector`, que já tem linha. Cobrar deles seria cobrar a mesma
 *   implementação duas vezes, e um dia divergiriam do que o `Selector` faz sem
 *   que ninguém soubesse qual dos três quebrou.
 */
/*
 * O caminho sai do `process.cwd()`, que o vitest fixa na raiz da configuração
 * (`frontend/`). O `import.meta.url` NÃO serve aqui: sob a transformação do
 * vite ele não é uma URL `file:`, e o `fileURLToPath` recusa. Se o diretório
 * mudar de lugar, quem acusa é o caso de controle da guarda — ele exige
 * levantamento não vazio, e um caminho errado devolve nada.
 */
const DIR_UI = join(process.cwd(), "src", "components", "ui");

/**
 * Tira comentários antes de procurar declaração.
 *
 * Os arquivos deste diretório são cheios de prosa que cita `error` e `hint` —
 * o cabeçalho do `Selector` gasta duas frases explicando por que `dot` e `hint`
 * continuam campos separados. Sem isto, comentário viraria declaração.
 */
function semComentarios(fonte: string): string {
  return fonte
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((linha) => !linha.trimStart().startsWith("//"))
    .join("\n");
}

/** O corpo de cada `interface …Props`, com as chaves balanceadas. */
function corposDeProps(fonte: string): string[] {
  const corpos: string[] = [];
  const abertura = /interface\s+\w*Props\b/g;
  let achado: RegExpExecArray | null;

  while ((achado = abertura.exec(fonte)) !== null) {
    // O `extends Omit<…, "onChange" | "type">` do `Checkbox` fica entre o nome
    // e o corpo, então a chave do corpo é a primeira DEPOIS do nome — não a
    // primeira da linha.
    const inicio = fonte.indexOf("{", achado.index);
    if (inicio === -1) continue;

    let nivel = 0;
    for (let i = inicio; i < fonte.length; i++) {
      if (fonte[i] === "{") nivel++;
      else if (fonte[i] === "}" && --nivel === 0) {
        corpos.push(fonte.slice(inicio + 1, i));
        break;
      }
    }
  }

  return corpos;
}

function declaraProp(corpos: string[], atributo: string): boolean {
  const decl = new RegExp("(^|[\\s;{])" + atributo + "\\??\\s*:");
  return corpos.some((corpo) => decl.test(corpo));
}

function repassa(fonte: string, atributo: string): boolean {
  return new RegExp("\\b" + atributo + "=\\{" + atributo + "\\}").test(fonte);
}

type Capacidade = "error" | "hint";

const CAPACIDADES: Capacidade[] = ["error", "hint"];

interface AchadoNoDisco {
  nome: string;
  capacidades: Capacidade[];
}

const NO_DISCO: AchadoNoDisco[] = readdirSync(DIR_UI)
  .filter((arquivo) => arquivo.endsWith(".tsx"))
  .map((arquivo) => {
    const fonte = semComentarios(readFileSync(join(DIR_UI, arquivo), "utf-8"));
    const props = corposDeProps(fonte);

    return {
      nome: arquivo.replace(/\.tsx$/, ""),
      capacidades: CAPACIDADES.filter(
        (cap) => declaraProp(props, cap) && !repassa(fonte, cap),
      ),
    };
  })
  .filter((achado) => achado.capacidades.length > 0);

// ─────────────────────────────────────────────────────────────────────
// A tabela: uma linha por implementador, capacidade escrita à mão
// ─────────────────────────────────────────────────────────────────────

interface Adereços {
  error?: string;
  hint?: string;
  required?: boolean;
}

interface Linha {
  nome: string;
  /** O que este implementador suporta. Escrito, não perguntado ao componente. */
  capacidades: Capacidade[];
  montar: (p: Adereços) => void;
  /** Quem carrega `aria-describedby`. */
  descrito: () => HTMLElement;
  /** Quem carrega `aria-invalid`. Só existe em quem declara `error`. */
  invalido?: () => HTMLElement;
  /**
   * Quem carrega o `required` nativo. Ausente no `Selector`, cujo gatilho é um
   * `<button>` — botão não é campo de formulário e não tem obrigatoriedade
   * nativa para herdar. Isto fica **fora** da guarda de propósito: a decisão que
   * ela automatiza é sobre `error` e `hint`, e a guarda não deve cobrar o que
   * não sabe conferir no disco.
   */
  nativo?: () => HTMLElement;
}

const OPCOES = [{ value: "a", label: "Aberto" }];

const campo = () => screen.getByLabelText("Título");

const TABELA: Linha[] = [
  {
    nome: "Input",
    capacidades: ["error", "hint"],
    montar: (p) => render(<Input label="Título" {...p} />),
    descrito: campo,
    invalido: campo,
    nativo: campo,
  },
  {
    nome: "Textarea",
    capacidades: ["error", "hint"],
    montar: (p) => render(<Textarea label="Título" {...p} />),
    descrito: campo,
    invalido: campo,
    nativo: campo,
  },
  {
    nome: "Select",
    capacidades: ["error", "hint"],
    montar: (p) => render(<Select label="Título" options={OPCOES} {...p} />),
    descrito: campo,
    invalido: campo,
    nativo: campo,
  },
  {
    // Só `error`. O `hint` do `Selector` é da OPÇÃO (`SelectorOption.hint`, a
    // linha secundária que desambigua homônimos na lista), não do campo:
    // `SelectorProps` não tem `hint`, e `<Selector hint=… />` nem compila.
    nome: "Selector",
    capacidades: ["error"],
    montar: ({ error }) =>
      render(
        <Selector
          value={null}
          onChange={vi.fn()}
          options={OPCOES}
          label="Título"
          error={error}
        />,
      ),
    descrito: () => screen.getAllByRole("button")[0],
    invalido: () => screen.getAllByRole("button")[0],
  },
  {
    // O `aria-describedby` mora no `<fieldset>`, que é quem tem o nome do
    // grupo; o `aria-invalid` mora em cada rádio, que é quem foi recusado.
    nome: "RadioCards",
    capacidades: ["error", "hint"],
    montar: ({ error, hint, required }) =>
      render(
        <RadioCards
          name="situacao"
          label="Título"
          value=""
          onChange={vi.fn()}
          options={OPCOES}
          error={error}
          hint={hint}
          required={required}
        />,
      ),
    descrito: () => screen.getByRole("group"),
    invalido: () => screen.getAllByRole("radio")[0],
    nativo: () => screen.getAllByRole("radio")[0],
  },
  {
    // Só `hint`. O `Checkbox` não tem prop de erro, e inventar uma para ele
    // caber inteiro na tabela seria mudar o componente para agradar o teste.
    nome: "Checkbox",
    capacidades: ["hint"],
    montar: ({ hint, required }) =>
      render(
        <Checkbox
          checked={false}
          onChange={vi.fn()}
          label="Título"
          hint={hint}
          required={required}
        />,
      ),
    descrito: () => screen.getByRole("checkbox"),
    nativo: () => screen.getByRole("checkbox"),
  },
];

const suporta = (linha: Linha, cap: Capacidade) => linha.capacidades.includes(cap);

const fatia = (filtro: (l: Linha) => boolean) =>
  TABELA.filter(filtro).map((l) => [l.nome, l] as const);

const COM_ERRO = fatia((l) => suporta(l, "error"));
const COM_DICA = fatia((l) => suporta(l, "hint"));
const COM_AMBOS = fatia((l) => suporta(l, "error") && suporta(l, "hint"));
const COM_NATIVO = fatia((l) => l.nativo !== undefined);

const nomes = (lista: { nome: string }[]) => lista.map((x) => x.nome).sort();

describe("a tabela cobre todo implementador do contrato", () => {
  it("o levantamento do disco não veio vazio", () => {
    // Se o caminho de `DIR_UI` errar, todo `toEqual` abaixo compara vazio com
    // vazio e a guarda aprova o silêncio. Este caso é o controle dela.
    expect(NO_DISCO.length).toBeGreaterThan(0);
  });

  it.each(CAPACIDADES)(
    "nenhum implementador de `%s` fica de fora, nem sobra declarado",
    (cap) => {
      // Nas duas direções, e é de propósito. Faltar na tabela é o defeito do
      // `Select`; sobrar é uma linha declarando capacidade que o componente não
      // tem — que faria a tabela cobrar contrato inexistente de quem está certo.
      expect(nomes(TABELA.filter((l) => suporta(l, cap)))).toEqual(
        nomes(NO_DISCO.filter((c) => c.capacidades.includes(cap))),
      );
    },
  );

  it("a tabela não tem linha sem capacidade nenhuma", () => {
    // Fecha a última fresta: uma linha com a lista de capacidades vazia passaria
    // nos casos acima sem rodar caso nenhum e sem provar coisa alguma.
    expect(nomes(TABELA)).toEqual(nomes(NO_DISCO));
  });
});

describe("campos — o erro é ligado ao controle", () => {
  it.each(COM_ERRO)("%s: o erro é apontado por aria-describedby", (_nome, linha) => {
    linha.montar({ error: "Informe o título" });

    const alvo = linha.descrito().getAttribute("aria-describedby");

    expect(alvo).toBeTruthy();
    expect(document.getElementById(alvo!)).toHaveTextContent("Informe o título");
  });

  it.each(COM_ERRO)("%s: o campo recusado é marcado como inválido", (_nome, linha) => {
    linha.montar({ error: "Informe o título" });

    expect(linha.invalido!()).toHaveAttribute("aria-invalid", "true");
  });

  it.each(COM_ERRO)("%s: campo sem erro não se declara inválido", (_nome, linha) => {
    // Negativo, e só roda em quem prova o positivo logo acima.
    linha.montar({});

    expect(linha.invalido!()).not.toHaveAttribute("aria-invalid");
  });
});

describe("campos — a dica é ligada ao controle", () => {
  it.each(COM_DICA)("%s: a dica é apontada por aria-describedby", (_nome, linha) => {
    linha.montar({ hint: "Máximo de 80 caracteres" });

    const alvo = linha.descrito().getAttribute("aria-describedby");

    expect(alvo).toBeTruthy();
    expect(document.getElementById(alvo!)).toHaveTextContent(
      "Máximo de 80 caracteres",
    );
  });
});

describe("campos — sem erro e sem dica, não se aponta para nada", () => {
  // Negativo do apontamento, e vale para toda linha da tabela: toda linha tem
  // ao menos uma capacidade, e o positivo dela roda num dos blocos acima.
  it.each(fatia(() => true))("%s", (_nome, linha) => {
    linha.montar({});

    expect(linha.descrito()).not.toHaveAttribute("aria-describedby");
  });
});

describe("campos — com erro, quem é apontado é o erro", () => {
  it.each(COM_AMBOS)("%s: a dica cede a vez ao erro", (_nome, linha) => {
    // A dica nem é renderizada quando há erro — o apontamento tem de seguir o
    // que está na tela, ou aponta para um id que não existe.
    linha.montar({ error: "Informe o título", hint: "Máximo de 80 caracteres" });

    const alvo = linha.descrito().getAttribute("aria-describedby");
    expect(document.getElementById(alvo!)).toHaveTextContent("Informe o título");
  });
});

describe("campos — o required nativo passa sem aria-required duplicado", () => {
  it.each(COM_NATIVO)("%s", (_nome, linha) => {
    linha.montar({ required: true });

    expect(linha.nativo!()).toBeRequired();
    expect(linha.nativo!()).not.toHaveAttribute("aria-required");
  });
});

describe("campos — o id deixa de sair do rótulo", () => {
  it("dois campos com o mesmo rótulo não compartilham id", () => {
    // O id vinha de `label.toLowerCase()`. Dois "Telefone" na mesma tela — e há
    // seis no projeto — geravam o MESMO id, o que faz o segundo `htmlFor`
    // apontar para o primeiro campo: clicar no rótulo de baixo foca o de cima.
    render(
      <>
        <Input label="Telefone" />
        <Input label="Telefone" />
      </>,
    );

    const [a, b] = screen.getAllByLabelText("Telefone");
    expect(a.id).toBeTruthy();
    expect(a.id).not.toBe(b.id);
  });

  it("campo sem rótulo ainda recebe id", () => {
    // Antes o id ficava `undefined`, e com ele o `htmlFor`.
    const { container } = render(<Input placeholder="Buscar" />);

    expect(container.querySelector("input")!.id).toBeTruthy();
  });

  it("o id passado por quem chama continua ganhando", () => {
    render(<Input label="Título" id="titulo-do-chamado" />);

    expect(screen.getByLabelText("Título").id).toBe("titulo-do-chamado");
  });
});
