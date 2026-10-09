# Checkpoint 2 — Componentes — HelpHS

Relatório da seção 32, cobrindo as **Fases 7 a 10**. A migração para aqui e
aguarda aprovação explícita antes da Fase 11.

## 1. O que foi entregue

| Fase | Escopo | Estado |
|---|---|---|
| 7 | core: `Button` `Card` `Badge` `Avatar` `Spinner` `Icon` | fechada |
| 8 | formulários: `Input` `Textarea` `Select` `Selector` `Checkbox` `Switch` `FileUpload` | fechada |
| 9 | dados: `Table` `Pagination` `SlaChip` | fechada |
| 10 | feedback e navegação: `Alert` `Modal` `Toast` `Tabs` | fechada |

**Todo componente de `ui/` foi lido e migrado.** Duas linhas da §7.1 não têm
correspondente aqui e **nada foi criado para preenchê-las**: `Tooltip` (não
existe no HelpHS) e `Radio` (decisão do operador: "Radio: nada").

## 2. Emendas ao pacote

Onze, mais a E7-b. Quatro nasceram neste checkpoint.

| Emenda | O que faltava na origem |
|---|---|
| E7 | `--border-control` — nenhuma borda alcançava 3:1 como contorno de controle |
| E7-b | o visto do `Checkbox` em `--color-white` sobre `--action`: 2,69:1 no escuro |
| E9 | `Checkbox` e `Switch` não mostravam **foco nenhum** |
| E10 | a seta do `Select` era data URI cravado — não aceita `var()`, nunca seguiu o tema |
| **E11** | o erro do formulário não chegava a quem não o vê |

A **E8** é do ChamadosHS e foi adotada aqui. A **E4** gastou o número de
propósito: autorizada, superada pela E5 antes de aplicar, registrada como **não
aplicada**.

**A E11 é a primeira emenda que existe como commit** — o pacote virou
repositório git em 03/09 (`5b67c7b`), depois do incidente descrito na §6.

## 3. A galeria, e o que ela mede

`3983e33` · `frontend/galeria.html` · `npx playwright test e2e/galeria.spec.ts`

| | |
|---|---|
| Elementos medidos | **85**, nos dois temas |
| Reprovações | **0** |
| Piso | 4,5:1 texto · 3:1 gráfico (WCAG 1.4.11) |
| Método | estilo **computado** no Chromium, fundo efetivo composto camada a camada |

Existe por causa de um erro concreto: na Fase 7 a medição de **tokens** do
`Badge` deu **zero** reprovações e o componente renderizado tinha **sete em
quarenta e duas**. As três formas de medir não se substituem:

| Ferramenta | O que ela vê |
|---|---|
| varredura estática do JSX | os pares escritos à mão nas telas |
| medição de token | a paleta, e **só** ela |
| galeria, estilo computado | o que o componente **de fato** pinta |

## 4. Contraste: o estado da catraca

**49 pares abaixo de 4,5:1, linha de base 49, em dia.**

Nasceu em 51 e desceu duas vezes, as duas **exigidas pela própria catraca** no
sentido "melhorou" — que é o que a separa de um carimbo:

| | |
|---|---|
| 51 → 50 | o `Select` largou o `bg-background-surface text-slate-500` do placeholder |
| 50 → 49 | o `Pagination` trocou `bg-primary text-white` (3,83:1) por `bg-action text-on-primary` |

Os 49 restantes são das **telas**, não dos componentes: trinta deles são
`text-slate-*` sobre superfície, vivos por causa do desvio D5, e saem tela a tela
nas Fases 11–16.

**A ferramenta ganhou uma armadilha nova neste checkpoint.** A décima segunda,
achada pela sessão do ChamadosHS: fechar a armadilha 4 abriu o buraco inverso —
uma classe do estático nunca encontrava uma classe de ramo do ternário, embora o
estático valha em todos os ramos. O modelo passou a ser por ramo. O número não
mudou (o HelpHS não tinha o padrão), mas 76 templates com interpolação passaram a
ser lidos corretamente.

## 5. O que este checkpoint aprendeu, e que a migração não previa

Quatro achados, e **nenhum deles é de cor**. As ferramentas desta migração medem
contraste; nenhuma destas quatro famílias aparece nelas.

### O sinal certo pelo mecanismo errado

Nome dado pela sessão do ChamadosHS. Seis ocorrências em dois dias, em arquivos
sem relação:

| Onde | A interface mostrava | A árvore dizia |
|---|---|---|
| `Pagination` | "esta é a página atual" | "esta opção não existe" — e fora da tabulação |
| `Checkbox.jsx` | traço de estado misto | "não marcado" |
| `SearchSelect` | uma lista escolhível | `role="listbox"` sem teclado nenhum |
| `Tabs` | abas | `role="tab"` sem setas e sem painel |
| erro de formulário | o texto do erro ao lado do campo | nada — `<p>` sem ligação |
| ordenar tabela | coluna clicável | `<th>` sem papel, sem tecla, sem `aria-sort` |

