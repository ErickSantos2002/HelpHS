# Revisão técnica — Helô Fase 1

**Data:** 20/08/2026
**Revisa:** [2026-08-11-helo-atendimento-ia-design.md](2026-08-11-helo-atendimento-ia-design.md) (Welton)
**Método:** cada afirmação do desenho conferida contra o código em `1ec4a73`
**Veredito:** desenho bem fundamentado; a leitura de "metade já existe" procede.
Mas há um pré-requisito não previsto (SLA), uma quebra de contrato da API e
uma migration delicada. A Fase 1 constrói um pouco mais de infraestrutura do
que o desenho estima.
**Emendado em 31/08/2026 (`71f84cb`):** a DeepSeek passou a ser o provedor
único de LLM. Duas afirmações abaixo envelheceram: a integração **não tem mais
fallback Anthropic** (continua assíncrona, que era o ponto da linha), e o
destino do dado do cliente na Fase 1 **não é a OpenAI** — é a DeepSeek. A
análise de LGPD que este documento faz continua valendo no mérito: muda para
quem o texto sai, não o fato de sair.

---

## O que confere

| Afirmação | Verificado em |
|---|---|
| Integração LLM pronta, com fallback Anthropic | `app/services/llm.py` — e **assíncrona** (`httpx.AsyncClient`), então não bloqueia o event loop |
| `is_ai` existe desde a primeira migration | `app/models/models.py:594` |
| **Nada no sistema jamais gravou `is_ai = true`** | os dois pontos que criam mensagem passam `is_ai=False` (`chat.py:217` e `:463`) |
| Bolha da IA já desenhada | `frontend/src/components/chat/ChatPanel.tsx:51` |
| Cálculo de próximo dia útil já existe | `app/utils/sla.py` (`add_business_days`, `_advance_to_business_hours`) |

A conclusão do desenho — "a Fase 1 liga peças que já estão no lugar" — está
correta no essencial. As ressalvas abaixo não a invalidam; ajustam o tamanho.

---

## 🔴 1. A regra de primeira resposta do SLA quebra — nos dois caminhos

O desenho se preocupa com a Helô **zerar** o relógio. O código revela um
problema maior, e anterior.

`sla_first_response` é gravado em três lugares (`tickets.py:176`, `:659`,
`:731`) e **todos** com a mesma condição: `old_status == TicketStatus.open`.
Ou seja, "primeira resposta" hoje não significa "alguém respondeu" — significa
**"o chamado saiu do estado inicial"**.

Com o chamado nascendo em `ai_handling`, as duas implementações possíveis
falham em direções opostas:

- **Nasce direto em `ai_handling`:** nunca passa por `open`, então
  `sla_first_response` fica **NULL para sempre** — inclusive depois de um
  humano responder. Esses chamados ficam eternamente no card "sem primeira
  resposta" (`dashboard.py:97`) e **desaparecem do tempo médio de resposta**
  (`dashboard.py:412`, que filtra por `is_not(None)`).
- **Nasce `open` e transiciona para `ai_handling`:** grava a primeira resposta
  no instante da criação → **SLA de 100% permanente**, exatamente o efeito que
  o desenho quer evitar.

### O problema já existe hoje, sem a Helô

`app/routers/chat.py` **não toca no SLA** (zero ocorrências). Um técnico que
responde pelo chat sem mexer no status **não registra primeira resposta**. O
indicador só se move quando alguém troca o status do chamado.

**Recomendação:** desacoplar "primeira resposta" de "saiu de `open`" **antes**
da Fase 1. É correção de um indicador que já está torto — e vira pré-requisito
porque a Helô o quebraria de vez. Como muda o significado de um número que a
equipe acompanha, o desenho da nova regra é decisão de produto, não escolha
técnica.

## 🔴 2. `sender_id` nulo quebra o contrato da API

O desenho acerta em não criar um usuário "Helô" — os três problemas que ele
lista (aparecer na lista de técnicos, poder ser atribuída, receber e-mail) são
reais. Mas o caminho escolhido tem duas consequências não citadas:

- `sender_id` **não é nullable** (`models.py:591`) → exige migration.
- `ChatMessageResponse.sender_id` é `uuid.UUID` **obrigatório**
  (`schemas/chat.py:26`). Com nulo, `_msg_to_response` levanta ValidationError
  e o **GET de mensagens do chamado vira 500**. Precisa virar
  `uuid.UUID | None`, com o tipo TypeScript correspondente atualizado.

O front resiste bem: a bolha da IA é ramo próprio (`ChatPanel.tsx:51`) e não
chega no código que usa `sender_name`/`sender_role`.

## 🟠 3. A migration do status é mais delicada do que parece

`status` é **enum nativo do Postgres** (`Enum(TicketStatus)`, tipo
`ticketstatus`, criado em `75ec9d264ccb_initial_schema.py:287`). Adicionar um
valor exige `ALTER TYPE ... ADD VALUE`, que tem restrições de uso dentro da
mesma transação — e no HelpHS **as migrations rodam sozinhas no boot do
container**. Migration que falha significa API que não sobe (aconteceu em
19/08 com o guard de CORS).

Some-se o alcance: 8 arquivos do frontend referenciam status (`Badge`,
`TicketFilters`, `ticketConstants`, `TechnicianDashboard`, `ReportsPage`,
`TicketDetailPage`, `TicketListPage`, `ticketService`), além das agregações do
dashboard e das regras de pausa de SLA no backend.

## 🟠 4. LGPD não é mencionada

A Fase 1 envia para a OpenAI: nome do cliente, produto, número de série do
equipamento e o texto livre que ele escrever. Num sistema que já trata
anonimização LGPD com cuidado (o `AuditLog` preservado na anonimização), a
ausência de qualquer parágrafo sobre base legal, retenção pelo provedor e o
que a política de privacidade informa é uma lacuna — não do desenho da
conversa, mas da decisão de adotá-la.

## 🟡 5. Pontos menores, todos com correção barata

- **A chave de desligar precisa ser flag explícita**, nunca inferida da
  presença da API key. Em 19/08 exatamente essa inferência (SMTP preenchido =
  confirmação de e-mail ativa) travou o login de todos os usuários. O padrão
  do projeto hoje é `EMAIL_VERIFICATION_ENABLED`: adoção explícita, com o boot
  recusando combinação incoerente.
- **Notificações:** `chat.py` dispara `notify` ao criar mensagem. A mensagem
  da Helô não pode notificar o técnico como se o cliente tivesse escrito.
- **Testes ausentes do desenho.** O `llm.py` está em 57% de cobertura e o
  caminho crítico — LLM falhou, escala em vez de prender o chamado — é
  justamente o que precisa de teste. O gate de 80% é do projeto inteiro.
- **Grafia:** a pendência do documento (Helô ou Elô) segue aberta.

---

## Ordem sugerida

1. **Corrigir a regra de primeira resposta** (independe da Helô e conserta um
   indicador já torto) — decisão de produto sobre o que conta como resposta.
2. Reunião com o cliente sobre as 12 perguntas do desenho.
3. Fase 1, começando pela migration do enum e pelo `sender_id` nullable, que
   são o alicerce do resto.
