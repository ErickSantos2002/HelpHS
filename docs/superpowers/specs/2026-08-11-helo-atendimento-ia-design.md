# Helô — atendimento por IA no HelpHS

**Data:** 11/08/2026
**Status:** validado com o cliente em 26/08/2026 — em construção
**Fases:** 3 — este documento detalha a Fase 1 e esboça as seguintes
**Emendado em 31/08/2026 (`71f84cb`):** o provedor de LLM mudou. Onde este
documento diz **OpenAI (`gpt-4o-mini`) com fallback Anthropic**, leia
**DeepSeek, provedor único e sem fallback** — decisão do Rickelme. A
integração continua pronta e assíncrona; o que deixou de existir é a segunda
tentativa em outro provedor. A estimativa de custo mais abaixo foi calculada
sobre o preço do `gpt-4o-mini` e **não foi refeita**: o número de chamadas por
chamado (1 a 2) continua valendo, o preço por chamada não. O endpoint e o nome
do modelo da DeepSeek ainda não foram conferidos contra a documentação oficial
— são configuração (`DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`), não constante.

---

## Decisões do cliente — 26/08/2026

As 12 perguntas do fim deste documento foram respondidas. O que ficou:

| Tema | Decisão |
|---|---|
| Nome | **Helô** (a pendência de grafia fecha aqui) |
| Tom | Apresenta-se pelo nome e trata o cliente pelo primeiro nome |
| Perguntas | Três, como desenhado |
| Fora do horário | Mantém a promessa do próximo dia útil |
| Feriado | **Ignorado** — o motor de SLA segue pulando só sábado e domingo |
| Status | **Nasce em `open`; vai para `in_progress` quando ela fala** |
| Desligar | Global, por CNPJ, por cliente **e por chamado** |
| Fase 2 | Cita a fonte; base própria no banco, separada da KB do HelpHS |
| Certificado, gás, RMA | Ela nunca envia documento — avisa que um atendente vai falar e escala |

### O status novo saiu, e com ele o maior risco da Fase 1

O `ai_handling` **não será criado**. `status` é enum nativo do Postgres, e
acrescentar valor exige `ALTER TYPE ... ADD VALUE` numa migration que roda
sozinha no boot do container — mais 8 arquivos do front que referenciam
status. Era o item 🟠 mais delicado da revisão técnica, e a decisão do cliente
o dissolveu.

Sobrou um ganho não previsto. O desenho original mandava o chamado para
**"Aguardando técnico"** depois da triagem — e esse status **pausa o relógio
do SLA** (`_PAUSE_STATUSES` em `app/utils/sla.py`). O cliente ficaria
esperando um humano com o cronômetro parado, o oposto do que o indicador deve
mostrar. Em `in_progress` o relógio corre.

> ⚠️ **Emendado em 28/08/2026 — o ganho valeu, mas o perigo voltou por outra
> porta.** Tirar o `ai_handling` resolveu a transição da *triagem*, e só ela.
> Em 28/08 foi preciso o `9eeb683` para o mesmo perigo chegando por outro
> caminho: o **cliente responde**, o chamado ainda não tem responsável, e a
> regra o mandava para "Aguardando técnico" do mesmo jeito — parando o
> relógio justamente enquanto ele esperava um humano. Antes da Helô o caso
> quase não aparecia; com ela triando em segundos, passou a atingir **todo**
> chamado novo. A regra passou a exigir `assignee_id`. Quem ler o parágrafo
> acima e concluir que "Aguardando técnico" está resolvido por desenho vai
> deixar de procurar a terceira porta, se houver.

**O preço, registrado para não virar surpresa:** "Em andamento" passa a
incluir chamado sem técnico atribuído — a Helô conversando, ou a triagem
encerrada esperando alguém pegar. Se a coluna for usada como "estou cuidando
disto", ela fica menos confiável. A correção, se incomodar, é um marcador
visual de IA no card — não um status novo.

### Desligar em três níveis

Por **chamado** (o técnico entra e cala a IA ali), por **cliente** e por
**CNPJ**. Os dois primeiros são campos; o terceiro depende de a empresa existir
como entidade confiável — ver
[empresa e aparelho compartilhado](2026-08-26-empresa-e-aparelho-compartilhado-design.md),
que por isso vem antes desta fase.

A chave global já existe: `LLM_ENABLED` (`79ef715`), flag explícita e não
inferida da presença da chave de API — que era exatamente a ressalva 🟡 da
revisão.

