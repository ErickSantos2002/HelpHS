# Primeira resposta do SLA — o que passa a contar

**Data:** 20/08/2026
**Implementado em:** `230d670`
**Origem:** achado 🔴 nº 1 de
[2026-08-20-revisao-helo-fase-1.md](2026-08-20-revisao-helo-fase-1.md) (`87dd05a`),
que revisa o [desenho da Helô](2026-08-11-helo-atendimento-ia-design.md) (Welton)
**Status:** aprovado e implementado; sem migration, sem backfill
**Emendado em 28/08/2026 (`77237c1`):** a regra abaixo continua valendo para
gente, mas a fala da **Helô** passou a carimbar também — decisão do cliente,
revertendo o desenho de 11/08. Isso inverte a previsão que este documento faz
logo abaixo: com a IA atendendo primeiro, o número não piora, ele sobe para
perto de 100% — e deixa de medir a equipe. O porquê está no docstring de
`register_first_response` e em `docs/decisoes-e-regras.md`.

Este documento existe para responder **"por que o número mudou?"**. O card de
violação de resposta e o tempo médio de primeira resposta vão piorar no dia do
deploy. A tabela da seção 1 é a razão.

> Todas as referências `arquivo.py:linha` apontam para `1ec4a73` — o código
> **antes** desta correção, que é o que o documento descreve. O `230d670`
> desloca algumas delas.

---

## O problema

`sla_first_response` era gravado em três lugares (`tickets.py:176`, `:659`,
`:731`), todos sob a mesma condição: `old_status == TicketStatus.open`.

"Primeira resposta" não significava "alguém respondeu". Significava **"o
chamado saiu do estado inicial"**. E como o mapa de transições só permite
`open → in_progress` e `open → cancelled`, sair de `open` quer dizer, na
prática, **"alguém assumiu ou cancelou"** — nunca "alguém falou".

Os dois indicadores que a equipe acompanha mediam o tempo até alguém clicar:

- card de violação de resposta — `dashboard.py:90-100`
- tempo médio de primeira resposta por prioridade — `dashboard.py:412`

---

## 1. Levantamento: os treze caminhos

Cada caminho pelo qual alguém age sobre um chamado, conferido contra o código.

| # | Caminho | Onde | Marcava? | Veredito |
|---|---|---|---|---|
| A | Técnico manda mensagem no chat (REST) | `chat.py:203` | **Não** | ❌ Falso negativo — e é o caminho mais comum |
| B | Técnico manda mensagem pelo WebSocket | `chat.py:456` | **Não** | ❌ Idem |
| C | Admin/técnico atribui o chamado | `assign_ticket` → `_auto_transition` → `tickets.py:176` | **Sim** | ❌ Falso positivo — atribuir a um terceiro marcava "respondeu" |
| D | Técnico assume (`PATCH /status` open→in_progress) | `tickets.py:659` | **Sim** | ❌ Falso positivo |
| E | Admin cancela via `PATCH /status` (open→cancelled) | `tickets.py:659` | **Sim** | ❌ Falso positivo grave: chamado cancelado entrava na média de tempo de resposta |
| F | Admin cancela via `DELETE /tickets/{id}` | `tickets.py:969` | **Não** | ⚠️ Certo por acidente — dois caminhos para cancelar, resultados de SLA diferentes |
| G | Técnico resolve direto um chamado `open` | `tickets.py:731` | **Sim** | ✅ Efeito certo, razão errada |
| H | Técnico resolve um chamado que já saiu de `open` | `tickets.py:731` (condição falsa) | **Não** | ❌ Chamado atendido e resolvido que **nunca** registrava primeira resposta |
| I | Cliente manda mensagem | `chat.py:203`/`:456` | Não | ✅ |
| J | Cliente responde e o status transiciona | `_auto_transition` | Não | ✅ |
| K | Técnico grava nota interna / `technician_notes` | `tickets.py:1037` / `:548` | Não | ✅ Nota interna não é visível ao cliente |
| L | Fechamento automático (worker) | `ticket_lifecycle.py` | Não | ✅ Só age em `resolved` |
| M | Reabertura | `tickets.py:772` | Não toca no campo | ⚠️ Ver seção 7 |

**Placar:** dois falsos negativos no caminho mais usado (A, B), três falsos
positivos (C, D, E), um buraco (H).

### O achado que veio junto: a violação se apagava sozinha

Nos três pontos, a ordem era carimba-primeiro-avalia-depois:

```
tickets.py:176   ticket.sla_first_response = now
tickets.py:183   check_breaches(ticket, now)      # ← já vê o campo preenchido
```

E `check_breaches` (`sla.py:161`) só olha o prazo **enquanto
`sla_first_response` é nulo**. Um chamado assumido três dias depois do prazo
saía com `sla_response_breach = False`. A condição viva do dashboard também
exige `sla_first_response IS NULL`, então a violação sumia dos dois lados.

**Na prática, uma primeira resposta atrasada quase nunca era contada como
violação.** Mesmo padrão em `tickets.py:659→667` e `:731→734`.

