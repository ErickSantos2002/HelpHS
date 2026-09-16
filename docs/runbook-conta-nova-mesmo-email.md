# HelpHS · Runbook de suporte · 15/09/2026

# Conta nova, mesmo e-mail

## Introdução

**Objetivo.** Orientar o atendimento quando um cliente em produção solicita excluir a própria conta para criar outra com o mesmo e-mail, e definir as verificações obrigatórias antes de qualquer operação irreversível.

**Público.** Suporte, TI, desenvolvimento, responsável pela autorização da intervenção, auditoria interna e futuras revisões de segurança ou ISO. O procedimento deve poder ser aplicado por quem não participou da análise original.

**Princípio operacional.** Um pedido de suporte não deve se tornar uma operação destrutiva no banco de dados antes de o impacto real ser medido.

O pedido de "refazer a conta" quase nunca é a necessidade real: é o sintoma. A causa pode ser uma senha esquecida, a perda do celular usado no segundo fator ou uma mudança de e-mail, e recriar a conta parece o caminho mais curto. Em produção, porém, a conta carrega chamados, conversas e registros de auditoria de outras pessoas.

A ordem de atuação é:

1. identificar a causa (Etapa 1);
2. aplicar o caminho menos destrutivo;
3. tratar a exclusão como último recurso, que quase nunca é o caminho correto, e somente após a verificação completa (Etapa 2).

### Quando não excluir uma conta

Não prossiga com a exclusão quando:

- o problema relatado for senha, segundo fator ou conta inativa, pois existem caminhos prontos que preservam o histórico (Etapa 1);
- o problema relatado for e-mail incorreto: o caminho recomendado é alterar o e-mail da conta existente, hoje registrado como lacuna (Etapa 1; Etapa 3, proposta 1);
- houver duas contas com histórico e o histórico ainda não tiver sido migrado;
- a medição indicar chamado ativo ou conteúdo real de outras pessoas que seria excluído (Etapa 2, passo 4);
- a premissa que justificou o pedido ainda não tiver sido verificada com dados (Etapa 2, passo 5).

### Exclusão e anonimização são operações diferentes

| Operação | O que acontece com a conta | Efeito sobre o histórico |
|---|---|---|
| Exclusão | A conta deixa de existir. As referências a ela precisam ser tratadas antes: desvincular, reatribuir ou excluir conscientemente cada registro. | Depende do tratamento escolhido para cada referência (Etapa 2, passo 6). |
| Anonimização (`POST /users/{id}/anonymize`) | A conta **não** é excluída. A linha continua existindo com status `anonymized`, e nesse status a conta perde o acesso: login e requisições autenticadas são recusados. Nome e e-mail são substituídos por valores derivados do ID, e o e-mail original fica disponível. | O histórico permanece e passa a exibir "Usuário Anonimizado". |

Os critérios de verificação final também são diferentes para cada operação (Etapa 2, passo 9).

# Etapa 1

## Triagem: qual é o problema de verdade?

Antes de consultar ou alterar o banco, pergunte ao cliente o que aconteceu. Cada linha indica o caminho recomendado. A coluna **Hoje** informa se esse caminho já existe ou se ainda é uma lacuna do produto.