### LGPD

O consentimento entra no **aceite dos termos, no cadastro**, deixando claro
que há tratamento por IA. Um detalhe que a decisão não cobre e é o que dá
valor jurídico a ela: **registrar o aceite** — quem, quando e qual versão do
texto. Sem isso não há como provar depois.

### O que já estava pronto quando a validação chegou

- `register_first_response` desacoplado do status (`230d670`) — resolveu o
  🔴 #1 da revisão técnica. Ele nasceu ignorando `is_ai`; em 28/08 o cliente
  pediu o contrário e a fala dela passou a carimbar (ver a seção do SLA)
- `LLM_ENABLED` desliga a IA sem esvaziar as chaves

---

## O problema

Hoje o cliente abre um chamado no HelpHS e espera. Fora do horário comercial,
espera até o dia seguinte sem nenhum sinal de que foi lido. Quando o técnico
enfim abre o chamado, precisa começar do zero: perguntar o que houve, quando
começou, o que já foi tentado.

A Health & Safety já teve uma IA de atendimento — a **Helô**, que atendia no
WhatsApp consultando uma base de conhecimento vetorizada. A proposta é trazê-la
para dentro do HelpHS, onde ela tem algo que nunca teve no WhatsApp: **o
cadastro do cliente e do equipamento já preenchido**.

---

## O que já existe no HelpHS

Vale registrar antes de qualquer estimativa, porque muda o tamanho do trabalho.

| Peça | Situação |
|---|---|
| Integração com LLM | **Pronta** — OpenAI (`gpt-4o-mini`) com fallback Anthropic |
| Campo `is_ai` na mensagem de chat | **Existe no banco** desde a primeira migration |
| Bolha de mensagem da IA no chat | **Já desenhada** — avatar roxo, rótulo "Assistente IA" |
| Artigos filtrados por produto do chamado | **Feito na v1.2.0** |
| Transição automática de status pelo chat | **Existe** |
| Resumo de conversa por IA | **Existe** — botão "Resumir" no chat |

Curiosidade reveladora: a bolha da IA foi desenhada e o campo criado no banco,
mas **nenhuma linha do sistema jamais gravou uma mensagem com `is_ai = true`**.
O lugar da Helô está reservado desde o início do projeto.

**Consequência prática:** a Fase 1 não constrói infraestrutura. Ela liga peças
que já estão no lugar.

---

## O que muda em relação à Helô do WhatsApp

O prompt antigo (v4.0, dezembro/2024) foi escrito para um canal sem cadastro.
Três coisas dele não sobrevivem à mudança de casa:

### 1. Ela para de pedir modelo e número de série

No WhatsApp era obrigatório — não havia como saber. No HelpHS o cliente
**escolhe produto e equipamentos no formulário antes de abrir o chamado**, e
desde a v1.6.0 pode escolher vários.

Perguntar de novo faria o sistema parecer burro na primeira frase. A Helô abre
já sabendo:

> *"Vi que seu chamado é sobre o Phoebus, série WATFR01-73041."*

### 2. As regras de formatação do WhatsApp saem

Um quarto do prompt antigo eram instruções sobre asterisco simples versus
duplo. No HelpHS isso produziria asteriscos literais na tela.

### 3. "Vou te transferir" vira uma ação de verdade

No WhatsApp, escalar era uma frase — alguém do outro lado precisava perceber.
No HelpHS a escalação **notifica a equipe**, com um aviso próprio que diz que o
cliente pediu uma pessoa. Sem isso, o cliente lê "já vou te transferir" e
ninguém é avisado.

⚠️ O desenho original prometia três efeitos aqui — mudar o status, notificar a
equipe e **desligar a IA**. Só a notificação existe. O status não muda, e
`ticket.ai_enabled` continua `True`: o silêncio dela vem do teto de falas e da
guarda de humano na conversa, não de a IA ter sido desligada. Hoje isso é
inofensivo, e na Fase 2 não é — está registrado como dívida com gatilho em
`docs/decisoes-e-regras.md`, com a Fase 2 como gatilho.

---

## Fase 1 — triagem e entrega

