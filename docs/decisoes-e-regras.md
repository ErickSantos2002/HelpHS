# Decisões e regras de negócio — HelpHS

Registro das regras que **não dá para deduzir lendo o código** e das decisões
tomadas junto ao cliente. Atualizado em 24/08/2026 (v1.8.0, ainda não publicada).

Para o histórico voltado ao usuário final, veja `frontend/src/data/changelog.ts`.
Para o detalhe de cada tabela, o `Documentação/Dicionario_Dados_HelpDesk_v1.docx`.
Para o registro do que mudou a cada dia de trabalho, `mudanças.md` e
`Changelog.md` na raiz.

---

## SLA

**Jornada: segunda a sexta, 08:00–17:00 (9 horas úteis por dia).**

O valor vive em `backend/app/utils/sla.py` (`_WORK_START` / `_WORK_END`). Havia
divergência entre as fontes: o docstring do módulo e o Dicionário de Dados diziam
18:00, enquanto a constante virou 17:00 no commit `5954d3b`. O documento de
Requisitos (RN-013) sempre disse 08h–17h, e o cliente confirmou 9h/dia em
05/08/2026. Documentação e testes foram alinhados ao código.

Feriados não são modelados nesta versão — só fins de semana.

### Quando o prazo é carimbado (22/09/2026)

**O chamado nasce sem prioridade e, portanto, sem prazo.** Quem carimba os dois
prazos é a triagem — técnico ou administrador, pelo
`PATCH /tickets/{id}/priority`. Até lá o chamado não tem `sla_response_due_at`
nem `sla_resolve_due_at`, não mostra relógio na tela e fica **fora do
denominador** da conformidade de SLA. Ele continua contando no total de
chamados, num balde próprio ("Sem prioridade").

**O prazo conta da ABERTURA, não da triagem.** `apply_sla_config` recebe
`ticket.created_at`, e não o instante do clique: o RN-013 diz que o SLA conta
da abertura até a resolução, e classificar não é recomeçar. A consequência foi
decidida com ela à vista — **triagem demorada entrega um chamado que já nasce
vencido**, e é assim que a demora aparece na conformidade em vez de sumir.

Duas exceções, as duas pelo mesmo princípio de não desfazer conclusão alheia:

- **Resposta já dada não vira violação retroativa.** `check_breaches` só olha o
  prazo de resposta enquanto `sla_first_response` é nulo. Quem respondeu antes
  de o prazo existir não passa a dever resposta.
- **Chamado encerrado não tem o prazo recalculado.** Corrigir a prioridade de
  um chamado resolvido, fechado ou cancelado grava o campo e o histórico, e
  deixa os prazos como estão — uma justificativa de violação já escrita se
  apoia neles.

**Na ordenação por prioridade, o não triado vem PRIMEIRO** — sem prioridade →
crítica → alta → média → baixa. Vale no `sort_by=priority` da API e no quadro
de chamados, com a mesma régua. O motivo é o prazo: ele corre desde a abertura,
então o chamado que espera triagem no fim da fila fica escondido justamente
enquanto o relógio anda. É ordem operacional — "sem prioridade" continua não
sendo um nível, e continua fora do denominador da conformidade. Prioridade
**desconhecida** (valor que o banco tenha e o código não conheça) vai para o
fim, não para o começo.

O desenho completo, com as cinco decisões aprovadas, está em
`docs/superpowers/specs/2026-09-22-prioridade-definida-na-triagem-design.md`.

### O contador da tela conta HORAS ÚTEIS (23/09/2026)

**O prazo mostrado no chip e na barra do cartão é tempo ÚTIL restante**, não a
diferença entre o relógio e o vencimento. Um prazo de 12h úteis carimbado às
09:11 mostra `12h 0m úteis`, e não as 27 horas corridas até 12:11 do dia
seguinte.

O contador **congela fora do expediente** — 17:00 às 08:00, fim de semana e
feriado — e volta a andar quando a jornada seguinte começa.

**O frontend não tem calendário.** O backend manda os minutos úteis restantes
(`business_minutes_between`), o prazo efetivo e o estado do expediente
(`estado_do_expediente`), e a tela só desconta o tempo que passa. Jornada, fim
de semana e feriado têm uma fonte só: `backend/app/utils/sla.py`. O fuso em que
o vencimento é exibido também viaja no contrato (`FUSO_DA_JORNADA`), para não
existir literal de fuso no frontend.

O prazo que a tela mostra é o **efetivo** (`prazo_efetivo` = carimbado + pausa
acumulada) — o mesmo que `check_breaches` compara. Antes o chip usava o prazo
cru e, num chamado pausado por três horas, escrevia "Vencido" três horas antes
de o motor concordar.

### Estender o prazo de resolução (23/09/2026)

**Técnico e administrador podem prorrogar o prazo de RESOLUÇÃO** em 1, 3, 5, 15
ou 30 **dias úteis**, com justificativa obrigatória que o cliente lê. O SLA de
**resposta** não é afetado.

Regras que valem a pena estar aqui:

- **O prazo original nunca é sobrescrito.** `sla_resolve_due_at` continua sendo
  o que a prioridade carimbou; o que cresce é `sla_resolve_extension_total_min`,
  um acumulador de minutos úteis. Guardar o acumulado — e não um prazo pronto —
  é o que faz +3 e depois +1 valerem exatamente +4, e o que faz a extensão
  sobreviver a uma troca de prioridade, que recarimba só a base.
- **Só antes de vencer.** A recusa compara `now` com o prazo efetivo do motor,
  e **não** com `sla_resolve_breach` — a flag só é recalculada em escrita, e um
  chamado vencido e intocado chega com ela falsa. A extensão serve para evitar
  o atraso, não para desfazê-lo.
- **Prorrogar não apaga violação já marcada.** O que aconteceu, aconteceu.
- **Reabrir zera a extensão do ciclo novo**, e não apaga os registros do ciclo
  anterior: o histórico continua mostrando que houve prorrogação antes.
- Cada concessão é uma linha em `ticket_sla_extensions`, **append-only pela
  regra de negócio**.

### ⚠️ O painel passou a medir o MESMO prazo do chamado (23/09/2026)

Até aqui o painel e os relatórios decidiam violação em SQL comparando a coluna
crua `sla_resolve_due_at` contra `now()`. Isso **ignorava a pausa acumulada**,
então um chamado pausado contava violação no painel que o chamado não contava
na tela. Ninguém tinha medido.

Passou a existir `sla_resolve_effective_due_at` — o prazo efetivo
**materializado**, escrito só por `atualiza_prazo_efetivo` e igual ao que
`prazo_efetivo_de_resolucao` devolve. O SQL compara essa coluna.

**A conformidade mudou no deploy por causa disso**, inclusive para chamados que
só tiveram pausa e nunca extensão. Foi decisão consciente: a alternativa era
manter duas definições de prazo, ou deixar um chamado prorrogado aparecer "no
prazo" na tela e "violado" no relatório.

A materialização é possível porque o prazo efetivo é função pura de três campos
**persistidos** — prazo base, pausa acumulada e extensão acumulada. A pausa
**em curso** (`sla_paused_at`) não participa, porque o motor nunca a
considerou. Se isso mudar um dia, a materialização deixa de ser possível — há
teste que falha se alguém tentar.

### ⚠️ Dívida conhecida: a pausa é tempo corrido num prazo útil

`sla_total_paused_ms` acumula tempo **corrido** e é somado a um prazo calculado
em horas **úteis**. Uma pausa das 16:00 às 09:00 acrescenta 17 horas a um prazo
que só perdeu 1 hora de atendimento — o chamado ganha folga muito maior do que
a pausa custou.

Registrado em 23/09/2026 e **deixado de propósito**: corrigir muda vencimento e
indicador de SLA, e por isso é frente própria, com desenho antes do código. Até
lá, tela, motor **e painel** usam a mesma conta — a de hoje, torta e igual nos
três.

### O que conta como primeira resposta

**A primeira resposta é a primeira fala dirigida ao cliente por alguém que não
é o autor do chamado.** Vale a primeira mensagem de chat de outra pessoa, e a
resolução como rede de segurança — a nota de resolução é texto que o cliente
lê, e sem ela o chamado resolvido sem conversa nenhuma ficaria eternamente sem
resposta registrada.

**A fala da Helô também carimba** — decisão do cliente em 28/08/2026,
revertendo o desenho de 11/08. O argumento: quando ela responde, o
atendimento começou de fato, e mostrar "aguardando primeira resposta" para
quem acabou de ser respondido é o indicador mentindo para o lado contrário. A
guarda de "não é o autor" passou a valer **só para gente** — a Helô fala com
remetente nulo, e sem uma saída explícita para ela a regra a recusaria
justamente no caso que o cliente pediu.

Mudança de status **não conta**, nem para "Aguardando cliente" — nem a
mensagem automática que a acompanha, que é o sistema narrando a si mesmo e não
alguém falando com o cliente. Se o atendimento aconteceu por telefone, a fala
precisa virar mensagem no chamado de qualquer forma — para o indicador e para
o próximo técnico que pegar o caso.

**A fala da Helô conta** — decisão do cliente em 28/08/2026. Quando ela
responde, o atendimento começou de fato, e dizer "aguardando primeira resposta"
a quem acabou de ser respondido é o indicador mentindo para o outro lado. A
saudação dela carimba `sla_first_response` no mesmo instante em que o chamado
nasce.

O desenho original dizia o contrário, e o motivo continua verdadeiro — está
registrado em `docs/superpowers/specs/2026-08-11-helo-atendimento-ia-design.md`
junto da reversão. Mensagem automática de sistema (`is_system`) segue sem
carimbar: mudança de status anunciada no chat não é alguém falando com o
cliente.

Até 20/08/2026 a regra era outra, e media coisa diferente do que o nome dizia:
o carimbo acontecia quando o chamado **saía de "Aberto"**. Como o mapa de
transições só permite `open → in_progress` e `open → cancelled`, "primeira
resposta" queria dizer, na prática, "alguém assumiu ou cancelou". Isso
distorcia o indicador nas duas direções ao mesmo tempo:

- técnico que respondia pelo chat sem mexer no status **não registrava nada** —
  e esse é o caminho mais usado;
- atribuir, assumir ou **cancelar** um chamado registrava resposta sem uma
  palavra ter sido dita, com poucos segundos de "tempo de resposta".

Havia ainda um efeito que apagava violação: o carimbo vinha **antes** da
avaliação de prazo, e `check_breaches` só olha o prazo enquanto
`sla_first_response` é nulo. Chamado atendido três dias depois do prazo saía
com `sla_response_breach = False`. Hoje `register_first_response`
(`app/utils/sla.py`) avalia a violação antes de carimbar, e é o único ponto do
sistema que grava esse campo.

> ⚠️ **Com a Helô ligada, este indicador tende a 100%.** Todo chamado passa a
> ter primeira resposta em segundos, porque ela responde na abertura. O número
> deixa de medir a equipe e passa a medir o robô, que é sempre rápido — a
> consequência foi dita antes da decisão e aceita com ela. Quem quiser saber
> quanto o cliente esperou por um **humano** precisa de uma coluna nova: não dá
> para extrair essa informação desta, porque o carimbo é um só e já foi usado.
> A flag `HELO_ENABLED` desliga a Helô, e com ela o indicador volta ao que era.

> ⚠️ **Os números de primeira resposta mudaram a partir da v1.8.0.** O card de
> violação sobe e o tempo médio sobe — não porque o atendimento piorou, mas
> porque o indicador deixou de contar clique como conversa e deixou de apagar
> violação atrasada. Comparações com relatórios anteriores a essa data não são
> justas. O levantamento dos treze caminhos que alimentavam a regra antiga está
> em `docs/superpowers/specs/2026-08-20-primeira-resposta-sla-design.md`.

> ⚠️ **E mudaram de novo, na direção oposta, quando a Helô passou a
> carimbar.** Com ela ligada todo chamado ganha primeira resposta em segundos:
> o indicador sobe para perto de 100% e o tempo médio despenca. Não é a equipe
> ficando mais rápida — é o indicador **deixando de medir a equipe e passando
> a medir o robô**, que é sempre rápido. Enquanto a Helô atender primeiro,
> este número não serve para avaliar gente, e comparação só é justa entre
> períodos do mesmo lado de 28/08/2026. O preço foi dito antes da decisão e
> aceito junto com ela.

## Ciclo de encerramento do chamado

Os dois prazos abaixo são contados em **dias úteis** a partir do momento em que
o chamado foi **resolvido** — não do fechamento. Em dias corridos, quem
resolvesse na sexta à tarde daria ao cliente praticamente nenhum dia de
trabalho para se manifestar.

| Evento | Prazo | Configuração |
|---|---|---|
| Resolvido → Fechado, sozinho | 3 dias úteis | `TICKET_AUTO_CLOSE_BUSINESS_DAYS` |
| Cliente ainda pode reabrir | 5 dias úteis | `TICKET_REOPEN_BUSINESS_DAYS` |

A janela de reabertura é **maior** que a de fechamento de propósito: o chamado
fecha sozinho no 3º dia, mas o cliente continua podendo reabrir por mais dois.
Sem essa folga, o fechamento automático tiraria dele a única saída.

Definido com o cliente em 07/08/2026. Os requisitos originais previam 5 e 7
dias; nenhum dos dois estava implementado até então.

### O que acontece em cada status

**Resolvido** — SLA parado, chat bloqueado, convite para avaliar enviado. É a
janela em que o cliente ainda pode se manifestar.

**Fechado** — arquivamento. Chegar aqui pela rotina automática marca
`auto_closed = true` no chamado, e a tela avisa que o fechamento não foi
decisão de ninguém.

### Reabertura

Quem reabre precisa **escrever o motivo** (mínimo 5 caracteres). Ele vai para o
histórico e é o que o técnico lê para saber por onde retomar — a nota de
resolução anterior continua no chamado.

O chamado volta para **Em andamento** quando tem responsável, e para **Aberto**
quando não tem, para ser distribuído como um chamado novo.

O prazo de 5 dias vale para o **cliente**. Admin e técnico reabrem a qualquer
momento: quando o encerramento foi engano da própria equipe, um prazo vencido
só obrigaria a abrir chamado novo e perder o histórico.

Reabrir **recalcula o prazo de resolução** e limpa a marca de SLA violado. Sem
isso o chamado voltaria já vencido, com o cronômetro parado no dia em que foi
resolvido. A violação original continua registrada no histórico.

### Relação com o SLA

Os dois relógios **não se cruzam**: o SLA conta da abertura até a resolução, e
os prazos acima só começam depois disso. `check_breaches` ignora os status
terminais, então nada continua vencendo depois de resolvido, e o fechamento
automático apenas troca um status terminal por outro.

Dois pontos onde a separação precisou ser feita à mão:

- **Tempo médio de resolução** passou a contar até `resolved_at`, não até
  `closed_at`. Como o fechamento automático reescreve o `closed_at` três dias
  úteis depois, a métrica passaria a medir a demora do cliente em responder e
  não o trabalho da equipe — todo chamado fechado pela rotina apareceria com
  ~27 h a mais.
- **Reabrir zera o `sla_total_paused_ms`.** Esse acumulado existe para esticar o
  prazo do ciclo em que a pausa aconteceu; como a reabertura já dá um prazo novo
  contado a partir do momento, mantê-lo daria ao ciclo novo horas de bônus que
  ninguém esperou.

A marca de **primeira resposta vencida** sobrevive à reabertura de propósito:
ela se refere ao primeiro atendimento, que de fato aconteceu (ou atrasou) uma
vez só.

**O prazo de resposta, porém, não é renovado — só o de resolução.** É preciso
dizer isso em voz alta porque o changelog da v1.4.0 anunciou mais do que o
código entrega: "reabrir um chamado devolve um prazo de atendimento novo, em
vez de trazê-lo de volta já vencido". Vale para a resolução; o
`sla_response_due_at` continua sendo o do ciclo original.

Até a v1.8.0 isso aparecia na tela como mentira: o chamado reaberto exibia
"Resposta: Vencido" para sempre, mesmo tendo sido respondido dentro do prazo no
ciclo anterior. O chip lia o relógio para escrever o texto e a flag do backend
para escolher a cor — daí o resultado contraditório de um selo âmbar (sem
violação) escrito "Vencido". Hoje o chamado que já teve resposta exibe
**"Respondido"**, sem contagem, porque aquele relógio não corre mais.

O conserto foi de **exibição**, e é honesto sobre o que não resolve: o ciclo
novo continua sem prazo de resposta próprio. Dar um exigiria decidir o destino
da primeira resposta do ciclo anterior, e apagá-la destruiria o único registro
que existe dela — o desenho provável é um campo por ciclo, não um por chamado.
Está na fila como melhoria futura, não como bug.

### Por que a rotina roda dentro da API

**É deliberado, não uma etapa que faltou.** O ambiente sobe um processo só — o
`start.sh` executa apenas o uvicorn — e uma rotina de hora em hora não paga o
custo de operar um segundo serviço: mais um container no EasyPanel, mais uma
fila para observar e mais um lugar de onde uma falha silenciosa pode vir.

Até 25/08/2026 o repositório tinha um pacote `app/worker/` com Celery e três
tarefas de exemplo que **nada executava** — nenhuma chamada `.delay()`, nenhum
worker, nenhum beat. Foi removido: um esqueleto que devolve `{"status":
"queued"}` sem fazer nada é pior que ausência, porque alguém acaba chamando
acreditando que funciona.

A rotina roda como task do próprio processo da API
(`backend/app/services/ticket_lifecycle.py`), a cada
`TICKET_AUTO_CLOSE_INTERVAL_SECONDS` (padrão 1 h). Como o uvicorn sobe com
`--workers 2`, um **lock no Redis** garante que só um processo trabalha por
rodada; sem Redis a rodada é pulada, porque fechar o mesmo chamado duas vezes
duplicaria histórico e notificação. Definir o intervalo como `0` desliga a
rotina.

