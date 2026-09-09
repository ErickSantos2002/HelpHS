import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * A barra de prazo da lista de chamados, e a semântica que ela não tinha.
 *
 * Lê o arquivo em vez de montar a `TicketListPage`: a barra é uma função local
 * não exportada, e montar a página arrastaria roteador, sessão, filtros e a
 * chamada de listagem para prender cinco atributos — mesma escolha dos testes
 * do link de pular, do botão de sair e do estado do antivírus.
 *
 * ── De onde isto veio ─────────────────────────────────────────────────
 *
 * O `Progress.jsx` do pacote tem `role="progressbar"` e diz, no próprio
 * arquivo, que nasceu do `SlaProgresso` do ChamadosHS. O pacote **melhorou o
 * que copiou**, e a melhoria nunca voltou para nenhum dos dois consumidores.
 * Achado pela sessão do ChamadosHS ao reler a referência de um componente que
 * ela mesma tinha escrito.
 *
 * É o gêmeo da regra da E5: depois de criar um token, varra quem deveria usá-lo;
 * **e depois de emprestar um componente, releia o que fizeram com ele.**
 *
 * ── Por que só esta barra, e não as cinco ─────────────────────────────
 *
 * O HelpHS tem cinco barras desenhadas à mão, e **duas delas não são
 * progresso**: a de contagem por categoria vai de zero ao maior valor da lista,
 * não a 100, e a empilhada por status é distribuição. Pôr `role="progressbar"`
 * nelas anunciaria um número numa escala que não existe — pior que não pôr
 * papel nenhum.
 *
 * As outras três entram nas Fases 11–16, uma por tela, registradas na §29:
 * conformidade e razão como `meter`; comparação e distribuição sem papel de
 * progresso.
 */
const TELA = readFileSync(
  resolve(process.cwd(), "src/pages/tickets/TicketListPage.tsx"),
  "utf-8",
);