> **Esta seção foi reescrita em 08/09/2026 para bater com o código.** O
> fluxograma e as tabelas descreviam o desenho de 11/08, e três rodadas de
> emenda passaram por cima delas sem corrigi-las: quem lia o fluxograma
> primeiro acreditava num status que nunca existiu, num destino que o
> `9eeb683` já tinha removido e num teto de conversa com o número errado.
> Emendar de novo já tinha falhado três vezes; o texto errado saiu.
>
> As duas seções riscadas mais abaixo — a do SLA e a do `ai_handling` — ficam
> como estão: elas guardam o **porquê** de decisões revertidas, e o próprio
> documento diz que ficam como registro. O que saiu foram conclusões erradas
> sem raciocínio junto. O histórico completo está no git.

### Fluxo

```
Cliente termina o formulário (produto: Phoebus, equipamento: WATFR01-73041)
        │
        ▼
Chamado nasce em "Aberto"
        │
        ▼
🤖 Helô: Olá, Suelen! Sou a Helô, assistente da Health & Safety.
        Vi que seu chamado é sobre o Phoebus (série WATFR01-73041).
        Para adiantar o atendimento, me conta:
        1. O que exatamente está acontecendo com o aparelho?
        2. Quando o problema começou?
        3. Você já tentou alguma coisa?
        │
        ▼
Status → "Em andamento" (a fala dela é o que move)
A fala dela CARIMBA a primeira resposta do SLA (decisão de 28/08)
        │
        ▼
Cliente responde
        │
        ├── um humano já está na conversa? ──► SIM: ela não fala. Fim.
        │                                      (responsável definido, OU alguém
        │                                       da equipe já escreveu no chamado)
        ▼ NÃO
🤖 Helô: ├── pediu uma pessoa  → "Sem problema! Já estou passando seu chamado
        │                         para um atendente."             → escala
        └── qualquer outra coisa → ela busca na base e RESPONDE
                                   (o turno inteiro está em "Fase 2")
        │
        ▼
Quando ela escala, a equipe é notificada — e o aviso diz POR QUÊ:
        ├── o cliente pediu uma pessoa → "Cliente pediu atendimento humano"
        └── qualquer outro motivo      → "Helô passou o chamado", com o motivo
                                          no texto
A conversa dela ENCERRA naquele chamado (`ticket.helo_saiu = True`), e o
histórico registra o motivo. O botão de IA do técnico só cai quando foi o
CLIENTE quem pediu uma pessoa — nos outros motivos ele fica de pé, senão a
sugestão de resposta e o resumo sumiriam justo onde a IA já falhou.
Status continua "Em andamento". Não vai para "Aguardando técnico":
esse status pausa o relógio do SLA, e o cliente está esperando um humano.
        │
        ▼
Helô sai de cena. Se o cliente escrever de novo, ela fica calada.
```

**A cauda deste fluxo mudou em 09/09/2026, com a Fase 2.** Até ali, a resposta
do cliente ENCERRAVA a triagem: ela agradecia ("Registrei tudo aqui"), dizia
quando alguém assumiria conforme o horário comercial, e o teto de duas falas a
calava dali em diante. Aquilo era o certo enquanto ela não tinha base para
consultar — despedir-se é a única saída honesta de quem não pode resolver.
Agora ela resolve, e a despedida fixa virou uma das saídas, não a única. O
texto anterior está no git.

**O resumo da triagem para o técnico ainda não existe** — é o último item da
Fase 1 e depende da chave da DeepSeek.

### Atalho: o cliente interrompe a triagem

Se o cliente disser que quer falar com uma pessoa — *"quero falar com um
humano"*, *"me passa pro atendente"* — a Helô **para a triagem na hora** e
escala, sem insistir e sem perguntar o motivo.

Essa é a regra mais importante do ponto de vista de experiência. Um robô que não
aceita "não" é pior do que robô nenhum.

Ela **interrompe**, não pula: a saudação com as três perguntas já foi gravada na
criação do chamado, antes de o cliente escrever qualquer coisa. Ele lê as
perguntas de qualquer jeito, e o pedido de humano é reconhecido na resposta
seguinte.

### Ela cala quando um humano já está na conversa

Acrescentado em 08/09/2026 (`12a5536`). Não estava no desenho original, e o
defeito que ele deixou passar era este: a Helô só olhava os interruptores, o
número de falas que já tinha dado e o pedido de humano — nenhum deles enxerga o
atendimento que já começou. Cliente abre às 3h e ela saúda; técnico assume às
8h e escreve; cliente responde às 9h; e ela gastava a segunda fala dizendo "um
atendente já vai assumir seu chamado" num chamado que já tinha dono. Junto ia o
aviso à equipe inteira dizendo que o chamado espera atendimento.

