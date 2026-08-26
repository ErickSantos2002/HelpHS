# Helô — atendimento por IA no HelpHS

**Data:** 11/08/2026
**Status:** validado com o cliente em 26/08/2026 — em construção
**Fases:** 3 — este documento detalha a Fase 1 e esboça as seguintes

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

- `register_first_response` ignora `is_ai` (`230d670`) — a fala da Helô não
  zera o SLA, que era o 🔴 #1 da revisão técnica
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
No HelpHS a escalação **muda o status, notifica a equipe e desliga a IA**. Sem
isso, o cliente lê "já vou te transferir" e ninguém é avisado.

---

## Fase 1 — triagem e entrega

### Fluxo

```
Cliente termina o formulário (produto: Phoebus, equipamento: WATFR01-73041)
        │
        ▼
Chamado nasce em "Atendimento IA"
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
Cliente responde
        │
        ▼
🤖 Helô: Obrigada! Registrei tudo aqui.
        ├── dentro do horário → "Um atendente já vai assumir seu chamado."
        └── fora do horário   → "Nossa equipe atende de segunda a sexta, das
                                 8h às 17h. Na segunda-feira pela manhã um
                                 atendente entra em contato."
        │
        ▼
Status → Aguardando técnico
Resumo da triagem gravado no chamado
        │
        ▼
Helô sai de cena. Se o cliente escrever de novo, ela fica calada.
```

### Atalho: o cliente pode pular a fila da IA

Se em qualquer momento o cliente disser que quer falar com uma pessoa — *"quero
falar com um humano"*, *"me passa pro atendente"* — a Helô **pula a triagem e
escala na hora**, sem insistir.

Essa é a regra mais importante do ponto de vista de experiência. Um robô que não
aceita "não" é pior do que robô nenhum.

### Decisões de comportamento

| Pergunta | Decisão |
|---|---|
| Quando ela entra | Assim que o chamado é aberto, sempre |
| Quais chamados | Todos, sem exceção |
| Quantas perguntas | Três, genéricas de suporte |
| Status enquanto atende | Novo status **"Atendimento IA"**, com coluna própria no quadro |
| Para onde vai depois | Aguardando técnico |
| Fora do horário | Faz a triagem igual; muda só a frase final |
| Qual dia ela cita fora do horário | O **próximo dia útil**, calculado — nunca "amanhã" fixo |
| Depois de escalar | Silêncio total — o chamado é do humano |
| Conta como primeira resposta do SLA | **Não** |

### Por que a Helô não conta para o SLA

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
| LLM fora do ar, timeout, chave inválida | Escala direto para Aguardando técnico com mensagem neutra. **Nenhum chamado fica preso** |
| Cliente entra num vai-e-vem sem fim | Teto de 3 trocas, depois escala |
| Helô começa a falar besteira com cliente | Variável de ambiente desliga tudo, sem deploy |
| Custo de API descontrolado | Teto de mensagens + saudação sem LLM |

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

Com a base de conhecimento ligada, ela deixa de ser recepcionista e passa a
resolver o que estiver documentado.

**Fluxo:** entende o problema → busca na base **filtrada pelo produto do
chamado** → se encontra, responde o passo a passo → pergunta se resolveu → se
não resolveu ou não encontrou, escala.

Aqui a decisão sobre horário ganha efeito de verdade: **com conhecimento na mão,
ela resolve de madrugada** em vez de só avisar que a equipe atende de manhã.

**O que é preciso:**
- Migrar a base da Helô antiga (Postgres existente) para o HelpHS
- Busca vetorial (`pgvector`) sobre esse conteúdo
- Filtro por produto — a parte já pronta desde a v1.2.0
- Regra rígida contra invenção: **não achou na base, não responde**

**Cuidado central:** a Helô da Fase 2 pode dar uma instrução errada a um cliente
mexendo em equipamento de medição legal. A regra de "só responder o que está na
base, citando a fonte" não é burocracia — é o que separa suporte de chute.

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

### Sobre a Fase 2

6. **Qual o apetite de risco?** A Helô resolvendo sozinha significa aceitar que
   às vezes ela vai errar. Qual erro é tolerável e qual não é?
7. **Ela deve citar a fonte** ("segundo o manual do Phoebus, seção 4")? Dá
   confiança ao cliente e facilita conferir, mas deixa a resposta mais longa.
8. **Certificado e gás de calibração continuam proibidos** para a IA, como no
   WhatsApp? Ou com a base ligada ela pode ao menos explicar o processo?

### Sobre a base antiga (técnico — para a Fase 2)

9. A base da Helô antiga usa `pgvector` ou os textos estão em tabela comum?
10. Quantos documentos, aproximadamente?
11. Qual modelo gerou os embeddings?
12. O conteúdo é o mesmo dos artigos da Base de Conhecimento do HelpHS, ou é
    material diferente que precisa conviver com ela?

---

## Riscos conhecidos

| Risco | Gravidade | Mitigação |
|---|---|---|
| Cliente se irrita por falar com robô | Alta | Ela escala na hora se pedirem humano, sem insistir |
| Instrução técnica errada (Fase 2) | Alta | Só responde o que está na base; não achou, escala |
| Chamado preso se o LLM falhar | Média | Escala automática em qualquer erro |
| Métrica de SLA distorcida | Média | Resposta da IA não conta como primeira resposta |
| Custo de API | Baixa | Teto de mensagens; saudação sem LLM |

---

## Pendência

O nome está grafado **Helô** neste documento, seguindo o prompt oficial da
versão do WhatsApp. Confirmar se é assim mesmo ou se o correto é "Elô".
