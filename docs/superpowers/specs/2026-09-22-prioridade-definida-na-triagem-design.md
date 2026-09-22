# Prioridade definida na triagem — o cliente não classifica a própria urgência

**Data:** 22/09/2026
**Origem:** pedido do Rickelme, com desenho aprovado no mesmo dia (decisões D1 a D4)
**Status:** aprovado e implementado; **com migration**, sem backfill
**Branch:** `feat/prioridade-definida-na-triagem`, worktree `HelpHS-prioridade`

Este documento existe para responder **"por que o número mudou?"**. Dois
indicadores se mexem no dia do deploy, e os dois se mexem para pior antes de
melhorar. A seção 4 é a razão.

> Referências `arquivo.py:linha` apontam para `236d000` — o código **antes**
> desta mudança.

---

## O problema

Quem abria o chamado escolhia a prioridade dele. O seletor era o primeiro
grupo de fichas da tela de abertura, e vinha com **"Média" já marcada**
(`TicketFormPage.tsx:360`, `defaultValues`).

Isso produzia duas coisas erradas ao mesmo tempo:

1. **O cliente classificava a própria urgência.** Todo problema é urgente para
   quem está com ele na mão; a régua de urgência é de quem atende, que enxerga
   a fila inteira.
2. **"Média" queria dizer duas coisas.** Era o nível escolhido de propósito e
   era também o chamado que ninguém olhou — e nada no sistema distinguia os
   dois. Um chamado com "Média" no painel podia ser uma decisão da equipe ou o
   default de um formulário que o cliente não mexeu.

O SLA era carimbado na criação com base nessa escolha
(`tickets.py:368-374`, `tickets.py:408`): o prazo de um chamado nascia da
prioridade que o próprio cliente marcou.

## 1. Levantamento: por onde a prioridade passava

### Backend

| Caminho | Antes | Veredito |
|---|---|---|
| `models.py:499` | `nullable=False, default=medium` | nulável, sem default |
| `schemas/ticket.py:22` | `TicketCreate.priority = medium` | campo sai |
| `schemas/ticket.py:34` | `TicketUpdate.priority` existia | campo sai (D3) |
| `tickets.py:368-374, 408` | busca `SLAConfig` por `body.priority` e carimba | move para a triagem |
| `tickets.py:970-985` | reabertura relê `ticket.priority.value` | **quebraria com nulo** |
| `tickets.py:527-534` | ordenação por prioridade, com `else_=4` | já aguentava nulo |
| `chat.py:454` | `str(ticket.priority)` para a LLM | mandaria a string `"None"` |
| `dashboard.py` (6 pontos) | `r.priority.value` | **`AttributeError` → 500** |

O ponto mais duro não estava no pedido: **o painel quebraria no primeiro
chamado sem prioridade**. `dashboard.py:136` montava
`{r.priority.value: r.cnt for r in priority_rows}`, e a linha do `GROUP BY`
com `NULL` derruba `/dashboard/stats` inteiro. Seis sítios iguais, dois deles
na tela inicial do administrador.

### Frontend

31 acessos a `.priority`, todos assumindo string válida. O `lib/prioridade.ts`
já recuava para o neutro em valor **desconhecido**, mas com `null` o selo
renderizava **vazio** — não "Sem prioridade".

Duas coisas já estavam certas e não precisaram de nada: `SlaChip.tsx:56` e
`TicketListPage.tsx:102` devolvem `null` quando não há prazo, então chamado
sem triagem simplesmente não mostra relógio.

## 2. A regra nova

O chamado nasce com `priority = NULL`. Técnico e administrador — **a mesma
permissão, sem diferença** — definem a prioridade pelo
`PATCH /tickets/{id}/priority`, que é o único caminho que grava o campo.

### D1 — O prazo conta da abertura, não do clique

`apply_sla_config(ticket, sla_config, ticket.created_at)`. O RN-013 diz que o
SLA conta da abertura até a resolução, e a triagem não é um recomeço.

### D2 — "Sem prioridade" é um balde, não uma ausência