**São duas condições, em disjunção** — qualquer uma cala a Helô:

| Condição | Por que sozinha não basta |
|---|---|
| O chamado tem **responsável** (`assignee_id`) | Assumir não grava mensagem nenhuma no chat — só histórico e notificação. Quem pegou o chamado e ainda não digitou é invisível para qualquer varredura de conversa. |
| **Alguém da equipe já escreveu** no chamado | Técnico e admin escrevem em qualquer chamado sem serem os responsáveis, e responder antes de assumir é o caminho normal da triagem da manhã. Além disso `assignee_id` é revogável: se só ele valesse, desatribuir ressuscitaria a Helô no meio de uma conversa que um humano já começou. Mensagem é append-only; atribuição não é. |

A frase que ela diria é mentira nos dois mundos. A guarda é a união deles.

A conferência de "alguém da equipe" é pelo **papel** de quem falou, e não pelo
atalho "remetente que não é o autor do chamado": o atalho só funciona porque
hoje a visibilidade do chamado é um "é seu?" cru, e calaria a Helô pelo motivo
errado quando a frente de empresa/CNPJ deixar colegas da mesma empresa
entrarem no chamado.

Isso ganha peso na Fase 2. Hoje o teto de duas falas já limitava o estrago; com
ela falando muitas vezes por chamado, esta guarda passa a ser o que impede a IA
de falar por cima do atendimento humano.

### Decisões de comportamento

| Pergunta | Decisão |
|---|---|
| Quando ela entra | Na abertura, **quando o autor é o cliente** e os três interruptores estão ligados |
| Quais chamados | Os que têm a IA ligada nos três níveis. `HELO_ENABLED` **nasce desligada** — o padrão é ela não falar |
| Quantas perguntas | Três, genéricas de suporte |
| Status enquanto atende | **"Em andamento"** — sem status novo; a fala dela é o que move o chamado para lá |
| Para onde vai depois | Continua em "Em andamento", sem responsável. Quem chama a equipe é uma **notificação**, não um status |
| Quantas vezes ela fala | **No máximo duas** (`FALAS_MAXIMAS = 2`): a saudação e o encerramento |
| Ao atingir o teto | **Silêncio** — ela não escala nem avisa nada |
| Se um humano já está na conversa | **Silêncio**, mesmo com fala sobrando (ver acima) |
| Fora do horário | Faz a triagem igual; muda só a frase final |
| Qual dia ela cita fora do horário | O **próximo dia útil**, calculado — nunca "amanhã" fixo |
| Depois de escalar | Silêncio total — o chamado é do humano |
| Conta como primeira resposta do SLA | **Sim** — revertido em 28/08 (ver abaixo) |

### ~~Por que a Helô não conta para o SLA~~ — revertido em 28/08

> **O cliente pediu o contrário.** Quando ela responde, o atendimento começou
> de fato, e mostrar "aguardando primeira resposta" a quem acabou de ser
> respondido é o indicador mentindo para o outro lado. A saudação passa a
> carimbar `sla_first_response`.
>
> O preço, aceito com a decisão: com a Helô ligada, todo chamado tem primeira
> resposta em segundos e o indicador vira ~100% permanente. Ele deixa de medir
> a equipe e passa a medir o robô. Se um dia fizer falta saber quanto o cliente
> esperou por um HUMANO, isso vira coluna nova — não dá para extrair desta.
>
> O texto abaixo fica como registro do que foi desenhado e por quê.

### Por que a Helô não contava para o SLA

Se a resposta dela zerasse o relógio, **todo chamado teria primeira resposta em
segundos** e o indicador de SLA viraria 100% permanente. O número deixaria de
medir o atendimento da equipe e passaria a medir a velocidade de um robô — que
é sempre a mesma.

O SLA de primeira resposta continua correndo até um humano falar. É o único jeito
de o indicador continuar significando o que sempre significou.

---

## Fase 1 — o que muda no sistema

### A Helô não vira um usuário

A mensagem de chat exige um remetente (`sender_id`). A saída **não** é criar um
usuário "Helô" no banco: ela apareceria na lista de técnicos, poderia ser
atribuída a chamados e receberia e-mails de notificação — três problemas novos
para resolver um.

Em vez disso, `sender_id` passa a aceitar nulo, com `is_ai = true` identificando
a mensagem. É o mesmo padrão já adotado em `ticket_history.user_id` para ações
automáticas do sistema, onde nulo significa "foi o sistema".

