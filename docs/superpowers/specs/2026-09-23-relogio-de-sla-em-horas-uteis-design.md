# O relógio de SLA da tela passa a contar horas úteis

**Data:** 23/09/2026
**Origem:** o Rickelme viu "27h" num prazo de 12h; desenho aprovado no mesmo dia (D1 a D5)
**Status:** aprovado e implementado; **sem migration**, sem backfill
**Branch:** `feat/relogio-de-sla-em-horas-uteis`, worktree `HelpHS-relogio`

Este documento responde **"por que o número mudou?"**. O prazo mostrado na tela
encolhe — de 27 horas para 12 — sem que prazo nenhum tenha sido alterado. A
seção 4 é a razão.

> Referências `arquivo:linha` apontam para `b8c88e0`, o código **antes** desta
> mudança.

---

## O problema

O chip de prazo fazia `new Date(dueAt).getTime() - Date.now()`
(`SlaChip.tsx:19`): **tempo corrido**.

O caso real: prioridade "Média" definida às 09:11, prazo de resolução de 12h.
O backend carimbou corretamente o vencimento para **12:11 do dia seguinte** —
7h49 até as 17:00 de hoje, mais 4h11 amanhã. A tela mostrava **27h**, porque a
subtração incluía as 15 horas entre 17:00 e 08:00, em que ninguém atende.

Quem lê "27h" e compara com o relógio da parede conclui que tem o dia
seguinte inteiro. Tem meia manhã.

### E um segundo erro, mais antigo

O chip nunca somava `sla_total_paused_ms`. O motor decide violação contra
`due_at + pausa`; o chip comparava contra o `due_at` cru. Num chamado que ficou
três horas em "Aguardando cliente", a tela escrevia **Vencido três horas antes**
de o backend concordar.

O front não tinha nem como acertar: `sla_total_paused_ms` **não estava no
`TicketResponse`** nem no tipo `Ticket` do `ticketService.ts`.

## 1. Levantamento: cinco contas erradas em dois arquivos

| # | Onde | O que fazia | Veredito |
|---|---|---|---|
| 1 | `SlaChip.tsx:19` | `dueAt - Date.now()` | tempo corrido |
| 2 | `SlaChip.tsx` | ignorava a pausa | discordava do motor |
| 3 | `TicketListPage.tsx:137` | `timeLeft = dueMs - now` | tempo corrido |
| 4 | `TicketListPage.tsx:140` | `pct = (now - created) / (due - created)` | **a barra enchia sozinha à noite** |
| 5 | `TicketListPage.tsx:139` | `breached = timeLeft <= 0` | declarava vencido cedo |
| 6 | `TicketDetailPage.tsx:1121` | lê as flags do backend | **certo**, não foi tocado |

O quarto é o mais visível e não estava no relato: a barra do cartão pinta de
vermelho aos 80%, e ela chegava lá durante o fim de semana.

### Por que o calendário não podia ir para o frontend

`e_dia_util()` não é "segunda a sexta". São os dez feriados nacionais da
biblioteca `holidays`, mais Carnaval e Cinzas **derivados da Páscoa** por
`dateutil.easter`, mais uma tabela manual de decretos, cacheados por ano
(`feriados.py`). Reimplementar isso em TypeScript criaria uma segunda verdade
que diverge no primeiro ano em que alguém atualizar só um dos lados.

### A função que faltava

`sla.py` tinha a ida — `add_business_minutes(start, minutes) → datetime`.
**Não tinha a volta.** Nada respondia "quantos minutos úteis faltam de A até B".

## 2. A regra nova, e o contrato

### `business_minutes_between(inicio, fim) → int`

A volta da ida, com as **mesmas peças**: `_advance_to_business_hours` e
`_proximo_inicio_util`. Nenhuma regra de calendário nasceu nela. Devolve zero
quando o prazo já passou — "faltam -40 minutos" não é informação que alguma
tela queira mostrar.

### `prazo_efetivo(due_at, total_paused_ms) → datetime | None`

Uma definição só para o prazo que o motor compara. A expressão estava escrita à
mão em **três** lugares — `check_breaches`, `violacao_ao_resolver` e
`register_first_response` —, e o chip não a fazia de jeito nenhum. Os três
passaram a chamá-la; comportamento idêntico, uma fonte.

> O levantamento da proposta dizia **dois** lugares. Eram três: o
> `register_first_response` também tinha a cópia. Medido ao implementar.

### `estado_do_expediente(agora) → (aberto, proxima_virada)`

O par que deixa a tela congelar sem saber o que é feriado.

### O contrato API → frontend

No **detalhe**, campos aditivos — nada existente mudou de lugar ou de nome:

```
sla_response_vence_em, sla_resolve_vence_em      # o prazo EFETIVO
sla_response_restante_min, sla_resolve_restante_min
sla_response_total_min, sla_resolve_total_min    # denominador da barra
expediente: { agora, aberto, proxima_virada, fuso }
```

Na **listagem**, `expediente` vem **uma vez no topo** e os itens o trazem
nulo — é relógio do servidor, não do chamado, e cinquenta cópias do mesmo
instante seriam lixo na resposta (D3).