describe("barra de prazo de SLA", () => {
  it("as duas barras são progressbar — a do prazo e a da resposta dada", () => {
    // Duas, e não uma: o estado "primeira resposta já dada" desenha a própria
    // barra cheia, e ficaria muda se só a outra fosse tratada.
    expect(TELA.match(/role="progressbar"/g)).toHaveLength(2);
  });

  it("declara a escala completa, e não só o valor", () => {
    // `aria-valuenow` sozinho não diz nada: sem `min` e `max` o leitor de tela
    // não sabe de que escala o número saiu.
    expect(TELA).toMatch(/aria-valuemin=\{0\}/);
    expect(TELA).toMatch(/aria-valuemax=\{100\}/);
    expect(TELA).toMatch(/aria-valuenow=\{Math\.round\(pct\)\}/);
    expect(TELA).toMatch(/aria-valuenow=\{100\}/);
  });

  it("tem nome acessível, e ele diz de que prazo se trata", () => {
    // "Prazo de 1ª Resposta" ou "Prazo de Resolução" — sem isso a barra é
    // anunciada como "barra de progresso" e nada mais, e há uma por chamado.
    expect(TELA).toMatch(/aria-label=\{`Prazo de \$\{phase\}`\}/);
  });

  it("o anúncio é o tempo que sobra, não a porcentagem", () => {
    // `aria-valuetext` troca "65%" — que não diz nada a quem ouve — por "2h
    // 15m restantes". A porcentagem é a forma; o tempo é a informação.
    expect(TELA).toMatch(/aria-valuetext=\{breached \? "prazo vencido"/);
    expect(TELA).toMatch(/aria-valuetext=\{breach \? "respondida com atraso"/);
  });

  it("as barras de comparação NÃO viraram progressbar", () => {
    // ── A decisão inteira, para ninguém ter de redescobri-la ────────────
    //
    // Uma passada do `AdminDashboard` declarou `role="progressbar"` nas TRÊS
    // barras desenhadas da tela citando a §29, e quebrou este arquivo. Foi
    // revertida, a distinção subiu ao operador, e ele decidiu assim:
    //
    //   comparação (contagem por categoria) → SEM papel, `aria-hidden`,
    //     valor em texto. O máximo é o MAIOR VALOR DA LISTA, não um teto:
    //     a barra mede tamanho relativo, e nenhuma escala existe para
    //     anunciar. `aria-hidden` é honesto porque a contagem está escrita.
    //   conformidade de SLA (por prioridade, e a da linha do técnico) →
    //     `role="meter"` com `aria-valuenow`/`min`/`max` e NOME. É medição
    //     dentro de faixa conhecida e fixa, 0 a 100.
    //
    // `meter` é o papel de MEDIÇÃO; `progressbar` é o de TAREFA AVANÇANDO —
    // o leitor de tela anuncia "60 por cento concluído" para ele, e a
    // conformidade de SLA não está concluindo nada. Por isso `progressbar`
    // segue proibido no `AdminDashboard` INTEIRO, para as duas coisas, e é o
    // que a primeira asserção guarda. As outras prendem o que entrou no
    // lugar, para que apagá-lo também reprove.
    //
    // (A `SlaConfigPage` tem uma razão, e entra na mesma fase pelo mesmo
    // caminho: medição, não progresso.)
    const painel = readFileSync(
      resolve(process.cwd(), "src/pages/dashboard/AdminDashboard.tsx"),
      "utf-8",
    );
    expect(painel).not.toMatch(/role="progressbar"/);

    // Duas barras de conformidade, e só elas: a da seção por prioridade e a
    // da linha de cada técnico. Uma terceira aqui seria a de comparação
    // voltando a declarar papel.
    expect(painel.match(/role="meter"/g)).toHaveLength(2);
    expect(painel).toMatch(
      /role="meter"[\s\S]{0,320}?aria-valuenow=\{Math\.round\(item\.compliance_rate\)\}/,
    );
    expect(painel).toMatch(
      /role="meter"[\s\S]{0,320}?aria-valuenow=\{Math\.round\(t\.sla_compliance_rate\)\}/,
    );
    // A escala completa, e não só o valor — mesma exigência das barras de
    // prazo acima: sem `min` e `max` o número não vem de escala nenhuma.
    expect(painel.match(/aria-valuemin=\{0\}/g)).toHaveLength(2);
    expect(painel.match(/aria-valuemax=\{100\}/g)).toHaveLength(2);
    // E o nome: são duas medições diferentes, e uma delas se repete por linha.
    expect(painel).toMatch(
      /aria-label=\{`Conformidade de SLA — \$\{rotuloDePrioridade\(item\.priority\)\}`\}/,
    );
    expect(painel).toMatch(
      /aria-label=\{`Conformidade de SLA de \$\{t\.technician_name\}`\}/,
    );

    // A de comparação: nenhum papel e fora da árvore. O único `aria-hidden`
    // declarado no arquivo é o dela — os ícones herdam o seu do `Icon` do
    // pacote. Conta a forma com atributo, e não a menção: o comentário logo
    // acima da barra cita `aria-hidden` em prosa, e contá-lo faria o caso
    // reprovar por edição de comentário.
    expect(painel.match(/aria-hidden="true"/g)).toHaveLength(1);
    expect(painel).toMatch(
      /aria-hidden="true"[\s\S]{0,320}?cat\.count \/ categoryMax/,
    );
  });

  it("os dois grupos SEM medição são `role=\"img\"`, e só eles", () => {
    // ── A segunda metade da mesma decisão ──────────────────────────────
    //
    // Esconder a barra de comparação foi certo e deixou um buraco: quem ouve
    // lia "Hardware 6" e nada sobre a PROPORÇÃO entre as categorias, que
    // passou a ser informação só visual. O mesmo valia para a faixa empilhada
    // da `StatusBar`, que nunca teve papel nenhum.
    //
    // O operador decidiu `role="img"` nos DOIS GRUPOS — a linha inteira da
    // categoria, e o cartão inteiro da distribuição —, com o texto no
    // `aria-label`. A barra de comparação continua `aria-hidden`: quem carrega
    // o significado passou a ser o grupo em volta dela.
    //
    // `img` e não `meter`: nenhuma das duas mede dentro de faixa fixa. Uma
    // compara com o maior da lista, a outra reparte um total. `img` é o papel
    // de "isto é um desenho, e este é o texto dele" — e é por isso que o texto
    // tem de estar inteiro no rótulo.
    const painel = readFileSync(
      resolve(process.cwd(), "src/pages/dashboard/AdminDashboard.tsx"),
      "utf-8",
    );

    // Dois, e só dois: comparação e distribuição. Um terceiro seria papel numa
    // barra que já tem outro, ou num desenho que ninguém decidiu.
    //
    // Conta a forma com ATRIBUTO — a linha em que só ele está —, e não a
    // menção: os comentários que explicam a decisão citam `role="img"` em
    // prosa quatro vezes, e contá-las faria o caso reprovar por edição de
    // comentário. É a mesma armadilha que o `aria-hidden` acima já tinha.
    expect(painel.match(/^[ \t]*role="img"\r?$/gm)).toHaveLength(2);

    // ⚠️ `role="img"` substitui a subárvore pelo rótulo. O nome e a contagem
    // deixam de ser lidos por conta própria, e o que o rótulo não disser some
    // para quem não vê. Por isso os TRÊS pedaços têm de estar lá.
    expect(painel).toMatch(
      /role="img"[\s\S]{0,200}?aria-label=\{`\$\{cat\.category\}: \$\{cat\.count\} chamados, /,
    );
    expect(painel).toMatch(/% do total`\}/);

    // O denominador da PROPORÇÃO é o total das categorias exibidas; o da
    // LARGURA da barra é o maior da lista. São dois números diferentes, e
    // trocar um pelo outro faz o rótulo dizer que o campeão é 100% do total.
    expect(painel).toMatch(
      /const categoryTotal = categoryData\.reduce\(\(s, c\) => s \+ c\.count, 0\)/,
    );
    expect(painel).toMatch(/cat\.count \/ categoryTotal/);
    expect(painel).toMatch(/cat\.count \/ categoryMax/);

    // A `StatusBar`: o rótulo é montado do MESMO par que a legenda escreve
    // embaixo — `label: value` —, para as duas versões da mesma contagem não
    // divergirem uma da outra.
    expect(painel).toMatch(
      /const distribuicao = segs\.map\(\(s\) => `\$\{s\.label\}: \$\{s\.value\}`\)/,
    );
    expect(painel).toMatch(
      /role="img"[\s\S]{0,200}?`Distribuição de status — \$\{distribuicao\}`/,
    );
  });
});