### ~~Status novo: `ai_handling`~~ — descartado em 26/08

> **Superado pela decisão do cliente.** O chamado nasce em `open` e vai para
> `in_progress` quando a Helô fala. Nenhum valor novo entra no enum, nenhuma
> migration de `ALTER TYPE`, nenhum dos 8 arquivos do front muda. O texto
> abaixo fica como registro do que foi desenhado e por quê.

Entra no enum de status, com coluna própria no quadro, entre "Aberto" e "Em
Andamento". Transições permitidas:

```
ai_handling → awaiting_technical   (triagem concluída ou cliente pediu humano)
ai_handling → in_progress          (técnico assume durante a triagem)
ai_handling → cancelled
```

A equipe vê de relance quantos chamados estão com a IA e quantos já são dela.

### A saudação não usa IA

A primeira mensagem é montada com dados do chamado — nome, produto, equipamento
— sem chamar o LLM. Três ganhos:

- **previsível**: a primeira coisa que o cliente lê nunca sai errada
- **instantânea**: sem esperar resposta de API
- **grátis**: metade das chamadas de LLM desaparece

O LLM entra só depois, para interpretar a resposta do cliente e gerar o resumo.

### Proteções

| Risco | Proteção |
|---|---|
| Helô começa a falar besteira com cliente | `HELO_ENABLED` desliga tudo sem deploy, e há desligamento por chamado e por cliente. Os três níveis são conjunção: qualquer um desligado a cala, e não existe religar num nível mais específico |
| Cliente entra num vai-e-vem sem fim | Teto de **2 falas dela** (`FALAS_MAXIMAS`), contadas por `is_ai` no chamado. Atingido o teto ela **cala** — não escala |
| Ela fala por cima do atendimento humano | Silêncio quando o chamado tem responsável ou quando alguém da equipe já escreveu (ver "Ela cala quando um humano já está na conversa") |
| Custo de API descontrolado | Teto de falas + saudação e encerramento montados **sem LLM** |
| Reprocessar faz ela falar de novo | A contagem é do que está gravado no banco, não de estado em memória |

⚠️ **A proteção contra falha de LLM não existe, e não tem gatilho hoje.** O
desenho previa "escala direto com mensagem neutra se o LLM cair". A Fase 1
inteira roda **sem chamar LLM nenhum**: a saudação e o encerramento são
montados com dado do cadastro e com o motor de SLA. `helo.py` não importa
`services/llm.py`. Quando a Fase 2 ligar o LLM, esta proteção precisa ser
construída — ela nunca foi.

### Custo estimado

Com `gpt-4o-mini`, cerca de **1 a 2 chamadas de LLM por chamado** (a saudação
não gasta). Algo em torno de **US$ 0,25 a US$ 0,50 por mês** em um volume de 500
chamados mensais.

O custo não é o fator de decisão aqui. O fator é a qualidade da conversa.

### Prompt da Fase 1

```
Você é a Helô, assistente virtual da Health & Safety — assistência técnica
autorizada exclusiva no Brasil para bafômetros e etilômetros.

Nesta etapa seu único trabalho é ACOLHER e TRIAR. Você não resolve problemas
técnicos e não inventa procedimentos.

CONTEXTO DO CHAMADO (já informado pelo cliente no cadastro):
- Cliente: {nome}
- Produto: {produto}
- Equipamentos: {equipamentos com número de série}
- Categoria: {categoria}
- Título: {título}

REGRAS:
1. NUNCA peça modelo ou número de série — você já tem essa informação acima.
   Cite-a para mostrar que o sistema reconhece o equipamento.
2. Faça as três perguntas de triagem de uma vez só, numeradas.
3. Se o cliente pedir para falar com uma pessoa, PARE a triagem
   imediatamente e escale. Não insista, não pergunte o motivo.
4. Se o cliente descrever risco à segurança ou operação parada, escale na hora.
5. Não prometa prazo, não fale de garantia, certificado de calibração,
   gás de calibração ou RMA. Isso é com o atendente humano.
6. Escreva em português brasileiro, tom profissional e acolhedor.
   Sem asteriscos, sem markdown.
7. Depois da resposta do cliente, agradeça e encerre sua participação.
   Você não continua a conversa.
```

O bloco de contexto é preenchido pelo sistema a cada chamado — a Helô nunca
adivinha esses dados.

### O que NÃO entra na Fase 1

