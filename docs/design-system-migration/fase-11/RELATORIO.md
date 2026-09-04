# Fase 11 — Templates — HelpHS

Relatório no formato da seção 32. **Em andamento.**

A §25 pede uma tela real de cada tipo — listagem, formulário e painel — montada
com os primitivos. Os candidatos, escolhidos pela síntese do mapeamento:

| tipo | tela | estado |
|---|---|---|
| painel | `ClientDashboard` | **fechada** |
| formulário | `TicketFormPage` | a seguir |
| listagem | `TicketListPage` | a seguir |

---

## Etapa 0 — o que veio antes de abrir tela

A síntese das seis telas foi taxativa: **quatro delas travavam no mesmo trabalho
de pacote**. Foi feito primeiro.

| | |
|---|---|
| `Selector` não estava no barril | quatro telas parariam na mesma linha faltante |
| `TableHeaderCell` sem `scope="col"` | é a associação cabeçalho-célula que faz a tabela ser tabela |
| `label` não chegava ao gatilho no `variant="filter"` | numa barra com quatro filtros, os quatro se anunciavam pelo valor escolhido |
| `KpiCard` em três cópias divergentes | prop de classe crua era a causa-raiz da cor fora do sistema nos painéis |
| prioridade em cinco mapas divergentes | virou `lib/prioridade.ts`, fonte única |
| `Button` não sabia ser link | a regra "navegação é link" vale em 16 lugares |

## Etapa 1 — a varredura mecânica

`1d1fca5`. **584 trocas em 44 arquivos, zero pixel** — os aliases do D2 apontavam
para os mesmos tokens. Uma ocorrência escapou e foi corrigida depois:
`ring-offset-background`, porque o utilitário é `ring-offset-` e o padrão só
previa `ring-`.

## Etapa 2 — `ClientDashboard`

### Ficha da §29

```text
Página: /dashboard — src/pages/dashboard/ClientDashboard.tsx

FUNCIONALIDADE
[x] carrega dados — duas chamadas a `getTickets`, mesmos params, mesmos limites
[–] filtra          — a tela não filtra
[–] busca           — a tela não busca
[x] pagina          — `Pagination`, mesma prop, mesmo PAGE_SIZE de 10
[–] ordena          — a tela não ordena
[–] cria            — o "Abrir chamado" leva ao formulário; não cria aqui
[–] edita  [–] exclui
[x] abre detalhes   — agora por link; ver "a área de clique" abaixo
[–] anexa/remove arquivo
[x] respeita permissões — a tela é do papel `client`; `creator_id` = usuário
[x] mostra erro     — `Alert variant="danger"`, `live` ligado (E12)
[x] mostra estado vazio — texto + botão-link "Abrir primeiro chamado"
[x] mostra loading  — `Spinner` na carga inicial e na troca de página
[x] funciona no mobile — coluna de protocolo `hidden sm:table-cell`, e o
                         protocolo reaparece dentro da célula do título
[x] funciona no tema escuro — zero classe sem `dark:` correspondente: não há
                         mais classe de cor crua nenhuma
[x] nenhum campo depende do placeholder — a tela não tem campo
[–] barras desenhadas — a tela não tem barra

ACRESCENTADOS PELAS DECISÕES
[x] o que a interface MOSTRA é o que a árvore DIZ, por estado
    repouso    tabela com cabeçalho de coluna, era pilha de botões
    foco       link por linha, nome = título do chamado
    hover      sublinhado no título, além da cor
    vazio      texto, não só ausência
    carregando `Spinner` (ver pendência)
[x] nenhuma ação só de mouse — a linha virou link; teclado alcança um por linha
[x] nenhum `text-slate-*` sem `dark:` — zero cor cravada
[x] nenhuma cor fora do sistema — zero
[x] `Alert` montado por ação leva `live` ligado — correto, é erro de carga
[ ] desvio F1 — a tela não tem campo; nada a alinhar
[x] nenhum primitivo reinventado — a tabela falsa virou `Table`
[x] a catraca desceu — 49 → 48
```

### Contagem do que resta à mão

```text
src/pages/dashboard/ClientDashboard.tsx: 2
```

**As duas ocorrências estão em comentário**, descrevendo o que a tela era antes.
Controles à mão de verdade: **zero**.

É o caso que a regra prevê — *conta, não julga*: número maior que zero significa
que alguém tem de olhar, não que há trabalho pendente. A sessão do ChamadosHS
encontrou o mesmo na primeira aplicação, com oito de 31.

### O defeito principal, e o que ele custava

A lista **parecia** uma tabela e não era nenhuma. O cabeçalho eram quatro
`<span>` numa grade CSS; cada linha era um `<button>`.

Quem enxerga lê "Protocolo | Título | Prioridade | Status" no topo e alinha a
coluna com o olho. Quem usa leitor de tela ouvia **dez botões** cujo nome era a
costura de tudo — *"HS-2024-0031 Impressora não imprime Alta Aberto"* — sem
"linha 3 de 10", sem nome de coluna, sem saber quantas colunas existem.

### A área de clique não se perdeu, e isso foi medido

Navegação é link, e um `<tr>` não pode ser um link. O acionável foi para dentro
da linha — o título — com um pseudo-elemento esticando-o sobre a linha inteira.

**Medido no navegador antes de escolher o desenho:** o pseudo-elemento cobre o
`<tr>` exatamente — 400×61 contra 400×61 — porque a linha é `relative`. Onde
isso falhar, o link continua funcionando e cobre apenas a própria célula:
degradação limpa, não quebra.

O nome do link é o **título do chamado**, não "Ver detalhes". Dez links chamados
"Ver detalhes" produzem uma lista em que nenhum diz para onde vai.

### O que a Etapa 2 ensina para as outras cinco

1. **Tabela falsa vira `Table`**, e o acionável vai dentro da linha.
2. **Botão que navega vira `Button to=`**, que é o primitivo e não uma classe
   copiada — 16 lugares, e as 16 divergiriam.
3. **`KpiCard` com `tone`**, nunca com classe.

### Pendência que a tela abre, e não é do sistema de design

Só o "Total" dos indicadores vem do servidor; "Em andamento" e "Resolvidos" são
contados **no cliente** sobre os 500 itens trazidos. Passando de 500 chamados a
tela mostra três números que não fecham, sem nenhum sinal de truncamento.

Está registrado no próprio arquivo. Entra na Fase 16, com o serviço — não viaja
num commit de token.