Este achado é independente da regra e teria sobrevivido a qualquer redesenho
que não olhasse para a ordem das linhas.

---

## 2. A regra nova

> **Marca a primeira resposta o instante da primeira mensagem de chat, no
> chamado, de alguém que não é o autor — e a resolução, quando nenhuma
> mensagem veio antes.**

Uma função só, `register_first_response` em `app/utils/sla.py`:

```
marca se:  sla_first_response is None
       e   not is_ai
       e   not is_system
       e   responder_id is not None
       e   responder_id != ticket.creator_id
```

**Nenhum status entra no predicado.** É a propriedade central, não um detalhe
de implementação — ver seção 6.

### Por que "não é o autor" e não "é staff"

É o mesmo critério que `_notify_other_party` (`chat.py:555`) já usa para
decidir a quem notificar. Mesma pergunta — "há alguém do outro lado?" —, uma
só resposta no código. E cobre de graça o admin que abre chamado interno:
respondendo a si mesmo, não marca.

Não há caso de borda: `creator_id = actor.id` sempre (`tickets.py:347`), não
existe abertura em nome de terceiro, e cliente só enxerga o próprio chamado.

### Por que a resolução também conta

A `resolution_note` é texto que o cliente lê. Sem essa regra o buraco (H)
continuaria: chamado simples, resolvido direto sem chat, ficaria sem primeira
resposta para sempre e sumiria da média. Marca **independente do status de
origem**, o que conserta (H) e coloca (G) sobre a razão certa.

O predicado de não-autor vale ali também: quando quem abre e quem resolve são
a mesma pessoa, não houve ninguém do outro lado esperando, e um tempo de
resposta de zero segundo só sujaria a média de uma conversa que não existiu.

### Por que `awaiting_client` manual não conta

1. Na prática ela quase nunca acontece sozinha — quem leva o chamado para
   `awaiting_client` é o `_apply_chat_transition` (`chat.py:527`), disparado
   por uma mensagem do técnico. A mensagem já marca; contar o status seria
   contar o mesmo fato duas vezes.
2. O caso restante é o técnico mudar o status na mão. Ali ele *afirma* ter
   pedido algo ao cliente, mas não há uma palavra registrada no chamado.
   Contar reabriria exatamente o buraco que estamos fechando.
3. Se a equipe atende por telefone, a fala precisa virar mensagem no chamado
   de qualquer jeito — para o SLA e para o próximo técnico que pegar o caso.

### A violação passou a ser avaliada antes do carimbo

`register_first_response` avalia o prazo (com o offset de pausa) e só então
grava. Sendo autocontida, a ordem nos call sites deixou de importar.

### Alternativas descartadas

| Alternativa | Por que não |
|---|---|
| Só mensagem de chat, sem a resolução | Mais purista, mas mantém o buraco (H) num caso comum |
| Aditivo: manter "saiu de `open`" e somar o chat | Menos ruptura, mas mantém os três falsos positivos e faz o indicador *melhorar* artificialmente — o inverso do que se quer |

---

## 3. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `app/utils/sla.py` | `register_first_response` — predicado, avaliação de violação e carimbo |
| `app/routers/chat.py` | Chama nos dois pontos que criam mensagem (REST e WebSocket) |
| `app/routers/tickets.py` | Remove as três condições `old_status == open`; `resolve_ticket` passa a chamar a função |

**Sem migration, sem mudança de schema, sem mudança no frontend.** Os campos e
o contrato da API são os mesmos; mudou só quando o campo é escrito.

---

## 4. Impacto nos dados existentes

**A regra é prospectiva. Decide quando gravar; não reescreve nada.**

| Situação | O que acontece |
|---|---|
| Chamados resolvidos e fechados | O valor gravado permanece. Relatório antigo não muda |
| Chamados vivos com o campo já preenchido "errado" | Continuam preenchidos — o predicado só age quando o campo é nulo. Não há reversão |
| Chamados vivos com campo nulo que já tiveram conversa | Continuam nulos até a próxima mensagem do técnico, e aí marcam |

### Sem backfill — decisão registrada

Migration roda sozinha no boot do container. Um `UPDATE` varrendo
`tickets × chat_messages` é a categoria de coisa que derruba a API na subida,
como o guard de CORS derrubou em 19/08.

O dado até existe (`chat_messages` tem `sender_id` e `created_at`, dá para
reconstruir a primeira mensagem de não-autor), então o backfill é *possível*.
Mas ele reescreveria números que a equipe já viu em relatório, e **mudar o
passado de um indicador é pior do que ter um passado torto e datado**.

O efeito também é autocorretivo: chamado vivo marca na próxima mensagem;
chamado morto não entra mais no numerador de nada em movimento.

Se um dia for pedido: script avulso, rodado uma vez com o resultado conferido
antes — nunca migration no boot.

### O número vai piorar, e essa é a intenção

No dia do deploy o card de violação de resposta sobe (deixa de apagar violação
atrasada e deixa de contar clique) e o tempo médio sobe (deixa de contar
cancelamento e atribuição como resposta em segundos). Não é regressão — é o
indicador parando de mentir. Combinar com a equipe antes.