- Consulta à base de conhecimento
- Resolução de problemas
- Qualquer promessa de prazo
- Assuntos de certificado, gás de calibração, garantia ou RMA
- Atendimento fora do chat do chamado (sem WhatsApp, sem e-mail)

---

## Fase 2 — a Helô resolve

> **Escrita como plano em 11/08/2026, reescrita em 09/09/2026 para descrever o
> que existe.** O plano acertou o rumo e errou o tamanho em dois pontos, e os
> dois ficam registrados porque explicam decisões que o código não explica
> sozinho: "migrar a base da Helô antiga (Postgres existente)" virou ingerir
> **oito manuais de arquivo**, porque o banco antigo não apareceu; e "busca
> vetorial" trouxe junto um **serviço de embedding próprio**, porque calcular
> embedding em provedor externo custava mais do que todo o resto da IA somado.
>
> O que saiu foi a lista de "o que é preciso" — conclusões, todas substituídas
> por fato. O raciocínio de cada etapa está nos commits.
>
> Em 10/09/2026 a fonte mudou de novo, e para melhor: a base da Helô passou a
> ser a própria Base de Conhecimento. Ver
> `2026-09-10-helo-base-de-conhecimento-design.md`.

Ela deixou de ser recepcionista: responde o que está documentado, citando a
fonte, e escala o que não está.

### O turno dela, do jeito que roda

```
Cliente escreve no chat
        │
        ▼
Os três interruptores (global, chamado, cliente) ─── desligado → silêncio
        │
        ▼
Um humano já está na conversa? ──────────────────── sim → silêncio
   (responsável definido OU alguém da equipe já escreveu)
        │
        ▼
Ela já se apresentou neste chamado? ─────────────── não → silêncio
   (chamado aberto antes de ela existir, ou com ela desligada)
        │
        ▼
O cliente pediu uma pessoa? ─────────────────────── sim → ESCALA
   (lista de trechos, ANTES do modelo: precisa funcionar com o LLM fora do ar)
        │
        ▼
Já foram 6 trocas? ──────────────────────────────── sim → ESCALA
        │
        ▼
Embedding da pergunta ──── serviço fora → sem vetor, base vazia
        │
        ▼
Busca vetorial: trechos de artigo PUBLICADO que sirva ao produto,
já embutidos, a no máximo 0,25 de distância, os 4 mais próximos
   (a consulta roda dentro de um SAVEPOINT: erro nela não pode levar
    junto a mensagem que o cliente acabou de escrever)
        │
        ▼
Prompt = [CADASTRO] + [BASE TÉCNICA] + [CONVERSA]  →  DeepSeek
        │
        ├── não respondeu, ou respondeu vazio ─────────→ ESCALA
        ├── respondeu com a linha `ESCALAR: <motivo>` ─→ ESCALA com o motivo
        └── respondeu ────────────────────────────────→ a fala vai para o chat
```

Escalar é uma ação, não uma frase: grava a fala dela, **desliga a IA naquele
chamado** e notifica a equipe com o motivo. Depois disso ela não fala mais ali,
mesmo que o cliente escreva de novo.

### A saudação continua sem LLM

Decisão de 09/09/2026, e não sobra da Fase 1. Ela é montada com dado do
cadastro: **previsível** — a primeira coisa que o cliente lê nunca sai errada —,
instantânea e grátis. O modelo entra a partir do **segundo** turno, que é onde
existe algo para interpretar.

### Os três blocos que o modelo recebe

| Bloco | De onde vem | O que o prompt manda fazer com ele |
|---|---|---|
| `[CADASTRO]` | Consultas ao banco: produto, empresa, equipamentos com série, categoria, título, horário de abertura e até três chamados anteriores **do mesmo equipamento** | Fato verificado. Citar para mostrar que o sistema reconhece o aparelho, e **nunca** pedir de novo |
| `[BASE TÉCNICA]` | A busca vetorial, já filtrada pelo produto | Única fonte de procedimento. Vazia ou `NADA ENCONTRADO` → escalar, sem segunda opção |
| `[CONVERSA]` | As mensagens do chamado em ordem, mais a que acabou de chegar | Não repetir pergunta já respondida |

Os chamados anteriores são recortados pela **empresa** do cliente (ou por ele
mesmo, quando não tem empresa). O número de série é único por produto e não por
dono: sem esse recorte, o título do chamado de um cliente entraria no prompt de
outro — vazamento por um caminho que nenhuma tela do sistema abre.