Virou **item fixo da §29**, por estado interativo: *o que a interface mostra é o
que a árvore de acessibilidade diz?* Registrado no `DECISOES.md` (`7ea97d8`).

### Ação que só o mouse alcança

`disabled` como sinal de página atual, `<th onClick>` para ordenar, `<tr onClick>`
para abrir registro, gatilho de aba fora da ordem de tabulação. Contraste não
mede ordem de tabulação.

### O componente escrito só para um tema

**Cinco** componentes de `ui/` — `FormDropdown`, `SearchSelect`, `Table`,
`Pagination`, `Tabs` — com `text-slate-300` e irmãos, sem um único `dark:`. A
explicação é histórica: o HelpHS nasceu escuro e o tema claro veio pela Fase 3,
que alcançou a casca e não o miolo. **O inventário está fechado**: todos foram
lidos, e não há um sexto.

### A cor fora do sistema que não é `slate`

O `SlaChip` não tinha nenhuma cor `slate` e mesmo assim estava fora do sistema:
usava `bg-red-500/15`, `bg-emerald-500/15`, `bg-amber-500/15` — a paleta **crua**
do Tailwind, com contraste nunca medido. Uma varredura que procura `slate` não o
acharia. O `richColors` do sonner era o mesmo vício com a paleta da biblioteca.

## 6. O incidente, e o que ele mudou

Em 03/09 o `EMENDAS.md` do pacote foi **truncado a zero byte** por um script na
forma `io.open(p, "w", ...).write(texto % (...))`: o Python abre em modo `"w"` —
truncando — antes de avaliar o argumento; o `%` colidiu com o `%2394a3b8` do data
URI da E10 e levantou `TypeError`. O `.write()` nunca rodou.

Reconstruído no mesmo dia. **Onze das doze seções são literais** — o texto
original sobrevive no registro das sessões como entrada dos scripts que o
gravaram. As tabelas de hashes da E7 e da E9 foram remontadas: os valores de
*antes* foram recalculados desfazendo as substituições de cada emenda, e **nove
de nove conferem** com o prefixo de 16 hex atestado e com a contagem de bytes.
**Um valor não fechou** e está marcado *não conferido* com o elo nomeado.

Três coisas saíram disto:

1. **O pacote virou git** (`5b67c7b`), com `.gitattributes` desligando conversão
   de fim de linha — sem isso o `core.autocrlf` devolveria CRLF no checkout e
   quebraria toda conferência de hash sem nada parecer errado. Testado: apagar e
   restaurar devolve os bytes idênticos.
2. **Regra de escrita atômica** no `DECISOES.md` (`753b614`): conteúdo destinado
   a arquivo nunca passa por formatador; a string é montada inteira antes de
   abrir, gravada em temporário e renomeada.
3. **Uma emenda = um commit**, daqui em diante.

## 7. Prova, somada

| | |
|---|---|
| Suíte | **678 testes**, 57 arquivos, todos passando |
| Galeria | 85 elementos × 2 temas, zero reprovações |
| Mutação | **todo teste novo deste checkpoint foi validado por mutação** |
| Testes cegos encontrados | **4**, todos pela mutação e nenhum por leitura |
| Tipos | `tsc -b` limpo |
| Catraca | 49 / 49, e as 16 provas da ferramenta passam |

Os quatro testes cegos merecem a linha própria, porque são o argumento para a
mutação ser rotina e não suspeita:

- o `aria-hidden` do `SlaChip` — o `Icon` já o marcava, o meu era redundante;
- o `type="button"` do `Modal` — o portal já impedia o envio;
- o caso 15 da varredura — o par caía na primeira combinação, que um caminho
  único também produz;
- o caso 16 — defendia uma alternativa vazia que é **inerte** para detecção.

Nos quatro, o teste estava correto, o código estava correto, e o teste não
provava o que dizia provar. Nenhuma leitura acharia.

## 8. O que fica em aberto

| | |
|---|---|
| Candidata a emenda | `Alert.jsx` do pacote usa `role="alert"` nas quatro variantes |
| Candidata a emenda | `SearchSelect.jsx` do pacote: `<label>` sem `htmlFor` |
| Desvio com prazo | **F1** — foco por `ring` em vez de `outline`; expira no Checkpoint 4 |
| Fases 11–16 | os 49 pares da catraca, os 20 `dot:` em hex cru, a linha de tabela plenamente acessível, as 4 barras de SLA restantes |
| Nunca exercitado | o modo linear da armadilha 12 — só o caso de prova o segura |

## 9. Pergunta ao operador

O checkpoint pede aprovação explícita para seguir. As duas candidatas a emenda
da §8 pertencem à origem e não podem ser escritas sem autorização — e a do
`Alert.jsx` afeta os dois repositórios, porque o ChamadosHS consome o mesmo
arquivo de referência.
