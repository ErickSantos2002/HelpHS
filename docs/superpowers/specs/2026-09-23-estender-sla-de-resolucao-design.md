# Estender SLA de resolução — e o painel passa a medir o mesmo prazo

**Data:** 23/09/2026
**Origem:** pedido do Rickelme, com desenho aprovado no mesmo dia (F1 a F5)
**Status:** aprovado e implementado; **com migration**, sem backfill de regra
**Branch:** `feat/estender-sla-de-resolucao`, worktree `HelpHS-extensao`

Este documento responde **"por que o número mudou?"**. A conformidade de SLA se
mexe no deploy — e **parte da mudança não vem desta funcionalidade**. A seção 3
é a razão, e foi decidida com o preço à vista.

> Referências `arquivo:linha` apontam para `11653e1`, antes desta mudança.

---

## O problema

Técnico percebe que não vai resolver no prazo da prioridade. Hoje ele tem duas
saídas, e as duas são ruins: deixar estourar, ou mudar a prioridade para
ganhar prazo — o que mente sobre a urgência do chamado e contamina o
indicador.

Faltava um terceiro caminho: **prorrogar o prazo, com justificativa que o
cliente lê**, sem apagar qual era o prazo original.

## 1. Levantamento: quem decide "violado"

### O achado que mudou o tamanho da entrega

| Caminho | Como decide | Considera a pausa? |
|---|---|---|
| **Motor** (`check_breaches`, chip, barra) | `prazo_efetivo(...)` em Python | ✅ sim |
| **Painel e relatórios** (`_resolve_breached_cond`) | `sla_resolve_due_at < now()` em **SQL** | ❌ **não** |

O painel **nunca** passou pelo motor: ele comparava a coluna crua. Isso já
significava que, num chamado pausado, ele contava violação que o chamado não
contava. Com a extensão, a divergência ficaria pior — um chamado prorrogado
apareceria "no prazo" na tela e "violado" no relatório.

E a condição alimenta **cinco números**: o card do painel, a conformidade por
prioridade, a comparação com o período anterior, e as violações por técnico
(individual e em lote).

### Os insumos do prazo efetivo, e quem escreve cada um

Varredura fechada — é o que permitiu materializar com segurança:

| Insumo | Escritas | Onde |
|---|---|---|
| `sla_resolve_due_at` | 2 | `apply_sla_config`, reabertura |
| `sla_total_paused_ms` | 3 | criação, reabertura, `resume_sla` |
| `sla_resolve_extension_total_min` | 2 (novas) | concessão, reabertura |

**`sla_paused_at` não é insumo.** O motor nunca considerou a pausa em curso —
só o acumulado. É exatamente isso que torna o prazo efetivo uma **função pura
de três campos persistidos**, sem nada que dependa do relógio, e portanto
materializável. Se um dia a pausa em curso passar a contar, a materialização
deixa de ser possível; há um teste que falha se isso mudar.

## 2. A regra nova

### F2 — Duas portas nomeadas, não um terceiro argumento

```python
prazo_efetivo_de_resposta(ticket)    # base + pausa
prazo_efetivo_de_resolucao(ticket)   # base + pausa + EXTENSÃO
```

A extensão vale só para resolução. Com um parâmetro opcional no
`prazo_efetivo`, bastava alguém passá-lo na chamada errada para o prazo de
resposta esticar em silêncio. Com duas portas **não existe onde escrever
isso** — e há mutação provando: injetar a extensão na porta de resposta
derruba teste.

Ordem das camadas: **base → pausa → extensão**. A pausa é tempo corrido
somado ao prazo; a extensão é tempo útil contado a partir do resultado.
Inverter daria outro instante.

### O acumulador, e por que não um prazo pronto

`sla_resolve_extension_total_min` guarda o **total de minutos úteis
concedidos**, e o prazo é sempre recomputado da base. Isso dá três
propriedades de graça:

- **+3 depois +1 == +4** — conceder é associativo;
- **trocar a prioridade não apaga a extensão** — `apply_sla_config` recarimba
  só a base;
- **idempotência** — recalcular nunca muda o resultado.

1 dia útil = a jornada inteira = **540 minutos**, via `minutos_uteis_de_dias`,
que deriva de `_WORK_HOURS_PER_DAY`. Não há `540` escrito à mão.

### F3 — Tabela própria para o evento

`ticket_sla_extensions`: `days`, `business_minutes`, `justification`,
`previous_effective_due_at`, `new_effective_due_at`, quem e quando.

A extensão é um **compromisso de prazo comunicado ao cliente**. Guardar a
quantidade concedida como informação derivada de `old_value`/`new_value` faria
a auditoria depender de reconstrução. **Append-only pela regra de negócio**:
nenhum fluxo edita ou apaga uma linha daqui, e a reabertura zera o acumulador
sem tocar no registro do ciclo anterior.

`days` **e** `business_minutes`, os dois: `days` é o que a pessoa escolheu;
`business_minutes` é o que entrou na conta. Só com os dias, reconstruir o
concedido dependeria da jornada **vigente**, não da que valia no dia.

A linha em `ticket_history` continua existindo — a timeline não pode ter um
buraco onde houve decisão de prazo —, mas a fonte auditável é a tabela.

### F4 — Preview pelo backend