### A base que existe hoje

**Desde 10/09/2026 a fonte é a Base de Conhecimento** — os mesmos artigos da
barra lateral, com `status = published` e `helo_pode_ler = true`. Artigo
publicado entra nas respostas na varredura seguinte (5 min); despublicar sai
na hora, porque a busca filtra ao vivo. Artigo sem produto vinculado vale para
todos os aparelhos; vinculado, só para o dele.

Os três manuais técnicos (Phoebus, Titan, iBlow 10 Pro) entram por uma
importação única (`scripts/importa_manuais_para_kb.py`) que cria cada um como
RASCUNHO, já com as senhas redigidas: uma pessoa lê e publica. As cinco fichas
comerciais não entram — têm preço. Com os três publicados, a base tem 46
trechos.

A tabela abaixo é do acervo de manuais de 09/09 — 74 trechos, 8 documentos, 7
produtos —, e continua valendo para o que os quatro produtos sem manual
significam na prática. Só **três** produtos têm manual técnico:

| Produto | Manual técnico | Ficha comercial |
|---|---|---|
| Titan | 15 trechos | — |
| Phoebus | 18 trechos | — |
| iBlow 10 Pro | 12 trechos | 8 trechos |
| Deimos, EBS-010, Mark X, Mercury | **nenhum** | 4 a 6 trechos cada |

Para um chamado dos outros quatro produtos, a base vem vazia em todo turno — a
menos que alguém publique na Base um artigo sem produto vinculado que responda:
ela saúda, o cliente responde, ela escala. Não é defeito — é o desenho
encontrando o acervo que existe. **É decisão de escopo do cliente**, não de
código.

### O teto de distância

Ordenar não é filtrar: sem teto, a busca sempre devolve os quatro trechos mais
próximos, por mais longe que estejam. Medido em 09/09/2026 contra o corpus real,
com 40 perguntas rotuladas — 27 com resposta conhecida no manual e 13 sem
resposta nenhuma lá dentro:

| grupo | n | mediana | extremo |
|---|---|---|---|
| tem resposta na base | 27 | 0,2185 | máximo 0,2850 |
| não tem resposta na base | 13 | 0,2789 | **mínimo 0,2590** |

`0,25` é o maior corte que ainda barra 100% dessas 13, preservando 22 das 27
com resposta. As cinco que ele derruba viram escalada — o lado barato de errar.

Remedido em 10/09/2026, depois da mudança de fonte, com as mesmas 40 perguntas
contra os três manuais importados como artigo: o 0,25 continua barrando as 13,
preserva 21 das 27 (as derrubadas passam a seis), e a margem até a pergunta sem
resposta mais próxima caiu de 0,009 para 0,007.

Mas as duas populações **se sobrepõem** entre 0,25 e 0,26: um acerto medido com
embedding real (*"como coloco o aparelho em português"*) fica a 0,2533, dentro
da faixa. O corte não separa duas nuvens; ele escolhe um lado da sobreposição, e
escolhe o apertado — cortar acerto custa uma escalada, passar trecho errado
custa uma instrução errada a quem está com um instrumento de medição legal na
mão. O número e suas fragilidades estão em `helo_base.py` e em
`docs/decisoes-e-regras.md`.

### O que a Fase 2 NÃO entrega

- **Resumo da triagem para o técnico** — continua sendo o último item da Fase 1.
- **Citação rastreável.** A resposta cita a fonte em texto, e nada liga a fala
  dela ao `chunk_id` de onde saiu. Auditar depois é reler o manual.
- **Aprender com o que o técnico responde.** É a Fase 3.
- **Base para os outros quatro produtos.** Depende de manual técnico existir.

**Cuidado central, inalterado desde 11/08:** a Helô da Fase 2 pode dar uma
instrução errada a um cliente mexendo em equipamento de medição legal. A regra
de "só responder o que está na base, citando a fonte" não é burocracia — é o
que separa suporte de chute.

---

## Fase 3 — a Helô melhora sozinha

Só faz sentido com a Fase 2 rodando e volume real acumulado.

- Medir taxa de resolução sem humano e satisfação dos atendimentos dela
- Identificar as perguntas que ela mais erra — cada uma é um artigo faltando
- Sugerir ao técnico transformar uma resposta boa em artigo da base
- Painel de desempenho da IA junto dos relatórios

O ciclo se fecha: o que o técnico responde hoje vira o que a Helô resolve
sozinha amanhã.

