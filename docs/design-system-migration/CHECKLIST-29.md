# Checklist da §29 — modelo por tela

Copiar para o relatório da fase, **uma cópia por tela migrada**, preenchida.
Um item não marcado bloqueia o checkpoint.

A lista canônica é a §29 do prompt mestre. Este arquivo a reproduz e acrescenta
os itens que as decisões registradas no `COMPARTILHADO/DECISOES.md` criaram
depois — que não estão no prompt mestre e valem para os dois repositórios.

---

```text
Página: <rota> — <arquivo>

FUNCIONALIDADE (§29 do prompt mestre)
[ ] carrega dados (chamada de API inalterada: método, URL, params)
[ ] filtra
[ ] busca
[ ] pagina
[ ] ordena
[ ] cria
[ ] edita
[ ] exclui (com confirmação)
[ ] abre detalhes
[ ] anexa/remove arquivo
[ ] respeita permissões (papéis testados: …)
[ ] mostra erro (rede, permissão, validação)
[ ] mostra estado vazio
[ ] mostra loading
[ ] funciona no mobile
[ ] funciona no tema escuro
[ ] nenhum campo depende do placeholder para ser entendido
[ ] toda barra desenhada tem papel declarado: `progressbar` quando há escala de
    0 a 100 e um alvo; `meter` quando é medida sem alvo; e nenhum papel de
    progresso quando é comparação ou distribuição

ACRESCENTADOS PELAS DECISÕES REGISTRADAS
[ ] para CADA estado interativo: o que a interface MOSTRA é o que a árvore de
    acessibilidade DIZ?
    (repouso · foco · hover · ativo · selecionado · atual · marcado · parcial ·
     desabilitado · inválido · carregando · aberto/fechado · ordenado)
[ ] nenhuma ação alcançável só pelo mouse: `<div onClick>`, `<tr onClick>`,
    `<th onClick>`, elemento clicável sem `tabIndex` nem `onKeyDown`,
    `focus:outline-none` sem nada no lugar
[ ] nenhuma classe `text-slate-*` sem `dark:` correspondente — a tela não pode
    assumir um tema
[ ] nenhuma cor fora do sistema: paleta crua do Tailwind, hex em `style={{}}`,
    hex em dados (`dot: "#f59e0b"`), cor de biblioteca
[ ] todo `Alert` que a tela renderiza JÁ MONTADO — e não em resposta a uma ação
    — leva `live={false}` (emenda E12)
[ ] o foco dos campos alinhou ao `outline` interno do pacote, e o desvio F1
    saiu desta tela (`VERSION.md`)
[ ] nenhum primitivo reinventado: se `ui/` já faz, a tela usa
[ ] a catraca desceu, ou a tela explica por que não desceu
```

---

## Por que o item dos estados é por ESTADO e não por tela

O defeito nunca está no repouso. Ele aparece quando a interface **muda** e só um
dos dois canais acompanha — o visual muda, o não-visual não. Uma tela passa numa
auditoria estática inteira e falha em todos os estados que ela não estava
exibindo no momento da auditoria.

Os seis casos que compraram o item, em dois dias e em arquivos sem relação:

| Onde | A interface mostrava | A árvore dizia |
|---|---|---|
| `Pagination` | "esta é a página atual" | "esta opção não existe" — e fora da tabulação |
| `Checkbox.jsx` | traço de estado misto | "não marcado" |
| `SearchSelect` | uma lista escolhível | `role="listbox"` sem teclado nenhum |
| `Tabs` | abas | `role="tab"` sem setas e sem painel |
| erro de formulário | o texto do erro ao lado do campo | nada — `<p>` sem ligação |
| ordenar tabela | coluna clicável | `<th>` sem papel, sem tecla, sem `aria-sort` |

**Em nenhum deles há cor errada**, e por isso nenhuma ferramenta desta migração
os encontra: a varredura mede contraste, a catraca conta pares reprovados, e a
galeria mede o que é pintado. As três passariam batido nos seis.

## O que a catraca vê, e o que não vê

Registrado na Fase 8 e confirmado na 9: a varredura casa `bg-*` com `text-*`
**na mesma string de classe**. Cor de texto cujo fundo vem do elemento **pai** é
invisível para ela — foi assim que 45 cores cravadas nos três seletores e 14 no
`Table` e no `Pagination` nunca apareceram no número.

**Consequência para estas fases:** o número da catraca não é medida de progresso
da tela. Uma tela pode sair com zero cores cravadas e o número não se mexer.
Quem mede a tela é o checklist, não a catraca.