O fechamento automático fica no histórico **sem autor** (`user_id` nulo,
exibido como "Sistema"). Apontá-lo para um administrador qualquer registraria
uma ação que ninguém praticou.

## Política de notificações

Registrado em **24/09/2026** (Fase 1 da frente de notificações).

Dois canais, e eles **não** são simétricos: o sininho é barato e chega a quem
está dentro do sistema; o e-mail alcança quem não está, e por isso é o que gera
ruído quando sobra. Toda a política abaixo é a consequência disso.

### Quem recebe o quê

| Evento | Cliente autor | Técnico atribuído | Equipe inteira | E-mail |
|---|---|---|---|---|
| **Chamado aberto** | 🔔 sininho | — | 🔔 **sininho** | ✉️ **autor e equipe** |
| Triagem / escalada da Helô | — | — | 🔔 sininho | ❌ |
| Nova mensagem no chat | 🔔 | 🔔 | — | ❌ |
| Atribuição | — | 🔔 | — | ❌ (staff) |
| Mudança de status | 🔔 | — | — | ✉️ cliente |
| Resolução | 🔔 | — | — | ✉️ cliente |
| Reabertura | 🔔 | 🔔 | — | ✉️ cliente · ❌ staff |
| Extensão de prazo | 🔔 | — | — | ✉️ cliente |
| Cancelamento | 🔔 | — | — | ✉️ cliente |
| Fechamento automático | 🔔 | — | — | ✉️ cliente |
| Pesquisa de satisfação | 🔔 | — | — | ❌ (só in-app) |

**Só o chamado novo mudou de audiência nesta fase.** Todos os outros eventos
continuam alcançando exatamente quem alcançavam.

### A audiência operacional tem uma definição só

`audiencia_operacional()` em `app/services/notifications.py`:

```
role IN (admin, technician) AND status == active
```

Ela nasceu inline no `_avisa_equipe_da_helo`, que era o único lugar do sistema
que respondia "quem é a equipe". Com o chamado novo avisando a equipe também,
aquela consulta viraria a segunda — e duas consultas com a mesma intenção
divergem no primeiro técnico desativado, sem nada avisando.

**`status == active`, e não `!= inactive`.** Existe um terceiro valor,
`anonymized`, que é conta apagada pela LGPD: o e-mail dela não é mais de
ninguém, e a comparação por desigualdade a deixaria entrar.

O filtro é uma cláusula `WHERE`, então ele é provado contra **PostgreSQL de
verdade** em `tests/test_audiencia_operacional_postgres.py`. Mock não executa
`WHERE` — a lição está registrada no cabeçalho de
`tests/test_helo_base_postgres.py`, e foi paga uma vez aqui.

### Dedup por usuário, e a confirmação do autor vence

Um técnico que abre chamado em nome de um cliente cai nas duas regras: é o autor
e é da equipe. Ele recebe **uma** notificação e **um** e-mail, e o que fica é a
confirmação do autor — `"Seu ticket foi registrado com o protocolo X"`.

Se a audiência vencesse, o autor-staff perderia a própria confirmação e
receberia no lugar um aviso escrito para outra pessoa. Deixar de mandar o aviso
operacional para quem acabou de abrir o chamado não perde informação nenhuma.

A exclusão é **explícita** (`exclude_user_ids`), e não efeito colateral da ordem
das chamadas: inverter as duas linhas do `create_ticket` dá o mesmo resultado.

### O e-mail para staff: o filtro de 04/09 continua valendo

Em 04/09/2026 a equipe pediu para desligar o e-mail de notificação para técnico
e administrador — quem passa o dia dentro do sistema já vê o sininho, e o e-mail
virava ruído. Esse filtro (`_SEM_EMAIL_POR_PAPEL`) **não foi revogado**.

O que entrou em 24/09 é uma exceção **por tipo**, nomeada e com um membro:

```python
_EMAIL_PARA_STAFF = frozenset({NotificationType.ticket_created})
```

Chamado novo é o único evento que dispara o atendimento e acontece **uma vez**
por chamado. O ruído que motivou o pedido de setembro vinha de eventos que se
repetem no mesmo chamado — atribuição e reabertura —, e esses continuam sem
e-mail para staff.

É o espelho do `_IN_APP_ONLY`: um conjunto de tipos que silencia o e-mail, outro
que o destrava.

Em 25/09/2026 a Fase 2A acrescentou o segundo membro, exatamente como estava
previsto — um nome no conjunto, não condição espalhada por router:

```python
_EMAIL_PARA_STAFF = frozenset({NotificationType.ticket_created, NotificationType.sla_warning})
```

E o critério de admissão foi honrado por **construção**, não por sorte: o aviso
de SLA só sai para quem consegue inserir a linha de `sla_alert_events`, sob
índice único. Sem essa garantia ele seria justamente o evento repetido que o
filtro de 04/09 existe para barrar — por isso a deduplicação e esta linha são o
mesmo assunto, e não dois.

`sla_breached` **não** entrou: ele continua sem produtor nenhum.

## Aviso de SLA próximo do vencimento (Fase 2A, 25/09/2026)

`SLAConfig.warning_threshold` está no schema desde a primeira migration, é
editável por prioridade, e a `SlaConfigPage` afirmava ao administrador que "o
alerta dispara quando o percentual do tempo já consumido atingir o limiar".
**Nada disparava.** Nenhum caminho de produção lia o campo. A Fase 2A não
acrescentou funcionalidade: ela cumpriu uma promessa que a interface já fazia.

### A semântica do limiar estava decidida — e em dois lugares

Percentual do tempo **consumido**, inteiro, de 1 a 100. Não é resto, não é
minutos, não é fração. Dois lugares independentes já afirmavam isso e
concordavam: o texto de ajuda da tela de SLA, e a fórmula da barra do cartão em
`TicketListPage`. O worker adotou a mesma, consumindo
`prazo_efetivo_de_resolucao` e `business_minutes_between` — sem espelho próprio.

⚠️ As fixtures de `frontend/src/test/services/slaService.test.ts` usam `0.8` e
`0.5`, como se fosse fração. É mock, não afeta produção, mas codifica a escala
errada. Há `CheckConstraint` no banco (`1..100`) e teste nomeado contra essa
confusão.

### O que a identidade do evento decide

```
(ticket_id, alert_kind, effective_due_at, warning_threshold)
```

`effective_due_at` carrega sozinho pausa acumulada, extensão e ciclo de
reabertura, porque é a saída de `prazo_efetivo_de_resolucao`. Por isso
`priority`, `reopen_count` e `extension_total_min` são gravados como
**auditoria** e ficam **fora** da chave: incluir qualquer um deles criaria uma
segunda resposta para "é o mesmo aviso?".

A consequência é deliberada: mesmo prazo e mesmo limiar nunca repetem; tudo o
que **muda** o prazo — prorrogar, reabrir, retomar de uma pausa, trocar a
prioridade — ou o limiar habilita um aviso novo.

### Por que tabela, e não booleano, `notifications` ou Redis

Booleano no ticket responderia a primeira vez e mentiria nas outras: "já avisei"
não é pergunta de sim/não, é pergunta sobre qual prazo e qual limiar.

`notifications` guarda o **efeito**, uma linha por pessoa, com `CASCADE` para
`users` — excluir o último destinatário apagaria a prova e a rodada seguinte
reenviaria.

Redis é **lock**, nunca memória de evento: chave que expira não pode ser a prova
de que um aviso foi dado. O precedente da casa para "o worker já fez isto" é
estado persistido próprio, duas vezes: `helo_indexacoes` na indexação, e a
transição de status no fechamento automático.

### Pausado não avisa, e vencido não avisa

A pausa **em curso** não entra no prazo efetivo (dívida antiga, registrada
acima e não corrigida aqui), então um chamado parado continua se aproximando do
vencimento. Avisar a equipe sobre um chamado que ela não pode tocar porque
espera o cliente é o começo do ruído que derruba o canal.

Passado o prazo o assunto é violação, não aviso. `sla_warning` sobre algo que já
venceu diria "está chegando" sobre o que chegou.

### O intervalo é 300 s, e não os 3600 s do fechamento automático

O limiar é um **ponto** na linha do prazo, não uma condição que fica de pé
esperando ser notada. Com 3600 s, um prazo de resposta de 30 minutos do nível
crítico atravessaria 80% e venceria dentro da mesma janela, e o aviso nunca
sairia.

**O cliente nunca é filtrado**, em nenhum tipo. Há duas contraprovas de teste
justamente porque alargar o filtro silenciaria quem está do lado de fora.

### O assunto do e-mail não é o título do sininho

```
sininho:  Novo chamado
assunto:  [HelpHS] Novo chamado HS-2026-0042 — Impressora sem conexão
```

As duas coisas passaram a querer textos diferentes: o sininho já mostra o tipo
num selo e tem largura de dropdown; o assunto precisa dizer protocolo e título
para ser reconhecível numa lista de caixa de entrada. Quem tem um assunto melhor
a dizer passa `email_subject` ao `notify`; sem ele, o fallback é
`[HelpHS] <título> — <protocolo>`.

Todo assunto leva o prefixo **`[HelpHS]`**, e o separador é **travessão** — o
ponto médio some em fonte estreita de lista de caixa.

### Vocabulário misto, conhecido e aceito

O aviso da equipe diz "chamado"; a confirmação do autor continua dizendo
"ticket". O aviso é texto novo, a confirmação é texto existente, e renomear os
dez textos visíveis ao cliente é refatoração editorial que ficou **fora** desta
frente por decisão de 24/09/2026.

### ⚠️ Dívida: `ticket_updated` agrega mais de um evento

`NotificationType.ticket_updated` é usado pela **reabertura** e pela **mudança
de status**. Não dá para dar políticas de e-mail diferentes a esses dois eventos
olhando só o `NotificationType`.

Aceito nesta fase porque é o comportamento atual e a Fase 1 não muda a semântica
do enum. Se um dia a distinção fizer falta, o caminho a avaliar **primeiro** é um
discriminador explícito no `data` ou uma camada de evento mais específica — não
expandir o enum, que é nativo do Postgres e custa `ALTER TYPE` em migration que
roda sozinha no boot.

### ⚠️ A Fase 1 NÃO garante entrega

Não há retry, não há fila, não há outbox. O envio continua sendo
`asyncio.create_task` depois do commit, e `email_sent` continua nascendo `False`
e nunca sendo atualizado.

O que isso significa na prática: **SMTP fora do ar ou reinício da API entre o
commit e o envio perdem o e-mail**, e o único rastro é uma linha de log. A
notificação do sininho sobrevive, porque ela é transacional com o fato que a
gerou. Durabilidade é a Fase 3.

### Otimização futura: o peso da logo

A logo por `cid:` acrescenta ~100 KB por mensagem MIME (PNG de 75 KB em base64).
Com quinze técnicos, um chamado novo gera ~1,5 MB de tráfego SMTP. Não bloqueia
nada — e o corte de ~102 KB do Gmail **não** se aplica, porque o anexo é parte
MIME separada e não conta no tamanho do HTML.

Uma frente futura pode criar uma variante otimizada exclusivamente para e-mail.
Deliberadamente **não** feito aqui: redimensionar ou recomprimir a marca é
decisão de identidade visual, não de engenharia de entrega.

## Pesquisa de satisfação (CSAT)

**Escala de 1 a 10.**

A coleta sempre foi 1–10, mas relatórios, gráficos e o filtro da API assumiam
1–5. O efeito colateral era grave: a distribuição do relatório ia de 1 a 5, então
**toda avaliação de 6 a 10 desaparecia do gráfico**. Unificado na v1.1.0.

A meta exibida no gráfico de tendência é 8.0 (era 4.0 na escala antiga).

### O convite é só no sininho

Disparado automaticamente quando o chamado entra em **Resolvido** — pelos dois
caminhos, "Concluir ticket" e "Alterar status". Passar para Fechado não dispara
nada: o convite já foi feito.

**Não sai e-mail** (`_IN_APP_ONLY` em `app/services/notifications.py`). A
avaliação é respondida no painel abaixo do chat, dentro do chamado; o e-mail
apenas pedia que a pessoa entrasse no sistema. Decidido em 07/08/2026.

Até então o caminho do "Alterar status" mandava **dois** e-mails — o da
notificação e outro escrito à mão logo abaixo.

Quem avalia é só **o cliente que abriu o chamado**, uma vez por chamado, sem
prazo para responder e sem poder alterar depois. Admin e técnico não veem o
painel.

### Duas perguntas, um envio

| Pergunta | Campo | Escala |
|---|---|---|
| Como você avalia o atendimento? | `rating` | 1 a 10 |
| O quanto você recomendaria nossa empresa? | `recommend_rating` | 1 a 10 |

As duas são **obrigatórias no formulário** — são dois cliques e o dado só serve
se vier completo. Na API a segunda é opcional, para não invalidar integrações
que enviem apenas a nota do atendimento.

`recommend_rating` é **nulo nas avaliações enviadas antes da pergunta existir**,
e continua assim: não há como recuperar a resposta de quem já avaliou. As médias
usam `AVG`, que ignora nulos — tratá-los como zero derrubaria o número sem
ninguém ter dado zero.

A média aparece no relatório, no card **Recomendação**, ao lado da Média CSAT.

> Não é o NPS de mercado. O NPS usa escala 0–10 e um cálculo próprio
> (% promotores − % detratores); aqui a escala é 1–10 e o que se mostra é a
> média simples, como foi pedido. Se um dia o número precisar ser comparável
> com o de fora, a escala precisa começar em 0.

## Permissões

### Qual é a autoridade sobre "de qual empresa é este cliente"

> **`companies.id` é a única autoridade.** O vínculo vive em
> `users.company_id`, e é ele que vale para escopo, permissão e unicidade.
>
> **`users.cnpj` nunca serve para isso.** É dado de onboarding autodeclarado:
> serve para exibir, sugerir e casar candidatos a vínculo — nada além.

A regra existe porque o sistema tem **dois** campos que parecem responder à
mesma pergunta, e escolher o errado tem consequência de segurança. O
`users.cnpj` é digitado pelo próprio cliente; o servidor apenas conta 14
dígitos, e quem confere os dígitos verificadores é o **frontend** — ou seja, é
validação que o cliente controla. Elegê-lo como chave de escopo deixaria o
usuário escolher em qual grupo de dados ele cai.

Consequência prática já sentida: a unicidade de número de série ficou **por
dono** e não por empresa (ver "Equipamentos do chamado"). Com esta regra
escrita, aquilo deixa de parecer contorno e passa a ser o que é — a decisão
correta, dado que não existe chave de empresa confiável hoje.

Duas coisas que decorrem disso e valem saber:

- **Cliente sem `company_id` é o caso comum, não a exceção.** Quem se
  autocadastrou e fez onboarding tem CNPJ preenchido e vínculo nulo. Qualquer
  regra futura "por empresa" precisa dizer, em voz alta, o que acontece com
  `company_id IS NULL` — provavelmente cair no escopo individual, nunca num
  balde comum.
- **Excluir uma empresa desvincula os clientes em silêncio** (`ON DELETE SET
  NULL`), sem aviso na tela e sem contagem do que será afetado.

O caminho para reconciliar os dois campos — normalizar as duas pontas, fechar o
laço das sugestões e só então criar regras por empresa — está levantado em
`docs/superpowers/specs/2026-08-24-duas-fontes-de-verdade-empresa.md`, com as
consultas de diagnóstico prontas.

### Entre técnicos — sem barreira

Qualquer técnico pode **atender, responder e concluir qualquer chamado**, mesmo
sem ser o responsável. Havia uma trava exigindo atribuição em três pontos
(concluir, chat REST e chat WebSocket), removida em 05/08/2026 a pedido do
cliente.

A trava não se sustentava: o mesmo técnico chegava a "Resolvido" pelo **Alterar
status**, que nunca exigiu atribuição. Bloqueava o caminho principal e deixava o
alternativo aberto.

> Se um dia isso virar problema de organização interna, o caminho do meio é a
> auto-atribuição: quem age num chamado sem responsável vira o responsável.

### A recusa não diz que o recurso existe

Quando um **cliente** pede um chamado, um equipamento ou um anexo que não é
dele, a resposta é **404 com o mesmo texto de um id que não existe** — nunca
403. O 403 é meia resposta a mais do que ele deveria conseguir: confirma que
aquele id existe no sistema, e quem só tem uma sequência de ids consegue mapear
o que há na base sem nunca ver o conteúdo.

Isso vale hoje em doze pontos — chamados, histórico, observação, reabertura,
anexos, chat (inclusive no código de fechamento do WebSocket) e avaliação — e
nos equipamentos. Há teste de paridade em cada arquivo comparando a recusa de
"alheio" com a de "inexistente": se alguém mudar a mensagem de um lado só, a
suíte fica vermelha.

**Para a equipe continua 403**, e é deliberado: admin e técnico já listam todos
os chamados, então esconder existência deles não fecharia nada — só mandaria um
administrador caçar um bug que não existe. Recusa de *papel* (o que
`authorize()` faz antes de buscar o recurso) também continua 403, porque
dispara antes de o id ser consultado e não diz nada sobre existência.

### Base de conhecimento

- **Admin e técnico** excluem qualquer comentário; cliente exclui só os próprios.
- **Cliente** vê a aba Base de Conhecimento dentro do próprio chamado. A API
  valida que ele só recebe sugestões de ticket que ele mesmo criou.
- O botão "Enviar ao cliente via chat" só aparece para a equipe.

## Base de conhecimento por produto

**Artigo sem nenhum produto vinculado vale para TODOS os produtos.**