---

## Perguntas para o cliente

### Sobre a Fase 1

1. **O tom da Helô está certo?** Ela se apresenta pelo nome e trata o cliente
   pelo primeiro nome. Formal demais, informal demais?
2. **Três perguntas é o número certo?** Duas seriam mais rápidas; quatro dariam
   mais material ao técnico.
3. **A frase de fora do horário deve prometer prazo?** Hoje diz que um atendente
   entra em contato no próximo dia útil. Isso é uma promessa — o SLA sustenta?
   Vale lembrar que quem abre chamado na sexta à noite vai ler "segunda-feira",
   e não há como suavizar isso com uma frase bonita.
4. **A equipe quer ver a coluna "Atendimento IA" no quadro**, ou prefere que o
   chamado apareça só depois da triagem, para não poluir a visão?
5. **O cliente pode desligar a Helô para uma empresa específica?** Há cliente que
   não queira falar com IA de jeito nenhum?

### Sobre a Fase 2 — respondidas

6. **Apetite de risco.** Errar por escalar demais é aceitável; errar por
   responder de cabeça, não. Toda decisão da Fase 2 desempata para esse lado —
   o teto de distância derruba cinco respostas boas (seis, na remedição de
   10/09) para não deixar passar nenhuma resposta inventada.
7. **Cita a fonte, sim.** Está no prompt, e a fonte viaja com o trecho desde a
   busca para o modelo não precisar inventar de onde tirou.
8. **Continuam proibidos.** Certificado de calibração, gás, RBC, INMETRO,
   garantia, RMA, preço e prazo estão na lista de escalada imediata do prompt.

### Sobre a base antiga (técnico) — respondidas em 08/09/2026

9-12. **A base antiga não entrou.** O Postgres da Helô do WhatsApp não estava
disponível, e a Fase 2 foi construída a partir de **oito manuais em `.txt`**
fornecidos pelo cliente — cinco fichas comerciais e três manuais técnicos.
Embeddings gerados pelo **bge-m3 quantizado**, em serviço próprio dentro da
infraestrutura (nenhum texto de manual sai para provedor externo). ~~O conteúdo é
material distinto dos artigos da Base de Conhecimento do HelpHS, e vive em
tabelas próprias (`helo_documents`, `helo_chunks`); os dois não se misturam.~~
**Invertido em 10/09/2026:** a base da Helô passou a ser a própria Base de
Conhecimento — os manuais técnicos entram como artigo, e `helo_documents`
deixou de existir. Ver a seção da Fase 2 acima e
`2026-09-10-helo-base-de-conhecimento-design.md`.

---

## Riscos conhecidos

| Risco | Gravidade | Mitigação |
|---|---|---|
| Cliente se irrita por falar com robô | Alta | Ela escala na hora se pedirem humano, sem insistir |
| Instrução técnica errada (Fase 2) | Alta | Só responde o que está na base; não achou, escala |
| Chamado preso se o LLM falhar | Alta | **Mitigado na Fase 2 (09/09/2026).** Timeout, chave inválida, serviço fora e resposta vazia são indistinguíveis no código e têm o mesmo destino: escalada com mensagem neutra, e o motivo `a IA não respondeu` na notificação da equipe — o que permite perceber que todos os chamados da noite escalaram pelo mesmo motivo. A busca vetorial roda em SAVEPOINT: erro nela não leva junto a mensagem do cliente. |
| IA fala por cima do atendimento humano | Média | Silêncio quando há responsável ou fala da equipe no chamado (`12a5536`) |
| Métrica de SLA distorcida | **Aceito** (era Média) | ⚠️ **A mitigação caiu em 28/08.** A fala da Helô **passou a carimbar** a primeira resposta, por decisão do cliente. O risco não foi mitigado: foi **aceito**, com o preço declarado antes e junto da decisão — o indicador vira ~100% permanente e deixa de medir a equipe. Ver a seção do SLA acima e a dívida com gatilho em `docs/decisoes-e-regras.md`. |
| Custo de API | Baixa | Saudação sem LLM (nunca chama), teto de 6 trocas por chamado, `max_tokens=800`, e embedding calculado em casa — o volume de chamadas subiu com a Fase 2, o custo por chamado continua limitado por construção |

---

## Pendência

O nome está grafado **Helô** neste documento, seguindo o prompt oficial da
versão do WhatsApp. Confirmar se é assim mesmo ou se o correto é "Elô".
