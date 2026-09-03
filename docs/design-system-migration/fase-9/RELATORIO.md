# Fase 9 — Componentes de dados — HelpHS

Relatório no formato da seção 32. **Fase fechada.**

Os três componentes de dados do HelpHS: `Table`, `Pagination` e `SlaChip`.
`Progress` e `Rating` são do ChamadosHS e não existem aqui.

## 1. Componentes

| Componente | Commit | O que mudou |
|---|---|---|
| `Pagination` | `491d893` | tokens; a página atual deixa de ser `disabled` |
| `Table` | `ef79aaf` | tokens; ordenar e linha clicável passam a existir para o teclado |
| `SlaChip` | `97d34aa` | as três tintas saem da paleta crua do Tailwind |

## 2. O padrão que a fase inteira revelou

**Os três componentes tinham ações ou estados que só o mouse alcançava**, e
nenhum deles era um defeito de contraste — que é o que esta migração tem
ferramenta para achar.

| Onde | O que era | O que é |
|---|---|---|
| `Pagination` | página atual marcada com `disabled`, **fora da ordem de tabulação** | `aria-current="page"`, clique inerte por guarda |
| `Table` | ordenar num `<th onClick>` | `<button>` de verdade, e `aria-sort` no `<th>` |
| `Table` | linha clicável num `<tr onClick>` | `tabIndex` e resposta a `Enter`/espaço |

O `disabled` do `Pagination` é o mais instrutivo: **o sinal estava certo e o
mecanismo errado**. Desabilitar comunica "esta é a página atual" a quem enxerga
e comunica "esta opção não existe" a quem navega por teclado — e ainda a remove
do alcance. É o mesmo formato da E9, e o mesmo das barras de SLA: o problema não
é a cor, é o significado.

**Nenhuma ferramenta desta migração pega isso.** A varredura mede contraste;
contraste não mede ordem de tabulação. Os três foram achados lendo o componente
inteiro antes de trocar as cores — que é o argumento para não tratar a adoção de
tokens como uma substituição mecânica de classes.

## 3. O que a catraca viu, e o que não viu

**Um par**, no `Pagination`: `bg-primary text-white` na página atual, **3,83:1
nos dois temas**, e página é texto. É a família da E1 outra vez — branco cravado
sobre um fundo que muda de tema. Trocado pelo par `bg-action text-on-primary`.

A catraca **desceu pela segunda vez: 50 → 49**, de novo exigida por ela mesma.

**As outras 14 cores cravadas ela não viu.** As 6 do `Table` e as 8 do
`Pagination` não tinham fundo co-locado na mesma string — o mesmo limite que a
Fase 8 registrou nos seletores. E as três tintas do `SlaChip` não eram `slate`:
eram `bg-red-500/15`, `bg-emerald-500/15`, `bg-amber-500/15`, da **paleta crua do
Tailwind**, com contraste nunca medido. Hoje usam os pares `tint`/`on-tint` que a
E2 e a E8 mediram.

## 4. O vício do tema escuro, terceira e quarta aparições

`Table` e `Pagination` eram **escritos só para o tema escuro** —
`text-slate-400`, `text-slate-200`, `text-slate-300`, sem um único `dark:`. Já
tinha acontecido no `FormDropdown` e no `SearchSelect` da Fase 8.

São quatro componentes de `ui/` com o mesmo vício, e a explicação é histórica: o
HelpHS nasceu escuro e o tema claro veio depois, pela Fase 3. O que a Fase 3 não
alcançou foi o que estava dentro dos componentes, porque o espelho do D5 só
reescreve `text-slate-*` — e reescrever não é o mesmo que aprovar. **Vale
suspeitar de qualquer arquivo de `ui/` que ainda não tenha sido lido nesta
migração.**

## 5. O que a mutação encontrou

No `SlaChip` escrevi `aria-hidden="true"` no ícone e um teste para prendê-lo. O
teste passou — e a mutação mostrou que passaria de qualquer jeito: o `Icon` já
marca `aria-hidden` internamente, e o meu atributo era redundante.

O atributo saiu, o teste ficou, e a validação passou a mutar o `Icon`. **É a
diferença entre um teste que passa e um teste que prova**, e foi a única vez em
três componentes que a mutação encontrou um teste cego.

## 6. Prova

| | |
|---|---|
| Testes novos | 19 (`Pagination` 5, `Table` 7, `SlaChip` 7) |
| Mutações | 14 aplicadas, **14 acusadas** — uma delas só depois de corrigir o alvo |
| Suíte | **611 passando**, 54 arquivos |
| Tipos | `tsc --noEmit` limpo |
| Catraca | **49**, linha de base 49, em dia |
| Contrato | os 18 testes que já existiam nos três passam |

## 7. Pendências que a fase abre

1. **Linha de tabela plenamente acessível.** O desenho correto põe o elemento
   acionável **dentro** da linha — o link do registro na primeira célula. Isso
   muda a marcação das telas e entra nas Fases 11–16, tela a tela. O que está
   aqui torna a linha alcançável sem quebrar a semântica de tabela, que é o que
   faz um leitor de tela anunciar "linha 3 de 40".
2. **O anel das tintas do `SlaChip` não foi medido.** É `ring-danger/30`, e o
   ajudante de contraste não expressa alfa arbitrário — o quarto parâmetro dele
   é o token de base, não a opacidade. Não medi outra coisa para publicar como
   se fosse esta: o anel é reforço, e quem carrega o estado é o texto
   (`Vencido`, `Respondido`, `2h 15m`).
3. **Duas tabelas escritas à mão** continuam fora do componente, no
   `AdminDashboard.tsx` e no `ReportsPage.tsx`. Entram com as telas.