`GET /tickets/{id}/sla/extend/preview?days=N` devolve prazo atual, novo prazo,
dias e minutos. Uma viagem quando a pessoa escolhe o valor, e **nenhum
calendário em TypeScript**.

### O endpoint

`POST /tickets/{id}/sla/extend`, `authorize(admin, technician)`, cliente 403.

Quatro recusas com **409** — a requisição está bem formada, o estado é que não
permite: encerrado, sem prioridade, sem prazo, ou **prazo efetivo já vencido**.

A última **não olha `sla_resolve_breach`**. A flag só é recalculada em escrita,
então um chamado vencido e intocado chega com ela falsa — e seria justamente
esse que alguém prorrogaria para apagar a violação antes de ela ser marcada.
Quem decide é a comparação de `now` com o prazo efetivo.

### Uma nota sobre o tipo dos dias

O desenho previa `Literal[1, 3, 5, 15, 30]`. **Medido: não serve.** O `Literal`
de int não converte a string que chega numa query, então o mesmo tipo aceitaria
`{"days": 3}` no corpo e recusaria `?days=3` no preview. Virou um enum de
inteiros — uma definição só, que vale nos dois caminhos, e continua recusando
qualquer outro valor no **contrato**, sem `if` para alguém esquecer.

## 3. ⚠️ O impacto na conformidade

**Migration aditiva.** `sla_resolve_extension_total_min` nasce `0` por
`server_default`; a tabela nasce vazia.

O `UPDATE` que preenche `sla_resolve_effective_due_at` **não é backfill de
regra nova**: ele materializa `base + pausa`, que já era o que o motor
calculava e ninguém guardava. Nenhum prazo muda, nenhuma decisão é reescrita.

### O que se mexe, e por quê

| Cenário | Antes | Depois |
|---|---|---|
| Sem pausa, sem extensão | violado se o prazo passou | **idêntico** |
| Com extensão válida | — | deixa de contar violação |
| **Com pausa** | contava violação | **deixa de contar** |
| Com pausa + extensão | contava | deixa de contar |

**A terceira linha é a que muda sem ser sobre extensão.** Ela é a divergência
antiga sendo eliminada: o painel passa a medir o mesmo prazo que o chamado
sempre mostrou. A conformidade pode **subir** no deploy, e parte dessa subida
não vem desta funcionalidade.

Foi a decisão F1, com as alternativas recusadas por escrito: manter duas
definições de prazo (E2), ou deixar o chamado dizer "no prazo" e o painel dizer
"violado" (E3).

**Não foi medido quantos chamados estão pausados agora** — isso exigiria
consultar produção.

### O que NÃO muda

- O **prazo original** (`sla_resolve_due_at`) continua persistido e intocado.
- A marca de violação **já gravada** continua contando: o `or_` da condição
  garante que prorrogar não apaga o que já foi concluído.
- O SLA de **resposta** não é tocado por nada disto.

## 4. Testes

**7 contra Postgres** (`test_sla_extensao_postgres.py`), incluindo os quatro
cenários de conformidade lado a lado e o invariante da materialização
percorrendo todos os caminhos; **1** de migration com `upgrade → downgrade →
upgrade`, provando que linha antiga nasce com `0` e com o prazo materializado
correto; **39** de contrato e motor; **11** de tela.

### As nove mutações

Todas derrubaram o teste. **Uma sobreviveu na primeira rodada, e o achado foi
real:** remover o zeramento da extensão na reabertura não quebrava nada, porque
o teste do invariante **simulava** a reabertura escrevendo os campos à mão. Só
o caminho de verdade prova o caminho de verdade — passou a haver um teste que
chama o endpoint de reabertura.

### Um defeito que a suíte pegou

`Ticket(...)` sem o campo deixa `sla_resolve_extension_total_min` como `None` em
memória: o `default=0` do ORM só vale no INSERT, e o chamado é serializado
**antes** do flush. É o mesmo que o `ai_enabled` já documenta neste arquivo, e
o conserto é o mesmo — passar explícito na criação.

## 5. Compatibilidade

- **Migration** `i5d6e7f8a9b0`, filha de `h4c5d6e7f8g9`. Head único.
- **Com o relógio (PR #39)**: o chip e a barra leem `sla_resolve_restante_min` e
  `sla_resolve_vence_em`, que saem das portas nomeadas. Eles passam a mostrar o
  prazo prorrogado **sem uma linha de mudança**.
- **F5 — ordenação**: `sort_by=sla_resolve_due_at` passa a ordenar pela coluna
  materializada. Pelo prazo cru, um chamado prorrogado para daqui a 15 dias
  continuaria aparecendo como se vencesse hoje.

## O que esta entrega NÃO conserta

`sla_total_paused_ms` continua sendo **tempo corrido** somado a um prazo em
horas úteis — uma pausa das 16:00 às 09:00 alarga o prazo em 17 horas quando só
1 hora útil se perdeu. Fora de escopo por decisão explícita: corrigir muda
vencimento e indicador, e é frente própria.

O F1 faz o painel **respeitar essa mesma regra torta**, não a conserta.

## Referências

- `docs/decisoes-e-regras.md`, seção "SLA"
- [2026-09-23-relogio-de-sla-em-horas-uteis-design.md](2026-09-23-relogio-de-sla-em-horas-uteis-design.md)
- `backend/app/utils/sla.py` — as portas nomeadas e a materialização