No painel, os chamados não triados contam num balde próprio
(`by_priority_none`), e **crítica + alta + média + baixa + sem prioridade =
total**. Ficam **fora** do denominador da conformidade de SLA: não se cobra
cumprimento de um prazo que ainda não existe.

### D3 — Um caminho só para prioridade

`priority` saiu do `TicketUpdate`. O `PATCH` genérico gravaria o campo **sem
recalcular o SLA**, e o chamado ficaria crítico com o prazo de quando era
baixo.

### D4 — Resposta dada antes da triagem não vira violação

`check_breaches` (`sla.py:268`) e `violacao_ao_resolver` (`sla.py:220`) já
guardavam a violação de resposta atrás de `sla_first_response is None`. A
regra foi mantida e **fixada em teste**: um prazo retroativo não acusa quem
respondeu antes de ele existir. A espera continua medida onde sempre foi —
`sla_first_response - created_at`, no relatório.

### Decisão que não estava nas quatro: chamado encerrado

O endpoint **não mexe no SLA** de chamado resolvido, fechado ou cancelado —
grava a prioridade e o histórico, e deixa o relógio como está. Uma
justificativa de violação já escrita se apoia naqueles prazos, e recalculá-los
reescreveria o número sobre o qual alguém deu uma explicação. É a mesma regra
que `marca_violacao_ao_resolver` já segue: só acrescenta, nunca desmarca.

### Alternativas descartadas

- **Contar o prazo da triagem.** Esconderia exatamente o atraso que a mudança
  cria: triagem lenta ficaria invisível, e o indicador diria que está tudo em
  dia.
- **Manter `medium` como default do banco.** Traria o problema de volta pela
  porta dos fundos — o campo continuaria sem distinguir escolha de omissão.
- **Deixar `priority` no `TicketUpdate` "só para o admin".** Dois caminhos
  para o mesmo campo, um deles sem SLA. É o defeito esperando data.

## 3. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `models.py` | `priority` nulável, sem default |
| `alembic/versions/h4c5d6e7f8a9` | `ALTER COLUMN priority DROP NOT NULL` |
| `schemas/ticket.py` | `priority` sai de `TicketCreate` e `TicketUpdate`; `TicketResponse.priority` aceita nulo; nasce `TicketPriorityUpdate` |
| `routers/tickets.py` | criação sem prioridade e sem SLA; `PATCH /tickets/{id}/priority`; reabertura tolera nulo |
| `routers/dashboard.py` | balde `by_priority_none`; seis pontos de `.value` protegidos |
| `schemas/dashboard.py` | `by_priority_none`; `priority` nulável em dois itens |
| `routers/chat.py` | manda `"sem prioridade definida"` para a LLM, não `"None"` |
| `Badge.tsx` | nasce `SemPrioridade` |
| `TicketFormPage.tsx` | o seletor, o resumo, a revisão e o corpo do POST perdem a prioridade |
| `ticketService.ts` | `updateTicketPriority`; tipos nuláveis |
| `TicketDetailPage.tsx` | "Sem prioridade" em três lugares; modal de triagem para a equipe |
| `TicketListPage.tsx`, dashboards, `ReportsPage.tsx` | "Sem prioridade" onde o selo assumia valor |

## 4. Impacto nos dados existentes

**Sem backfill.** A migration não escreve em linha nenhuma. Chamado antigo
mantém a prioridade que tem, inclusive os que receberam `medium` por omissão —
a regra nova é prospectiva. Separar "média de verdade" de "média por
omissão" no histórico exigiria um script avulso e uma decisão que não é esta.

### Os dois números que se mexem, e a intenção

**A distribuição por prioridade deixa de ser quatro fatias.** A partir do
deploy, todo chamado novo nasce no balde "Sem prioridade" e só sai de lá na
triagem. O tamanho desse balde passa a ser a medida de quanto trabalho está
esperando classificação — informação que não existia.

**A conformidade de SLA piora quando a triagem demora.** Crítica resolve em
120 minutos úteis (`seeds.py:66`). Um chamado triado como crítico no dia
seguinte nasce com `sla_resolve_due_at` cerca de 7 horas úteis no passado, e
o `check_breaches` do próprio endpoint liga `sla_resolve_breach` na hora.