Essa é a regra central. Ela existe para que artigos genéricos ("Como abrir um
chamado", "Política de garantia") não precisem apontar para um produto
arbitrário — e é o que manteve válidos, sem backfill, todos os artigos criados
antes da tabela `kb_article_products`.

No formulário isso aparece como a caixa **"Vale para todos os produtos"**. O
campo é obrigatório no sentido de que o técnico precisa decidir: ou marca a
caixa, ou escolhe pelo menos um produto.

### Como o artigo chega ao cliente no chamado

As sugestões buscam em camadas, da mais específica para a mais ampla, até
completar o limite (5 artigos):

| Ordem | Critério |
|---|---|
| 1 | produto do ticket **e** mesma categoria |
| 2 | produto do ticket, em qualquer categoria |
| 3 | mesma categoria, em qualquer produto (aqui entram os "todos os produtos") |
| 4 | palavra-chave do título do chamado |

Basta **produto OU categoria** casar. O produto vem do campo Produto do ticket;
se estiver vazio, do equipamento escolhido pelo cliente.

Na **listagem** da base (fora do chamado) não há restrição: todos veem a base
inteira, e produto e categoria são apenas filtros.

## Acesso: confirmação de e-mail e recuperação de senha

### A confirmação é adotada de propósito, não deduzida

**Exigir confirmação de e-mail depende de duas coisas ao mesmo tempo: a flag
`EMAIL_VERIFICATION_ENABLED` (padrão `false`) e SMTP configurado.** Preencher
as variáveis de SMTP sozinho não liga nada; ligar a flag sem SMTP **recusa o
boot** em produção, ao lado das validações de `CORS_ORIGINS` e `FRONTEND_URL`.

A regra anterior era inferência — bastava `SMTP_FROM_EMAIL` ou `SMTP_USER`
estarem preenchidos. A intenção era boa (publicar o código antes das
credenciais), mas ela quebrou a produção em 19/08/2026: o `.env.example` **vem
com as duas variáveis preenchidas**, com senha `CHANGE_ME`. Quem semeou o
painel a partir dele ligou a confirmação sem ter SMTP funcional — as contas
nasciam não verificadas, o e-mail nunca saía, e **ninguém conseguia entrar**,
lendo "Confirme seu e-mail para ativar a conta" sem nunca ter recebido e-mail
nenhum.

A lição que vale além deste caso: **configuração que muda comportamento
sensível precisa ser afirmada, nunca adivinhada a partir de outro campo estar
preenchido**. Uma variável preenchida diz que alguém digitou algo ali, não que
a funcionalidade está pronta para uso.

Quando o SMTP de produção entrar, ligar a confirmação é mudar a flag no painel
— e é o mesmo gatilho da resposta neutra no cadastro (ver "Pendências
conhecidas").

### O envio sai pelo Resend, não pelo Microsoft 365 da empresa

A empresa paga Microsoft 365 e a pergunta é inevitável: por que mais um
fornecedor para mandar e-mail? Porque **o destinatário destes e-mails é o
cliente, fora do tenant** — e o Exchange Online é feito para e-mail humano,
não para disparo de aplicação.

O que pesou, em ordem:

- **Visibilidade.** "O cliente diz que não recebeu o link" é a ocorrência
  número um em recuperação de senha. O Resend responde isso numa tela
  (`delivered`, `bounced`, `complained`); no Exchange, a investigação é pelo
  message trace, que dá bem mais trabalho e guarda menos tempo.
- **Bounce e supressão.** Exchange Online não entrega webhook de bounce nem
  mantém lista de supressão. Sem isso, endereço morto continua sendo tentado.
- **Reputação separada.** O disparo automático sai de
  `mail.healthsafetytech.com`, um subdomínio. Se um cliente marcar o e-mail
  automático como spam, quem sofre é o subdomínio — não o domínio que a
  empresa usa para falar com cliente todo dia.
- **Prazo do Basic Auth.** SMTP AUTH com usuário e senha no Exchange Online
  passa a vir desabilitado por padrão no fim de dez/2026. Funcionaria hoje,
  mas viraria manutenção com data marcada.

Duas alternativas foram descartadas por motivo concreto, e vale registrar para
não serem re-propostas: o **HVE (High Volume Email)** seria o produto certo —
conta de aplicação, sem consumir licença de caixa — mas **só envia para dentro
do tenant** desde jun/2025. E o **Azure Communication Services Email** é
tecnicamente equivalente ao Resend, inclusive com SMTP (`smtp.azurecomm.net`),
com a vantagem de cair na mesma fatura MCA da Microsoft; perdeu por exigir
subscription Azure, app registration e IAM para chegar no mesmo lugar. Se um
dia a exigência for "nada fora da Microsoft", é para ele que se muda — não
para o Exchange.

**O DNS do domínio não foi tocado.** Os registros do M365 (MX, SPF `-all`,
DKIM) continuam no domínio raiz exatamente como estavam; tudo do Resend
(DKIM, SPF e o MX de bounce) vive sob `mail.healthsafetytech.com`, que era
espaço vazio. Foi decisão de projeto, não acaso: mexer no SPF da raiz para
acomodar um segundo remetente é o tipo de edição que derruba o e-mail
corporativo inteiro se sair errada.

Para conferir a configuração sem subir a aplicação, existe
`backend/scripts/testa_smtp.py`.

### Fluxo

Cadastro completo → conta criada bloqueada → e-mail com link → clique → conta
ativa → login → onboarding da empresa.

Quem tenta entrar antes de confirmar recebe **o motivo real** ("Confirme seu
e-mail...") e um botão para reenviar o link — não o genérico "e-mail ou senha
incorretos", que deixaria a pessoa tentando a senha à toa.

### Links

São JWT assinados, sem tabela e sem limpeza periódica:

| Link | Validade | Observação |
|---|---|---|
| Confirmação de cadastro | 24 h | `EMAIL_VERIFICATION_TOKEN_HOURS` |
| Redefinição de senha | 1 h | **uso único** |

O **uso único** funciona sem guardar estado: o token carrega uma impressão
digital da senha vigente, conferida contra a senha atual do usuário. Trocada a
senha, o link morre — inclusive o que acabou de ser usado. Sem isso, um link
esquecido na caixa de e-mail abriria a conta meses depois.

Cada token tem um tipo (`email_verify` ou `password_reset`) e não serve para
outra finalidade — um token de login também não vira link de arquivo.

### Por que as mensagens são vagas de propósito

"Esqueci a senha" e "reenviar confirmação" **sempre** respondem *"Se este e-mail
estiver cadastrado, você receberá..."*, mesmo quando o e-mail não existe.

Parece ruim para o usuário, mas responder "e-mail não encontrado" permitiria
que qualquer pessoa descobrisse quais e-mails têm conta no sistema, testando
endereços um a um.

Uma exceção deliberada: **redefinir a senha confirma o e-mail junto**. Quem
abriu o link provou ser dono da caixa.

### O admin inicial não nasce de seed em produção

`start.sh` roda `python -m app.seeds` **a cada boot do container**, entre a
migration e o uvicorn — inclusive em produção. Enquanto a senha do admin esteve
escrita no código, todo deploy criava (ou recriava, se alguém apagasse a linha)
um administrador ativo com credencial publicada no repositório.

Duas defesas, independentes de propósito:

1. **`APP_ENV` de produção não cria a conta.**
2. **Sem `SEED_ADMIN_PASSWORD` não cria a conta** — não há literal para cair.

A segunda não é redundância: `app_env` tem default `development`, então a
primeira falha **aberta** se a variável faltar ou vier digitada errada. Senha
ausente é o que segura esse caso, e é por isso que ela é a correção — a guarda
de ambiente é só a defesa.

Nenhuma das duas levanta exceção. Isso separa esta regra da do módulo de seeds
do Playwright, que **deve** falhar ruidosamente em produção porque nada o chama
lá: `seed_admin` está no caminho do boot, sob `set -e`, e levantar trocaria um
vazamento de credencial por uma indisponibilidade. A recusa vai para o log e a
execução segue — produto e configuração de SLA continuam sendo semeados
normalmente, porque são catálogo, não credencial.

O seed continua idempotente, e isso protege quem já trocou a senha em produção:
com a linha presente, nada é tocado. Em contrapartida, **apagar o usuário não é
uma forma de reiniciá-lo**: sem a variável, ele simplesmente não volta.

## Segundo fator (TOTP)

Vale **só para `admin` e `technician`**. Cliente não tem o recurso, e as rotas
respondem 403 para ele — não é uma tela escondida, é um caminho que não existe.
Adesão é individual e voluntária: ninguém é obrigado, e uma conta sem MFA
continua entrando exatamente como sempre entrou.

### O segredo é cifrado, não hasheado — e a diferença não é estilo

Conferir um código TOTP exige **recalculá-lo a partir do segredo** a cada
tentativa. Um hash tornaria a verificação impossível: não há o que comparar.

O que protege a coluna, então, é a chave da cifra morar **fora do banco**, em
`MFA_SECRET_ENCRYPTION_KEY`. Um dump da tabela, sozinho, não gera código nenhum.

**Não existe chave default, e não há nenhuma no repositório.** Uma chave
versionada cifraria e decifraria sem erro, o sistema pareceria funcionar, e o
segredo estaria protegido contra exatamente ninguém — o repositório é justamente
onde ela estaria. Sem a variável, o recurso se declara indisponível e o login
segue intocado; nenhum boot é derrubado por causa dela.

⚠️ **Trocar a chave torna ilegíveis os segredos já cadastrados.** Quem tiver MFA
ativo precisa cadastrar de novo — e, até lá, não entra. É o preço de a chave
morar fora do banco, e é consciente.

### Cadastrar não liga

São dois passos: `/auth/mfa/setup` gera o segredo e o guarda cifrado;
`/auth/mfa/activate` só liga depois que um código prova que o aplicativo pareou.

Ligar no cadastro trancaria quem lesse o QR errado — e a conta trancada é o
medo que faz as pessoas não ativarem o recurso.

O banco recusa o par impossível: `CHECK (mfa_enabled = false OR mfa_secret IS
NOT NULL)`. A regra caberia só no código, e caberia bem até o dia em que um
caminho de escrita novo esquecesse dela.

### O login vira dois tempos, e 2xx sempre significa sessão

Com o segundo fator ativo, `/auth/login` responde **403** com um desafio, e não
200 com campos vazios. A regra que isso preserva é: **qualquer 2xx no
`/auth/login` significa que a sessão existe**.

Não é preciosismo. Com um 200 de desafio, um consumidor que gravasse
`access_token`/`refresh_token` sem conferir gravaria `undefined` — que foi
exatamente o defeito corrigido no interceptor do front em 26/08. O status
diferente torna esse erro **impossível**, em vez de improvável.

O token do desafio é **opaco**, não um sexto tipo de JWT: um JWT novo
compartilharia a chave RS256 e o `iss` dos outros cinco, e a separação passaria
a depender de todo consumidor futuro de `decode_token` lembrar de conferir o
claim `type`.

### Ativar e desligar despejam as sessões abertas

`/auth/refresh` confere tipo, correspondência e status da conta — **nunca
`mfa_enabled`**. Sem apagar o refresh na ativação, quem já tivesse a senha e uma
sessão aberta seguiria renovando access tokens por até sete dias sem jamais ver
um código: o recurso falharia exatamente no caso em que alguém o liga por
desconfiar que foi comprometido.

⚠️ Isso **não** invalida os access tokens já emitidos — ver a dívida com gatilho
correspondente.

### Nada falha para o lado de deixar entrar

Redis fora do ar, segredo ilegível, conta desativada entre a senha e o código:
tudo vira recusa. Um segundo fator que se desliga sozinho quando uma dependência
cai não é um segundo fator — e a dependência cai justamente quando alguém está
atacando.

### Perdeu o celular

**Não há códigos de recuperação**, por decisão de escopo: com cinco pessoas de
staff e o TI dentro de casa, um script operado por nós cobre o caso sem inventar
mais uma superfície de credencial.

A saída é `backend/scripts/desliga_mfa.py`, rodado à mão, com dry-run por padrão
e rastro em `audit_logs`. A API **não tem** esse caminho, e não deve ter:
`DELETE /auth/mfa` exige a senha *e* uma sessão — nenhuma das duas quem está
trancado fora possui — e um endpoint de admin para desligar o fator de terceiros
seria uma forma de remover a proteção de outra pessoa.

⚠️ **`redefine_senha.py` não resolve esse caso.** Com `mfa_enabled = true`, a
senha nova não destranca nada: o login segue pedindo o código depois dela. Para
"perdi o celular", é o `desliga_mfa`. Para "perdi os dois", os dois, nessa ordem.

## Chat em mais de um worker

O `ConnectionManager` guarda as salas na memória **do processo**: um dicionário
de `ticket_id` para os WebSockets abertos ali. Isso é rápido e simples, e tem uma
consequência que não aparece sozinha.

### Por que a falha sem backplane era silenciosa

Com dois workers, duas pessoas no mesmo chamado caem em processos diferentes com
probabilidade alta. Nenhuma das duas recebe erro: as conexões ficam abertas, as
mensagens continuam sendo **gravadas corretamente no banco**, e só o tempo real
some. Elas descobrem ao recarregar a página, e o sintoma se confunde com problema
de rede do usuário.

É o pior formato de falha que este sistema tem: invisível para o monitoramento,
visível só para o cliente, e difícil de reproduzir.

### O desenho

Cada worker assina o canal `helphs:chat` no Redis e reemite o que chega para os
sockets que tem em memória. O `broadcast` entrega **local primeiro** e publica
depois.

Quatro decisões, e cada uma tem um teste que a sustenta:

**A origem é atributo de instância, não global de módulo.** É o carimbo que
impede o worker de entregar duas vezes a própria mensagem — o Redis devolve a
publicação a todos os inscritos, inclusive a quem publicou. Com a origem em
variável de módulo, dois `ConnectionManager` do mesmo processo dividiriam o
carimbo, a supressão de eco descartaria a mensagem que deveria atravessar, e **o
teste de entrega entre processos não teria como ser escrito**. Um desenho
intestável exatamente na propriedade que o justifica.

**Entrega local antes do publish.** Publicar primeiro faria a latência do Redis
atrasar o socket que está no mesmo processo — o caso mais comum, ainda mais com
um worker só. O teste afirma a ordem, não só o resultado.

**`publicar` nunca levanta.** A régua é que o chat hoje não usa Redis nenhum:
uma dependência nova não pode piorar a disponibilidade do que já funciona. Com o
Redis fora, a entrega local acontece igual e o chat fica exatamente como é hoje.

**Canal único, com o chamado dentro do envelope.** Canal por chamado obrigaria
`SUBSCRIBE`/`UNSUBSCRIBE` dentro do `connect`/`disconnect` — que são síncronos —,
metendo chamada de rede no aperto de mão do WebSocket, que hoje não depende do
Redis. O custo do canal único é cada worker decodificar um JSON pequeno e
descartar o que não é seu.

**Log só na transição.** Um aviso quando a assinatura cai, um quando volta. Uma
linha por tentativa, a cada poucos segundos, transformaria uma queda de Redis
numa inundação — e o log que deveria denunciar o problema viraria o problema.

### Por que o `--workers 1` continua

Não é mais impedimento técnico, é **estágio**. Com um worker o assinante já sobe,
publica e recebe as próprias mensagens de volta, descartando-as pelo carimbo: ele
fica exercitado em produção sem risco nenhum. O readiness reporta
`chat_backplane.assinado` — reportado, não usado para derrubar, mesma regra do
carimbo do auto-close.

Depois de alguns dias com a assinatura de pé, subir para dois vira trocar um
número no `start.sh`, com evidência atrás em vez de esperança.

⚠️ **O que o backplane não resolve** está na tabela de dívidas com gatilho: o
pub/sub não guarda nada, então mensagem publicada durante uma reassinatura se
perde para aquele worker.

## Equipamentos do chamado

**Um chamado aceita vários equipamentos** (teto de 20). Antes era um só, e o
cliente com três aparelhos do mesmo produto com o mesmo defeito precisava abrir
três chamados ou citar os números de série na descrição — onde a busca não
alcança.

A coluna `tickets.equipment_id` **deixou de existir**; o vínculo vive na tabela
`ticket_equipments`. Manter as duas criaria duas verdades sobre a mesma
informação.

Regras que vieram junto:

- **O cliente só vincula equipamento que é dele.** Sem essa checagem, mandar
  ids aleatórios para a API devolveria na resposta o nome e o número de série
  de aparelhos de outras empresas.
- **Trocar o produto no formulário limpa a seleção** — a lista mostra os
  aparelhos daquele produto, e manter os antigos deixaria no chamado
  equipamento que sumiu da tela.
- **A busca acha o chamado por qualquer um dos seriais**, não só pelo primeiro.
- **As sugestões da base consideram todos os produtos envolvidos.** Um chamado
  com aparelhos de produtos diferentes recebe artigos de todos; filtrar por um
  só esconderia o artigo do segundo produto.
- Sem produto informado, o chamado herda o do **primeiro equipamento** — é o
  que o cliente responderia se perguntassem de qual produto é o chamado.

Na edição, omitir `equipment_ids` mantém os equipamentos atuais; mandar lista
vazia desvincula todos.

### Quem enxerga qual equipamento

**O cliente vê apenas os equipamentos que são dele** — na listagem por produto
e na consulta por id. Equipamento **sem dono também é negado** a ele (*fail
closed*), pelo mesmo critério de "Meus equipamentos", que só devolve o que é
seu. A equipe (admin e técnico) continua vendo o parque inteiro, porque precisa
para dar suporte.

Antes disso, qualquer pessoa autenticada lia o **número de série** de qualquer
cliente — dado de cliente exposto entre empresas concorrentes.

### O dono do equipamento

Equipamento cadastrado pela tela de Produtos nascia **órfão**: o formulário não
tinha o campo, e nenhuma API permitia atribuir dono depois. O resultado era um
aparelho permanentemente invisível para o cliente real — que não conseguia nem
recadastrá-lo, porque o número de série já estava tomado.

Hoje o cadastro e a edição têm o seletor de dono, com busca pelo nome do
cliente, e a listagem tem um **filtro de equipamentos sem dono** para achar os
órfãos que ficaram. O campo existe só nos endpoints da equipe: nos
`/equipment/my*` ele não é aceito, senão o cliente escolheria de quem é o
aparelho.

### Número de série é único por dono, não no sistema inteiro

**Dois clientes diferentes podem ter o mesmo número de série cadastrado.** Até
a v1.8.0 a unicidade era global, o que produzia dois problemas: um cliente era
impedido de cadastrar o próprio aparelho porque outra empresa já tinha aquele
número, e a recusa (`409`) funcionava como oráculo — dava para descobrir quais
seriais existem na base sondando o cadastro.

No banco são dois índices: `(owner_id, serial_number)` para quem tem dono, e um
índice parcial sobre `serial_number` `WHERE owner_id IS NULL`, porque no
Postgres nulos não conflitam entre si e dois órfãos com o mesmo serial passariam
em silêncio.

**O furo aceito:** dois usuários da *mesma* empresa podem cadastrar o mesmo
aparelho, cada um no próprio escopo. O escopo certo seria a empresa, e não é
por falta de vontade que não é — é porque **não existe chave de empresa
confiável** hoje: `users.cnpj` é autodeclarado e não serve para escopo (ver
"Permissões"), e `users.company_id` está preenchido só para quem um admin
vinculou à mão pela tela de Grupos.

Evoluir para escopo por empresa depende de reconciliar esses dois campos
primeiro — caminho levantado em
`docs/superpowers/specs/2026-08-24-duas-fontes-de-verdade-empresa.md`.

## Cadastro do cliente

**CNPJ e CEP são obrigatórios** no onboarding e ao salvar os dados da empresa no
perfil. O CNPJ é validado pelos dois dígitos verificadores, tanto no frontend
(`frontend/src/lib/documents.ts`) quanto no backend (`OnboardingUpdate`) — a
regra não é contornável pela API.

As colunas seguem `nullable` no banco de propósito: **clientes cadastrados antes
da regra não são bloqueados**. Eles veem um aviso no perfil pedindo para
completar o cadastro.

## Telefone do cliente

### `users.phone` é a fonte canônica — e `companies.phone` não é alternativa

> **Quem o sistema liga é a pessoa, não a empresa.** O telefone do atendimento
> é `users.phone`. `companies.phone` **não** é usado como reserva.

Existem duas colunas gêmeas, ambas `String(20)` e anuláveis: `users.phone`
(`models.py:209`) e `companies.phone` (`models.py:177`). Elegê-las as duas
criaria duas fontes de verdade para a mesma pergunta — o erro que o par
`users.cnpj` / `companies.cnpj` já custou caro (ver "Qual é a autoridade sobre
'de qual empresa é este cliente'").

Não existe precedência do tipo `users.phone ?? companies.phone`. Três medições
de 18/09/2026 sustentam a escolha:

- o caminho majoritário de criação de empresa **nasce sem telefone** — a
  sugestão montada do onboarding não tem o campo, e o front não o envia;
- `users.phone` é dado pessoal declarado na política de privacidade, e a
  anonimização o apaga; `companies.phone` é dado de empresa;
- desvincular um cliente da empresa é `ON DELETE SET NULL`, então uma regra
  apoiada na empresa perderia efeito no instante em que alguém clicasse em
  Desvincular.

### E.164 é a representação interna

O telefone é guardado em **E.164** (`+5581999999999`), normalizado por
`app/utils/telefone.py`, que é a autoridade; `frontend/src/lib/telefone.ts`
espelha a mesma regra para o usuário saber o que errou antes de enviar.

**E.164 é a forma canônica interna do HelpHS e não depende de fornecedor
nenhum.** A conversão para o formato que a telefonia espera no momento de
discar é responsabilidade isolada do adapter da integração — não está
implementada, e a grafia exata segue em aberto com o fornecedor.

A máscara é coisa de tela, como no CNPJ. Entradas brasileiras razoáveis são
aceitas e normalizadas (`81999999999`, `5581999999999`, `+5581999999999`,
`(81) 99999-9999`); número de fora do Brasil exige o `+` explícito, porque sem
ele não há como saber onde termina o código do país — e chutar `+55` produz
número indiscável gravado com cara de telefone bom.

### A regra é prospectiva: proíbe a PERDA, não a ausência

> **Novo cliente ativo precisa de telefone. Cliente ativo que já tem telefone
> não pode ficar sem. Cliente legado sem telefone continua editando o resto do
> cadastro normalmente.**

São exatamente duas proibições, implementadas em `_guarda_telefone_do_cliente`
(`app/routers/users.py`) e cobradas em `tests/test_telefone.py`:

| | O que é proibido |
|---|---|
| **P1 — remoção** | tinha telefone e a requisição o esvazia, sendo cliente ativo |
| **P2 — transição** | virar `client`, ou voltar a `active`, sem telefone |

O que **não** é proibido: um cliente ativo que já estava sem telefone salvar o
nome, o departamento ou a foto. Medido em produção em 18/09/2026: **18 contas
`role=client` + `status=active`, das quais 14 sem telefone**. O responsável
informou que essa população é composta por contas **fictícias/de teste** — ou
seja, o número não descreve qualidade cadastral de clientes reais, e sim
**legado técnico**. Mas elas existem fisicamente, e uma exigência genérica
("cliente ativo sempre precisa de telefone", cobrada em todo `PATCH`) as
deixaria incapazes de editar o próprio nome. Regra nova é prospectiva; dado
histórico se corrige em script avulso.

A obrigatoriedade **não** mora no `UserUpdate`: esse schema é compartilhado por
`PATCH /users/me` e `PATCH /users/{id}` e não conhece o usuário alvo, o estado
atual dele nem o resultante. Ele só valida e normaliza quando o campo vem, e o
`exclude_unset` do router é o que distingue "não enviou" de "enviou vazio" —
distinção da qual a regra depende inteiramente. Quem decide é o router.

O `RegisterRequest` é a exceção: o cadastro público grava `role=client` e
`status=active` como literais, então não há estado a descobrir e a exigência
cabe no próprio schema.

**A anonimização continua podendo zerar o telefone.** O direito ao esquecimento
é mais forte que esta regra: `anonymize_user` escreve `phone = None` direto no
objeto, sem passar pelos guards, e há teste dedicado para que ninguém
"conserte" isso depois.

**Até a Fase 1B não havia constraint no banco**, e o caminho até ela mudou
depois de um experimento — ver a seção seguinte. A Fase 1C criou o `CHECK`
validado de presença; tudo o que está descrito acima continua valendo como o
que a **aplicação** faz.

### Por que não usamos CHECK NOT VALID para telefone

> **`CHECK ... NOT VALID` é incompatível com a regra prospectiva acima.** A
> constraint de banco só pode nascer quando **nenhuma** linha a violar.

O desenho anterior previa criar o `CHECK` como `NOT VALID`, no entendimento de
que isso deixaria as linhas legadas isentas. **Não deixa**, e a diferença foi
medida em PostgreSQL 16.2 descartável, com uma linha por cenário para que um
caso não contaminasse o outro:

| Cenário | Regra da Fase 1A | `CHECK NOT VALID` |
|---|---|---|
| legado: `UPDATE` só o `name` | permite | **recusa** |
| legado: `UPDATE` só o `department` | permite | **recusa** |
| legado: `UPDATE name` + `phone=NULL` (formulário completo) | permite | **recusa** |
| legado: acrescentar telefone válido | permite | permite |
| legado: mudar situação para `inactive` | permite | permite |
| remover telefone de cliente ativo (P1) | recusa | recusa |
| `inactive` → `active` sem telefone (P2) | recusa | recusa |
| novo cliente ativo sem telefone (P2) | recusa | recusa |

**Três divergências em onze**, todas sobre o legado.

O motivo é simples depois de visto: `NOT VALID` pula **apenas o escaneamento
inicial**. Dali em diante o PostgreSQL avalia o `CHECK` sobre a **nova versão
da linha** em todo `UPDATE` — e não existe, para `CHECK`, a otimização de
"pular quando as colunas da constraint não mudaram" que existe para chave
estrangeira. Trocar só o nome de uma linha legada produz uma versão que
continua violando, e o `UPDATE` falha.

`ALTER TABLE ... VALIDATE CONSTRAINT` com linha legada presente também foi
medido: **recusa**. Só dá para validar depois que o legado zera.

**Um gatilho foi testado e rejeitado.** Um `BEFORE INSERT OR UPDATE` enxerga
`OLD` e `NEW`, então reproduz P1 e P2 com **zero divergências** — medido. Mas
ele cria uma **segunda fonte de verdade** para a regra: ela passaria a viver
em PL/pgSQL e em Python ao mesmo tempo, e o lado do banco não tem teste de
mutação, nem `mypy`, nem o guard de fonte que hoje cobra a versão da
aplicação. O ganho não paga a deriva.

**A condição para a constraint é `LEGADO_INVALIDO = 0`.** Quem mede é
`backend/scripts/diagnostico_telefone.py`, que imprime a linha
`LEGADO_INVALIDO=<N>` e sai com 0 (pronto), 1 (há legado) ou 2 (falha
operacional — banco fora do ar não pode ser lido como "ainda há legado").

Quando esse número chegar a zero, a constraint pode ser criada **validada**,
sem `NOT VALID`. O PostgreSQL ainda verifica as linhas existentes nesse
momento, mas com o volume atual da tabela esse custo é operacionalmente
pequeno — e, com zero linhas violando, não há divergência possível.

O fatiamento ficou assim:

| Fase | O que faz |
|---|---|
| **1A** | ✅ regra na aplicação, normalização E.164, front. Em `main`. |
| **1B** | ✅ readiness oficial. **Sem migration.** Em `main`. |
| **1C** | ✅ `CHECK` validado de presença — `ck_users_cliente_ativo_tem_telefone`. |

**O portão foi aberto por saneamento, não por exceção.** O readiness mediu
`LEGADO_INVALIDO=14` em produção. As contas eram exemplos e foram
**inativadas administrativamente** — sem telefone inventado, sem exclusão de
histórico, sem `UPDATE` de saneamento dentro de migration. A medição seguinte
deu `LEGADO_INVALIDO=0`, e só então a constraint passou a poder existir.

A constraint é **validada**, sem `NOT VALID`. O PostgreSQL verifica as linhas
existentes ao criá-la, mas com o volume atual da tabela esse custo é
operacionalmente pequeno — e, com zero linhas violando, não há divergência
possível com a regra da aplicação.

**A aplicação não foi simplificada por causa dela.** Os guards da Fase 1A
continuam onde estavam: o banco recusa o estado impossível, a aplicação
explica o porquê em português e devolve 422 no campo certo. Defesa em
profundidade só vale com as duas camadas vivas.

⚠️ **A anonimização e a constraint, um detalhe que morde.** Medido em
PostgreSQL real: gravar `phone = NULL` e `status = anonymized` **na mesma
instrução** passa — que é exatamente o que `anonymize_user` faz, num `commit`
só. Mas limpar o telefone **antes** de mudar a situação é recusado, e o
resultado é pior que um erro visível: a conta terminaria `anonymized` **com o
telefone intacto**. Vale para qualquer script avulso de anonimização escrito
no futuro; há teste cobrindo os dois caminhos.

⚠️ **Não cite valor de enum acrescentado por `ALTER TYPE` numa migration.**
Descoberto ao mutar esta constraint: o projeto não usa
`transaction_per_migration`, então `alembic upgrade head` roda a cadeia
inteira numa transação só. Como `anonymized` entrou em `userstatus` por
`ALTER TYPE ... ADD VALUE`, mencioná-lo em DDL estoura com `unsafe use of new
value "anonymized" of enum type userstatus` ao subir do zero. O predicado
escolhido isenta o anonimizado **sem nomeá-lo**, e por isso não esbarra nisso.

`companies.phone` segue fora de tudo isto: não é fonte da telefonia, e nenhuma
constraint foi criada para ela.

### Telefone só chega ao front quando alguém vai ligar

O contrato do chamado **não** carrega telefone. Ele expõe apenas se a ação de
ligar está disponível e, quando não está, o motivo. O número é buscado por
endpoint próprio e autorizado, no momento em que a confirmação da ligação
abre — e o backend **rebusca o telefone no banco** ao disparar a chamada, sem
aceitar número vindo do navegador.

Minimização de dado pessoal: sem isso, o telefone de todo cliente trafegaria em
cada abertura de chamado, inclusive para quem nunca vai ligar.

## Respostas rápidas do chat

Lista **única para toda a equipe** — não há respostas por técnico. Admin e
técnico gerenciam em Gestão › Respostas Rápidas.

No chat, `/` abre o menu; continuar digitando filtra por atalho ou título,
ignorando acentos. Resposta inativa continua cadastrada mas some do menu.

Fora de escopo por ora: variáveis dinâmicas (`{{nome_do_cliente}}`), anexos e
categorias de resposta.

## Armazenamento de arquivos

**Anexos de chamado e fotos de perfil ficam em disco**, no caminho de
`UPLOAD_DIR` (padrão `/app/uploads`). Antes iam para MinIO/S3; a troca foi feita
em 05/08/2026 porque o ambiente de produção não tem serviço de storage e a
hospedagem oferece volume.

**No deploy, esse caminho precisa ser um volume.** Sem volume, o Docker descarta
o conteúdo a cada redeploy e todos os anexos somem. No EasyPanel:
serviço `helphs-api` › Armazenamento › **Adicionar Montagem de Volume**, com
`/app/uploads` como caminho no container.

O `Dockerfile` cria `/app/uploads` já pertencente ao `appuser` antes de trocar
de usuário. Isso é necessário: o container não roda como root, e um volume
montado sobre um diretório de root ficaria sem permissão de escrita.

### Como o arquivo chega ao navegador

Por **link temporário assinado**, não pela sessão do usuário — a foto de perfil e
a pré-visualização de anexo são carregadas pelo `<img src>`, que não envia
cabeçalho de autenticação.

1. A API devolve `/api/v1/files/<token>`, com validade de `FILE_URL_EXPIRES_SECONDS`
2. O frontend prefixa com o host da API (`resolveFileUrl`), porque em produção
   frontend e API ficam em domínios diferentes
3. O endpoint valida a assinatura e o tipo do token antes de servir o arquivo

O token é do tipo `file`: um token de login **não** serve para baixar arquivo, e
vice-versa. A key é validada contra path traversal — nenhum caminho sai de
`UPLOAD_DIR`.

### Por que quase tudo desce como download

Os arquivos vêm de upload de cliente. Servi-los inline no domínio da API é o
mesmo que deixar terceiros publicarem conteúdo naquela origem: um `.html` ou um
`.svg` com script rodaria **como se fosse do sistema** (XSS armazenado).

Por isso o endpoint `/files`:

- só exibe inline **png, jpeg, gif e webp** — o necessário para foto de perfil e
  pré-visualização de imagem;
- **SVG fica de fora de propósito**: é imagem, mas aceita `<script>` dentro;
- qualquer outro tipo vira `application/octet-stream` com
  `Content-Disposition: attachment`;
- toda resposta leva `X-Content-Type-Options: nosniff` e
  `Content-Security-Policy: default-src 'none'; sandbox`.

Hoje a allowlist de upload (`UPLOAD_ALLOWED_EXTENSIONS`) não aceita `.html` nem
`.svg`, mas ela é configurável por variável de ambiente — a proteção no download
existe para que mudar essa variável não abra um buraco.

Como o arquivo em disco tem nome interno (uuid), o backend acrescenta
`?filename=` na URL do anexo para o download sair com o nome original.

## LGPD

A anonimização de usuário existe no backend e foi **removida da interface de
propósito**. Manter o endpoint para uso futuro.

---

## E-mail sem distinção de maiúsculas

`Fulano@x.com` e `fulano@x.com` são a mesma caixa postal no mundo real — e
até 15/09 eram duas contas possíveis no sistema (o `EmailStr` só baixa o
domínio, e as buscas comparavam igualdade exata). Produção foi conferida no
mesmo dia: zero duplicatas; a porta fechou limpa. Três camadas:

- **Regra prospectiva**: toda entrada de e-mail (cadastro, login,
  esqueci-a-senha, criação por admin) usa o tipo `EmailNormalizado`
  (`app/utils/email_normalizado.py`) — minúsculas no tipo, no padrão do CNPJ.
  Guard de fonte em `tests/test_email_normalizado.py` pega schema novo que
  declare `EmailStr` cru.
- **Passado**: `scripts/normaliza_emails.py` (avulso, dry-run por padrão)
  baixa linhas antigas; colisão por caixa é relatada e NUNCA fundida — a
  decisão é humana.
- **Trava de banco**: índice único em `lower(email)` (revision
  `e1z2a3b4c5d6`). Roda no boot e FALHA se houver duplicata — por isso o
  script roda ANTES do deploy que leva a migration.

## Limite de tentativas (rate limiting)

Aplicado com slowapi (`app/core/rate_limit.py`), contadores no Redis — valem
entre os workers e sobrevivem a restart do backend. Desligado sob
`APP_ENV=testing`. Três limites, todos por IP e por janela de 15 minutos:

| Variável | Default | Endpoints |
|---|---|---|
| `RATE_LIMIT_LOGIN` | 5/15min | login e verificação do segundo fator (tentativa de credencial) |
| `RATE_LIMIT_ACCOUNT` | 5/15min | registro, reenviar confirmação, esqueci minha senha (disparam e-mail) |
| `RATE_LIMIT_TOKEN` | 10/15min | confirmar e-mail, redefinir senha (quem chega já tem token assinado) |

Decisões:

- **Por IP real** — exige `FORWARDED_ALLOW_IPS=*` no serviço do backend, o que
  só é seguro com a porta do backend **despublicada** (feito em 26/08, depois
  do incidente em que o contador virou um balde único no IP interno do proxy
  e bloqueou o login de todos os usuários de uma vez).
- O bloqueio **passa sozinho** ao fim da janela; tentar de novo durante o
  bloqueio não zera nada. Destravar na mão: console do Redis →
  `KEYS *LIMITER*` → `DEL` nas chaves listadas.
- O 429 responde `Retry-After` com o tempo real que falta na janela, e o front
  converte em "aguarde X minutos" (`src/lib/apiError.ts`). **Não** mostramos
  "restam X tentativas" de propósito: esse contador ajuda quem está
  adivinhando senha a saber quando parar.
- "Por IP" significa por conexão de internet: um escritório atrás do mesmo
  roteador divide o contador. Se algum cliente sentir o limite, o ajuste é a
  env var no painel — não é mudança de código.

## Formato do código

### O formatador do backend é o `black`. O `ruff` é linter, nunca formatador.

O CI roda os dois (`.github/workflows/ci.yml`): `ruff check .` e
`black --check .`. Eles **discordam** de formatação, e quem manda é o `black`,
rodado de dentro de `backend/`.

**Nunca rode `ruff format` num arquivo do backend.** Ele reformata o arquivo
inteiro no estilo dele, inclusive linhas que você não escreveu, e o
`black --check` reprova o resultado. Em 08/09/2026 isso derrubou o CI de um
commit de migration por causa de um `assert` de outra pessoa, num arquivo de
teste que só tinha sido tocado numa fixture.

No frontend a regra é diferente e igualmente contraintuitiva — ver o Prettier
em `mudanças.md`: os arquivos estão em 80 colunas, o `.prettierrc` diz 100, e
o CI não checa formato. Lá, rodar `--write` polui o commit.

## Base da Helô

### A base da Helô é a Base de Conhecimento (desde 10/09/2026)

A fonte deixou de ser uma pasta de manuais e passou a ser `kb_articles` com
`status = published` e `helo_pode_ler = true`. Artigo publicado alimenta as
respostas da Helô **sem ninguém rodar nada**: uma varredura periódica
(`app/services/helo_indexacao.py`, a cada 5 min) indexa o que é novo ou
editado, e a busca filtra publicação, marcação e produto AO VIVO — despublicar
tira o texto das respostas no mesmo instante.

⚠️ **Publicar artigo passa a mudar o que a Helô diz para o cliente.** O suporte
não tinha esse poder e não foi avisado de que passou a ter. Passo a passo
errado num artigo publicado vira procedimento errado ditado ao cliente, com a
fonte citada — o que faz parecer conferido.

**Duas regras de vínculo de produto, em dois lugares, de propósito:**

| Onde | Vínculo ausente | Por quê |
|---|---|---|
| Base de Conhecimento (tela) | vale para TODOS os aparelhos | é escolha de quem escreveu |
| Importação dos manuais (script) | ERRO FATAL | quem cria é máquina; ninguém escolheu nada |

Quem unificar as duas achando que achou inconsistência reabre o caminho para o
passo a passo do Phoebus chegar a quem tem um Titan.

**Chamado SEM produto não recebe nada — nem o artigo universal.** Decidido em
10/09/2026; até ali era só o comportamento herdado de antes da mudança de
fonte, e está escrito aqui para não parecer esquecimento amanhã. Chamado sem
produto é chamado em que não sabemos qual aparelho está na mão do cliente, e
citar procedimento é mais arriscado justamente aí: todos os aparelhos não é o
mesmo que nenhum. É a mesma assimetria do teto de distância — escalar custa um
turno de humano; procedimento errado num instrumento de medição legal custa
mais.

**O filtro de tipo morreu**, e com ele uma proteção: se alguém publicar uma
ficha com preço na Base, ela vira fonte da Helô. A proteção passou a ser a
marcação `helo_pode_ler`, que alguém precisa desligar.

### O modo da Helô: triagem até os sete manuais (desde 15/09/2026)

`HELO_MODO` diz o que ela faz quando está ligada. **`triagem`** é a
recepcionista da Fase 1 — saudação, encerramento e escalada, nada de
embedding, nada de LLM, teto de duas falas. **`completa`** é a Fase 2, que
busca na Base de Conhecimento e responde com o modelo. O padrão é `triagem`, e
valor ausente ou não reconhecido também é `triagem`: o modo seguro é o que o
sistema assume quando não sabe. Caixa e espaço não importam; um valor
preenchido e desconhecido (o erro provável é `completo`) deixa aviso no log.

**Por que existe.** Os manuais técnicos dos sete aparelhos estão sendo
reescritos pela assistência técnica, em cerca de quinze dias. Até lá a base
não tem manual técnico publicado (os três importados em 10/09 continuam
rascunho), e a Fase 2 sem manual devolve escalada em toda pergunta técnica — o
cliente responderia às três perguntas e seria transferido para um atendente
em vez de ler "registrei tudo aqui". A Fase 2 **dorme, não foi removida**:
nenhuma lógica dela saiu (o diff só acrescenta o desvio da triagem e o teto
por modo), e ela acorda virando o modo.

**O modo é ortogonal ao `HELO_ENABLED`.** Desligada é desligada em qualquer
modo. As quatro guardas valem igual nos dois, e cada uma tem teste nos dois
modos: os três interruptores (nada religa num nível mais específico), o
humano já na conversa, o pedido de humano antes do encerramento e antes de
qualquer peça da Fase 2, e a saída gravando `helo_saiu` — com o pedido
explícito de humano derrubando também o `ai_enabled`. A ordem: interruptores,
humano na conversa, saudação que nunca aconteceu, teto de falas, pedido de
humano.

**O pedido de humano passa por cima do teto, nos dois modos** — decidido em
15/09/2026, e diverge da Fase 1 **de propósito**. Na Fase 1, passadas as duas
falas, "quero falar com um atendente" recebia silêncio. O teto de duas existia
porque ela só tinha duas coisas a dizer, não como recusa a um pedido: silêncio
depois de um pedido explícito o cliente lê como sistema ignorando, e o custo de
atender é uma escalada a mais num chamado que já ia para a fila. A exceção é só
do pedido — resposta comum passado o teto continua em silêncio — e não passa
por cima dos interruptores nem da guarda de humano na conversa. Fidelidade à
Fase 1 não é argumento para desfazer; há teste que prende isto.

**Recusado: usar a ausência da `DEEPSEEK_API_KEY` como standby.** O
`_chamar_deepseek` devolve `None` antes de montar a URL quando a chave falta,
então ligar sem chave não vaza nada — mas a segurança passaria a depender de
faltar uma configuração. No dia em que alguém preenchesse a chave para testar
outra coisa, ela acordaria sozinha, com a base vazia, falando com cliente, sem
ninguém ter decidido. Chave ausente continua sendo falha de infraestrutura,
com o destino que já tinha. Em triagem, nem com chave e URL preenchidas um
cliente HTTP é construído — há teste disso, com um controle no modo completo
provando que a armadilha dispara.

**Duas escolhas que o modo trouxe junto:**

- **O encerramento grava `helo_saiu`**, com histórico, e o `ai_enabled` fica
  onde está. Sem isso, o chamado triado continuaria com duas falas e crédito
  até sete no modo completo: no dia do gatilho ela voltaria a falar num chamado
  em que já disse "um atendente já vai assumir".
- **O encerramento chama a equipe com "Triagem concluída"**, o aviso da Fase 1
  (`db88a34`). O `f2421ac` o tinha tirado porque o encerramento deixara de
  existir; sem ele, o chamado triado e sem dono ficaria sem ninguém avisado.

**O que continua rodando em triagem, por decisão (15/09/2026):** a varredura
de indexação (`helo_indexacao.py`). Ela manda texto de artigo — não de
cliente — ao serviço de embedding, e deixar a base pronta durante os quinze
dias é exatamente o que se quer. Desligá-la seria
`HELO_INDEXACAO_INTERVALO_SEGUNDOS=0`.

**Limitação conhecida, não consertada: voltar de `completa` para `triagem`
com conversa em andamento.** Nesses chamados ela fica calada para resposta
comum, sem aviso à equipe — eles já passaram das duas falas. (O pedido de
humano continua sendo atendido, porque passa por cima do teto.) Só importa com
`HELO_ENABLED=true`, e nesse cenário quem vira o modo sabe o que está fazendo.
Em 15/09/2026 o `HELO_ENABLED` estava `false` no painel de produção — medido
pelo Rickelme —, então não havia conversa em modo completo para esta mudança
calar.

#### O gatilho para virar para `completa`

**Os sete manuais publicados na Base de Conhecimento.** Não "os manuais
chegaram": publicados, vinculados ao produto e marcados para a Helô, e
indexados. Antes de virar, conferir:

1. Os sete artigos publicados, com vínculo de produto e `helo_pode_ler`, e
   trechos indexados para cada um (`helo_chunks` por `article_id`).
2. O teto de distância remedido — é gatilho da dívida "O teto de 0,25 depende
   do acervo": entra manual de produto que hoje não tem.
3. O serviço de embedding respondendo e a `DEEPSEEK_API_KEY` configurada.
4. **Os chamados triados antes de o `helo_saiu` existir.** Se a Helô chegou a
   ficar ligada com o código anterior à Fase 2 — não medido: o `HELO_ENABLED`
   nasce `false` desde o `8e9286c`, e o encerramento só entrou numa versão a
   partir da v1.11.0 (`db88a34`) —, esses chamados têm duas falas dela e o
   campo em `false`. No modo completo eles ganham crédito para mais cinco, e
   ela voltaria a falar em quem não tiver responsável nem mensagem da equipe.
   A consulta não depende de data; contar antes de virar:

   ```sql
   SELECT t.status, count(*)
   FROM tickets t
   WHERE t.helo_saiu = false
     AND t.ai_enabled = true
     AND t.assignee_id IS NULL
     AND (SELECT count(*) FROM chat_messages m
          WHERE m.ticket_id = t.id AND m.is_ai) >= 2
     AND NOT EXISTS (
       SELECT 1 FROM chat_messages m JOIN users u ON u.id = m.sender_id
       WHERE m.ticket_id = t.id AND u.role IN ('admin', 'technician'))
   GROUP BY t.status;
   ```

   Havendo algum, a correção é script avulso que grava `helo_saiu` — nunca
   migration (dado histórico se corrige fora dela).
5. O documento de LGPD: a Fase 2 manda conteúdo de chamado para a DeepSeek.

### O interruptor da Helô é dela; o `ai_enabled` é de gente

Decidido em 10/09/2026, corrigindo uma escolha de dois dias antes.

`tickets.ai_enabled` sempre significou "alguém quer a IA fora deste chamado" —
é o botão que o técnico aperta na tela, e ele fecha a Helô, a sugestão de
resposta e o resumo. Quando a escalada passou a gravar nesse campo, ele ganhou
um segundo significado: "a Helô já saiu daqui". Enquanto ela falava uma vez por
chamado os dois davam no mesmo. Com ela conversando, deixaram: escalar por
decisão do modelo, por teto de trocas ou por a IA estar fora do ar tirava a
ferramenta do técnico **nos chamados em que a IA já tinha falhado**.

`tickets.helo_saiu` é o campo dela, e ela escreve nos **quatro** motivos — e,
desde 15/09, também no encerramento do modo triagem.

**A exceção é deliberada e tem teste só para ela:** no pedido explícito de
humano os dois campos caem. Ali quem quis sair da IA foi o cliente, e a vontade
dele vale para as ferramentas todas. Sem prender isso, a assimetria com os
outros três motivos pareceria esquecimento, e alguém "consertaria" tirando a
linha.

**A saída dela grava histórico**, como o botão da tela já gravava, com o motivo
no comentário — o texto que o próprio modelo escreveu na linha `ESCALAR:`. Sem
isso o técnico abre o chamado, vê a IA calada e não tem onde ler por quê. Foi
o que forçou o gravador de histórico a sair de `routers/tickets.py` para
`utils/history.py`: `tickets.py` importa `services.helo`, então a Helô
importando de volta seria ciclo, e a alternativa era uma segunda cópia da
regra.

### O teto de distância da busca foi medido, não escolhido

Ordenar não é filtrar: sem teto, `busca_trechos` sempre devolve os quatro
trechos mais próximos, por mais longe que estejam — e o modelo os recebe num
bloco que o prompt chama de "sua única fonte de verdade técnica".

Medido em 09/09/2026 com 40 perguntas rotuladas contra o corpus real:

| grupo | n | mediana do 1º | extremo |
|---|---|---|---|
| tem resposta na base | 27 | 0,2185 | máximo 0,2850 |
| não tem resposta na base | 13 | 0,2789 | **mínimo 0,2590** |

`TETO_DE_DISTANCIA = 0.25` é o maior corte que ainda barra **100%** das
perguntas sem resposta, preservando 22 das 27 com resposta. De quebra, corta o
enchimento das que passam: nessas 40 perguntas chegavam 160 trechos ao modelo,
passam a chegar 25 — e em 74% das que têm resposta sobra exatamente UM trecho,
o certo, no lugar de um mais três de ruído.

**Remedido em 10/09/2026, depois da mudança de fonte**, com as mesmas 40
perguntas contra os três manuais vindos da Base de Conhecimento: sem resposta,
13 de 13 barradas (mínimo 0,2570); com resposta, 21 de 27 ainda recebendo
trecho (eram 22). O texto dos trechos mudou de forma e a distância mexeu em até
oito milésimos. O corte continua valendo, e ficou mais apertado: a margem
abaixo, de 0,009, hoje é de 0,007.

⚠️ **A margem é de 0,007** (0,25 contra 0,2570; na medição de 09/09 era 0,009,
contra 0,2590). É um ajuste a 40 pontos, não uma lei, e vale para o **bge-m3
com estes textos**: trocar o modelo de embedding invalida a medição sem que
nada quebre visivelmente. Quando remedir está na dívida "O teto de 0,25
depende do acervo", em Pendências conhecidas; como remedir, logo abaixo.

⚠️ **A população "tem resposta" está enviesada para o fácil, e isso é limite
conhecido da medição.** As 27 perguntas foram escritas por quem já tinha lido
os manuais, e por isso usam as palavras do manual. Cliente escreve *"não sai
nada no visor"*, não *"como interpreto os resultados"* — e a distância só
cresce com essa diferença. Os 81% de acertos preservados são o **melhor caso**,
não a expectativa: em produção o número é menor, e quanto menor só se descobre
medindo com pergunta de cliente de verdade, quando houver conversa gravada para
isso. Quem for revisitar o 0,25 começa por refazer a medição com perguntas
reais — não por mexer no número.

⚠️ **E o "barra 100%" é do conjunto de perguntas, não do mundo.** As perguntas
foram escritas por quem já sabia a resposta, e saíram mais gentis que as de um
cliente. A prova está no `test_helo_pooling_postgres.py`, com embedding real:
*"como coloco o aparelho em português"* casa a seção certa a **0,2533** — um
acerto DENTRO da faixa que a medição tratou como território de quem não tem
resposta. Ou seja: as duas populações se sobrepõem entre 0,25 e 0,26, e o corte
não separa duas nuvens, ele **escolhe um lado da sobreposição**.

A escolha é de apetite de risco, e é a do desenho: passar trecho errado faz a
Helô ditar procedimento de instrumento de medição legal a partir dele; cortar
acerto faz um humano responder. Os dois erros terminam em escalada; só um deles
pode terminar em instrução errada. Por isso o corte fica no lado apertado.

**Quando o teto corta tudo, o resultado é o mesmo `NADA ENCONTRADO` de quando a
busca não devolve nada.** Não existe estado novo para "achei, mas está longe":
seria só mais uma coisa para o modelo interpretar errado.

#### Como remedir

O método das duas medições (09/09 e 10/09), para quem for refazer. Ele não
está em script no repositório: está aqui, e as 40 perguntas vão junto.

1. Com a base indexada como produção a veria (artigos publicados e marcados
   para a Helô), embutir cada pergunta pelo mesmo serviço de embedding dela.
2. Para cada pergunta, rodar a consulta de `busca_trechos` com os mesmos
   filtros — publicação, marcação e o **produto da pergunta** — mas SEM o
   teto, e guardar a distância e a seção do 1º colocado.
3. Separar pelo rótulo: com resposta (a seção esperada existe na base; casa
   se o rótulo aparece no título da seção, sem diferenciar maiúsculas) e sem
   resposta (preço, certificado, dano físico, entrega, nota fiscal, função
   que o aparelho não tem — nada disso está em manual).
4. O teto é o maior corte que ainda barra **100%** do grupo sem resposta.
   Anotar quantas com resposta ele preserva e a margem até a sem resposta
   mais próxima — é a margem que diz se o número ainda se sustenta.

⚠️ **O viés vem junto com o método.** As 27 perguntas com resposta foram
escritas por quem já tinha lido os manuais, e usam as palavras deles: os
acertos preservados são o **melhor caso**. Refazer com as mesmas 40 mede o
quanto o acervo andou, não o cliente — medir o cliente pede pergunta de
conversa gravada.

As perguntas estão como foram embutidas, **sem acento**. Reescrever uma é
trocar de pergunta: a distância muda, e a comparação com as medições
anteriores deixa de valer para ela.

<details><summary>As 40 perguntas rotuladas</summary>

| Produto | Pergunta | Seção esperada (trecho do título) |
|---|---|---|
| Titan | como ajusto a data e a hora do aparelho | 8.1 |
| Titan | como mudo o idioma para portugues | 8.2 |
| Titan | onde vejo quantos testes ja foram feitos | 8.3 |
| Titan | como apago os testes da memoria | 8.4 |
| Titan | o titan precisa de bocal descartavel | FAQ |
| Titan | de quanto em quanto tempo preciso calibrar | Calibra |
| Titan | como ligo o aparelho | Passo a Passo |
| Titan | o que significa resultado acima do limite | Interpreta |
| Titan | posso deixar o aparelho guardado no sol | Cuidados |
| Titan | como conecto o titan no aplicativo do celular | Aplicativo |
| Titan | quanto custa a calibracao do titan | — (sem resposta) |
| Titan | quero o certificado de calibracao rbc | — (sem resposta) |
| Titan | o aparelho caiu e a tela quebrou | — (sem resposta) |
| Titan | qual o prazo de entrega de um aparelho novo | — (sem resposta) |
| Titan | como conecto na impressora | — (sem resposta) |
| Titan | quero cancelar a compra e devolver o aparelho | — (sem resposta) |
| Titan | como troco a celula de combustivel eu mesmo | — (sem resposta) |
| Phoebus | como ajusto data hora e fuso horario | DATA, HORA |
| Phoebus | como mudo o idioma do dispositivo | IDIOMA |
| Phoebus | como conecto o phoebus na internet por cabo de rede | INTERNET |
| Phoebus | como faco para ocultar o resultado na tela | RESULTADO EXIBIDO |
| Phoebus | como ajusto o volume da voz e do bip | UDIO E BIP |
| Phoebus | o reconhecimento facial esta aceitando a pessoa errada | FACIAL |
| Phoebus | o phoebus tem impressora | Impressora |
| Phoebus | quais formas de identificacao ele aceita | Autentica |
| Phoebus | para que serve a plataforma web | Plataforma |
| Phoebus | quanto custa uma calibracao | — (sem resposta) |
| Phoebus | o aparelho molhou na chuva | — (sem resposta) |
| Phoebus | quero trocar o phoebus por outro modelo | — (sem resposta) |
| iBlow 10 Pro | como conecto no bluetooth do celular | Bluetooth |
| iBlow 10 Pro | como carrego a bateria do aparelho | Carregamento |
| iBlow 10 Pro | o que fazer quando aparece calibracao requerida | Erros |
| iBlow 10 Pro | qual a diferenca entre o modo normal e o outro modo | Modos |
| iBlow 10 Pro | o que significa led vermelho com bipes curtos | Interpreta |
| iBlow 10 Pro | o protetor de saliva pode ser lavado | Composi |
| iBlow 10 Pro | qual a capacidade da bateria em mah | Especifica |
| iBlow 10 Pro | como vejo o historico dos ultimos testes | Avan |
| iBlow 10 Pro | quanto custa o iblow | — (sem resposta) |
| iBlow 10 Pro | quero a nota fiscal do aparelho | — (sem resposta) |
| iBlow 10 Pro | o aparelho queimou depois de uma queda | — (sem resposta) |

</details>

### As duas hipóteses foram medidas: a A caiu, a B se confirmou

Levantadas em 09/09/2026 a partir de UMA observação — *"como coloco o aparelho
em português"* num Titan devolvia `6. Passo a Passo` (0,2420) à frente de
`8.2 Alterar Idioma` (0,2592). As duas leituras pediam consertos opostos, e por
isso ficaram separadas em vez de virar conserto na hora.

Medidas no mesmo dia, com 40 perguntas rotuladas à mão contra o corpus real —
27 com resposta conhecida no manual do produto e 13 sem resposta nenhuma.

**Hipótese A — "trecho curto perde por ter menos sinal" — CAIU.** É o oposto:
os trechos mais curtos da base são os que mais acertam. As quatro subseções
`8.x` do Titan têm de 104 a 137 caracteres, e são os melhores resultados do
corpus inteiro — `8.1 Ajustar Data e Hora` a 0,1527, `8.3` a 0,1753, `8.2` a
0,2028, `8.4` a 0,2184. O que a observação original pegou foi sensibilidade à
FORMA da pergunta, não ao tamanho do trecho: *"como mudo o idioma para
português"* traz o `8.2` em primeiro, *"como coloco o aparelho em português"*
não. **Não juntar subseção curta com a vizinha** — seria estragar o que está
melhor.

**Hipótese B — "o `6. Passo a Passo` é um aspirador" — CONFIRMOU.** Ele ficou
em primeiro lugar em 4 de 8 perguntas de assuntos diferentes num sondagem
livre, incluindo *"como conecto na impressora"* num aparelho que não tem
impressora. O equivalente do iBlow (`5. Passo a Passo`) fez o mesmo em 3 de 8.
Virou dívida com gatilho — ver a tabela de dívidas.

**O teto de distância tira a maior parte do dano, e agrava um caso.** Com
0,25, as duas perguntas em que o aspirador vencia sem concorrência (0,2789 e
0,2710) passam a não devolver nada, que é o certo. Mas a pergunta original
desta seção fica PIOR: `6. Passo a Passo` (0,2420) sobrevive ao corte e o
`8.2` (0,2592) não, então o modelo passa a receber só o trecho errado onde
antes recebia os dois. É o contraexemplo conhecido do teto, e é a melhor razão
para a dívida da hipótese B existir.

## Testes

### Teste cuja garantia É uma cláusula `WHERE` não vai em mock

Regra nascida de um defeito medido, não de preferência.

A suíte do backend mocka a sessão do banco. O mock devolve o resultado que o
teste combinou de antemão — ele **não olha a consulta**. Isso isola bem quem
depende do banco, e não prova nada sobre quem depende do `WHERE`.

Como isso apareceu: a guarda de silêncio da Helô (`_humano_ja_esta_na_conversa`)
pergunta se alguém da equipe já falou no chamado, com três condições no
`WHERE` — o chamado, a junção com o autor e o papel dele. **Removendo o filtro
por papel, os 39 testes de `test_helo.py` continuavam verdes.** Sem esse filtro
a consulta casaria a mensagem do próprio cliente, que está sempre presente
quando a Helô vai responder: ela ficaria muda em todo chamado, para sempre. Um
defeito de comportamento total, invisível para a suíte inteira.

**A regra:** quando o que o teste promete garantir é o conteúdo de um `WHERE` —
um filtro por papel, por dono, por escopo de empresa, um `EXISTS`, um `JOIN`
que decide inclusão — o teste vai para um arquivo `*_postgres.py`, que executa
a consulta contra PostgreSQL de verdade. Mock continua certo para o resto:
ramificação, contrato de rota, texto, erro de provedor.

Os arquivos `*_postgres.py` (`test_helo_postgres.py`,
`test_dashboard_postgres.py`, `test_tickets_postgres.py`,
`test_migrations_postgres.py`) leem `TEST_POSTGRES_URL` quando existe — o CI
passa a variável (`.github/workflows/ci.yml`), então **eles rodam no gate** —
e senão sobem um Postgres efêmero via `pgserver`. Sem nenhum dos dois, pulam
em vez de falhar: quem não tem Postgres à mão continua rodando a suíte inteira.

⚠️ **O alcance disto é maior do que a Helô.** Se o mock responde sem olhar a
consulta, então **toda** cláusula `WHERE` coberta apenas por mock está sem
cobertura de fato — inclusive as de escopo por cliente e por empresa, que são
as mais valiosas do sistema. O que existe hoje em `*_postgres.py` é um começo,
não um inventário. Ao mexer numa consulta cuja correção é o filtro, presuma
que ela não está coberta e confira.

**Como conferir se um teste prova o que diz:** apague a cláusula do código e
rode. Se nenhum teste cair, o teste não cobre a cláusula — cobre o caminho até
ela.

## ⚠️ O `.env` de desenvolvimento aponta para produção

**O que está protegido: a suíte de testes e, desde 10/09/2026, a migration.**
O `backend/tests/conftest.py` **atribui** `DATABASE_URL` para um localhost
falso no topo do módulo, antes de qualquer import de `app` — atribuição e não
`setdefault`, com o comentário dizendo exatamente por quê. `pytest` é seguro.
E o `alembic/env.py` recusa host remoto fora do contêiner — ver "A trava
EXISTE", abaixo.

**O que não está protegido: todo o resto.** Tudo que lê a configuração de
verdade pega a URL de produção:

- ~~**`alembic upgrade head` na máquina local.** O `alembic/env.py` monta a URL
  com `get_settings().database_url`, que lê o `.env`. Migration aplicada por
  engano em produção não tem desfazer barato.~~ Travado em 10/09/2026.
- os scripts avulsos de `backend/scripts/` (`redefine_senha.py`,
  `funde_empresas_duplicadas.py`, `normaliza_cnpj.py`, ...);
- `python -c` e shell interativo que importem `app.core.config`;
- `psql` com a URL copiada do `.env`.

**Por que isso vira risco agora.** A primeira coisa que a Fase 2 da Helô roda é
uma migration criando extensão no banco (`pgvector`). O gesto natural de testar
isso é exatamente `alembic upgrade head` — e, até a trava de 10/09, esse
comando, dessa máquina, aplicava em produção sem perguntar nada. O erro era
silencioso: sem confirmação, sem aviso, e o sucesso indistinguível do sucesso
local.

### Mitigação

**O conserto de verdade é o `.env` não guardar credencial de produção.** A URL
de produção vive no painel do EasyPanel; a da máquina aponta para um Postgres
local. Isso remove a arma em vez de travá-la. Custa subir um banco local —
`pgserver` já está instalado e as migrations montam o schema sozinhas (ver a
Rota B em `desenvolvimento-local.md`, na raiz).

**A trava EXISTE desde 10/09/2026** (`app/utils/migrations.py`,
`exige_alvo_liberado`): o `alembic/env.py` recusa host remoto, nomeando o host
antes de abortar, e o `start.sh` exporta a liberação. Continua sendo trava, não
conserto — a arma segue na mesa para script avulso e para `psql`.

O ponto delicado do desenho é que ela **não pode quebrar o boot do container**,
onde rodar migration contra produção é o comportamento certo — o `start.sh`
faz `alembic upgrade head` na linha 5. A saída que não depende de ninguém
lembrar de nada: **o próprio `start.sh` exporta a variável de liberação** antes
de chamar o alembic. Ele está no repositório e sempre roda no container, então
produção passa por construção, e um laptop nunca tem a variável. Uma variável
que precisasse ser configurada no painel seria pior: esquecer de configurar
derruba o deploy, e o modo de falha do deploy é sempre pior que o do laptop.

Três detalhes do desenho que os testes prendem, e que não são óbvios:

- **A liberação é o literal `"1"`.** `"true"`, `"sim"` e `"yes"` não liberam:
  variável sobrevivente no shell de alguém não pode virar liberação por
  acidente de valor.
- **Alvo local passa sem liberação nenhuma.** Barrar quem desenvolve ensinaria
  a exportar a variável no `.bashrc`, e aí a trava estaria morta para tudo.
- **URL ilegível passa.** A trava não pode ser o motivo de o contêiner não
  subir, e erro de digitação o alembic reporta melhor do que ela.

O teste que importa roda `python -m alembic upgrade head` como **subprocesso**,
com URL remota no ambiente: trava escrita e não ligada passa em teste de
unidade e não impede nada. Há também um teste que lê o `start.sh` e confere que
o nome da variável bate com a constante — renomear uma sem a outra travaria o
DEPLOY, com o EasyPanel mostrando build verde e o contêiner não subindo, que é
o mesmo modo de falha do `alembic heads`.

**O hábito que vale desde já e não custa nada** — antes de migration ou script,
imprimir para onde se está apontando:

```
cd backend && python -c "from app.core.config import get_settings; print(get_settings().database_url.rsplit('@', 1)[-1])"
```

Se sair host que não é `localhost`, o próximo comando fala com produção.

Ver `desenvolvimento-local.md` e `docs/fechar-banco-para-a-internet.md` — o
banco estar alcançável da máquina do desenvolvedor é a outra metade disto.

# Pendências conhecidas

## Dívidas com gatilho — escolhas conscientes, não esquecimentos

Saíram da auditoria de agosto/2026. Cada uma foi decidida com o custo na mão;
o que está escrito é **quando revisitar**, para que a decisão não vire hábito
por inércia.

| Dívida | Por que ficou assim | Revisitar quando |
|---|---|---|
| ~~**Chat sem backplane**~~ | **Quitada em 27/08/2026** — ver "Chat em mais de um worker" abaixo. O `--workers 1` fica por estágio, não por impedimento. | — |
| **O backplane perde mensagem durante a reassinatura** | Redis pub/sub não guarda nada: não há replay, confirmação nem cursor. Se a assinatura de um worker cair, o que os outros publicarem naquela janela não chega a ele. A mensagem está no banco e aparece num F5 — mas ninguém sabe que precisa dar F5. | O readiness mostrar reassinatura frequente, ou alguém relatar mensagem que não apareceu. A saída é Redis Streams, que tem posição de consumidor — bem mais complexidade. |
| **Protocolo por leitura-e-escrita** | A ordenação passou a ser numérica, o que remove a trava do 10.000º chamado. A corrida entre dois cadastros simultâneos continua mitigada por retentativa, não eliminada. | Colisão de protocolo começar a aparecer no log. A saída é uma sequência do PostgreSQL por ano — que resolve os dois de uma vez. |
| **Prazo de resposta sem campo por ciclo** | Reabrir renova só o prazo de resolução. A exibição foi corrigida (o chip diz "Respondido" em vez de mentir "Vencido"), mas o ciclo novo não ganha prazo de resposta próprio. | A operação precisar medir a resposta do ciclo reaberto. Exige um campo por ciclo, não por chamado. |
| ~~**Sem MFA para contas de staff**~~ | **Quitada em 26/08/2026** — ver "Segundo fator" abaixo. | — |
| **Access token sobrevive à revogação de sessão** | Ativar ou desligar o segundo fator apaga o refresh, despejando as sessões. Os access tokens já emitidos, porém, valem até o próprio vencimento: a exposição cai de 7 dias para 8 h, não para zero. Fechar de verdade pede um `sessions_valid_after` conferido no `get_current_user`. | Houver incidente real de sessão comprometida — ou o TTL do access subir. |
| **Não existe mais o tempo de espera por um HUMANO** | Consequência aceita da decisão de 28/08/2026 (ver "O que conta como primeira resposta"): com a Helô carimbando, o único tempo gravado é o dela. Quanto o cliente esperou até alguém de carne e osso responder deixou de entrar no banco — e por isso **não volta por filtro nem por relatório**, só por coluna nova. | A operação precisar cobrar prazo da equipe, ou alguém estranhar o indicador vivendo em 100%. A saída é um campo próprio (`sla_first_human_response`), carimbado no mesmo ponto e com a guarda de autor que valia antes. |
| ~~**Escalar não desliga a IA no chamado**~~ | **Quitada em 09/09/2026**, na Etapa 4 da Fase 2 — no mesmo commit em que o teto deixou de ser de falas e virou de trocas, que era o gatilho registrado. `ticket.ai_enabled = False` no caminho de escalada, e vale para os dois jeitos de escalar: o pedido explícito de humano, reconhecido antes do modelo, e a escalada que o próprio modelo pede com a linha `ESCALAR:`. ⚠️ **A consequência aceita ali durou um dia e foi revertida em 10/09**: desligar o `ai_enabled` fechava também o `suggest-reply` e o `summarize` do TÉCNICO, e nos três motivos que não são o pedido do cliente isso tirava a ferramenta dele justamente nos chamados em que a IA já tinha falhado. Hoje quem guarda o estado é `tickets.helo_saiu`, e o `ai_enabled` voltou a ser só o botão de gente — com uma exceção deliberada: no pedido explícito de humano os dois caem, porque ali quem quis sair da IA foi o cliente. Ver "O interruptor da Helô é dela; o `ai_enabled` é de gente" abaixo. | — |
| **Editar um artigo reindexa todos os trechos dele** | Reescrita em 10/09/2026, quando a fonte passou a ser a Base de Conhecimento: a varredura de `helo_indexacao.py` compara o hash do corte do artigo INTEIRO e, se mudou, apaga todos os trechos dele e recria com ids novos, pagando embedding de todos. Corrigir uma linha de contato no manual do Phoebus reembute os 18 trechos, inclusive os 17 idênticos. Hoje custa pouco: o embedding é do serviço próprio (CPU, segundos por artigo), e nada fora da busca referencia `helo_chunks`. | A base crescer a ponto de a varredura pesar, ou — o que torna urgente de vez — a resposta da Helô registrar a citação por `chunk_id`: aí o refaz deixa citação apontando para trecho que não existe mais. A saída é casar trecho a trecho por hash do conteúdo antes de apagar — os iguais mantêm id e embedding, e só `ordem`/`secao` são atualizados. |
| **O `.env` de desenvolvimento aponta para produção** | A suíte está blindada (o `conftest.py` força uma URL falsa) e, desde 10/09/2026, a migration também (o `alembic/env.py` recusa host remoto fora do contêiner). Script avulso, shell e `psql` na máquina do desenvolvedor continuam falando com o banco real. Ver a seção própria acima. | O gatilho registrado — a primeira migration da Fase 2 — chegou e foi atendido pela trava. O próximo é **qualquer script avulso novo que escreva no banco**; o conserto de verdade é o `.env` deixar de guardar credencial de produção. |
| **O trecho genérico domina a busca (hipótese B)** | `6. Passo a Passo para Utilização` do Titan — e o `5.` equivalente do iBlow — fala de operação em geral e vence perguntas de assunto diferente: 4 de 8 numa sondagem livre, incluindo impressora num aparelho sem impressora. O teto de 0,25 tira a maior parte do dano hoje, e num caso conhecido agrava: para *"como coloco o aparelho em português"*, o aspirador sobrevive ao corte e o `8.2 Alterar Idioma` não. Com três manuais dói pouco — quase toda pergunta fora do manual já não devolve nada. | **Quando houver manual técnico para mais de três produtos.** Aí o aspirador passa a competir com candidatos legítimos dentro do teto, e o dano deixa de ser contornado por ele. O conserto é do lado do trecho — cortar aquele mais fino, ou tirá-lo da base —, e NÃO do corte de todo mundo: a hipótese A foi medida e caiu, os trechos curtos são os que mais acertam. |
| **O teto de 0,25 depende do acervo** | Registrada em 10/09/2026. O número foi medido em 09/09 contra 74 trechos de 8 arquivos (margem de 0,009) e remedido em 10/09 contra 46 trechos de 3 artigos (margem de 0,007): mudou a fonte, mudou a margem, e ninguém mexeu no número. Com o suporte escrevendo artigos, o acervo vai continuar andando e o teto anda junto sem que nada quebre — a falha dele é silenciosa nas duas direções: acerto virando escalada, ou trecho errado passando. O método, as 40 perguntas e o viés (as 27 com resposta foram escritas por quem sabia a resposta; os acertos preservados são o melhor caso) estão em "Como remedir", na seção do teto. | **O acervo indexado mudar de ordem de grandeza** (46 trechos em 10/09; chegando às centenas, remedir), **ou entrar artigo de produto que hoje não tem manual** (Deimos, EBS-010, Mark X, Mercury) — as 40 perguntas não têm nenhuma sobre eles, então remedir inclui escrever perguntas para esse produto. Trocar o modelo de embedding invalida a medição inteira e também é gatilho. |
| **Contador de artigo útil sem voto identificado** | `POST /kb/articles/{id}/feedback` incrementa sem registrar quem votou; o mesmo usuário incrementa em laço. Não vaza nada. | O número for usado para decidir alguma coisa. |
| **O chamado não sabe quem é o cliente quando o staff o abre** | Medido em 18/09/2026: `Ticket` tem exatamente duas FKs para `users` — `creator_id` e `assignee_id` —, `TicketCreate` não tem campo de destinatário e `creator_id = actor.id` é incondicional. Quando um técnico abre chamado em nome de alguém (prática que o próprio código reconhece em comentário), **o cliente real fica sem vínculo nenhum**: some da listagem dele, leva 404 no detalhe, no chat e nos anexos, e a pesquisa de satisfação fica travada. Na mesma medição: 23 chamados, 4 abertos por staff, **os 4 já fechados e nenhum ativo**. Por isso a telefonia sai com o caminho barato — a ligação só aparece quando o criador do chamado é `role=client`, e nos demais a ação fica indisponível com motivo, em vez de discar para a pessoa errada. | **Antes de suportar formalmente a abertura de chamado por staff em nome de um cliente.** A saída é um `requester_id`/`client_id` explícito no chamado, com migration e backfill do histórico — e aí ele passa a ser a fonte do telefone da ligação, no lugar do criador. |
| **Antivírus aceita quando está fora do ar** | Bloquear upload com o ClamAV indisponível derrubaria o anexo por falha de infraestrutura. Hoje o estado é reportado, não mais silencioso, e há script de revarredura. | O ClamAV estiver no ambiente e estável — aí bloquear passa a custar pouco. |


Coisas que os documentos de Requisitos preveem e que **não estão implementadas**.
Nenhuma delas foi pedida pelo cliente até agora — estão aqui para não se
perderem.

### Não há fila de tarefas assíncronas

Deixou de ser pendência em 25/08/2026: o Celery que estava no repositório nunca
executou nada e foi removido (ver "Por que a rotina roda dentro da API"). O que
precisa rodar sozinho roda dentro do processo da API.

Se um dia aparecer trabalho pesado o bastante para justificar — algo que não
caiba numa rodada de hora em hora, ou que não possa competir com as requisições
pelo mesmo processo — aí sim vale subir uma fila de verdade. A decisão de qual
ferramenta fica em aberto de propósito: escolher agora, sem o problema na mão,
foi exatamente o que produziu o pacote morto.

### Telefonia (API4COM): o que já está fechado com o fornecedor

Nada da integração está implementado — o que existe é a Fase 1A do telefone,
acima. O que segue é contrato **confirmado**, registrado para que ninguém
precise redescobrir, e para que a implementação não copie o material
desatualizado que circula.

| Item | Valor confirmado |
|---|---|
| Autenticação | `Authorization: <token>` — **o token cru, SEM o prefixo `Bearer`**. Confirmado pelo suporte e medido na nossa conta (`GET /users/me` → HTTP 200). |
| Endpoint de chamada | `POST /calls`. O `POST /dialer` está **descontinuado** na documentação oficial e devolve um id que não é o da chamada. |
| Payload | `caller`, `called`, `extension`, `metadata` — o `{extension, phone, metadata}` que aparece em material antigo é o da rota morta. |
| `webhookVersion` | literal **`"1.8"`**, sem o prefixo `v`. ⚠️ A nossa conta tem uma integração armazenada como `v1.8`; o valor a ENVIAR é `1.8`, confirmado pelo suporte. |
| `webhookConstraint` | `{"metadata": {"gateway": "HelpHS"}}` — recomendação direta do suporte para esta integração. A chave é definida por quem chama (a integração `pipedrive` da mesma conta usa `api4comGateway`), então o `POST /calls` precisa enviar `metadata.gateway = "HelpHS"` **exatamente assim**, ou a entrega para em silêncio. |
| Eventos | `channel-answer` e `channel-hangup`, e só esses dois. |

⚠️ **Duas integrações da conta estão sem filtro** (`webhook` com
`webhookConstraint` nulo, `oficina` com `{}`). Se constraint vazia significar
"sem filtro", os webhooks das chamadas do HelpHS também serão entregues nesses
endpoints, que pertencem a outros sistemas da empresa. É mais um motivo para o
`metadata` não levar nome, e-mail, CPF nem texto do chamado — só identificadores.

**Quatro coisas seguem em aberto, e nenhuma pode ser resolvida por suposição:**

- **o formato aceito em `POST /calls.called`** — a documentação mostra
  `4833328530` e `+554833328530` para a mesma rota, e o suporte não definiu
  canônico. O que `GET /calls` devolve descreve o que a API emitiu, não o que
  ela aceita;
- **o fuso semântico dos webhooks** — os exemplos vêm sem offset. O `GET
  /calls` da nossa conta devolve ISO com offset explícito, mas isso é outro
  contrato. Gravar data de webhook antes de resolver isto é erro de três horas
  que não levanta exceção nenhuma;
- **o payload completo de `channel-answer`** — o evento existe, exemplo
  público não;
- **autenticação de origem do webhook** — não há HMAC, assinatura, secret nem
  faixa de IP documentados. A proteção terá de ser desenhada do nosso lado.

### Fase 2A da telefonia: a fundação existe e não liga para ninguém

`backend/app/services/api4com.py` sabe fazer `POST /calls`. **Nenhum router,
lifespan ou laço de fundo o importa**, e isso é o desenho, não uma etapa que
faltou: em produção a 2A continua incapaz de iniciar ligação por ausência de
consumidor. Quem ligar o primeiro precisa ter lido as quatro categorias de erro
abaixo.

**A integração nasce desligada.** `API4COM_ENABLED=false`, pelo mesmo raciocínio
do `HELO_ENABLED`, só que mais forte: ligada, ela disca para o telefone de uma
pessoa.

| Variável | Default | Papel |
|---|---|---|
| `API4COM_ENABLED` | `false` | interruptor |
| `API4COM_TOKEN` | vazio | credencial, **`SecretStr`** |
| `API4COM_BASE_URL` | `https://api.api4com.com/api/v1` | configuração com padrão, critério do `DEEPSEEK_BASE_URL` |
| `API4COM_TIMEOUT_SECONDS` | `15` | teto de UMA tentativa |

`API4COM_CALLER` e `API4COM_EXTENSION` **não existem**. O número de origem tem
formato ainda não definido com o fornecedor, e o ramal é identidade do agente —
dado de usuário, não configuração global. Os dois são argumentos de
`create_call` até a Fase 2C resolver a origem deles.

#### Três divergências deliberadas do resto da casa

**1. `SecretStr`, e é o único do projeto.** `smtp_password`,
`deepseek_api_key` e `mfa_secret_encryption_key` são `str` cru e saem por
extenso em `repr`, `str`, `model_dump` e `model_dump_json` — o que os segura
hoje é disciplina de quem escreve log, não o tipo. Segredo novo não precisa
nascer com essa dívida. O valor é lido por `get_secret_value()` num único
ponto: a montagem do `Authorization`. Um teste documenta o ESCOPO da
divergência e cai se alguém converter os antigos sem conversar sobre migração
de painel.

**2. A validação de boot roda também em dev e testing.** Todas as outras
validações do `model_post_init` saem cedo em `is_development or is_testing`,
porque protegem contra subir PRODUÇÃO com valor de desenvolvimento — e em dev
aquele valor é o certo. Esta protege contra ligar a integração sem ter como
autenticar, o que está errado em qualquer ambiente. Por isso a chamada fica no
**topo** do `model_post_init`, antes do `return`; há teste que prende essa
posição.

**3. A exceção de configuração NÃO é `ValueError`.** Enquanto era, o pydantic a
embrulhava num `ValidationError` — que imprime `input_value=` com o dicionário
de entrada **truncado no meio**, cabeça e cauda visíveis. MEDIDO no pydantic
2.11.3, com o token vindo do ambiente e outra validação falhando: os 22
caracteres finais do token saíam na mensagem, e iam para o log de boot.
`ConfiguracaoDaTelefoniaInvalidaError` herda de `RuntimeError`, que o pydantic
deixa subir intacta. Consequência: `pytest.raises(ValueError)` não pega esta.

#### Por que nunca pode haver retry em `POST /calls`

É a **primeira escrita externa** do HelpHS. Todas as outras chamadas que saem
daqui são leitura (ViaCEP, BrasilAPI) ou idempotentes na prática (DeepSeek,
embedding). Escrita externa traz o problema que nenhuma delas tem: quando a
resposta não volta, não dá para saber se o outro lado agiu — e aqui "agir"
significa tocar o telefone de alguém.

Medido no `httpx` 0.28.1 / `httpcore` 1.0.9 instalados:

- `retries` default é **0** nos dois transportes;
- o laço de retentativa vive em `_connect()` e captura estritamente
  `(ConnectError, ConnectTimeout)` — cobre TCP/TLS, e **nenhum byte de
  requisição é escrito ali**. `ReadTimeout`, 5xx e 429 nunca são repetidos,
  nem com `retries` alto;
- a **única** porta de duplicação é o redirect: `follow_redirects` vem `False`,
  mas 307 e 308 preservam método e corpo (`_redirect_method` só rebaixa para
  GET em 301/302/303). Ligar redirect no cliente da telefonia criaria duas
  ligações com um clique.

Por isso `retries=0` e `follow_redirects=False` vão **explícitos**, mesmo sendo
os defaults. `httpcore` é transitiva e **não está pinada** (só `httpcore==1.*`
pelo metadado do httpx): pinar foi descartado para não mexer no gate de
dependências, e quem avisa se um rebuild mudar o comportamento é o teste que
prende `await_count == 1`.

#### As quatro categorias de erro respondem sempre a mesma pergunta

**A ligação saiu?**

| Situação | A ligação saiu? | Exceção |
|---|---|---|
| flag desligada | não houve tentativa | `Api4ComDesligadaError` |
| `ConnectError`, `ConnectTimeout` | não houve comunicação HTTP útil | `Api4ComIndisponivelError` |
| **HTTP 4xx** | rejeição HTTP confirmada | `Api4ComRecusadaError` |
| **HTTP 5xx** | ⚠️ **INDETERMINADO** | `Api4ComResultadoIndeterminadoError` |
| **HTTP 3xx** | ⚠️ **INDETERMINADO** | `Api4ComResultadoIndeterminadoError` |
| transporte após conexão | ⚠️ **INDETERMINADO** | `Api4ComResultadoIndeterminadoError` |
| 2xx com corpo ilegível | ⚠️ **INDETERMINADO** | `Api4ComResultadoIndeterminadoError` |

⚠️ **5xx não significa que a chamada não ocorreu, e essa é a linha que custa
caro.** O fornecedor pode ter recebido o POST, disparado a ligação e só então
quebrado por dentro: o 500 descreve o estado do servidor dele, não o do telefone
de quem ia receber. A primeira versão deste módulo tratava todo não-2xx como
recusa — o que autorizaria uma segunda tentativa e tocaria o telefone duas
vezes. `Api4ComRecusadaError` é **só 4xx**, e a afirmação que ela faz é sobre a
REQUISIÇÃO ter sido rejeitada, nunca sobre o telefone.

3xx pela mesma razão: com `follow_redirects=False` o redirect chega sem ter sido
seguido, e um redirect inesperado num endpoint de escrita não é sucesso nem
recusa de domínio. Nunca seguir, nunca reenviar.

O resto do indeterminado leva demais `TransportError` (leitura, escrita,
protocolo, pool, proxy). `PoolTimeout` e `ProxyError` entram aí de propósito —
dá para argumentar que a requisição não saiu, mas o argumento depende de
detalhe interno de biblioteca não pinada, e o custo de errar para o lado
otimista é ligar duas vezes para a mesma pessoa.

**Em TODOS os casos: zero retry automático de `POST /calls`.**

Só a `Api4ComRecusadaError` guarda atributo, e é um `status_code`. **Nenhuma
guarda `Response` ou `Request`**: o objeto do httpx carrega os cabeçalhos por referência, e uma
exceção que o segurasse levaria o `Authorization` para dentro de qualquer
traceback. Pelo mesmo motivo a tradução usa `from None`.

#### `metadata` é fechado, e o motivo não é zelo

O corpo leva exatamente `{"gateway": "HelpHS"}`, sem parâmetro que permita
acrescentar nada — não dá para sobrescrever `gateway` porque não há por onde
passar. Duas integrações desta conta no fornecedor estão **sem filtro**
(`webhookConstraint` nulo e `{}`), e se constraint vazia significar "sem
filtro", os webhooks das nossas chamadas serão entregues a endpoints de outros
sistemas da empresa. Enquanto isso não for resolvido, `metadata` não carrega
nome, e-mail, documento, telefone nem texto de chamado.

#### `diagnose=False` nos três sinks do loguru

Não é da telefonia; é consequência de introduzir um segredo externo. O default
do loguru é `diagnose=True`, que acrescenta ao traceback o **valor das
variáveis locais** citadas na linha exibida de cada quadro. Uma função que
monte um `Authorization` passaria a imprimir a credencial em qualquer exceção
que atravessasse aquele quadro. O patcher de `_SEGREDO_NA_QUERY` não alcança
isso: ele reescreve `record["message"]`, e o bloco de diagnóstico é montado
depois, ao formatar a exceção. `backtrace` ficou como estava — ele mostra os
quadros e não imprime valor nenhum.

#### O que a 2A NÃO resolve

`create_call` repassa `caller`, `called` e `extension` **byte a byte como
chegaram**. Não normaliza telefone, não acrescenta nem remove `+55`, não valida
regra brasileira: o formato aceito em `called` segue em aberto com o fornecedor
(ver a seção acima), e transporte que "conserta" o número cria uma segunda
fonte de verdade competindo com `app/utils/telefone.py`.

`Api4ComCreateCallResult` tem `status_code` e `payload`, e **nenhum campo para
o identificador da chamada**: o schema da resposta de `POST /calls` não está
confirmado. Inventar `id`, `call_id` ou `data.id` criaria um contrato que o
fornecedor não prometeu. **A Fase 2B segue bloqueada até haver evidência.**

### Fase 2B: a telefonia ganha memória, e o contrato do `id` sai do escuro

A Fase 2A dizia, em código e em documento, que o schema da resposta de
`POST /calls` "não estava confirmado". **Estava.** A documentação oficial
baixada na Fase 0 responde a pergunta, e ninguém a tinha lido até o fim. Fica
registrado porque o erro foi de método, não de fato: tratamos por "não
determinado" algo que estava escrito, e por isso a 2B nasceu bloqueada sem
precisar.

#### O que a documentação oficial diz

`POST /calls`, seção **Respostas / 200**:

```json
{ "status": "200", "message": "successful request", "id": "1PkXhmBsYAvr9legLB2d7BimT0Q" }
```

E a prosa da mesma página: *"o `id` retornado por este método corresponde ao
mesmo ID da chamada exibido na Lista de Chamadas, podendo ser usado tanto para
consultas quanto para cancelar a chamada."* A página do
`POST /calls/{id}/hangup` confirma do outro lado: parâmetro de caminho `id`,
**tipo `string`, obrigatório**.

Portanto está estabelecido: **campo `id`, no topo do JSON, tipo `string`,
mesmo identificador usado no hangup.**

#### ⚠️ O formato NÃO está estabelecido, e é por isso que ele é opaco

Dois documentos oficiais mostram formatos diferentes **para o mesmo campo**:

| Fonte | Exemplo | Forma |
|---|---|---|
| Referência da API (`clickToCall`, `hangupCall`) | `1PkXhmBsYAvr9legLB2d7BimT0Q` | 27 caracteres, base62 |
| Guia "Integração utilizando Webphone próprio" | `bdf199fa-f85b-4378-80cd-0ac28c1355e9` | UUID textual, 36 |
| Payload do webhook `channel-hangup` | `2ee13fa4-975c-499d-bbb8-5177ff418316` | UUID textual, 36 |

Consequência direta, e é a decisão de schema da 2B: a coluna é **`TEXT`**, não
`uuid` nativo. O tipo nativo do PostgreSQL **rejeitaria o primeiro formato**. O
HelpHS trata o identificador como **string opaca**: não valida formato, não
valida comprimento, não transforma, não normaliza caixa nem espaço. Há teste
que grava `"  com-espaco  "` e exige que volte igual.

Estreitar depois, quando o fornecedor confirmar, é uma linha. Ter quebrado em
produção por validar o que ele nunca prometeu, não.

#### Só 200 é sucesso. 201 e 202 são indeterminados

A documentação publica **apenas 200** como criação aceita. Aceitar 201 seria
assumir contrato que o fornecedor não escreveu — e se ele responder 202 com o
corpo em outro formato, teríamos aceitado um identificador que não sabemos ler.
A pergunta está na lista enviada ao suporte.

A classificação completa do `services/api4com.py` passa a ser:

| Situação | A ligação saiu? |
|---|---|
| flag desligada | não houve tentativa |
| `ConnectError` / `ConnectTimeout` | não houve comunicação HTTP útil |
| HTTP 4xx | rejeição HTTP confirmada |
| **HTTP 200 com `id` legível** | **SIM — e temos o identificador** |
| HTTP 200 sem `id` utilizável | INDETERMINADO |
| HTTP 201 / 202 / outro 2xx | INDETERMINADO |
| HTTP 3xx e 5xx | INDETERMINADO |
| transporte após conexão | INDETERMINADO |

Para o 200, exigimos: corpo é JSON, é objeto, tem `id`, `id` é `str`, e tem
pelo menos um caractere não-branco. Qualquer falha vira **indeterminado**, e
não erro de contrato — houve HTTP 200, então o fornecedor provavelmente criou a
chamada; o que falhou foi nossa capacidade de saber **qual**. Chamar isso de
falha autorizaria uma segunda tentativa.

#### `Api4ComCreateCallResult` encolheu

Era `(status_code, payload)`; virou `(status_code, provider_call_id)`. A 2A
devolvia o corpo inteiro porque não sabíamos qual campo importava. Agora
sabemos, e carregar o resto seria mais um lugar por onde `message`, metadata ou
dado de terceiro poderiam vazar para um log. Provado por busca que não havia
consumidor de `.payload` antes de remover.

#### `ticket_calls`: uma linha é uma TENTATIVA

O nome importa. A linha nasce **antes** de existir chamada, e pode terminar sem
que jamais saibamos se existiu.

| Coluna | Tipo | Por quê |
|---|---|---|
| `id` | UUID | identidade interna; é o que a 2C poderá mandar no `metadata` para reconciliar |
| `ticket_id` | UUID, FK `CASCADE` | como as outras sete filhas de `tickets` |
| `initiated_by_id` | UUID, FK `SET NULL`, nulável | a tentativa é fato do chamado e sobrevive à exclusão da conta; quem some é a autoria |
| `provider_call_id` | **TEXT, nulável, índice único** | string opaca; NULL é estado legítimo e frequente |
| `creation_status` | String(20) + CHECK | ver abaixo |
| `provider_http_status` | Integer, nulável | NULL quando não houve resposta — a diferença entre "não respondeu" e "respondeu 500" |

**Por que `provider_call_id` aceita NULL:** porque o estado mais perigoso da
integração é justamente aquele em que não temos o identificador. Uma coluna
NOT NULL tornaria o indeterminado **impossível de registrar** — e é ele que
precisa ser reconciliado, e o que impede uma segunda tentativa às cegas.

**O CHECK que existe:** `creation_status <> 'confirmed' OR provider_call_id IS
NOT NULL`. Confirmada sem identificador seria um registro que afirma saber da
chamada sem ter como apontá-la, nem para consultar nem para desligar. **O
inverso não é imposto**: ter identificador sem estar `confirmed` é estado
legítimo que a reconciliação da 2D pode produzir.

#### `creation_status` é String com CHECK, e não enum nativo

Decisão de custo, com os dois precedentes desta casa na mão: acrescentar valor
a enum nativo exige `ALTER TYPE ... ADD VALUE`, que aqui não pode ser citado em
DDL posterior porque o alembic roda a cadeia inteira numa transação só; e
remover valor custa recriar o tipo e converter toda coluna que o usa, como a
`f2a3b4c5d6e7` teve de fazer com `ticketcategory`. Esta máquina de estados
**ainda vai crescer na 2D**.

Os cinco estados descrevem o **resultado da criação**, não o estado telefônico:
`pending`, `confirmed`, `rejected`, `unavailable`, `indeterminate`. `ringing`,
`answered` e `hangup` chegam pelo webhook e são outra coluna, em outra fase — há
teste que recusa esses três valores nesta.

#### O que a 2B deliberadamente NÃO guarda

Telefone, `caller`, `extension`, cabeçalho, corpo da requisição, corpo da
resposta, `message` do fornecedor, metadata, URL de gravação. O telefone
canônico continua em `users.phone`.

A garantia não é disciplina: **nenhuma função de `services/telefonia.py` aceita
esses dados como parâmetro**, e há teste que varre as assinaturas e a lista de
colunas procurando por eles. Não há como persistir por descuido.

#### `services/telefonia.py` não conhece o transporte

Ele não importa `httpx` nem `api4com.py` — provado por AST em teste. É o mesmo
arranjo de `helo_embedding.py` (cliente) e `helo.py` (domínio). A orquestração
`banco → API4COM → banco` é da Fase 2C; a máquina de estados fica provada antes
de haver efeito externo para depurar junto.

#### Ainda em aberto, e registrado

- **Idempotência: NÃO DOCUMENTADA / NÃO CONFIRMADA.** A varredura em toda a
  documentação não encontrou `Idempotency-Key`, `externalId` nem
  `clientReference` — mas ausência na documentação não é prova de inexistência.
  Sem resposta do fornecedor: nada de chave de idempotência inventada, nada de
  retry automático. É pergunta aberta para a 2C.
- **Formato e comprimento do `id`** — pergunta enviada ao suporte.
- **Status 201/202** — idem.
- **`metadata` com o UUID interno da tentativa**: a documentação afirma que a
  metadata enviada em `POST /calls` chega no webhook, o que abriria a
  reconciliação do indeterminado. **Não implementado na 2B** — o payload segue
  só com `gateway`. Decisão da 2C.
- **Duplo clique e concorrência**: a 2B não cria unique de `pending` por
  chamado, lock nem rate limit. A tabela só precisa conseguir representar o
  estado; a proteção é decisão da 2C, junto com o endpoint.

#### Correção ao que a Fase 0 registrou sobre o formato de `called`

A sonda anota que "a doc mostra três grafias para o mesmo número". Separando
por rota, isso não se sustenta:

| Grafia | Onde | Natureza |
|---|---|---|
| `4833328530` | `POST /calls` (rota atual), campo `called` | **entrada documentada** |
| `+554833328530` | `POST /dialer` **descontinuada**, campo `phone` | rota morta, campo diferente |
| `04833328530` | payload do webhook, campo `called` | **saída**, não entrada |

A rota atual mostra **uma** grafia. Um exemplo não é especificação — a pergunta
segue na lista do suporte —, mas é bem mais forte que "três grafias
contraditórias".

### Antivírus (ClamAV) não está no ambiente

O upload de anexo passa por varredura antivírus antes de gravar
(`backend/app/services/antivirus.py`). Como o serviço **não existe no EasyPanel**,
o resultado da varredura vem como `unavailable` e o arquivo é aceito assim mesmo,
marcado como não escaneado (`virus_scanned = false` na tabela `attachments`).

Ou seja: **nenhum anexo enviado hoje é verificado contra vírus**. Nada trava, mas
arquivo malicioso enviado por um cliente entra sem checagem.

Decidido em 05/08/2026 manter assim por ora e revisar depois. Para ligar, basta
subir um serviço `clamav/clamav:latest` e apontar `CLAMAV_HOST`/`CLAMAV_PORT` —
o código já está pronto, não precisa de alteração.

### `tsc --noEmit` no frontend dá falso verde

O `frontend/tsconfig.json` é um *solution file* (`"files": []` + references), então
`npx tsc --noEmit` **termina sem saída mesmo com erros de tipo**. Quem confiar
nele passa direto por erro que derruba o build do EasyPanel.

Para validar de verdade: **`npm run build`** (`tsc -b && vite build`), o mesmo
comando do Dockerfile. Aconteceu em 11/08/2026 — um deploy quebrou com um
import faltando e um conflito de tipos que o `--noEmit` não acusou.

O CI **ainda roda o comando inútil** no passo "TypeScript check"
(`.github/workflows/ci.yml`), mas o risco está neutralizado: o passo de Build,
logo depois, roda o `tsc -b` de verdade e reprova o pipeline. Ou seja, o passo
existe como teatro — trocar por `tsc -b` seria uma linha e evitaria que alguém
leia o verde dele como garantia.

### Cobertura de testes desigual

A cobertura do backend é **concentrada**: alta na média e baixa em módulos
específicos, sendo o `groups.py` o ponto fraco persistente.

O número atual **não fica escrito aqui** — um percentual em documento nasce
certo e vira mentira sozinho, sem ninguém mexer nele. O valor por arquivo sai
do `term-missing` a cada execução (`pytest` a partir de `backend/`), e o CI
reprova abaixo de 80% (`--cov-fail-under=80` no `backend/pyproject.toml`).

### O prazo de resposta não é renovado na reabertura

Ver "Ciclo de encerramento do chamado". A exibição foi corrigida, mas o ciclo
novo continua sem prazo de resposta próprio. O desenho provável é um campo por
ciclo em vez de um por chamado — decisão de produto, não conserto.

### SMTP de produção não está configurado

Sem ele não há confirmação de e-mail nem recuperação de senha em produção.
Duas coisas esperam por isso:

- **ligar `EMAIL_VERIFICATION_ENABLED`** (ver "Acesso");
- **resposta neutra no cadastro.** Hoje o cadastro com e-mail já existente
  devolve `409`, o que permite descobrir quem tem conta. O desenho aprovado é
  responder `201` neutro e mandar um e-mail de "você já tem conta" — e ele
  depende do SMTP existir, senão o usuário legítimo fica sem conta e sem aviso.

O envio em `forgot-password` e no reenvio de confirmação **já sai em segundo
plano**, então o tempo de resposta não vai denunciar quais e-mails existem
quando o SMTP entrar. O cadastro ainda envia inline; quando a resposta neutra
for implementada, o envio precisa ir junto para segundo plano, senão a
neutralidade nasce furada pelo relógio.

### Rate limit de login é um balde único

O `start.sh` sobe o uvicorn sem autorizar proxy nenhum, e o padrão do uvicorn
faz o contador do rate limit enxergar sempre o **IP do proxy** do EasyPanel. Na
prática, `RATE_LIMIT_LOGIN=5/15minutes` vale para o sistema inteiro: cinco
senhas erradas de qualquer pessoa travam o login de todos.

Ligar `FORWARDED_ALLOW_IPS` resolve, **mas só depois de fechar a publicação da
porta 8000**. Com a porta aberta na internet, autorizar cabeçalhos de proxy
deixa qualquer um forjar o `X-Forwarded-For` e furar o limite por completo —
pior do que o balde único. A ordem é: fechar a porta, depois autorizar.

### `PATCH /kb/articles/{id}` com `null` explícito dá 500 — defeito anterior à Helô

**Não foi introduzido pelo trabalho da Helô**, e está escrito aqui para o
próximo a encontrar não achar que foi. O laço que causa o defeito está no
`main` desde o CRUD da Base (`3db616c`, 06/04/2026); a Fase 2 só acrescentou
`helo_pode_ler` à lista de campos que ele atinge, e ele atinge os outros igual.

Todos os campos de `KBArticleUpdate` são `X | None = None`, então a validação
aceita `{"campo": null}`. O `model_dump(exclude_unset=True)` mantém o `null`
explícito — ele foi enviado —, e o laço de `setattr` grava `None` no artigo.
Todas as colunas de `kb_articles` são NOT NULL, e a aplicação não tem tratador
de `IntegrityError`:

| Campo | Onde falha |
|---|---|
| `title` | antes do banco: `slugifica(None)` chama `.lower()` em `None` |
| `content`, `category`, `tags`, `status`, `helo_pode_ler` | no commit: violação de NOT NULL |
| `product_ids` | **não falha**: o `pop` trata `null` como "não enviado" |

Nos dois casos nada é gravado: é erro 500, não dado corrompido. **Lido no
código em 10/09/2026, não medido.** O conserto vale para a rota inteira, não
para `helo_pode_ler` sozinho — recusar `null` explícito no schema, ou
descartar os `None` antes do laço.

### Quatro dos sete produtos não têm manual técnico

> **Superado em parte em 15/09/2026.** O escopo mudou: os sete aparelhos
> ganham manual técnico novo, escrito pela assistência técnica, e a Helô fica
> em `HELO_MODO=triagem` até os sete estarem publicados — ver "O modo da Helô".
> O "ela saúda, o cliente responde, ela escala" abaixo vale só no modo
> `completa`; em triagem a resposta do cliente recebe o encerramento.

Constatado em 09/09/2026, ao rodar as primeiras buscas de verdade. **É decisão
de escopo do cliente, não pendência de código** — fica registrado para ninguém
tratar como defeito nem "consertar" publicando a ficha comercial na Base. A
tabela é do acervo de manuais de 09/09; desde 10/09 só os três manuais técnicos
entram, como artigo.

| Produto | Manual técnico | Ficha comercial |
|---|---|---|
| Titan | 15 trechos | — |
| Phoebus | 18 trechos | — |
| iBlow 10 Pro | 12 trechos | 8 trechos |
| Deimos | **nenhum** | 6 trechos |
| EBS-010 | **nenhum** | 5 trechos |
| Mark X | **nenhum** | 6 trechos |
| Mercury | **nenhum** | 4 trechos |

Desde 10/09 a base é a Base de Conhecimento, e ficha comercial não entra nela:
tem preço e promessa de venda, e é justamente o que não pode virar procedimento
técnico. Então, para um chamado dos quatro últimos, a base vem vazia **em todo
turno** — a menos que exista artigo publicado sem produto vinculado que
responda: ela saúda, o cliente responde, ela escala. É o comportamento correto.
O efeito prático é que a Helô só ajuda de fato em três dos sete aparelhos até
existir manual dos outros.

### Duas contradições nos manuais esperam decisão do suporte técnico

Levantadas em 08/09/2026, ao preparar a base da Helô (Fase 2). **Não são
decisão de código:** ninguém no desenvolvimento sabe qual dos números está
certo, e escolher no chute seria escolher por ela.

Por que importa: busca vetorial não resolve contradição. Ela traz os dois
trechos e o modelo escolhe um, ou mistura — e a Helô responde **com a fonte
citada**, que é pior do que responder sem fonte, porque parece conferível.

| Contradição | O que a documentação diz |
|---|---|
| **Titan: memória e autonomia** | "Memória: até 8.000 testes" e "Autonomia: até 8.000 testes por carga", num aparelho com bateria Ni-MH de 400 mAh. O segundo número parece cópia do primeiro — uma bateria dessas dificilmente sustenta 8.000 sopros por carga. Enquanto não houver resposta, a Helô pode prometer autonomia que o aparelho não tem. |
| **Canal de contato oficial** | Três telefones — (11) 4007-1507, (81) 9 9118-9612, (81) 98177-1177 — e dois e-mails, `cs@` e `sac@`. Não há como saber qual é o canal para o cliente sem perguntar. |

**As outras contradições do corpus não precisam de decisão**, e vale registrar
por quê para ninguém reabrir: todas elas são ficha comercial contra manual
técnico — o aplicativo do iBlow10 Pro (Health App na ficha, i-SOBER no
manual), os dois aplicativos do Deimos, o tempo de análise do iBlow10 Pro
(5 s na ficha, 2 s no manual). Como as fichas comerciais ficam **fora da busca
técnica** por decisão da Fase 2, esses pares nunca chegam juntos à Helô. Se um
dia existir uma Helô comercial, elas voltam a valer.

## `backend/scripts/` vai para a imagem de propósito

O `.dockerignore` exclui `tests/` e **não** exclui `scripts/`. Isso não é
descuido: os scripts avulsos são operados **pelo terminal do container**, e é lá
que eles precisam existir.

É o caso do `redefine_senha.py` quando alguém perde a senha e o SMTP de produção
ainda não entrega o "Esqueci minha senha"; do `desliga_mfa.py` quando some o
celular com o segundo fator; do `diagnostico_empresa_aparelho.py` antes de uma
migration que cria índice único. Nenhum deles roda no boot, nenhum é importado
por módulo de `app/` — mas todos são rodados contra o banco real, e o terminal
do container é o único lugar onde as credenciais de produção já estão no
ambiente.

Tirá-los da imagem trocaria isso por copiar script e credencial para uma máquina
de quem administra, na hora do incidente. Pior em todo sentido.

### O que isso obriga

**Estar na imagem não é estar no caminho de execução, e a diferença importa na
hora de classificar um alerta.** Nenhum script é alcançável por requisição: não
há rota, não há import a partir de `app/`, e o `start.sh` não os toca. Um alerta
de análise estática em `scripts/` é sempre sobre o que acontece quando *uma
pessoa* roda aquilo à mão.

O que não muda é a régua do conteúdo: **script que vai à imagem é código que
chega a produção**, então nada de segredo escrito, nada de valor de exemplo que
alguém possa copiar, e nada de saída que revele credencial. Foi o que motivou o
`testa_smtp.py` a trocar a máscara parcial — que imprimia os 6 primeiros e os 4
últimos caracteres da chave — por uma impressão digital que não revela caractere
nenhum. Máscara pela metade continua sendo vazamento, e o mais enganoso é que a
saída *parece* segura.
