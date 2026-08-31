# Registro da revisão aceita — consentimento LGPD

**Data:** 31/08/2026
**Status:** PROPOSTA — aguardando OK do Rickelme, nada implementado
**Origem:** a Política de Privacidade entregue pela qualidade em 31/08/2026
(`Politica_De_Privacidade_HelpHS.pdf`, revisão 00) lista, na tabela de
retenção, o item *"Registro de aceite dos Termos e desta política"* com a
justificativa **"comprovação da revisão aceita pelo titular"**. O sistema não
grava qual revisão foi aceita.

**Prazo real:** o campo precisa existir **antes** de a revisão 01 ser
publicada — é ela que ativa a IA. Publicada a 01 sem o campo, não há como
distinguir quem aceitou a 00 de quem aceitou a 01, que é exatamente a
comprovação prometida.

---

## 1. Levantamento — por onde o consentimento é gravado hoje

Cinco caminhos escrevem `lgpd_consent`. Os vereditos abaixo são sobre o que
cada um significa como **prova**, não sobre o código estar certo.

| # | Caminho | O que grava | Veredito |
|---|---|---|---|
| 1 | `POST /register` ([auth.py:196](../../../backend/app/routers/auth.py#L196)) | `True` fixo; o validador `must_accept_lgpd` recusa `false` antes | ✅ **Consentimento de verdade** — a pessoa marcou a caixa. É o único caminho em que o titular manifestou vontade. |
| 2 | `POST /users` ([users.py:115](../../../backend/app/routers/users.py#L115)) | `body.lgpd_consent`, informado por quem cria | ⚠️ **Consentimento afirmado por terceiro.** Um admin ou técnico cria a conta de um cliente e marca a caixa por ele. O registro fica indistinguível do caminho 1. |
| 3 | `PATCH /users/me/lgpd-consent` ([users.py:487](../../../backend/app/routers/users.py#L487)) | o valor enviado pelo próprio titular | ✅ para conceder; ❌ para revogar — ver abaixo |
| 4 | `POST /users/{id}/anonymize` ([users.py:542](../../../backend/app/routers/users.py#L542)) | `False` + `at = None` | ✅ correto: a conta deixou de existir como pessoa |
| 5 | Seeds (`seeds.py:133`, `seeds_e2e.py:75`) | `True` | ✅ contas de sistema e de teste, não titulares |

### O achado que muda o desenho: revogar apaga a prova

No caminho 3, revogar faz `lgpd_consent = False` **e**
`lgpd_consent_at = None`. O carimbo da concessão anterior é **destruído**.

Se alguém consente hoje, usa o sistema por um ano e revoga amanhã, não sobra
registro de que houve consentimento durante aquele ano — e é justamente esse
período que precisaria ser defendido, porque foi nele que o tratamento
aconteceu. A política promete guardar o registro de aceite "todo o período da
relação e até 5 anos após o seu encerramento". Hoje o sistema o apaga no
primeiro exercício de um direito do titular.

Isso não é efeito colateral do campo novo: já é assim. Mas acrescentar
`revisão` a um par de campos mutáveis **herda o defeito** — a revisão some
junto.

---

## 2. Proposta

**Consentimento vira histórico append-only, não um par de campos mutáveis.**

Tabela nova `lgpd_consents`: `user_id`, `revisao_termos`, `revisao_politica`,
`concedido_em`, `revogado_em`, `origem` (enum: `auto_cadastro`,
`criado_por_terceiro`, `alteracao_propria`), `ip`. Uma linha por evento;
nada é sobrescrito, nada é apagado.

Os campos `lgpd_consent` e `lgpd_consent_at` **permanecem** no `users`,
refletindo o estado atual — é o que as telas leem, e mexer nelas espalharia a
mudança por front, schemas e testes sem necessidade. A tabela é a prova; as
colunas são a leitura rápida.

### Por que histórico, e não só mais uma coluna

Minha inclinação inicial era a mínima: acrescentar
`lgpd_consent_revisao: str | None` ao `users` e pronto. **Defendo o contrário**
por duas razões concretas, não por gosto de arquitetura:

Primeira, a coluna só sabe representar a **última** revisão aceita. Quem
aceitou a 00, foi tratado sob ela por meses e depois aceitou a 01 deixa de ter
prova da 00 — e a 00 é a que ampara o tratamento já ocorrido. Uma coluna que
esquece o passado não serve como comprovação.

Segunda, o defeito da revogação acima. Com colunas mutáveis ele continua e
passa a valer também para a revisão. Com histórico, revogar é **escrever
`revogado_em`**, não apagar linha.

⚠️ **O preço, dito antes:** é tabela nova, migration e um lugar a mais para
escrever em cinco caminhos. É mais trabalho que uma coluna. Se você preferir a
coluna, ela atende ao pé da letra o que a política pede hoje e eu implemento —
mas ficaria registrado que a comprovação vale só para a revisão vigente.

### Duas revisões ou uma

Gravo `revisao_termos` e `revisao_politica` **separados**, mesmo que hoje os
dois documentos saiam juntos. Um campo só assume que eles serão sempre
versionados em conjunto, e isso é decisão da qualidade, não nossa. Dois campos
custam quase nada agora e evitam migration de correção depois.

**Pergunta para o Hyago e o Gustavo, não para nós:** os Termos e a Política
terão sempre a mesma revisão, ou podem andar em ritmos diferentes?

### De onde sai "a revisão vigente"

Duas configurações: `LGPD_REVISAO_TERMOS` e `LGPD_REVISAO_POLITICA`, com valor
padrão. Não é tabela de revisões — não há o que consultar, há o que declarar,
e publicar revisão nova é evento raro e manual, do mesmo tipo do deploy.

⚠️ Se a configuração estiver vazia, o cadastro **não pode** gravar
consentimento em branco fingindo que gravou. Ou falha explicitamente, ou grava
`NULL` com significado de "revisão não declarada". Defendo **falhar no boot**,
como já fazem `CORS_ORIGINS` e `FRONTEND_URL`: consentimento sem revisão é
exatamente o estado que estamos consertando, e deixá-lo possível recria o
problema por esquecimento de variável.

---

## 3. Impacto nos dados existentes — **nenhum backfill**

Os usuários que já existem aceitaram um texto que **não existia**. A revisão
deles não é "00": é **desconhecida**, e essa é a verdade que precisa ficar
gravada.

O histórico nasce vazio. Ninguém ganha linha retroativa. `lgpd_consent = true`
com `lgpd_consent_at` preenchido e nenhuma linha em `lgpd_consents` significa,
sem ambiguidade: *consentiu antes de haver documento*. Inventar uma linha "00"
para essas pessoas seria fabricar prova — o oposto do que a tabela existe para
fazer.

Regra da casa aplicada: regra nova é prospectiva, não reescreve o passado, e
backfill nunca vai dentro de migration.

**Consequência que a qualidade precisa saber:** quando a revisão 01 for
publicada, todos os cadastros anteriores estarão sem revisão registrada. Se o
jurídico exigir aceite explícito da 01 para continuar o tratamento por IA, isso
vira uma tela de re-aceite no próximo login — trabalho de front que **não está
nesta proposta** e precisa de decisão antes de virar escopo.

---

## 4. Como testar sem depender de relógio

A revisão vem de configuração, então o teste a define e confere o que foi
gravado — nada de `datetime.now()` no meio.

- **Mutação obrigatória:** trocar o valor de `LGPD_REVISAO_POLITICA` tem que
  mudar o que foi gravado. Se o teste passar com qualquer valor, ele não está
  provando nada.
- Um teste por caminho dos cinco do levantamento, cada um provando a `origem`
  correta — em especial o caminho 2, que precisa gravar
  `criado_por_terceiro` e **não** se disfarçar de auto-cadastro.
- **Revogar não apaga:** conceder, revogar, e provar que a linha original
  continua lá com `concedido_em` intacto e `revogado_em` preenchido. É o
  defeito de hoje; o teste é o que impede a volta dele.
- **Boot sem a configuração falha**, com o mesmo padrão das outras validações
  de produção.
- Migration com `upgrade` → `downgrade` → `upgrade` contra Postgres real.

---

## 5. Compatibilidade com o que vem depois

**Revisão 01 e a IA.** É o motivo do prazo. A ordem é: campo no ar → qualidade
publica a 01 → chave do DeepSeek no painel → `LLM_ENABLED` ligado. A política
promete 15 dias de aviso prévio aos usuários antes do início do tratamento, o
que dá folga confortável para o campo entrar antes.

**As páginas de Termos e Política.** Não existe rota para elas; a caixa do
cadastro nomeia dois documentos que não abrem. Isso é trabalho separado e
provavelmente vem antes, mas não depende desta proposta nem ela dele — só
precisam usar o mesmo identificador de revisão.

**Anonimização.** O caminho 4 continua zerando as colunas do `users`. A linha
do histórico **fica**, sem dado pessoal além do `user_id` que já está anonimizado
— é registro de que houve consentimento, que é o que a política manda guardar.

**O caminho 2, em aberto.** Esta proposta faz o registro dizer a verdade sobre
ele (`origem = criado_por_terceiro`), mas não decide se um terceiro **pode**
consentir por outra pessoa. É pergunta jurídica, vai junto com o retorno à
qualidade, e não bloqueia o campo.

---

## O que eu NÃO verifiquei

Se o jurídico aceita `NULL` como "consentiu antes de haver documento" ou se
exige re-aceite de todos. A resposta muda a parte 3 e pode acrescentar uma tela
inteira ao escopo.