| O cliente diz | Causa provável | Caminho recomendado | Perde dados? | Hoje |
|---|---|---|---|---|
| "Não lembro a senha" | Senha esquecida | **Preferencial:** "Esqueci minha senha", desde que o SMTP esteja entregando os e-mails. **Alternativa:** `scripts/redefine_senha.py` | Não | Pronto |
| "Troquei de celular e não consigo entrar" | Perda do dispositivo do segundo fator (MFA). No código, as rotas de adesão ao MFA são restritas aos papéis `admin` e `technician`; o papel `client` recebe 403 | `scripts/desliga_mfa.py`. Se a senha também foi perdida: primeiro `scripts/desliga_mfa.py`, depois `scripts/redefine_senha.py` | Não | Pronto |
| "O sistema diz que minha conta está inativa" | Status `inactive` | Reativar a conta na tela de Usuários, que alterna entre ativo e inativo | Não | Pronto |
| "Mudei de e-mail" / "Cadastrei o e-mail errado" | O e-mail precisa ser alterado; a conta não precisa ser recriada | Alterar o e-mail da conta existente. **Hoje o administrador não consegue:** `UserUpdate` não possui campo de e-mail | Não | Lacuna |
| "Criei outra conta sem querer" | Conta duplicada, sem histórico de atendimento | Depende de como a conta nasceu. **Autocadastro:** o próprio cadastro grava um registro de auditoria em nome da conta nova, e auditoria é um dos vínculos que impedem a exclusão, então a tela recusa. **Criada por admin ou técnico:** o registro de criação fica em nome de quem criou, e a exclusão pela tela só passa enquanto a conta não tiver sido usada, porque login, logout, troca de senha e edição do próprio perfil também gravam auditoria em nome dela | Somente a conta duplicada | Condicional |
| "Tenho duas contas e as duas têm chamados" | Conta duplicada com histórico nas duas | Não excluir nenhuma das contas sem migrar o histórico antes. Caminho proposto: fusão, movendo o histórico para a conta que permanece e excluindo a outra depois. Referência: `scripts/funde_empresas_duplicadas.py` | Não | Lacuna |
| "Quero que apaguem meus dados" | Pedido relacionado à eliminação ou anonimização de dados pessoais (LGPD) | Anonimizar por `POST /users/{id}/anonymize`. O e-mail original fica disponível e o histórico passa a exibir "Usuário Anonimizado". **Disponível somente pela API:** o frontend possui a função `anonymizeUser`, mas nenhuma tela a chama | Nome, e-mail, telefone, departamento, foto e consentimento LGPD; a conta perde o acesso | Somente API |
| Conta de teste com dados fictícios | Não se trata de conta de cliente | Exclusão definitiva, **somente após concluir toda a Etapa 2** | Sim | Script avulso |

A classificação como "conta de teste" é uma premissa e deve ser confirmada com dados no passo 5 da Etapa 2.

# Etapa 2

## Verificação antes de anonimizar ou excluir

Os passos abaixo são obrigatórios e seguem uma ordem fixa: cada passo depende do resultado do anterior.

**Aplicação por operação.** Os passos 1 a 5 e o passo 9 valem para exclusão e para anonimização. Os passos 6 a 8 foram escritos para a exclusão executada por script. Para a anonimização por `POST /users/{id}/anonymize`, a forma de aplicar os passos 6 a 8 não está definida neste runbook e deve ser decidida por quem autoriza a intervenção, antes da chamada ao endpoint. Essa decisão inclui a reatribuição dos chamados ativos exigida no passo 9, porque a anonimização deixa esses chamados com um responsável anonimizado (Etapa 3, proposta 3).

### Definição: chamado ativo

O sistema tem sete status de chamado. Para este runbook, **chamado ativo** é o chamado que está em um destes quatro:

| Status | Situação |
|---|---|
| `open` | Aberto |
| `in_progress` | Em andamento |
| `awaiting_client` | Aguardando o cliente |
| `awaiting_technical` | Aguardando atendimento técnico |

Os outros três status são de chamado encerrado: `resolved`, `closed` e `cancelled`. Essa é a mesma separação que o backend usa nos painéis e no SLA.

**Cuidado com um termo parecido.** Ao recusar a exclusão de uma conta, o sistema informa a quantidade de "chamado(s) aberto(s)". Esse rótulo conta os chamados **criados** pela conta, em qualquer status, e não corresponde à definição de chamado ativo acima.

### Regra de parada

**Se qualquer resultado divergir da premissa que justificou a exclusão, interrompa a operação e leve o achado a quem autorizou a intervenção.** A mesma regra vale para a anonimização e para qualquer passo que não atenda ao seu critério para prosseguir. Não avance para o passo seguinte sem nova decisão.