### O `fuso` viaja no contrato (D5)

`FUSO_DA_JORNADA = str(SP_TZ)`, derivado da constante do motor. O frontend
**formata** com ele e não crava literal nenhum. Se a jornada mudar de fuso um
dia, muda em `sla.py` e a tela acompanha.

### Por que o decorrido é medido localmente

`decorridoMs` conta do instante em que a resposta chegou, e **não** de
`Date.now() - expediente.agora`. Aquela subtração mistura o relógio do servidor
com o da máquina de quem olha, e um desvio de dez minutos — comum — apareceria
como dez minutos no prazo. A duração da janela
(`proxima_virada - agora`) é subtração de dois instantes **do servidor**, então
serve de teto sem sofrer do problema.

### Alternativas descartadas

- **Pedir o restante ao backend a cada minuto.** Correto e trivial, mas troca
  um erro de representação por tráfego permanente — e a lista teria de repolar
  cinquenta chamados por minuto.
- **Endpoint separado `GET /tickets/{id}/sla`.** Uma viagem a mais no detalhe e
  não serve a lista, onde estão quatro dos cinco defeitos.
- **Mandar o `pct` pronto.** Enviar valor de apresentação em vez do dado.

## 3. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `utils/sla.py` | nascem as três funções; os três cálculos de prazo viram um |
| `schemas/ticket.py` | `ExpedienteInfo`; seis campos aditivos; `expediente` na listagem |
| `routers/tickets.py` | `_serialize_ticket` recebe `agora` e preenche o contrato |
| `lib/tempoUtil.ts` | **novo** — a aritmética da tela, sem calendário |
| `SlaChip.tsx` | conta tempo útil, congela fora do expediente, pede recarga na virada |
| `TicketListPage.tsx` | texto, percentual e vencimento em tempo útil |
| `ticketService.ts`, `Galeria.tsx` | tipos e vitrine no contrato novo |

## 4. Impacto

**Nenhuma migration, nenhum backfill, nenhuma escrita.** Tudo é cálculo de
leitura, e **nenhum prazo mudou**.

O que muda é o que a pessoa vê:

| Situação | Antes | Depois |
|---|---|---|
| Média triada 09:11, prazo 12h | `27h 0m` | `12h 0m úteis` |
| O mesmo às 18:00 | seguia correndo | **congelado**, `· fora do expediente` |
| Sexta 16:00, prazo de 4h | `64h` até segunda | `4h 0m úteis` |
| 3h em "Aguardando cliente" | **Vencido** cedo demais | acompanha o motor |
| Barra do cartão, fim de semana | enchia sozinha | parada |

**A conformidade de SLA não se mexe** — ela lê as flags do backend, que sempre
estiveram certas. O que muda é a tela passar a dizer a mesma coisa que o motor.

## 5. Testes

**45 casos** em `test_sla_tempo_util.py` (os limites: expediente, 17:00 em
ponto, noite, antes das 08:00, sexta→segunda, feriado, prazo no mesmo dia,
atravessando dias, pausa, vencido), **16** em `tempoUtil.test.ts` e **22** em
`SlaChip.test.tsx`.

A prova que amarra os dois lados é a **ida e volta**:
`business_minutes_between(t, add_business_minutes(t, n)) == n`, em quatro
instantes (expediente, noite, sábado, véspera de feriado) e quatro durações.
Se alguém mexer numa função e não na outra, ela cai.

### As onze mutações

Todas derrubaram o teste correspondente. **Uma sobreviveu na primeira rodada:**
cravar o fuso na formatação da **data** não derrubava nada, porque o caso usava
um instante em que São Paulo e UTC caem no mesmo dia. Só a hora estava provada.
Isolado com `2026-09-24T02:00:00Z`, que em São Paulo ainda é dia 23.

## 6. Compatibilidade

- **Sem migration**: o head do Alembic não se mexe.
- **Com a triagem de prioridade** (PR #37, mesclado hoje): chamado sem
  prioridade não tem prazo, os campos saem nulos e o chip não desenha.
- **Resposta antiga em cache**: as guardas são `== null`, que pega nulo e
  indefinido — uma resposta sem os campos novos não derruba a tela.
- **Com o `sort_by=sla_resolve_due_at`**: ordenação é do banco, por coluna;
  intocada.

## O que esta entrega NÃO conserta

**`sla_total_paused_ms` acumula tempo CORRIDO e é somado a um prazo calculado
em horas ÚTEIS.** Uma pausa das 16:00 às 09:00 acrescenta 17 horas a um prazo
que só perdeu 1 hora de atendimento.

É inconsistência real, e foi decidido em 23/09/2026 que ela vira **frente
separada**: corrigi-la muda vencimento e indicador de SLA, que é exatamente o
tipo de mudança que exige desenho próprio. Nesta entrega o contador reproduz
**fielmente** a regra de hoje — o objetivo era a tela parar de discordar do
motor, não mudar o motor.

## Referências

- `docs/decisoes-e-regras.md`, seção "SLA" — o RN-013 e a jornada
- `backend/app/utils/sla.py` — as três funções novas
- `frontend/src/lib/tempoUtil.ts` — a aritmética da tela