**Isso é a intenção, não efeito colateral.** O chamado passou o dia sem
ninguém olhar; o indicador passa a dizer isso. Antes, ele nascia "Média" e com
prazo de 720 minutos, e a demora da triagem não aparecia em lugar nenhum.

### Borda conhecida e aceita

Chamado respondido antes da triagem e triado depois como crítico **não** marca
violação de resposta, mesmo que a resposta tenha levado mais que os 30 minutos
do nível novo (D4). O tempo médio de primeira resposta continua contando a
espera real; o que não acontece é a acusação retroativa.

## 5. Testes

**13 casos** em `tests/test_prioridade_na_triagem.py`, **3** em
`test_dashboard_postgres.py` (contra Postgres, porque a linha `NULL` do
`GROUP BY` é defeito de banco e nenhum mock a produz), **1** em
`test_migrations_postgres.py` (a subida e a descida, rodando de verdade) e
**7** em `TicketDetailPage.test.tsx`.

O prazo é provado **sem depender do relógio**: a abertura é fixa
(`2026-09-14 12:00 UTC`), e o teste compara o prazo carimbado com
`add_business_minutes(abertura, 30)`. Trocar a âncora por `now` derruba as
duas asserções.

### As doze mutações

Oito no backend, quatro no frontend, cada uma derrubando o teste
correspondente. **Duas passaram na primeira rodada e viraram conserto:**

1. **`TicketCreate` voltou a aceitar `priority` e nenhum teste caiu.** Duas
   defesas cobriam o mesmo caminho: o router não escreve o campo, então o
   teste de POST continuava verde com o contrato errado. Isolado por
   `test_o_contrato_de_abertura_nao_tem_campo_de_prioridade`, que afirma sobre
   o schema.
2. **O botão de triagem apareceu para o cliente e nenhum teste caiu.** A seção
   de Ações inteira é `(isStaff || canReopen)`, e com o chamado aberto o
   cliente nunca chega ao guarda do botão. O cenário que isola existe e é
   real: cliente vendo o **próprio chamado resolvido** dentro do prazo de
   reabertura — a seção aparece (ele vê "Reabrir chamado") e o guarda do botão
   é a única coisa segurando a triagem.

Uma terceira ficou mais firme sem ser falsa: `getAllByText("Sem prioridade")`
com `toBeGreaterThan(0)` continuava verde com dois dos três lugares
quebrados. Passou a contar: dois na tela inicial, três depois de abrir a aba
Detalhes.

## 6. Compatibilidade

- **Migration:** `h4c5d6e7f8a9`, filha de `g3b4c5d6e7f8`. Head único, medido;
  `origin/main` não ganhou migration nova desde o ponto de partida.
- **O downgrade escreve, e é a única forma de existir.** `NOT NULL` não volta
  com linha nula na tabela. Ele carimba `medium` no que está nulo — o valor
  que o código antigo teria gravado — e isso está provado rodando.
- **A Helô:** chamado não triado agora chega ao prompt como "sem prioridade
  definida". Ela continua desligada pelo documento de LGPD.
- **`ai_classification`** já guarda a prioridade que a LLM sugere
  (`tickets.py:118`) e a API já a devolve — **nenhuma tela mostra**. O modal de
  triagem é o lugar óbvio para ela aparecer como sugestão. Fora do escopo
  desta entrega.
- **Filtro de "sem prioridade" na lista** não existe: o filtro por prioridade
  segue com os quatro níveis, como estava. Não foi pedido, e mexer nele era
  mexer em filtro existente.

## Referências

- `docs/decisoes-e-regras.md`, seção "SLA" — o RN-013 e a jornada
- [2026-08-20-primeira-resposta-sla-design.md](2026-08-20-primeira-resposta-sla-design.md)
  — a regra de `sla_first_response` que o D4 preserva
- `app/utils/sla.py` — `apply_sla_config`, `check_breaches`,
  `violacao_ao_resolver`