Premissas como "é conta de teste", "não usa mais" ou "não tem dado importante" não devem ser tratadas como fato sem verificação. No caso de 15/09/2026, a conta havia sido apresentada como conta de teste, e a medição encontrou chamados com indícios de atendimento real (ver [Caso medido](#caso-medido)). O exemplo mostra por que a verificação existe.

### 1. Confirmar em qual banco você está

Existe mais de um ambiente, e o `.env` de cada árvore de trabalho aponta para um banco. Antes de qualquer escrita, é obrigatório saber em qual banco a operação será realizada.

São dois valores diferentes, e os dois precisam ser conferidos:

1. **O que está escrito no `.env`**, que fica em `backend/`. É o que a aplicação lê.
2. **O que está exportado no terminal**, na variável de ambiente `DATABASE_URL`. É o que os scripts deste runbook realmente usam para conectar: `scripts/redefine_senha.py`, `scripts/desliga_mfa.py` e `scripts/funde_empresas_duplicadas.py` leem a variável de ambiente, e não o arquivo.

Conferir só o arquivo não diz para onde o script vai conectar.

Em PowerShell 5.1, que é o terminal usado pela equipe, a partir da raiz do repositório:

```powershell
Select-String -Path backend\.env -Pattern '^DATABASE_URL=' | ForEach-Object { $_.Line -replace '://[^@]*@', '://***@' }

if ($env:DATABASE_URL) { $env:DATABASE_URL -replace '://[^@]*@', '://***@' } else { "DATABASE_URL nao esta exportada nesta sessao" }
```

Em shell POSIX, como o Git Bash, o equivalente para o arquivo, executado a partir de `backend/`, é:

```bash
grep -E '^DATABASE_URL=' .env | sed -E 's#(://)[^@]*@#\1***@#'
```

Os dois comandos trocam usuário e senha por `***` antes de imprimir.

**Critério para prosseguir:** o host exibido corresponde ao ambiente em que a intervenção foi autorizada, e o valor exportado no terminal aponta para o mesmo host do arquivo.

### 2. Identificar a conta pelo ID, não pelo nome

- **a.** Execute o dry-run de `scripts/redefine_senha.py`. Nesse modo o script apenas lê e exibe nome, papel, status e ID da conta.
- **b.** Confira a identidade da conta.
- **c.** Registre o ID.
- **d.** Use o ID em todos os passos seguintes, e não o nome ou apenas o e-mail.

**Critério para prosseguir:** o e-mail e o papel correspondem ao que o cliente relatou.

### 3. Mapear no catálogo tudo o que referencia a conta

Os models da aplicação não são suficientes para determinar o efeito real de uma exclusão. A referência é o schema efetivamente instalado no PostgreSQL, consultado em `pg_constraint`.

Para cada referência a `users`, registre:

- a tabela e a coluna;
- a regra de exclusão da foreign key: `CASCADE`, `SET NULL` ou `NO ACTION`;
- se a coluna aceita `NULL`.

```sql
SELECT c.conrelid::regclass, a.attname, c.confdeltype, NOT a.attnotnull AS anulavel
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
WHERE c.contype = 'f' AND c.confrelid = 'users'::regclass;
```

A coluna `confdeltype` volta como um código de uma letra. A documentação do PostgreSQL traduz assim:

| Código | Regra de exclusão |
|---|---|
| `a` | no action |
| `r` | restrict |
| `c` | cascade |
| `n` | set null |
| `d` | set default |

### 4. Medir o raio de impacto

Liste cada chamado em que a conta aparece, com status e criador. Em seguida, conte o conteúdo de **outras pessoas** dentro desses chamados.

Um chamado não é apenas uma linha em `tickets`. O schema declara sete referências a `tickets.id`, todas com `ON DELETE CASCADE`, então excluir um chamado exclui junto:

| Conteúdo | Tabela |
|---|---|
| Mensagens de chat | `chat_messages` |
| Histórico | `ticket_history` |
| Notas internas | `ticket_notes` |
| Anexos | `attachments` |
| Pesquisa de satisfação do cliente | `satisfaction_surveys` |
| Equipamentos vinculados | `ticket_equipments` |
| Etiquetas | `ticket_tags` |

Essa lista é o que o schema declara no commit `d3bd1ac`. Na medição de 15/09/2026, o catálogo do banco de produção trouxe essas mesmas sete referências, todas em cascata. Antes de excluir um chamado, confirme no banco de destino com a consulta do passo 3, trocando `users` por `tickets`.

Classifique cada registro afetado:

| Tipo de registro | Descrição | Tratamento preferencial |
|---|---|---|
| Registro exclusivo da conta | Existe apenas em função da conta | Pode ser excluído |
| Vínculo em conteúdo de outra pessoa ou do chamado | A conta aparece como autora ou responsável em um registro que pertence a outra pessoa ou ao chamado | Desvincular ou reatribuir |
| Conteúdo compartilhado | Registro com participação da conta e de outras pessoas; excluí-lo exclui também o conteúdo das demais pessoas | Preservar o registro; desvincular ou reatribuir a referência à conta |

Regras:

- Se o chamado ou o conteúdo precisa continuar existindo, **desvincule ou reatribua em vez de excluir**.
- Quando a coluna não aceita `NULL`, não é possível desvincular. Não crie um autor fictício e não force a exclusão: a decisão entre reatribuir e excluir conscientemente o registro cabe a quem autorizou a intervenção.

**Critério para prosseguir:** nenhum chamado ativo e nenhum conteúdo real de outras pessoas seria excluído. Se houver, aplique a [regra de parada](#regra-de-parada): não execute nenhuma escrita neste passo, registre a desvinculação ou a reatribuição necessária e leve o achado a quem autorizou a intervenção. Com a nova decisão, o tratamento é definido no passo 6 e executado somente no passo 8.

### 5. Testar a premissa com dados

Premissas como "é teste", "são fictícios" ou "não usa mais" devem ser confirmadas nos próprios registros: títulos, criadores e datas dos chamados.

Se o resultado divergir da premissa, aplique a [regra de parada](#regra-de-parada). No caso de 15/09/2026, a premissa não se sustentou integralmente.

### 6. Escolher entre excluir, desvincular e reatribuir

Decida registro a registro, com base na classificação do passo 4:

| Situação | Ação |
|---|---|
| O registro pertence exclusivamente à conta | Excluir |
| O registro está em chamado ou conteúdo de outra pessoa, ou é conteúdo compartilhado, e a coluna aceita `NULL` | Desvincular (a referência fica vazia, como já ocorre com as mensagens de sistema) ou reatribuir. Chamado ativo em que a conta é responsável deve ser reatribuído, para atender ao passo 9 |
| A coluna não aceita `NULL` (por exemplo, autor de nota ou criador de chamado) | Reatribuir ou excluir conscientemente o registro, conforme autorização |

### 7. Guardar backup das linhas afetadas

Antes de qualquer escrita, gere um arquivo JSON com o estado das linhas afetadas. **Não se trata de backup completo do banco:** é um snapshot operacional restrito ao que a operação vai alterar.

Registre no JSON:

- as linhas que serão excluídas;
- os IDs dos registros que serão desvinculados;
- as relações que serão alteradas e os valores anteriores relevantes.

Finalidade do snapshot:

- conferência posterior;
- reconstrução manual, caso a decisão se mostre incorreta;
- registro para auditoria da ação.

O snapshot não oferece restauração automática.

### 8. Executar numa transação com contagens esperadas

As quantidades de cada comando são medidas antes, nos passos 3 e 4, e escritas no script como expectativa. Na execução, a quantidade de linhas efetivamente afetada por cada comando é comparada com a esperada.

Exemplo ilustrativo (não é resultado de execução):

| Esperado | Obtido | Resultado |
|---:|---:|---|
| 5 | 5 | A execução prossegue |
| 5 | 4 ou 6 | A transação é revertida com `ROLLBACK` |

Uma divergência indica que o estado do banco mudou entre a medição e a execução. A comparação protege contra alterações concorrentes e contra premissas desatualizadas.

Registre a ação em `audit_logs`.

### 9. Verificar o resultado e informar o cliente

Os critérios de verificação dependem da operação realizada.

#### Se a operação for exclusão

Confirme que:

- a conta deixou de existir;
- não restou referência à conta nas colunas mapeadas no passo 3;
- nenhuma referência órfã inesperada ficou no banco;
- o e-mail está disponível novamente, conferido com `lower(email)`;
- os chamados preservados continuam íntegros;
- os chamados ativos têm responsável adequado.

Somente após essas verificações informe ao cliente que ele pode se cadastrar novamente. A nova conta é criada com o papel `client`.

#### Se a operação for anonimização

Confirme que:

- os campos previstos foram substituídos ou apagados: nome, e-mail, telefone, departamento, foto e consentimento LGPD, com o status passando a `anonymized`;
- nome e e-mail originais não permanecem expostos onde deveriam ter sido removidos;
- o histórico que deve permanecer foi preservado e passou a exibir "Usuário Anonimizado";
- o e-mail original está disponível para reutilização, conforme o comportamento registrado na Etapa 1;
- os chamados ativos não permanecem atribuídos à conta anonimizada, que não pode mais atendê-los.

Somente após essas verificações comunique o resultado ao cliente.

# Caso medido

## O que a verificação encontrou em 15/09/2026

**Contexto.** Conta de técnico apresentada inicialmente como conta de teste, com pedido de exclusão definitiva para que um novo cadastro fosse feito com o mesmo e-mail. Todos os números abaixo foram medidos no banco de produção antes de qualquer escrita.

### Status da execução ao final da análise

**Ao final desta análise, a exclusão não havia sido executada.** A execução foi bloqueada pela proteção automática contra operações destrutivas em produção, e o caso aguardava decisão do responsável.

O desfecho está em [Atualização posterior do caso](#atualização-posterior-do-caso).

### Medições

| Medição | Resultado |
|---|---:|
| Referências a `users` | 19 |
| Tabelas em que essas referências estão distribuídas | 18 |
| Chamados em que a conta aparece como criadora ou responsável | 6 |
| Registros de auditoria com a conta como autora | 48 |
| Chamados com indícios de atendimento real | 3 |
| Chamados com indícios de atendimento real ainda aguardando o cliente | 1 |

### Premissa e resultado

A conta havia sido apresentada como conta de teste. A medição mostrou que a premissa não se sustentava integralmente: 3 chamados apresentavam indícios de atendimento real, e 1 deles ainda aguardava o cliente.

### Registros que poderiam ser excluídos

Registros da própria conta:

- a conta;
- 1 chamado criado pela conta e identificado como teste, com o conteúdo relacionado excluído em cascata;
- 1 nota interna, cuja coluna de autor não aceita `NULL`;
- 29 notificações e 1 vínculo de equipamento, para os quais o banco possui comportamento de exclusão em cascata.

### Registros que deveriam permanecer, mas ser desvinculados

Registros em chamados de outras pessoas:

- 5 chamados: o responsável fica vazio;
- 11 mensagens de chat: o remetente fica vazio;
- 25 registros de histórico: o autor fica vazio.

Registros de auditoria, que são trilha institucional e não conteúdo de chamado:

- 48 registros de auditoria: o autor fica vazio.

**Um desses 5 chamados estava aguardando o cliente**, ou seja, ativo pela definição da Etapa 2. Pela regra do passo 6, ele exigia reatribuição, e não apenas a desvinculação do responsável.

Nas referências de agenda, equipamento, comentário da Base de Conhecimento e respostas rápidas, o banco possui comportamento que anula a referência à conta na exclusão, conforme medido. A referência de equipamento desta lista é distinta do vínculo de equipamento excluído em cascata, citado acima.

### Registros sem autor em produção

A condição de registro sem autor já existia em produção antes desta análise: 14 mensagens de chat, 24 registros de histórico e 64 registros de auditoria. No componente de avatar, a interface já possui tratamento para nome de autor vazio.

## Atualização posterior do caso

A seção anterior é a fotografia do momento da análise. O caso não parou ali.

Ainda em 15/09/2026, depois do encerramento da análise, **a exclusão foi executada pelo responsável**. O resultado foi conferido por leitura, sem nova escrita:

- as contagens previstas para cada operação foram conferidas durante a execução e coincidiram;
- a conta não existia mais;
- o e-mail estava novamente disponível, conferido com `lower(email)`;
- não restaram referências à conta nas colunas mapeadas no passo 3;
- a exclusão ficou registrada em `audit_logs` às 18:59 UTC de 15/09/2026;
- os 5 chamados preservados continuaram existindo, sem responsável.

O chamado que aguardava o cliente permaneceu sem responsável, como os demais. O critério do passo 9 "os chamados ativos têm responsável adequado" não foi atendido na execução, e a reatribuição segue pendente de decisão de quem autorizou.

# Etapa 3 · Propostas — nada implementado

## Lacunas que empurram clientes para "refazer a conta"

Os itens abaixo são propostas. Nenhum foi implementado, e cada um precisa de desenho aprovado antes da implementação.

### 1. Alteração de e-mail pelo administrador

**Prioridade proposta:** alta (maior impacto entre as lacunas).

**Situação atual:** o administrador não consegue alterar o e-mail de uma conta, porque `UserUpdate` não possui campo de e-mail.

**Justificativa:** evita a recriação de conta para corrigir o e-mail e mantém o histórico intacto.

**Requisitos a considerar:**

- verificar unicidade do e-mail sem diferenciar maiúsculas de minúsculas. Hoje, no código, o cadastro, o login e a criação por administrador comparam o e-mail por igualdade exata, e o índice único é sobre a coluna crua;
- registrar a alteração em auditoria, com o valor anterior e o novo;
- com SMTP disponível, avaliar a confirmação do novo endereço.

**Evidência de demanda:** já houve chamado pedindo exatamente isso: "Troca de email na plataforma".

### 2. Fusão de contas duplicadas

**Formato inicial proposto:** script avulso.

**Proposta:** mover chamados, chat, histórico, notas e vínculos de uma conta para a outra numa transação e, depois, excluir pela tela a conta que ficou vazia.

**Requisitos conceituais:**

- dry-run por padrão;
- relatório antes da execução;
- execução em transação;
- contagens esperadas;
- relatório depois da execução.

**Referência:** `scripts/funde_empresas_duplicadas.py`.

### 3. Ação de anonimização na interface

**Classificação:** lacuna de UX/produto.

**Situação atual:**

| Camada | Estado |
|---|---|
| Backend | Possui o endpoint `POST /users/{id}/anonymize` |
| Serviço do frontend | Possui a função `anonymizeUser` |
| Interface | Nenhuma tela chama a função; não existe ação de anonimização |

O modal de exclusão orienta a "usar Anonimizar", mas essa ação não existe na interface. Hoje a anonimização só é possível pela API.

**Ponto a considerar no desenho:** a anonimização deixa os chamados ativos com um responsável anonimizado, que não pode mais atendê-los. Sugestão a avaliar: um passo "Transferir chamados abertos para:".

### 4. Recuperação de senha por e-mail (SMTP)

**Classificação:** configuração, não desenvolvimento.

**Situação atual:** o fluxo de recuperação de senha está implementado no código e depende apenas do SMTP de produção.

**Efeito esperado:** com o SMTP em funcionamento, o caso de senha esquecida (primeira linha da triagem) deixa de exigir intervenção no banco.

**Apoio ao diagnóstico:** `scripts/testa_smtp.py` ajuda a distinguir um problema de credencial ou de configuração de um defeito da aplicação.

# Referência da análise

- Fatos de código conferidos no commit `d3bd1ac` (`main`), incluindo o que a tela de Usuários chama.
- Contagens medidas no banco de produção em 15/09/2026.
- Segunda revisão em 16/09/2026, com os fatos de código reconferidos no mesmo commit: escopo da anonimização, vínculos que impedem a exclusão, status de chamado, referências em cascata a partir de `tickets` e regra de papel do segundo fator.
- A tradução dos códigos de `confdeltype` vem da documentação do PostgreSQL.
- Este documento não contém dados pessoais de clientes.