### Borda conhecida e aceita

Chamado que a mesma pessoa abre e resolve não marca primeira resposta. Se ele
passar do prazo de resposta, o `check_breaches` que roda em seguida registra a
violação, que agora persiste depois da resolução. É um chamado sem ninguém
esperando do outro lado; some das duas métricas de tempo e aparece uma vez no
card. Aceito por ser raro e por não valer a complexidade de tratar.

---

## 5. Testes

17 testes, nenhum dependendo do relógio: `now` é sempre injetado por parâmetro
e a função nova não chama `datetime.now()`.

**Núcleo puro** (`tests/test_sla.py`, estilo `_mock_ticket` com datas
explícitas em `America/Sao_Paulo`):

| Caso | Espera |
|---|---|
| não-autor responde | marca |
| autor do chamado escreve | não marca |
| segunda mensagem do técnico | não marca (idempotente) |
| `is_ai=True` | não marca |
| `is_system=True` | não marca |
| `responder_id=None` | não marca |
| resposta depois do prazo | marca **e** registra a violação |
| resposta dentro do prazo | marca sem violação |
| 2h de pausa esticando o prazo | marca sem violação |
| chamado sem SLA aplicado | marca sem inventar violação |

**Rotas** (`tests/test_chat.py`): mensagem do técnico marca; mensagem do autor
não marca.

**Regressões** (`tests/test_tickets.py`): assumir não marca; cancelar pelo
status não marca; atribuir não marca; resolver fora de `open` marca; resolver
o próprio chamado não marca.

Suíte completa verde — 466 testes, cobertura 82,65%.

---

## 6. Compatibilidade com a Helô

Esta correção é pré-requisito da Fase 1, não um efeito colateral dela.

- **A regra não menciona status nenhum.** Chamado que nasce em `ai_handling` e
  nunca passa por `open` funciona igual. Os dois modos de falha que a revisão
  previu — `NULL` para sempre, ou SLA de 100% permanente — deixam de existir,
  porque nascer num status deixou de ser um evento de SLA.
- **A mensagem da Helô é excluída por dois filtros independentes:** `is_ai` e
  `responder_id is None`. Qualquer um sozinho basta — se ela um dia ganhar um
  usuário, o `is_ai` segura; enquanto for `sender_id` nulo, o outro segura. É
  a linha "conta como primeira resposta do SLA: **não**" da tabela de decisões
  do desenho, garantida no lugar certo em vez de no comportamento.
- **A escalação `ai_handling → awaiting_technical` não marca nada**, porque
  status deixou de marcar. O relógio corre até um humano escrever.
- **O teste de `responder_id=None` já está no repositório**, antes de a Helô
  existir. O comportamento chega travado à Fase 1.

**Restrição para a Fase 1:** o resumo da triagem, se virar mensagem no chat,
precisa sair com `is_ai=True` ou `is_system=True`. Gravado como mensagem de um
usuário técnico, marcaria primeira resposta indevida. O caminho natural é o
campo `ai_conversation_summary`, que já existe no ticket e não passa pelo chat.

---

## 7. Fila: a reabertura não renova o prazo de resposta (item M)

**Fora do escopo desta rodada. Registrado, não corrigido.**

`reopen_ticket` (`tickets.py:824-838`) renova `sla_resolve_due_at` e limpa
`sla_resolve_breach`. Não toca em `sla_response_due_at`, `sla_response_breach`
nem `sla_first_response`.

Conferido contra o anúncio da v1.4.0 (RN-005/RN-006), **há contradição**. O
changelog do produto (`frontend/src/data/changelog.ts:54`) diz:

> "Reabrir um chamado devolve um prazo de atendimento novo, em vez de
> trazê-lo de volta já vencido."

E o chamado reaberto volta com metade do prazo vencido, visivelmente:
`TicketDetailPage.tsx:1063-1064` desenha dois chips lado a lado. O chip
**"Resolução"** mostra a contagem nova. O chip **"Resposta"** mostra
`sla_response_due_at`, que ficou no dia da abertura original — e o `SlaChip`
(`:242`) exibe **"Vencido"** para qualquer prazo no passado.

O comentário do código é explícito ("Prazo de resolução novo"), então a
intenção do `0e00a31` foi só a resolução; o changelog do produto generalizou
para "prazo de atendimento". A promessa cobre mais do que o código entrega.

Não é conserto trivial, e é por isso que fica na fila: renovar o prazo de
resposta obriga a decidir o que fazer com `sla_first_response`. Zerá-lo dá um
ciclo novo de verdade, mas apaga o único registro da primeira resposta do
ciclo anterior — o que provavelmente pede um campo por ciclo, não um campo por
chamado. Decisão de produto, própria, com seu próprio desenho.

---

## Referências

- Desenho da Helô: [2026-08-11-helo-atendimento-ia-design.md](2026-08-11-helo-atendimento-ia-design.md)
- Revisão técnica: [2026-08-20-revisao-helo-fase-1.md](2026-08-20-revisao-helo-fase-1.md) (`87dd05a`)
- Implementação: `230d670`
