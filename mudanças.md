# Mudanças — Rickelme David

Registro do trabalho feito por **Rickelme David** neste repositório, por data.
O changelog do produto (o que o cliente vê) fica em
`frontend/src/data/changelog.ts`; o changelog do repositório, para devs, é o
[Changelog.md](Changelog.md).

---

## 27/08/2026 — O chat sobrevive a mais de um worker

Fecha a Fase 3. Cada worker passa a assinar um canal Redis e reemitir para os
próprios sockets, então duas pessoas no mesmo chamado se enxergam mesmo caindo
em processos diferentes.

### O painel salvou o desenho

Submeti três propostas a um julgamento por três lentes antes de escrever. Os
juízes convergiram num defeito que **nenhuma das propostas tinha visto**: duas
delas punham a origem — o carimbo que impede o worker de entregar a própria
mensagem duas vezes — como variável de módulo.

Num processo só, dois `ConnectionManager` dividiriam esse carimbo, a supressão
de eco descartaria a mensagem que deveria atravessar, e **o teste de entrega
entre processos não teria como ser escrito**. Um desenho intestável exatamente
na propriedade que justifica a fase.

A origem virou atributo de instância. Mutar de volta para global derruba dois
testes.

### As decisões, cada uma com o teste que a sustenta

| Decisão | Por quê |
|---|---|
| Entrega local **antes** do publish | Publicar antes faria a latência do Redis atrasar o socket do mesmo processo — o caso mais comum. O teste afirma a ordem, não só o resultado |
| `publicar` nunca levanta | O chat hoje não usa Redis; dependência nova não pode piorar o que já funciona. Teste com o broker quebrado exige que o socket local receba assim mesmo |
| Canal único, chamado no envelope | Canal por chamado obrigaria rede dentro do `connect`/`disconnect`, que são síncronos |
| Log só na **transição** | Uma linha por tentativa vira inundação numa queda de Redis. O teste deixa ~20 tentativas correrem e exige no máximo um aviso |

### O `--workers 1` fica, e o comentário mudou de razão

O `start.sh` dizia que não havia backplane. Agora há, e deixar isso escrito
enganaria a próxima pessoa. O número segue em 1 por **estágio**: com um worker o
assinante já sobe, publica e descarta o próprio eco, então fica exercitado em
produção sem risco nenhum. O readiness passou a reportar
`chat_backplane.assinado`; depois de alguns dias com a assinatura de pé, subir
vira trocar um número com evidência atrás.

**Resíduo assumido, escrito no código:** pub/sub não guarda nada. Durante uma
reassinatura, o que os outros publicarem para aquele worker se perde. Fica no
banco e aparece no F5 — mas ninguém sabe que precisa dar F5. Resolver de verdade
pede Redis Streams.

---

## 26/08/2026 (noite) — Rate limit, correlação de log, e uma migration que não subia

Três frentes numa tarde, mais um incidente que eu mesmo causei.

### O incidente: duas migrations com o mesmo id

Eu e a frente paralela criamos migrations com o id `v2q3r4s5t6u7` — partimos do
mesmo head e escolhemos o próximo da sequência ao mesmo tempo. O efeito não é
teste vermelho: `alembic upgrade head` recusa com "Multiple head revisions" e o
`start.sh` morre **antes** do uvicorn.

Ficou assim no `origin/main` por algumas horas. Qualquer deploy do backend teria
falhado — com o EasyPanel mostrando build verde e o container antigo
continuando a servir, que é o sintoma mais confuso possível.

A primeira tentativa de conserto **colidiu de novo**: a outra frente tinha
avançado três migrations, não uma.

E no mesmo dia deixei o CI vermelho por outro descuido meu: inseri um import por
`sed`, o bloco ficou fora de ordem, e eu rodei `black` e `mypy` naquele arquivo
mas **não o `ruff`** — que é o que o CI roda.

**Duas regras que passam a valer:** rodar `alembic heads` e confirmar um head só
sempre que criar migration; e rodar `ruff check .` da raiz do `backend/`, não só
nos arquivos tocados.

### Rate limiting — metade feita, e uma retirada deliberada

`/reset-password` e `/verify-email` não tinham limite nenhum; o primeiro é um
caminho de **escrita** que troca senha a partir de um token. O knob virou três,
um por modelo de ameaça, porque um só reaproveitado em quatro endpoints fazia
apertar o login apertar junto o cadastro.

O `Retry-After` passa a sair da janela real do limiter. Há teste que adianta o
relógio e exige que o número encolha junto — sem ele, uma constante de 900
passaria em qualquer asserção de intervalo.

**O `/refresh` ficou de fora, de propósito.** Com `FORWARDED_ALLOW_IPS` vazio o
rate limit enxerga o IP do proxy — um balde único para o sistema inteiro, como o
próprio `config.py` documenta. E o `/refresh` é chamado automaticamente pelo
interceptor de toda sessão ativa: um limite por IP ali deslogaria a empresa
inteira assim que o volume normal passasse do teto. Trocaria um risco hipotético
por uma indisponibilidade certa. Está registrado em teste, com o motivo.

### Correlação de log

O backend não tinha **nada**: nem `request_id`, nem `ContextVar`, nem middleware
que não fosse o CORS. Cada linha era um evento solto.

Agora toda requisição tem um id que atravessa o cabeçalho, o contexto e todas as
linhas — então o `serialize=True` que já estava ligado passa a produzir JSON
*com* campo, em vez de JSON sem nada além da mensagem.

Middleware **ASGI puro**, não `BaseHTTPMiddleware`: o do Starlette embrulha a
requisição em tasks e interfere em streaming, `BackgroundTasks` e propagação de
exceção — exatamente o que este projeto usa. Há teste de que 422, 404 e os
cabeçalhos de CORS continuam idênticos.

O `X-Request-ID` de fora é **adotado, mas conferido**: ele entra em toda linha de
log, então ecoar entrada arbitrária ali é injeção de log — uma quebra de linha
forja registros inteiros.

E oito linhas de `auth.py` logavam e-mail em claro. A pior registrava o e-mail
**digitado** numa tentativa falha: de quem não tem conta, e às vezes a senha,
quando a pessoa erra o campo.

### WebSocket

Duas defesas que o caminho HTTP tinha e o WS não: a **blacklist** (o logout
derrubava o HTTP e deixava o WebSocket aberto até o token vencer, até oito horas
depois) e o **teto de tamanho** — que não era só do WS: `ChatMessageCreate`
validava `min_length=1` e nenhum máximo, com a coluna em `Text`, então os dois
caminhos aceitavam megabytes.

**Um item do meu próprio plano foi retirado depois de ler o código:** trocar a
autorização inline do WS pelo `ensure_ticket_visible`. O helper é literalmente
uma comparação com `raise HTTPException(404)`; reusá-lo ali significaria
envolver um `raise` num `try/except` só para convertê-lo em close code. Seria
preferência, não correção.

### A varredura de contrato rendeu três defeitos

Depois do bug do refresh, varri os 18 serviços do front contra os schemas do
back procurando a mesma classe de defeito. Saíram dois, e a correção de um
revelou o terceiro:

| onde | o quê |
|---|---|
| filtro de usuários | "Suspenso" mandava um valor fora do enum → 422, a lista não carregava |
| calendário | `description: null` era ignorado → não dava para apagar a descrição |
| grupos | mesmo defeito, em `description` e `notes` |

Três outras pistas do mesmo formato foram lidas e **não** eram defeito — em
`tickets.py` e no `updateClientNotes` a atribuição é incondicional.

O console fez os dois primeiros e foi além do pedido: em vez de só remover as
oito ocorrências de "suspended", tornou `USER_STATUSES` a fonte única e tipou os
mapas por ela, então um estado inventado **para de compilar** em vez de virar
422. E trocou o teste que afirmava que gravar "suspended" funcionava por um que
**lê o enum do `models.py`** e compara — sem repetir a lista, porque lista
copiada volta a divergir.

| | Antes | Depois |
|---|---|---|
| Testes backend | 742 | **800** |
| Testes frontend | 314 | **315** |
| Cobertura backend | 86,9% | **87,6%** |

---

## 26/08/2026 (tarde) — Segundo fator para o staff, e um bug de sessão que ninguém tinha reportado

Primeira das cinco frentes de endurecimento. Começou por um diagnóstico do
código atual — não da memória da auditoria — e o diagnóstico achou coisa que
não estava na lista.

### O bug que apareceu sem ser procurado

Lendo o contrato de autenticação para planejar o MFA: o `/auth/refresh` devolve
`AccessTokenResponse` — três campos, **sem `refresh_token`**. O front declarava
que havia. O genérico do axios é uma afirmação sobre o runtime, não uma
verificação, então o TypeScript não tinha como reprovar: `data.refresh_token`
era `undefined`, e `localStorage.setItem` grava isso como a **string
`"undefined"`**, que é truthy e passa pela guarda.

O efeito não aparecia na renovação, e sim na seguinte. O refresh promete sete
dias; entregava **dezesseis horas** — uma renovação para gravar o lixo, outra
para morrer nele. Como o sintoma é "fui deslogado" e a reação é logar de novo,
o que reescreve o localStorage correto, isso podia nunca ter chegado como bug.

Os três mocks de `api.test.ts` descreviam um servidor que não existe, então o
interceptor tinha 100% de cobertura defendendo o defeito. Corrigidos. Entrou
também um teste no backend que fixa o **conjunto** de campos da resposta, não só
a presença — foi na folga entre as duas coisas que o front supôs um campo por
tempo indeterminado.

Aproveitei para varrer os 18 serviços do front contra os schemas do backend
procurando a mesma classe de defeito. Achou mais dois, **ainda não corrigidos**:

| onde | o quê |
|---|---|
| filtro de usuários | a opção "Suspenso" manda `status=suspended`, que não existe no enum — 422, a lista não carrega |
| calendário | `description: null` é ignorado no PATCH; não dá para apagar a descrição de um evento |

### O segundo fator

Antes de escrever, submeti o desenho do contrato de login a um painel
adversarial. **Ele derrubou a minha proposta**, e o motivo é real: o
`/auth/refresh` confere tipo, correspondência e status da conta — **nunca
`mfa_enabled`**. Sem apagar o refresh na ativação, quem já tivesse a senha e uma
sessão aberta seguiria renovando token por sete dias sem nunca ver um código. O
recurso falharia exatamente no caso em que alguém liga o MFA por desconfiar que
foi comprometido.

O que entrou, então:

- **Segredo cifrado, não hasheado.** Conferir o código exige recalculá-lo, então
  o servidor precisa recuperá-lo. O que protege é a chave morar fora do banco.
  Não existe chave default: uma chave versionada cifraria sem proteger de
  ninguém. Sem a variável, o recurso se declara indisponível e o login segue
  igual — nenhum boot é derrubado, ao contrário do que o guard de `CORS_ORIGINS`
  já custou em deploy.
- **Desafio em 403, não 200.** Com um 200 de desafio, um front que gravasse os
  tokens sem conferir reproduziria o bug de cima. O status diferente torna o
  erro impossível, não improvável.
- **Token de desafio opaco**, não um sexto tipo de JWT que dependeria de todo
  consumidor futuro de `decode_token` lembrar de conferir o `type`.
- **Nada falha para o lado de deixar entrar**: Redis fora, segredo ilegível,
  conta desativada no meio do caminho — tudo vira recusa, e há teste para cada.
- **`CHECK` no banco** proibindo `mfa_enabled` ligado sem segredo: esse par é
  uma conta trancada, e a regra caberia só no código até o dia em que um caminho
  de escrita novo esquecesse dela.

### O teste que mentia

O melhor retorno do dia veio de uma mutação que **sobreviveu**. Escrevi um teste
chamado "o mesmo desafio não serve duas vezes" e ele passava — mas mutando o
`consumir` para devolver sempre `True`, a suíte continuou verde. Ele provava o
antirreplay, não o uso único: sequencialmente, a segunda tentativa já morre na
leitura, porque o `DEL` apagou a chave. O retorno do `DEL` só importa numa
**corrida**.

Corrigir exigiu duas coisas: um teste com `asyncio.gather` e dar ao Redis falso
um `await asyncio.sleep(0)` em toda operação — sem ceder o event loop, duas
requisições sob `gather` correm sequencialmente e a corrida não acontece. Sem
isso eu teria commitado um teste que promete uma coisa e prova outra.

Dezenove mutações ao longo do dia, dezenove pegas depois disso.

### Decisões de escopo, ditas em voz alta

- **Sem códigos de recuperação.** A saída de emergência é o
  `scripts/desliga_mfa.py`, provado rodando em cinco cenários contra Postgres
  real. Com cinco pessoas de staff e o TI dentro de casa, um script operado por
  nós cobre o caso do celular perdido sem inventar mais uma superfície de
  credencial.
- **Sem leitor de QR.** Exigiria dependência nova no front para uma tela usada
  uma vez na vida por cinco pessoas. O segredo sai agrupado de quatro em quatro
  e o link `otpauth://` abre o app direto no celular.
- **Resíduo assumido:** apagar o refresh não invalida os access tokens já
  emitidos. A exposição cai de sete dias para 8 horas, **não para zero**. Fechar
  de verdade pede algo como `sessions_valid_after` no `get_current_user` — é a
  correção certa e é arquitetura nova, então fica como proposta separada.

### Antes de subir

1. **`MFA_SECRET_ENCRYPTION_KEY` no EasyPanel**, gerada com
   `Fernet.generate_key()`. Trocar essa chave depois torna ilegíveis os segredos
   já cadastrados.
2. **Front primeiro.** Se o backend subir antes, quem tiver ativado o MFA recebe
   um 403 que o front antigo não sabe ler.

| | Antes | Depois |
|---|---|---|
| Testes backend | 679 | **742** |
| Testes frontend | 305 | **314** |
| Cobertura backend | 86,5% | **86,9%** |
| Migrations | 22 | **23** |
| Dependências backend | — | `+pyotp`, `cryptography` pinada |

---

## 26/08/2026 — Fecho da auditoria do backend

Encerra o ciclo aberto em 24/08 com um code review de sistema inteiro: 17
routers, 24 modelos, 23 migrations, os serviços, o worker, o Docker e o CI.
As rodadas individuais estão registradas abaixo, por data; esta entrada é o
arco.

| | Antes | Depois |
|---|---|---|
| Achados abertos | 26 | **0** |
| Testes de backend | 574 | **679** (cobertura 86,5%) |
| Redes no CI | ruff, black, pytest | **+ mypy, + PostgreSQL real** |

### O que teria doído, e quando

Três achados não eram dívida — eram data marcada:

- **O protocolo travaria no 10.000º chamado do ano.** A busca do maior número
  ordenava texto, e `'HS-2026-9999' > 'HS-2026-10000'`. Depois desse chamado,
  nenhum outro poderia ser aberto até a virada do ano. A ~500/mês, faltavam
  cerca de vinte meses.
- **Nenhum e-mail sairia no dia em que o SMTP fosse ligado.** Com
  `SMTP_REPLY_TO` vazio — como nasce no `.env.example` — a montagem da
  mensagem levantava antes de qualquer tentativa de entrega, e o `except`
  registrava como falha de rede. Estava mascarado só porque não há SMTP.
- **O `PATCH /sla-configs/{id}` já estava quebrado**, em 100% das chamadas,
  desde que foi escrito: três kwargs que não existem no modelo. Configurar
  prazo de SLA pela interface nunca funcionou.

### As quatro vezes em que a auditoria errou

Vale mais registrar isto do que os acertos, porque diz como usar o documento:
em quatro dos vinte e seis achados, **quem foi implementar mediu e derrubou o
auditor**.

1. As anotações de retorno do `routers/sla.py` estavam corretas — seguir a
   auditoria teria trocado uma anotação certa por uma errada.
2. O `default=[]` da coluna não é o clássico argumento mutável: default de
   coluna vale na inserção, e `KBArticle().tags` é `None`.
3. O `mypy` **não** teria pegado o endpoint de SLA quebrado — modelo
   declarativo não tem `__init__` conferido. A rede que faltava era teste de
   endpoint.
4. O problema dos testes não era "SQLite tolera e esconde": as agregações do
   dashboard **não eram executadas contra banco nenhum**. Subir PostgreSQL no
   CI sem consumidor não acrescentaria nada — os testes vieram primeiro, o
   serviço depois.

### Dívidas registradas, com o gatilho de quando revisitar

Nenhuma é achado em aberto; são escolhas conscientes com a condição de saída
escrita:

| Dívida | Revisitar quando |
|---|---|
| Chat sem backplane (roda com 1 worker) | For preciso voltar a 2 workers — o backplane vem antes |
| Protocolo por leitura-e-escrita em vez de sequência | Colisão de protocolo aparecer no log |
| Prazo de resposta do SLA sem campo por ciclo | A operação precisar medir resposta do ciclo reaberto |
| Sem MFA para contas de staff | Houver conta de staff fora do time de TI |
| Contador de "artigo útil" sem registro de quem votou | O número for usado para decidir algo |
| Antivírus aceita anexo quando está fora do ar | O ClamAV estiver no ambiente e estável |

---

## 26/08/2026 — O A6, com o obstáculo desfeito

Ontem eu devolvi o A6 dizendo duas coisas. A primeira estava certa e foi
aceita: subir Postgres no CI sem consumidor não gate nada, porque as
agregações não são executadas contra banco nenhum. A segunda estava **errada**:
eu disse que não havia Postgres nesta máquina. Há — via `pgserver`, sem Docker,
na Rota B do `desenvolvimento-local.md`.

| Commit | O que foi feito |
|---|---|
| `205a893` | `fix:` **índice de `calendar_events`** declarado duas vezes |
| `fcd1f86` | `test:` **agregações do dashboard** contra PostgreSQL real |
| `docs:` | Este fechamento |

### Medir antes de escrever

O pedido foi explícito: o número primeiro, e um "não paga" com o número na mão
seria aceito. Medi:

| O quê | Custo |
|---|---|
| Subir o `pgserver` (uma vez, local) | 12,9 s |
| `create_all` das 24 tabelas | 1,2 s |
| Isolamento por transação revertida | **2 ms/teste** |
| Isolamento por `TRUNCATE` do subconjunto | 729 ms/teste |
| Funções com construção só-Postgres | 6 |
| Custo no CI (banco já de pé) | ~11 s |

Duas medições mudaram o desenho. A transação revertida é **365× mais barata**
que o `TRUNCATE`, então o isolamento por teste deixou de ser um custo a pesar.
E no Postgres o `create_all` vale para as 24 tabelas — o subconjunto que o
`test_groups.py` precisou é limitação do SQLite, não da abordagem.

Com 2 ms por teste e ~11 s no CI, contra seis funções sem gate nenhum, o número
paga. Segui.

### Medir já encontrou um defeito

A primeira tentativa de `create_all` falhou:
`relation "ix_calendar_events_start_date" already exists`. A coluna tinha
`index=True`, que já gera esse nome, e o `__table_args__` declarava um `Index()`
com o mesmo nome — duas definições, dois `CREATE INDEX`.

Não era bug vivo, e vale dizer por quê: em produção quem construiu o schema foi
o Alembic, e a migration cria o índice uma vez só. O banco está correto. O que
existia era divergência entre o modelo e a migration, invisível justamente
porque ninguém pedia `create_all` — e que travaria qualquer fixture montando o
schema a partir dos modelos.

O teste que fechou isso não prende esta linha: prende que **nenhum** índice
pode ser declarado duas vezes em toda a metadata. É de metadata, sem conexão,
então roda sempre.

### Nenhuma agregação falhou — e era o desfecho esperado

As cinco passaram de primeira contra Postgres real. Isso é consistente com o
que você verificou de fora: as agregações estão no ar e funcionando. O que se
compra aqui é proteção contra regressão.

Um teste que passa de primeira precisa ser validado por mutação, como manda a
casa. Troquei `isodow` por um campo inválido e o teste do relatório caiu com
`ProgrammingError` — a rede pega erro de dialeto, que é exatamente o que ela
existe para pegar.

A prioridade foi por risco, e o primeiro da fila é código meu: o
`_resumos_de_tecnicos`, reescrito na rodada do N+1 para agregar com `GROUP BY`,
era o único SQL novo que nunca tinha tocado um Postgres. Um dos testes afirma
que ele e a versão individual produzem os **mesmos números** — o contrato
daquele refatoramento, e se divergirem uma das duas telas mente.

### O que custou medição na fixture

Dois detalhes que só apareceram rodando, e ficaram escritos no arquivo:

A fixture do servidor é **síncrona** de propósito. Em fixture async de escopo
de módulo o pytest-asyncio dá um laço de evento por teste, e a conexão criada
no laço do módulo morre no primeiro uso — `transaction already deassociated
from connection`. Foi o primeiro erro que apareceu, e não tinha nada a ver com
as agregações.

E o serviço no CI entrou **por último**, depois de existir consumidor. Provei
os dois caminhos rodando: o do CI, simulando `TEST_POSTGRES_URL` com o banco já
de pé (5 passaram, 10,6 s), e o do skip, escondendo o `pgserver` para confirmar
que quem não tem Postgres continua com a suíte verde (5 pulados).

Suíte: 674 → 679 testes, verdes, cobertura 87%. mypy limpo. Sem migration. Nada
foi executado contra produção.

---

## 25/08/2026 (madrugada) — Cinco dos seis altos, e um que parei antes de fazer

Cinco entregues, um devolvido com a premissa corrigida. Seis commits.

| Commit | O que foi feito |
|---|---|
| `32f07de` | `fix:` **protocolo** deixa de travar no 10.000º chamado 🔴 |
| `ab791c3` | `fix:` **upload** deixa de materializar antes de medir 🔴 |
| `36bfc85` | `fix:` **TLS do SMTP** verificado; cadastro não espera o envio 🔴 |
| `9175752` | `fix:` **um worker** enquanto o chat for memória de processo |
| `79ef715` | `feat:` **`LLM_ENABLED`** desliga a IA sem apagar as chaves |
| `docs:` | Este fechamento |

### O A6 eu parei — e o motivo não é o previsto

O pedido era copiar o bloco `services: postgres:16` do `e2e.yml` e esperar
falhas, porque "os testes rodam em aiosqlite". Fui verificar antes de mexer, e
a premissa não se sustenta:

**Só o `test_groups.py` usa banco de verdade**, e ele escolhe SQLite em memória
de propósito, com o porquê escrito no próprio arquivo. É o único
`create_async_engine` da suíte inteira. Todo o resto mocka.

O `ci.yml` tem a variável `DATABASE_URL` e nenhum serviço — mas **nada se
conecta a ela**: o engine é criado na importação e nunca abre conexão, porque o
lifespan não roda sob `ASGITransport`.

Ou seja: subir o Postgres daria **zero falhas e zero cobertura nova**. Um
container em todo CI para não ser usado por ninguém — exatamente a
"configuração que mente" que passamos as últimas rodadas removendo.

E o achado de fundo é pior do que o descrito: as 26 construções só-Postgres do
`dashboard.py` (`date_trunc`, `isodow`, `count().filter()`, JSONB) **não passam
por tolerância do SQLite — elas não são executadas contra banco nenhum**. O
`test_dashboard.py` tem 9 testes, todos mockados. O que falta não é o serviço,
são os testes que executem essas queries.

O segundo obstáculo foi prático: não há Docker nem Postgres nesta máquina. Eu
escreveria esses testes, mas não conseguiria rodá-los — a primeira execução
seria no CI, contra a regra da casa de provar rodando. Preferi devolver com o
diagnóstico a empurrar teste que nunca vi passar.

### O menor conserto do dia impedia abrir chamado

O A2 é uma linha de `order_by`, e o efeito é o sistema parar. A sequência tem
4 dígitos e a ordenação é de texto, então a partir do 10.000º chamado do ano
`'HS-2026-9999' > 'HS-2026-10000'`. O máximo volta a 9999 **para sempre**, o
gerador propõe 10000 de novo, as cinco tentativas colidem no índice único e
nenhum chamado novo é aberto.

O A6 tinha sido posto antes justamente para tornar isto testável — mas a
tabela `tickets` compila no SQLite (ao contrário de `kb_articles`, com sua
coluna ARRAY), e comparação de texto é comparação de texto nos dois bancos. Deu
para testar em banco de verdade, verificável agora e rodando no CI de hoje.

Escolhi `length` desc antes do texto em vez de um CAST do sufixo para inteiro:
o CAST é mais direto de ler, mas estouraria no Postgres se uma linha com sufixo
não-numérico entrasse por fora do gerador. O `length` não tem como levantar.

### Testes que contam o que NÃO aconteceu

Dois itens desta rodada precisaram do mesmo tipo de teste, e vale registrar o
padrão porque ele se repete.

No A5, um teste que afirmasse só o `413` continuaria **verde** com a versão que
lê tudo primeiro — o status está certo nas duas. O que separa as duas versões é
quantos bytes o servidor aceitou antes de recusar, então é isso que o teste
conta: mandando 2 GB contra um limite de 64 KB, a leitura tem de parar perto do
limite.

No A8, um teste que afirmasse só `is None` passaria com a requisição sendo
feita e falhando — as funções já devolvem `None` quando falham. O que separa
"não mandou" de "mandou e deu errado" é a rede, então o teste conta
**construções de `httpx.AsyncClient`**: com a flag desligada, zero.

Esse segundo teste pagou na hora. Eu tinha posto a guarda nos dois helpers
`_call_openai` e `_call_anthropic`, achando que eram o ponto único — e o teste
mostrou quatro chamadas saindo mesmo assim. O `suggest_reply`, o
`summarize_conversation` e o `improve_message` montam as suas próprias
requisições; são oito construções de cliente HTTP no arquivo. A guarda foi para
as quatro entradas públicas.

### Um worker, e o lock que fica

O A3 é uma linha, e o que importa é o que vai junto. O `ConnectionManager`
guarda as conexões WebSocket na memória do processo: com dois workers, duas
pessoas no mesmo chamado caem em processos diferentes e não se ouvem — sem erro
nenhum, o que é o pior tipo de falha.

O lock no Redis do fechamento automático **fica**, mesmo sendo desnecessário
com um worker só. Voltar a dois é mudar um número no `start.sh`; sem o lock,
essa volta duplicaria histórico e notificação de cada chamado fechado, calada,
do mesmo jeito que a do chat. Remover agora seria trocar custo zero por
armadilha.

Três comentários no código afirmavam `--workers 2` e virariam mentira com a
mudança. Foram corrigidos para não depender do número — que é o ponto, porque
ele muda.

### O que a flag da IA existia para ser

O `LLM_ENABLED` nasce `true`, e a justificativa é a mesma que faz a flag
existir: desligar por padrão apagaria a classificação automática em produção no
deploy seguinte, sem ninguém pedir. Uma flag de emergência que muda
comportamento sozinha é o oposto de uma flag de emergência.

O que faltava não era a capacidade de parar — era parar **de forma
reversível**. Apagar as chaves do painel funciona e não tem volta sem ter as
chaves de novo.

Suíte: 668 → 673 testes, verdes, cobertura 86%. mypy limpo. Sem migration. Nada
foi executado contra produção.

---

## 25/08/2026 (fim da noite) — Os três altos baratos

Independentes entre si, poucas linhas cada, um commit por item. O mais barato
dos três era o único que quebrava uma funcionalidade inteira.

| Commit | O que foi feito |
|---|---|
| `45a1601` | `fix:` **anonimizar admin** vira privilégio de admin 🔴 |
| `43c3238` | `fix:` **PATCH de SLA** deixa de dar 500 em toda chamada 🔴 |
| `bdd1418` | `fix:` **rascunho da KB** some para quem não é da equipe 🔴 |
| `docs:` | Este fechamento |

### Três kwargs e uma funcionalidade que nunca funcionou

O A1 parecia o menor dos três: trocar `resource_type` por `entity_type` e mais
dois nomes. O tamanho do diff engana — **configurar prazo de SLA pela interface
nunca funcionou**. O `AuditLog` é construído depois de aplicar as mudanças e
antes do commit, então o `TypeError` derrubava a requisição inteira: 500 em
100% das chamadas, e a alteração nunca chegava ao banco.

O que vale registrar não é o erro, é por que ele durou tanto. Duas redes
falharam ao mesmo tempo, e nenhuma das duas por acaso:

O `test_sla.py` tinha **30 testes** — todos do motor de SLA, nenhum batendo no
endpoint. Um arquivo com trinta testes passa a impressão de coberto, e a
impressão é exatamente o que ele não deveria dar.

E o mypy, que acabou de ser ligado, **não pega isto**: modelo declarativo do
SQLAlchemy não tem `__init__` conferido — a mesma limitação que já tinha sido
medida quando se avaliou se ele teria pego o A1 da auditoria. Ligar o
verificador não substitui o teste de endpoint; ele fecha outra classe.

Por isso o segundo teste afirma os nomes dos campos da linha de auditoria, e
não só o 200: um `AuditLog` construído com qualquer nome passaria no primeiro.

### Exigir o ator no fetch, em vez de um helper de checagem

No A4 o pedido era extrair um helper e chamá-lo nos quatro pontos, no molde do
`ensure_ticket_visible`. Fiz um pouco diferente, e o motivo é a classe de erro
que se quer fechar.

Um helper de checagem separado depende de alguém lembrar de chamá-lo — que é
exatamente a falha que produziu o achado: a checagem existia no `GET` e os três
vizinhos não a repetiam. Então em vez de `_get_article_or_404(...)` seguido de
`ensure_article_visible(...)`, o **próprio fetch** passou a exigir o ator. Não
sobra caminho para carregar um artigo sem passar pela guarda; quem escrever o
próximo endpoint não tem como esquecer a linha, porque o parâmetro é
obrigatório.

Há uma diferença de desenho em relação ao `ensure_ticket_visible` que vale dizer
em voz alta. Lá o helper **não** conhece papel de propósito: a regra é "é seu?"
e a exceção de staff é decisão do call site, para não virar passe-livre
invisível. Aqui o papel não é exceção à regra — é a regra inteira: rascunho e
arquivado existem para quem escreve e revisa. Um helper que não soubesse disso
não teria o que checar.

### Guarda só onde não tem volta

No A0 a auditoria agrupava quatro endpoints e o pedido foi fechar um. Concordo,
e a razão é boa o bastante para ficar escrita: **anonimizar é o único que não
tem volta**. Editar e desativar são reversíveis e fazem parte do dia a dia de
uma equipe de dois técnicos — fechar os dois trocaria um risco pequeno por
atrito diário. Excluir já é barrado pelas chaves estrangeiras.

Sem técnico externo na empresa, o risco que sobra é o clique errado e a conta
de técnico comprometida. A segunda pesa mais aqui do que pesaria em outro
sistema, porque não há MFA.

### Achado vizinho, registrado sem corrigir

O `POST /kb/articles/{id}/feedback` incrementa `helpful` **sem registrar quem
votou**: o mesmo usuário incrementa em laço, e o contador de "este artigo foi
útil" não significa o que a tela diz que significa. Não é a mesma classe do A4
(não vaza nada) e não entrou nesta rodada. Fica aqui para não se perder.

Suíte: 644 → 656 testes, verdes, cobertura 86%. mypy limpo. Sem migration. Nada
foi executado contra produção.

---

## 25/08/2026 (noite) — Os oito médios restantes, em três blocos

Fechamento da auditoria do backend: cinco pequenos sem decisão pendente, os
dois mecânicos maiores e o preparo do antivírus. Nove commits.

| Commit | O que foi feito |
|---|---|
| `6e8f409` | `fix:` **o spec da API** deixa de ser público fora de dev 🔴 |
| `e3cea9a` | `fix:` **ambiente não-local** para de escapar das validações 🔴 |
| `52a3b7f` | `fix:` **DELETE de usuário** confere o que o banco recusa |
| `8e03e05` | `fix:` as duas listagens param de **mentir o `limit`** |
| `e8c642e` | `fix:` **link de confirmação** vira de uso único 🔴 |
| `d765587` | `perf:` as três listagens param de **consultar por item** |
| `846c6c4` | `chore:` **mypy zerado e ligado** no CI |
| `8ff214c` | `feat:` **revarredura de anexos** e aviso de antivírus fora |
| `docs:` | Este fechamento |

### O erro que a lista fechada conserta

O M4 parecia blindagem para um staging que ainda não existe, e é — mas o
desenho mudou de forma no meio. A condição era `if not self.is_production:
return`, e `is_production` só reconhece `"production"` e `"prod"`.

Trocar por "valide também staging" resolveria o caso citado e deixaria o
problema de pé, porque o problema não é o nome *staging*: é a **direção do
default**. Com a lista de quem valida sendo aberta, todo nome novo — e todo
nome digitado errado — nasce fora da validação. Um typo em `production`
desligava, de uma vez, a checagem de `SECRET_KEY`, de CORS e de `FRONTEND_URL`.

Com a lista de quem **escapa** sendo fechada (`development`, `testing`), o
mesmo typo agora *liga* as validações. O erro passou a apontar para o lado
seguro, que é a única coisa que se pode pedir de um default.

Apertar a validação não promove o ambiente: `is_production` continua False para
staging, senão ele herdaria decisões que são só de produção — o `/docs`
desligado, o seed de admin que não roda.

### O achado que não era bug

Ao zerar o mypy, `schemas/tag.py` acusou `strip_whitespace=True` no `Field`.
Não é parâmetro do `Field` no pydantic v2: chegava como kwarg extra — era a
deprecation que sujava toda rodada de teste — e não fazia nada.

Antes de mexer, conferi o comportamento em vez de deduzi-lo: `TagCreate(name='
urgente ')` **estrutura o nome sem espaços**. O strip acontece, só que quem faz
é o `str_strip_whitespace=True` do `AppBaseModel`, herdado. Ou seja: decoração
morta, com o comportamento certo chegando por outro caminho. Remover não muda
nada — e é por isso que dá para remover sem susto.

Vale registrar porque o caminho oposto era plausível: se eu tivesse "consertado"
o que o mypy apontou passando o parâmetro para onde ele funciona, teria mexido
num comportamento que já estava correto.

### O DELETE que recusava errado

O M5 tinha um sintoma pequeno (500 em vez de 409) e uma causa que valia
levantar: a guarda contava `Ticket.creator_id` e o banco tem **onze**
referências a `users.id` sem `ondelete`. Levantei uma a uma — as outras seis
têm `SET NULL` ou `CASCADE` e se resolvem sozinhas.

A consequência merece atenção: como auditoria está entre as onze, usuário que
já fez qualquer coisa no sistema deixa de ser excluível e passa a ser caso de
anonimização. Isso é o comportamento correto para a LGPD e já era a intenção
declarada do código (`"Use anonymize instead"`); a diferença é que antes a
intenção falhava com 500. Quem nunca agiu continua excluível — o log de
auditoria da criação aponta para o admin que criou, não para a conta criada.

### Números reais, não paginação

No M9 a escolha entre "paginar de verdade" e "devolver os números reais" não é
de gosto: depende do que a rota é. As duas são listas completas por
necessidade — o dropdown de responsável e os aparelhos do próprio usuário.
Paginar esconderia opções atrás de uma página que a tela não sabe pedir,
trocando uma mentira cosmética por um bug silencioso.

### O que o script de revarredura recusa fazer

O ClamAV vai subir, e o M7 preparou os dois lados. O script é o de sempre —
dry-run por padrão, `--aplicar` para gravar, no molde do `normaliza_cnpj` — mas
a decisão que importa está na tradução da resposta do ClamAV.

`unavailable` e `error: ...` **não** viram exame. Marcar como examinado um anexo
que o ClamAV não conseguiu ler seria inventar resultado, e é exatamente o erro
que um script apressado comete: contar o que tentou em vez do que conseguiu.

E nada é apagado, nem arquivo infectado. Anexo é prova de um chamado; um script
de limpeza que descarta o que não entende é pior que o problema que veio
consertar. Infectado sai em destaque no relatório para quem lê decidir.

O aviso de boot não muda a política — bloquear upload com o antivírus fora
derrubaria o anexo inteiro por causa de um serviço auxiliar. Só faz o estado
deixar de ser invisível, e a mensagem já aponta o script.

### Nota sobre o zap-scan

O M3 desliga o `/openapi.json` fora de dev, e o `zap-scan.yml` se alimenta dele
— por isso o cabeçalho e a descrição do input passaram a dizer que o alvo
precisa ser um ambiente com o spec exposto.

⚠️ Enquanto mexia ali notei outra coisa, que **não** consertei por não conseguir
verificar a topologia do deploy: o workflow monta o alvo como
`${target_url}/openapi.json` com `target_url` terminando em `/api/v1`, mas o
spec é servido na **raiz** (`/openapi.json`), porque `openapi_url` é
configuração do FastAPI e não passa pelo prefixo dos routers. Se não houver um
proxy reescrevendo, esse alvo já estava 404 antes desta mudança. Vale conferir
na próxima vez que o scan rodar.

Suíte: 632 → 639 testes, verdes, cobertura 85%. mypy limpo em 66 arquivos. Sem
migration. Nada foi executado contra produção.

---

## 25/08/2026 (tarde) — Fazer o sistema conseguir dizer que está quebrado

Três achados médios com um tema só: **o sistema não tinha como avisar que
parou**. A rotina do RN-005 morria em silêncio, o healthcheck respondia "ok"
sem conferir nada, e o e-mail saía antes de o fato existir — as três formas de
o software afirmar uma coisa e viver outra.

| Commit | O que foi feito |
|---|---|
| `9146dc2` | `fix:` **o laço do fechamento automático** sobrevive ao erro e se carimba |
| `ec533c4` | `feat:` **`/api/v1/health` vira readiness**; `/health` intocado |
| `66f2569` | `fix:` **e-mail só sai depois do commit** que o torna verdade |
| `docs:` | Este fechamento |

### A pergunta que decidiu o M6

O desenho do M6 tinha duas alternativas na mesa e eu fui instruído a escrever o
argumento antes de tocar nos 13 chamadores. As duas caíram por motivo prático,
não por gosto:

**BackgroundTasks do FastAPI** só existe onde existe request. O
`ticket_lifecycle.py:131` notifica de dentro do laço de fechamento automático,
sem request nenhum — precisaria de um segundo mecanismo só para esse caminho, e
o `_auto_transition`, que notifica e é chamado de outro handler, teria de
carregar o parâmetro pela cadeia inteira.

**Listener de `after_commit` do SQLAlchemy** era o desenho elegante: automático,
invisível, sem tocar em chamador nenhum. Morreu numa linha do `conftest.py` —
"o banco é mockado em todos os testes". Com `session = AsyncMock()`, o commit
não é um commit do SQLAlchemy e o evento nunca dispararia: o mecanismo inteiro
ficaria fora do alcance da suíte. Mecanismo que a suíte não enxerga não entra.

Sobrou o registro de pendências chaveado por sessão. Antes de propor, testei a
parte que só falha na prática: `WeakKeyDictionary` aceita como chave tanto a
`AsyncSession` real quanto o `AsyncMock` da suíte, e isola sessões simultâneas.

### O detalhe que resolveu a retentativa de graça

A pendência é **retirada do registro antes** do commit, não depois. Parece
detalhe de ordem e é o que faz o laço de protocolo funcionar sem que ninguém
mexa em `rollback`: se o commit levanta, a pendência daquela tentativa já saiu
e não sobra para a próxima. Cinco tentativas, um e-mail — e os outros dois
`rollback` do projeto (`groups.py`, `surveys.py`) estão em módulos que nem
notificam.

Troquei os **15** commits dos três módulos que notificam, não só os que seguem
um `notify()`. O `_auto_transition` notifica e é chamado de outro handler, então
qual commit carrega pendência não se decide olhando o site isolado — provar o
negativo caso a caso seria mais frágil que a uniformidade.

### Dois testes que fixavam o problema como contrato

`test_notify_schedules_email_task_when_settings_provided` afirmava que o
`notify()` criava a task de envio na hora. Isso **era** o bug do M6: o teste
travava o envio-antes-do-commit como se fosse a regra. Foi substituído por um
que prova as duas metades — notify sozinho não envia, o commit envia uma vez só.

No M2, `test_health_check_versioned` afirmava 200 e `status: ok` numa rota que
não conferia nada; virou redundante com o teste novo de readiness e saiu. O da
versão passou a valer nos **dois** estados, porque a resposta de degradado é a
que mais convida a despejar detalhe de diagnóstico — e é a que um curioso
consegue provocar.

### Um teste meu que prometia demais

O teste de cancelamento do laço do M1 passou de primeira, então verifiquei por
mutação, como manda a casa. Trocar o `except` por `except BaseException` — que
engoliria o cancelamento — **manteve o teste verde**. Desde o 3.11 o asyncio
re-entrega o cancelamento pendente no `await` seguinte, então o teste não
consegue distinguir. Corrigi o docstring e o comentário para dizerem o que a
coisa realmente prova: que o laço termina no `cancel`. Quem protege o
desligamento é o `except Exception` — `CancelledError` é `BaseException` —, não
o teste.

### O resto

O `/health` não foi tocado de propósito, e agora há teste que trava isso: é o
alvo do `HEALTHCHECK` do Dockerfile e dos compose, e um liveness que depende do
banco transforma oscilação de Postgres em restart de container. Antes de mudar
o status code do `/api/v1/health` conferi quem o consome: ninguém
programaticamente — todo probe automático do repositório bate em `/health`.

Suíte: 600 → 611 testes, verdes, cobertura 86%. Sem migration. Nada foi
executado contra produção.

---

## 25/08/2026 — A rodada dos achados pequenos, e o que um deles escondia

Os seis achados de severidade baixa da auditoria do backend, em dez commits.
Nenhum deles é urgente sozinho; juntos são quase todos a mesma doença — **o
repositório afirmando coisas que o código não faz**. Configuração que promete
um controle inexistente, pacote que parece implementado, anotação que declara
um tipo que não é o dele, docstring que descreve uma permissão diferente da que
o `authorize` aplica, versão congelada em `1.0.0` enquanto o produto ia para
v1.8.0.

| Commit | O que foi feito |
|---|---|
| `c615ad7` | `fix:` **log de e-mail deixa de descartar destinatário e motivo** |
| `c53bb80` | `fix:` **nenhum e-mail sairia com `SMTP_REPLY_TO` vazio** 🔴 |
| `b30f75e` | `refactor:` remove **sete configurações** sem uso |
| `3cf63d2` | `refactor:` remove o **bloco SLA** do `config.py` ⚠️ |
| `3c4b433` | `refactor:` remove o **pacote `worker/` e o Celery** |
| `4e975b7` | `chore:` `.dockerignore` passa a excluir `.coverage` e `uploads/` |
| `21e8b22` | `refactor:` `tags.py` para de anotar usuário como `object` |
| `e1985a4` | `fix:` **tags do artigo da KB** deixam de ser lista compartilhada |
| `dcfc25f` | `refactor:` **versão** ganha fonte única e sai da resposta pública |
| `a8de8c6` | `fix:` **pesquisa de satisfação** cai junto com o ticket no ORM |
| `docs:` | Este fechamento |

### O achado pequeno que escondia um grande

O item B1 pedia uma coisa modesta: cinco chamadas de log usavam placeholder de
`%`-formatting, que o loguru não entende — a linha saía com o literal `%s` e os
argumentos iam para o lixo. O pedido incluía, "se der", um teste que capturasse
o log e afirmasse que o destinatário aparece na linha.

O teste foi escrito, ficou vermelho pelo motivo certo, e depois da correção
**continuou vermelho por outro motivo**. A linha registrada não era a falha de
SMTP que o teste simulava: era um erro de validação do `MessageSchema`. O
`send_email` monta a mensagem com `reply_to=None` quando `SMTP_REPLY_TO` está
vazio, e o fastapi-mail recusa `None` nesse campo — exige lista.

Ou seja: **com `SMTP_REPLY_TO` vazio, nenhum e-mail sairia**. A exceção estoura
na montagem, antes de qualquer tentativa de entrega, e o `except` a engole como
se fosse falha de rede. E `SMTP_REPLY_TO` nasce vazio — no `config.py` e no
`.env.example`.

Hoje isso não aparece porque não há SMTP em produção: o `send_email` retorna
antes, na guarda de "SMTP não configurado". A falha apareceria inteira, e como
"e-mail simplesmente não funciona", no dia em que o Erick ligasse o SMTP.

O teste que já existia para esse caminho — `test_send_email_handles_smtp_failure`
— passava. Ele afirmava só `result is False`, e `False` era verdade pelos dois
motivos: pela falha simulada e pelo erro de montagem que ninguém tinha visto.
Um teste que afirma pouco demais não é uma rede de segurança, é uma luz verde
sobre um buraco.

### O bloco de SLA era o inverso: o código certo, a configuração mentindo

O `config.py` anunciava `SLA_BUSINESS_HOURS_END=18:00`. O `utils/sla.py`
calcula com `_WORK_END = 17`. E não existe uma linha ligando os dois — o
`sla.py` não importa `Settings`.

O perigo aqui não é o valor errado, é o **conserto** errado. Quem abrisse os
dois arquivos veria uma divergência óbvia e uma correção óbvia: ligar a
configuração ao motor. Isso mudaria o prazo de todos os chamados de uma vez,
sem ninguém perceber, contra uma regra confirmada com o cliente em 05/08 e
registrada como RN-013.

Por isso este foi o único item em que remover não era preferência e sim a única
opção segura — e por isso veio em commit separado dos outros sete campos
mortos, onde a escolha entre remover e ligar era de gosto. Tirei os quatro
campos do bloco, não só os dois do horário: `sla_business_days` e `sla_timezone`
estavam igualmente mortos e são a mesma armadilha para o próximo.

A proteção real não é o commit — é um comentário nas constantes do `sla.py`
explicando por que são constantes e apontando para o documento de decisões.
Mensagem de commit ninguém lê daqui a um ano; o comentário está onde a pessoa
vai estar olhando.

### Dois achados que a auditoria descreveu com mais gravidade do que tinham

Registro porque a diferença muda o que se deve fazer com eles.

O default mutável de `KBArticle.tags` **é** um problema, mas não o clássico
`def f(x=[])`: default de coluna vale na **inserção**, não na construção —
`KBArticle().tags` é `None`, não `[]`. O estrago real é que o `default=[]`
guarda um único objeto reusado em toda inserção, então mutar o valor que veio
dali contamina os artigos inseridos depois no mesmo processo. `default=list`
resolve, e o teste afirma exatamente essa propriedade: duas avaliações do
default precisam devolver objetos distintos.

Já as anotações do `routers/sla.py` **não eram um achado**. A auditoria pedia
para "anotar o tipo real" em `-> list[SLAConfig]` e `-> SLAConfig`, mas esse já
é o tipo real: as funções devolvem objetos do ORM, e é o `response_model` que
filtra para a resposta HTTP. Anotar `SLAConfigResponse` ali seria trocar uma
anotação correta por uma errada. Não mexi. (O `sla.py` usa `= Depends(...)`
onde o resto do projeto usa `Annotated[...]` — inconsistência de estilo, não
mentira de tipo; fica para quem quiser uniformizar.)

### O resto

O pacote `app/worker/` saiu inteiro. Não havia uma chamada `.delay(` no
repositório, nem processo Celery no `start.sh`, e as duas tarefas de negócio
devolviam `{"status": "queued"}` sem fazer nada — inclusive uma
`tasks.classify_ticket` que era um stub vazio ao lado do `classify_ticket` de
verdade, no `services/llm.py`. Nos documentos, a rotina periódica dentro da API
deixou de aparecer como consequência de uma falta ("o Celery está configurado
mas não tem worker") e passou a constar como decisão, com o motivo. Os dois
comentários no código que ainda citavam o Celery como configurado foram
corrigidos junto — se ficassem, seriam a próxima mentira.

A versão fez as duas coisas que o achado colocava como alternativa, porque
resolvem problemas diferentes: fonte única em `app/__init__.py`, para não
congelar de novo; e fora do `/api/v1/health`, que responde sem autenticação e
não tem por que entregar a release exata a qualquer um.

Suíte: 586 → 594 testes, todos verdes, cobertura 85%. Nenhuma migration —
`default=list` e cascade de relationship são comportamento do ORM, o DDL não
muda. Nada foi executado contra produção.

---

## 24/08/2026 — Duas fontes de verdade para "empresa", e o começo da reconciliação

Frente nova, aberta pelo próprio trabalho de documentação: escrever a
atualização do `decisoes-e-regras.md` esbarrou numa dívida que ninguém tinha
mapeado — existem **duas** fontes de verdade para "de qual empresa é este
cliente" (`User.cnpj` e `User.company_id`), e elas não conversam. Não é dívida
teórica: foi ela que, três dias antes, empurrou a unicidade de número de série
para "por dono" quando a decisão de negócio correta era "por empresa".

| Commit | O que foi feito |
|---|---|
| `99b0847` | `docs:` **levantamento** das duas fontes de verdade |
| `f7ddadc` | `docs:` **`companies.id` declarado única autoridade** de escopo por empresa |
| `62f022e` | `fix:` **CNPJ com pontuação deixa de chegar ao banco**, com script de backfill |
| `1c414c0` | `fix:` nome de teste que **prometia mais do que provava** |
| `e30968e` | `fix:` **cobertura parava de contar** depois do primeiro `await` no banco |
| `470d56c` | `test:` **domínio de empresa em `groups.py`** sai do descoberto |
| `abdee48` | `feat:` **criar empresa pela sugestão passa a vincular** os clientes |
| `3478bae` | `fix:` **admin de seed deixa de nascer com senha do repositório** 🔴 |
| `b736114` | `test:` as duas defesas do seed de admin |
| `docs:` | Este fechamento |

### O levantamento corrigiu a própria premissa

A suspeita inicial era que nenhum dos dois campos fosse normalizado. O
levantamento provou o contrário, e o contrário é pior: `users.cnpj` **é**
normalizado desde sempre — o `OnboardingUpdate` tira a pontuação, e o front
ainda confere os dígitos verificadores antes de enviar. Quem não normalizava
era `companies.cnpj`, texto livre sem validador nenhum, alimentado por um
`placeholder` que ensinava o admin a digitar `00.000.000/0000-00`.

As duas colunas estavam normalizadas em **direções opostas**. Uma guardava
`11222333000181`, a outra `11.222.333/0001-81`. Nenhuma comparação por string
entre elas jamais daria igual. O `e41684c` do dia anterior afirmava o contrário
e foi corrigido no `f7ddadc`.

Três outras coisas saíram do mapa, e nenhuma era esperada:

- **`company_id` não existe fora da tela de Grupos.** Não está no
  `UserResponse` — o cliente não recebe o próprio vínculo, e nenhuma outra tela
  sabe que o campo existe.
- **Já havia uma ponte**, `GET /groups/companies/suggestions`, que agrupa
  clientes sem vínculo pelos dados de onboarding. Só que criar a empresa a
  partir da sugestão **não vincula ninguém**: os clientes seguem com
  `company_id` nulo, a sugestão reaparece e clicar de novo cria uma empresa
  duplicada.
- **Excluir uma empresa desvincula os clientes em silêncio.** Comprovado em
  Postgres efêmero, rodando o mesmo caminho de código do endpoint: a FK é
  `ON DELETE SET NULL`, o ORM concorda, as notas da empresa somem junto e nada
  avisa quantos clientes foram soltos. Não há teste dizendo qual é a regra —
  **nenhum** teste da suíte referencia `Company`, `company_id` ou qualquer
  endpoint de `/groups`.

### A recomendação não foi nenhuma das três opções

As opções na mesa eram normalizar o CNPJ e derivar a empresa dele (a), vincular
a `Company` no onboarding (b), ou só documentar quem manda (c). A recomendação
foi uma **sequência**, porque (a) sozinha é uma falha de autorização esperando
acontecer: o CNPJ é autodeclarado e o servidor só conta 14 dígitos — quem
confere os dígitos verificadores é o front, que é o cliente. Eleger esse campo
como chave de escopo é deixar o cliente escolher em que escopo ele cai.

Primeiro declarar a fonte de verdade (`f7ddadc`), depois normalizar as duas
pontas para que casar seja **possível** (`62f022e`), depois fechar o laço das
sugestões vinculando por CNPJ normalizado — é ali que (a) e (b) se encontram
sem os defeitos de nenhuma das duas: o casamento usa o CNPJ, a autoridade
continua sendo o clique do admin.

### A normalização, e a decisão de pôr a regra no tipo

O caminho óbvio era repetir o `@field_validator` nos três schemas que não
tinham. Não foi o escolhido: um validador copiado por modelo deixa o **próximo**
campo de CNPJ nascer sem validação nenhuma, que é literalmente o defeito que o
`CompanyCreate` tinha. A regra passou a viajar no tipo — `CnpjOpcional` e
`CnpjObrigatorio` — e esquecer dela agora exige contrariar a anotação.

O cuidado que mais custou pensamento foi o campo opcional. `None` e string
vazia precisam passar e virar `None`, porque limpar o campo no front manda
`""` e não `null`; um validador estrito ali quebraria criar empresa sem CNPJ,
que hoje funciona, e todo `PATCH` que não mexe em CNPJ. Mas `"abc"` não é
campo limpo, é erro de digitação, e virar `None` em silêncio seria perder dado.
São dois testes separados justamente porque a distinção é fácil de errar.

No front, o `placeholder` de empresa passou a pedir dígitos e a máscara voltou
só na exibição. Apareceu de brinde uma terceira duplicação: `OnboardingPage` e
`ProfilePage` tinham a **mesma** máscara de digitação copiada, e foi ela que
colidiu com o import do helper novo. As duas cópias saíram.

### O script que não apaga o que não entende

O backfill é avulso e roda à mão — regra do projeto, e desta vez com um motivo
a mais: o `.env` local aponta para produção. Dry-run por padrão, `--aplicar`
para gravar, e importando a **mesma** normalização do validador, porque uma
cópia própria da regra gravaria linha que a API recusaria depois.

A decisão que importa é o que fazer com a linha que não soma 14 dígitos:
ela é **relatada e deixada como está**. Um script de limpeza que descarta o que
não entende é pior que o problema que veio consertar; quem decide o destino
dela é quem lê o relatório.

Rodar de verdade num Postgres efêmero pagou o preço na hora: o relatório morria
com `UnicodeEncodeError` antes da primeira linha, porque o console do Windows
abre em cp1252 e o script roda na máquina de quem administra, não no container.
Testar só a função pura nunca teria mostrado isso.

### O que fica

O Passo 3 — fechar o laço das sugestões — depende de `groups.py` ganhar
testes, e ele não tem nenhum. O Passo 4, regras "por empresa" de verdade, só
faz sentido depois de medir quantos clientes têm `company_id`; as consultas de
diagnóstico estão prontas no documento de investigação e ainda não foram
rodadas em produção. O backfill também não.

E ficou registrado que o escopo de chamados é provavelmente mais urgente que a
série: hoje o cliente vê só os próprios chamados, então dois funcionários da
mesma empresa não enxergam o que o colega abriu.

### Cobrir antes de mexer, e o que a cobertura revelou

O Passo 3 saiu em duas partes, e a ordem não era formalidade: mexer no
`groups.py` sem teste seria repetir o próprio bug que ele tem — ação que
promete o que não cumpre.

Escrever os testes trouxe duas descobertas que não estavam no plano.

A primeira: **a suíte inteira media cobertura errado.** O relatório dizia que
`update_company` tinha a primeira linha coberta e as sete seguintes não — o
laço inteiro dado como não executado, com teste passando por ele. A mutação
provou o contrário: quebrar aquelas linhas derrubava o teste, então elas
executavam. A causa é o greenlet — o SQLAlchemy async atravessa
`greenlet_spawn` a cada `await` de banco e o coverage perde o rastro na volta.
Uma linha de configuração resolveu, e `groups.py` foi de 43% para 62% **com os
mesmos testes**. Todo número de cobertura que este repositório reportou até
hoje estava abaixo do real.

A segunda: **uma asserção minha não sobreviveu à própria checagem.** Eu tinha
escrito `assert resp.content == b""` para provar que a exclusão de empresa é
silenciosa. Ao mutar o endpoint para devolver um corpo, o teste continuou
passando — o `204` já garante corpo vazio, então a asserção não provava nada.
Foi trocada pelo status, que cai se a exclusão virar bloqueante (`409`) ou
informativa. É a mesma armadilha do teste renomeado no `1c414c0`, e desta vez
quem pegou foi a mutação, não a leitura.

Os testes usam banco de verdade, não mock, e isso foi decisão e não gosto: a
desvinculação silenciosa **não dá para provar com mock**. Quem desvincula o
cliente é o SQLAlchemy com a FK `ON DELETE SET NULL` por baixo; um mock
afirmaria que `db.delete` foi chamado e passaria mesmo que a regra fosse a
oposta. SQLite em memória reproduz o mesmo resultado do Postgres efêmero do
levantamento e roda no CI sem subir serviço.

### O laço fechado, e o defeito que virou cosmético

Criar empresa pela sugestão agora vincula quem a gerou. As três decisões:

**Endpoint próprio**, e não parâmetro no `create_company`. Cadastro manual não
pode ganhar efeito colateral de vínculo em massa — uma empresa criada à mão
que, por coincidência de CNPJ, arrastasse clientes junto seria o inverso exato
do defeito consertado aqui: ação que faz **mais** do que diz.

**Reaproveitar em vez de duplicar**, mas só dentro do mesmo grupo. Isso não
foi preferência: `Company.group_id` é `NOT NULL` e único, então "reusar" uma
empresa de outro grupo seria *mudá-la de grupo*. A pergunta se dissolveu no
schema.

**Lista explícita e prévia.** O vínculo vai pelos `client_ids` que a tela
mostrou, não por uma consulta que o servidor refaz, e o modal ganhou um passo
de confirmação com nome e e-mail de cada um. Vincular em massa sem ver quem é
ação que ninguém desfaz. De brinde, some a janela entre a tela e o clique:
cliente que mudou de estado no meio derruba tudo com `409`, e nada é gravado
— nem a empresa.

O agrupamento das sugestões pela tupla inteira **ficou como está**. Rechaveá-lo
no CNPJ exige decidir qual nome vence quando dois clientes da mesma empresa
digitaram nomes diferentes, e o que fazer com quem tem `company_name` mas não
tem CNPJ — decisões de produto, não de implementação. Mas o estrago acabou: com
o reaproveitamento por CNPJ, os dois cards caem na mesma empresa. O defeito
virou cosmético — dois cliques em vez de um — em vez de gerar duplicata.

### O achado do dia: o boot de produção criava um admin com senha pública

Verificação de segurança pedida no fim do dia, e o resultado foi o pior tipo:
não era hipótese, era cadeia confirmada em três arquivos. `Dockerfile` chama
`start.sh`; `start.sh` roda `python -m app.seeds` a cada boot; `seed_admin`
criava `admin@healthsafety.com` com `Admin@123456` — senha escrita no código
deste repositório — como administrador **ativo**, sem nenhuma guarda de
ambiente.

O detalhe que mais incomoda é que o projeto **já sabia**. O `app.seeds_e2e`
tem guarda de produção, tem teste, e a docstring dele diz com todas as letras
que colocar conta de teste no `app.seeds` criaria "logins com senha em texto
claro conhecida por qualquer um que leia este repositório". O raciocínio certo
foi escrito, aplicado à conta de teste, e não à de admin — que é a mais
poderosa das duas.

A correção tem duas defesas, e elas não são a mesma coisa dita duas vezes.
`APP_ENV` de produção não cria a conta; **e** sem `SEED_ADMIN_PASSWORD` não
cria a conta. A segunda existe porque a primeira falha **aberta**: `app_env`
tem default `development`, então variável ausente ou digitada errada
desligaria a guarda de ambiente sozinha. Tirar a senha do código é a correção;
a guarda de ambiente é só a defesa.

E uma decisão que contraria a letra do pedido, de propósito: **nenhuma das
duas levanta exceção.** O pedido era "mesmo fail-fast do `seeds_e2e`", mas
`run_seeds` está no caminho do boot, e o `start.sh` roda com `set -e` — um
`RuntimeError` ali deixaria o container sem subir. Seria trocar um vazamento
de credencial por uma indisponibilidade. No `seeds_e2e` o `raise` é seguro
justamente porque nada chama aquele módulo em produção. A recusa vai para o
log e a execução segue; produto e SLA continuam sendo semeados, porque são
catálogo e não credencial.

Efeitos colaterais que precisaram vir junto: o workflow de e2e passou a
definir a variável (senão o Playwright perde o login do admin, contra o banco
efêmero do job) e a receita de ambiente local ganhou o `export` — com uma
pegadinha documentada, porque "subiu e o admin não loga" agora é sintoma
esperado de variável esquecida. Tem teste guardando o acoplamento entre o
workflow e o `helpers.ts`.

**O incidente não está fechado.** Falta verificar se a conta existe hoje em
produção e com que senha; a consulta está proposta e nada foi executado contra
o banco real. E note a assimetria que a idempotência cria: ela protege quem já
trocou a senha, mas em compensação apagar o usuário deixou de ser forma de
reiniciá-lo — sem a variável, ele não volta.

### O que continua na fila

O backfill e as cinco consultas de diagnóstico seguem sem rodar em produção.
O Passo 4 — regras "por empresa" de verdade — continua dependendo de medir
quantos clientes têm `company_id`. E limpar o CNPJ de uma empresa pela tela
segue sem funcionar: a guarda `if val is not None` do `update_company` vale
para os sete campos, então mexer nela é frente própria. Tem teste segurando
o comportamento atual para que a mudança seja escolha.

---

## 21/08/2026 — Fila técnica, oráculos e um tema que passa a perguntar

Dia sem frente de produto. Produção estável, `main` em `5fc10ce`, e as três
pendências do painel (`CORS_ORIGINS`, porta 8000, SMTP) paradas com o Rickelme
e o Erick. Sobrou o que estava na fila.

| Commit | O que foi feito |
|---|---|
| `f7945e0` | `test:` **FilterSelect, FormDropdown e ThemeContext** saem do descoberto |
| `3f3af90` | `feat:` **filtro de equipamentos sem dono** na listagem de Produtos |
| `77a8e9c` | `fix:` **/onboarding** deixa de abrir para quem não tem onboarding |
| `7371bc7` | `fix:` **chamado alheio deixa de denunciar que existe** |
| `902d331` | `fix:` **e-mail sai da frente da resposta** no forgot-password |
| `0e1a917` | `refactor:` duas linhas mortas — comentário e guard do dropdown |
| `8542183` | `feat:` **tema segue a preferência do sistema operacional** |
| `d5fa7a6` | `feat:` **número de série único por dono**, com migration |
| `32fc736` | `fix:` **chip de SLA** para de dizer Vencido para resposta já dada |
| `d361e78` | `ci:` **Playwright em workflow separado**, acionado à mão |
| `docs:` | Este fechamento |

### Três componentes que o CI protegia sem saber

O Vitest é gate do CI desde `1583b8b`. Isso significa que tudo que **tem**
teste está protegido — e que tudo que não tem passa como se estivesse. Os três
apontados pela rodada de test review não eram casca: são o dropdown de filtro
das listagens, o dropdown dos formulários e o tema.

O que justifica teste próprio em cada um é o que um `<select>` nativo daria de
graça e aqui é código nosso:

- **FilterSelect** renderiza o painel em portal no `document.body`, para não
  ser cortado pelo `overflow` da barra de filtros. O preço é que ele flutua
  ancorado a uma posição calculada **uma vez** na abertura, e por isso precisa
  fechar sozinho em clique fora, scroll e resize. Também reancora pela direita
  quando abriria fora da janela — sem isso, o filtro do fim da barra mostra
  metade das opções cortadas.
- **FormDropdown** é o irmão de dentro dos formulários: sem portal (dentro de
  um modal o portal escaparia da pilha de foco), com rótulo, erro de validação
  e desabilitado. Nos dois, a linha do placeholder devolve `""` — e esse é o
  contrato com quem consome.
- **ThemeContext** guarda a preferência em dois lugares que precisam
  concordar: a classe `dark` no `<html>`, que é o que o Tailwind lê, e a chave
  `helphs-theme`. Um sem o outro dá o bug clássico de escolher claro, dar F5 e
  voltar escuro — então tem um teste que fecha o ciclo escolher/sair/voltar,
  que é onde a divergência apareceria.

Um achado de escopo, registrado no próprio teste: **o padrão é o escuro, não a
preferência do sistema operacional**. O `ThemeContext` não lê
`prefers-color-scheme`; quem chega sem nada salvo — e quem chega com um valor
estragado — vê o escuro. Isso agora está afirmado por teste em vez de
subentendido, e se um dia virar decisão mudar, o teste é onde a conversa começa.

Teste escrito depois do código passa na primeira execução, o que não prova
nada. Cada arquivo foi então verificado por mutação: quebrar o fechamento do
painel do filtro, o fechamento do dropdown e a gravação da preferência derruba
exatamente os testes correspondentes, e só eles.

### O órfão que ninguém achava

O `3efb0cf` subiu o seletor de dono. Mas para usar o seletor o staff precisa
primeiro **achar** o equipamento órfão, e não tinha como: a listagem só
oferecia busca por nome e situação.

O ponto que decidiu a forma da solução: **`list_equipments` é paginada no
servidor**. Filtrar no navegador varreria só a página aberta — com 200
equipamentos e 20 por página, o órfão da página 7 ficaria invisível para
sempre, que é exatamente o caso que o filtro existe para resolver. Precisava
ser parâmetro novo do endpoint.

Entre um `without_owner: bool` e um filtro de dono genérico, ficou o booleano.
Não por ser menor: as duas coisas **não são alternativas**, são ortogonais.
"Sem dono" é a *ausência* de `owner_id` e não caberia num `owner_id=<uuid>` sem
inventar um valor sentinela para o nulo — e sentinela em query param é o tipo
de contrato que ninguém lembra seis meses depois. Um filtro por dono
específico, se fizer falta, entra ao lado deste sem renegociar nada.

O detalhe que virou teste: o filtro **soma** ao escopo por dono do cliente,
nunca substitui. Cliente pedindo `without_owner=true` recebe `owner_id = <ele>`
**E** `owner_id IS NULL`, que não casa com nada — lista vazia. A versão errada
dessa mesma linha seria uma enumeração do parque órfão inteiro por qualquer
cliente autenticado, então ela tem teste próprio dizendo isso.

### Uma porta que já estava trancada por dentro

`/onboarding` ficava sob o `AuthGuard` e fora do `OnboardingGuard`. Qualquer
autenticado abria a tela digitando a URL: o staff, que não tem onboarding
nenhum, e o cliente que já completou — para quem refazer significaria
sobrescrever dados de cadastro já revisados.

Ficar fora do `OnboardingGuard` era proposital: ele redireciona *para*
`/onboarding`, então colocá-la dentro apontaria o redirecionamento para si
mesmo. O que faltava não era mover a rota, era o **par**: o `OnboardingGuard`
empurra para a tela quem ainda deve preencher, o `OnboardingOnlyRoute` novo
tira de lá todo o resto.

Vale dizer o que isto **não** é: não é correção de segurança. A porta que
importava — o endpoint — já foi fechada no `b1ab978`. Isto é higiene de rota,
só no front.

### Doze cópias de uma regra que dizia demais

Aprovado o levantamento, foi execução. O `403` de chamado alheio dizia
"existe, mas não é seu" — meia resposta a mais do que quem só tem o id deveria
conseguir. Com uma lista de UUIDs dava para enumerar o sistema sem ler um
chamado sequer.

O tamanho real do problema só apareceu no levantamento: a regra estava copiada
em **quatro arquivos sob três nomes** — `_check_ticket_access` nos anexos,
`_get_ticket_or_403` no chat e mais quatro cópias inline em tickets e
avaliações. Doze pontos de entrada. A premissa de que o helper dos anexos era
compartilhado entre routers não se sustentou: ele nunca saiu do arquivo dele;
o que viajou foi a *ideia*, recopiada à mão cada vez.

Passa a existir `ensure_ticket_visible` em `app/utils/`. **Ele não abre exceção
para staff** — quem decide isso é o call site, e essa foi a decisão explícita
do Rickelme. O motivo tem precedente no `2ad773c`: um helper que "sabe" que
admin passa vira passe-livre invisível no dia em que alguém o chamar de um
endpoint novo sem ler o corpo dele. Aqui a regra é só "é seu?", e cada endpoint
diz em voz alta quem submete a ela.

**Só para cliente.** Técnico e admin já listam o sistema inteiro sem escopo, de
modo que `404` entre eles não fecharia oráculo nenhum e quebraria
assumir/atender — escopo entre técnicos seria regra de acesso nova, conversa de
produto. E onde a recusa é de **papel**, o `403` fica: técnico na observação do
cliente, staff que não abriu o chamado na avaliação. Trocar por `404` ali não
esconderia existência de nada e trocaria "seu perfil não faz isso" por uma
mentira que manda o admin caçar um bug que não há. Os dois casos têm teste
dizendo isso.

#### Três coisas que uma varredura de status HTTP não acharia

1. **`GET /attachments/{id}` vazava duas vezes** — pelo id do anexo *e* pelo do
   chamado pai, com três respostas distinguíveis. O cliente agora recebe a
   mesma nos três casos, e ela fala do **anexo**: responder "chamado não
   encontrado" a quem pediu o anexo já confirmaria que o anexo existe.
2. **O WebSocket tinha o mesmo oráculo em código de fechamento** — `4003`
   contra `4004`. Quem tivesse a lista de ids enumerava o sistema pelo chat sem
   nunca receber um HTTP `403`. Fecha `4004` nos dois casos, com o mesmo
   motivo. Não havia teste nenhum de WS no repositório; agora há, com um
   harness que dispensa o lifespan da app (que abre conexão real com o
   Postgres).
3. **`"Attachment not found"` não tinha tradução** em `apiError.ts`. O
   Rickelme pegou isso conferindo o dicionário antes de aprovar. Sem somar a
   entrada, a correção de backend entregaria ao cliente um toast cru em inglês
   — exatamente o bug que o `2db8dfa` consertou para equipamento. Foi no mesmo
   commit: o texto só passa a chegar ao cliente por causa da mudança do
   backend, e separar deixaria uma janela com a tela em inglês.

#### O que impede a regra de divergir de novo

O texto da recusa e o do id inexistente saem de **uma constante por recurso**
em cada router. Não é enfeite: dois `404` com mensagens diferentes continuariam
separando "não é seu" de "não existe", só que com mais disfarce. Além disso,
cada arquivo ganhou um teste de paridade no molde do
`test_ownership_refusal_message_is_the_same_everywhere` que já guardava os
equipamentos — a versão anterior desta regra divergiu justamente por uma cópia
esquecida, então o contrato agora é executável.

Cobertura nova nos três ramos que não tinham teste nenhum: `observation`,
`GET /attachments/{id}` e o WebSocket. Sem migration, sem backfill. **471 → 490
testes no backend.**

### O oráculo que ainda não existe

O envio de e-mail do `forgot-password` era aguardado dentro do handler, e o
SMTP só é chamado no ramo da conta existente. Enquanto for assim, os dois ramos
respondem em tempos diferentes e o **relógio diz o que a mensagem cala** — o
mesmo oráculo de enumeração que o `f8e6013` fechou no login, renascendo ao lado
dele.

O que torna o caso interessante é que **ele não existe em produção hoje**. Não
por cuidado nosso: só porque não há SMTP configurado. O oráculo nasceria pronto
no dia em que o Erick ligasse o SMTP, sem ninguém ter tocado numa linha de
código. É a diferença entre uma dívida e uma armadilha com data marcada — e o
motivo de o Rickelme ter mandado entrar antes.

`BackgroundTasks` nos dois endpoints com o mesmo formato — `forgot-password` e
`resend-verification`. A resposta sai antes de o envio começar.

O teste não mede relógio. Mock de rede não tem latência real, e teste de tempo
em CI compartilhado é instável por natureza — ele mediria o runner, não o
código. Mede a **ordem**: chamando a app pelo ASGI cru dá para ver os eventos
que saem. Antes da correção a sequência era
`['envio', 'response.start', 'response.body']`; agora o envio vem por último.
Mais dois testes garantem que os ramos neutros não agendam envio nenhum —
agendar seria pior que aguardar, porque mandaria e-mail a quem não tem conta.

Ficou de fora, de propósito: o `register` também envia inline. Lá a resposta já
difere por ramo (`409` de e-mail duplicado), então o relógio não acrescenta
nada ao que o status já conta. Quando o **#3.1** tornar o register neutro, este
mesmo tratamento precisa ir junto — senão a neutralidade nasce furada pelo
tempo.

### O tema passa a perguntar antes de decidir

Ontem o teste do `ThemeContext` registrou que o padrão era escuro fixo e que o
app não lia `prefers-color-scheme`. Registrar em vez de consertar foi o certo:
era decisão de produto, não bug. O Rickelme decidiu mudar.

Agora quem nunca escolheu recebe a preferência do sistema operacional; quem já
escolheu manda, contra o sistema inclusive — o SO é o palpite inicial, não uma
ordem. Duas consequências que a mudança de regra arrastou junto, e que não eram
óbvias no enunciado:

1. **A gravação saiu do efeito de montagem.** O código antigo gravava o tema no
   `localStorage` a cada montagem. Mantendo isso, o valor do SO seria capturado
   na primeira visita e **congelado ali**: quem trocasse o tema do sistema
   depois nunca mais veria a mudança refletida, e "seguir o sistema" valeria
   por uma visita só. A gravação foi para o `toggleTheme` — só escolha de gente
   é gravada.
2. **O `index.html` tinha a regra duplicada.** Existe ali um script anti-flash,
   que roda antes do bundle, com a lógica antiga ("se não for `light`,
   escurece"). Sem acompanhar, quem usa o SO no claro veria um flash escuro em
   **toda** visita — exatamente o que aquele script existe para evitar. Ele
   precisa repetir a regra à mão porque roda antes do JS da aplicação; os dois
   lados agora apontam um para o outro em comentário, e está escrito no arquivo
   que essa cópia não tem teste que a segure.

No teste, o ciclo escolher/sair/voltar continua — agora com o SO fingindo o
tema **oposto** ao escolhido. Sem isso ele passaria pelo motivo errado, caindo
no padrão do sistema em vez de ler o que foi gravado.

E as duas linhas mortas que ontem ficaram registradas viraram remoção: o
comentário de `products.py` citando um helper que o `7371bc7` apagou, e o
`!disabled &&` do `FormDropdown` que a verificação por mutação mostrou nunca
rodar — o atributo `disabled` do `<button>` já impede o navegador de disparar o
clique.

### O serial deixa de ser único no mundo

A unicidade de número de série era global. Duas coisas erradas: empresas
diferentes podem ter aparelhos de mesmo número — fabricantes repetem séries
entre lotes e linhas — e o `409` global era um oráculo: contava ao cliente que
**outra** empresa tinha cadastrado aquele serial.

**Uma correção na minha análise, que precisa constar.** Na proposta eu descrevi
o custo do escopo por `owner_id` invertido: escrevi que dois usuários da mesma
empresa *não* poderiam cadastrar o mesmo serial. É o contrário. Com unicidade
por `owner_id`, cada colega tem o próprio escopo, então **dois usuários da mesma
empresa podem cadastrar o mesmo aparelho físico, um por cabeça**. Esse é o
**furo aceito** — o Rickelme decidiu com o trade-off já corrigido: `owner_id`
agora, porque a migration é segura e sem backfill; a evolução para escopo por
empresa/CNPJ fica na fila, **condicionada à normalização do campo CNPJ**, que
hoje é texto livre digitado no onboarding (dois usuários da mesma empresa podem
ter gravado `12.345.678/0001-90` e `12345678000190`). Rodada própria.

A migration tem **dois índices**, porque em SQL `NULL` não conflita com `NULL`:
só o composto `(owner_id, serial_number)` deixaria dois equipamentos sem dono
com o mesmo serial passarem em silêncio — e órfão é estado transitório que
alguém vai consertar, então o conflito apareceria tarde. O índice parcial
`WHERE owner_id IS NULL` fecha isso sem depender de `NULLS NOT DISTINCT`
(Postgres 15). O índice simples por serial fica, não-único: a busca de chamados
usa a coluna.

O upgrade é seguro por construção: a regra nova é estritamente mais fraca que a
antiga, então nada que existia viola o índice novo — raciocínio que dispensa
consultar produção. O **downgrade pode falhar** se, depois do upgrade, dois donos
cadastrarem o mesmo serial; é a natureza da volta e está no docstring.

**Testado num Postgres efêmero (`pgserver`), não no banco do `.env`** — que
aponta para produção. Upgrade com os três índices; mesmo dono repetindo
recusado; donos distintos aceitos; órfão × com-dono aceito; dois órfãos
recusados; downgrade recusado com duplicado entre donos e OK depois de limpar;
upgrade de volta. Dois tropeços meus no caminho, ambos antes do commit: escolhi
o `down_revision` pela data do arquivo e acertei numa revisão que já existia
(`s9n0…`) — o Alembic acusou "present more than once"; e o detector de erro do
meu script lia só stdout enquanto o `psql` mandava as violações para stderr, o
que produziu dois "inesperado" que eram, na verdade, o banco recusando
corretamente.

No código, as quatro cópias da checagem viram `_recusa_serie_duplicada`. O
`PATCH` de staff valida o **par final** (dono, serial): mover um equipamento
para um dono que já tem aquele serial não muda o serial, e um check de "o serial
mudou?" deixaria passar. A suíte mocka o banco, então o mock **emula a tabela**
— lê os parâmetros compilados da consulta e só devolve a linha se o par bater.
É o que permite provar "dois donos com o mesmo serial passa" sem Postgres.

### O chip que dizia Vencido para quem já tinha respondido

A hipótese do Rickelme estava certa, e o mecanismo era mais simples do que ela.
O `SlaChip` recebia `dueAt` e `breached` e usava cada um para uma coisa: o
**texto** vinha do relógio, a **cor** vinha do backend. Chamado respondido no
prazo e reaberto: âmbar (certo) com "Resposta: Vencido" (errado). E sem
reabertura nenhuma: respondeu às 9h, prazo às 14h, às 15h dizia Vencido.

A causa real: `sla_first_response` **não era enviado ao front**. O chip não
tinha como saber. Passou a ser exposto (leitura, sem migration), e o chip
ganhou `respondedAt` — preenchido, diz "Respondido" e para o relógio.

Por que **não** silenciar pelo `breached`, que seria o reflexo: `check_breaches`
só roda em caminhos de **escrita**, nunca na leitura nem num timer. Um chamado
que venceu há duas horas e ninguém tocou chega com `breached = false`, e a
contagem ao vivo é o único lugar que conta a verdade sobre ele. Esconder o
Vencido pela flag trocaria uma mentira por outra, na direção mais perigosa. Está
em comentário no chip e em teste.

O chip saiu de dentro da `TicketDetailPage` para `components/ui`, onde dá para
testar; verificado por mutação. A lista de chamados tinha o mesmo bug em outra
roupa — a barra de "1ª Resposta" virava "SLA Vencido" por `timeLeft <= 0`, e o
chamado respondido pelo chat, que desde o `230d670` não sai de `open`, ficava
vermelho com a resposta dada há horas. Mesmo tratamento.

**O que fica para depois, registrado:** dar ao ciclo reaberto um prazo de
resposta próprio. Hoje o chip diz "Respondido" com base no ciclo 1 — verdade,
mas não a medição que a operação vai querer um dia. Campo por ciclo.

### O Playwright ganha um lugar para rodar — com um veto no meio

Ordem combinada: seed do cliente → `e2e.yml` só com `workflow_dispatch` → duas
execuções manuais verdes → ligar o `schedule`. O arquivo já traz o bloco de
agendamento comentado com essa instrução.

O **veto do Rickelme** mudou onde o seed mora, e é o ponto mais importante da
frente: os usuários do e2e **não podem** entrar no `app/seeds.py`. Ele roda no
boot de produção (`start.sh`), e isso criaria contas de teste com senha em
texto claro conhecida no banco real. O cliente e2e vive em `app.seeds_e2e`,
módulo separado que só o workflow chama e que **se recusa a rodar em produção
antes de abrir sessão** — nem para ler. Dois testes são o contrato: em produção
levanta e não toca no banco; `app.seeds` rodado num banco vazio não cria conta
nenhuma com e-mail de teste, e o código-fonte dele não menciona e2e.

O resto do levantamento virou linha do workflow, cada uma com o motivo escrito
no arquivo: `APP_ENV=testing` porque a suíte faz ~16 logins do mesmo IP contra
um limite de 5 por 15 minutos; chaves JWT efêmeras geradas no job com `openssl`
(nenhum segredo do repositório); Redis como service mesmo o boot só avisando,
porque chat e blacklist de token usam; o cliente nasce com
`onboarding_completed`, senão o guard o joga em `/onboarding` e o spec que
espera `/403` morre no primeiro passo.

A credencial de técnico saiu do `helpers.ts` em vez de ganhar usuário: nenhum
spec loga como técnico. Um teste no backend garante que `helpers.ts` e
`seeds_e2e` têm os mesmos valores — se um lado mudar e o outro não, o e2e
falharia no login sem dizer por quê.

**Fase 3 (k6): sem mudança, e de propósito.** Teste de carga contra os
`services` de um runner do GitHub mede o runner, não a aplicação — Postgres em
container efêmero, sem volume, sem os dois workers do `start.sh`, sem a rede do
EasyPanel. O número que saísse teria aparência de medição, e isso é pior que
nenhum número. Segue aguardando staging.

### Decisões registradas, sem código

- **Guard de produção: fica como está.** O `fail-fast` do boot quando falta
  `CORS_ORIGINS` já pegou configuração errada duas vezes. O silêncio custou
  semanas; o barulho custou minutos. Não vira aviso.
- **Reunião da Helô** segue com o Rickelme. Fase 1 continua bloqueada por ela,
  sem ação técnica nossa.

### O que fica na mesa

- **`CORS_ORIGINS`, porta 8000 e SMTP** seguem no painel, com o Rickelme e o
  Erick.
- **`register` neutro (#3.1)** — quando entrar, o `BackgroundTasks` precisa ir
  junto, senão a neutralidade nasce furada pelo tempo de resposta.
- **Serial único por empresa/CNPJ** — evolução do escopo por `owner_id`, para
  fechar o furo aceito (colegas da mesma empresa duplicando o mesmo aparelho).
  Condicionada à normalização do campo CNPJ; rodada própria.
- **SLA por ciclo de reabertura** — o chip agora diz a verdade sobre o ciclo 1;
  dar prazo próprio ao ciclo reaberto é outra conversa.
- **`e2e.yml`: duas execuções manuais verdes e depois ligar o `schedule`** (o
  bloco está comentado no arquivo). O primeiro run vai dizer se a estimativa de
  8–12 min por execução bate.
- **k6 / Fase 3** aguarda staging. Não tocar.

---

## 20/08/2026 — O SLA passa a medir conversa, não clique

Primeira frente da Helô — e a única que não depende da reunião com o cliente.
O Welton desenhou o atendimento por IA em
[`2026-08-11-helo-atendimento-ia-design.md`](docs/superpowers/specs/2026-08-11-helo-atendimento-ia-design.md);
a revisão contra o código (`87dd05a`) achou um pré-requisito que ninguém tinha
previsto, porque **já estava quebrado sem a Helô**.

| Commit | O que foi feito |
|---|---|
| `230d670` | `fix:` **primeira resposta do SLA passa a exigir uma fala ao cliente** |
| `docs:` | Desenho da regra nova + fechamento |

### O indicador media o tempo até alguém clicar

`sla_first_response` era gravado em três lugares, sempre sob
`old_status == TicketStatus.open`. Como o mapa de transições só deixa `open`
virar `in_progress` ou `cancelled`, "primeira resposta" queria dizer, na
prática, **"alguém assumiu ou cancelou o chamado"**.

O levantamento dos treze caminhos (tabela completa no
[desenho](docs/superpowers/specs/2026-08-20-primeira-resposta-sla-design.md))
achou distorções nas duas direções ao mesmo tempo:

- **Dois falsos negativos, no caminho mais usado.** `chat.py` não tocava no
  SLA — zero ocorrências. Técnico que responde pelo chat sem mexer no status
  não registrava nada. Pior: o `_apply_chat_transition` nem transiciona a
  partir de `open`, então o chamado ficava parado e mudo para o indicador.
- **Três falsos positivos.** Atribuir marcava. Assumir marcava. E **cancelar
  pelo `PATCH /status` marcava** — chamado cancelado entrava no tempo médio de
  resposta com poucos segundos. Cancelar pelo `DELETE`, o outro caminho, não
  marcava: dois jeitos de cancelar, dois resultados de SLA.
- **Um buraco.** Resolver um chamado que já saíra de `open` não marcava nada.
  Atendido, resolvido, e invisível para a métrica.

### O achado que apareceu no meio do caminho

Melhor que o problema original. Nos três pontos a ordem era esta:

```
ticket.sla_first_response = now
check_breaches(ticket, now)      # ← já vê o campo preenchido
```

E `check_breaches` só avalia o prazo **enquanto `sla_first_response` é nulo**.
Um chamado assumido três dias depois do prazo saía limpo, com
`sla_response_breach = False`. A condição viva do dashboard também exige o
campo nulo, então a violação sumia dos dois lados. **Na prática, primeira
resposta atrasada quase nunca era contada como violação.**

O conserto é a ordem: `register_first_response` avalia o prazo e só então
carimba. Autocontida, a ordem nos call sites deixou de importar.

### A regra nova não menciona status nenhum

Marca a **primeira mensagem de chat de quem não é o autor do chamado**, mais a
resolução como rede de segurança — a nota de resolução é texto que o cliente
lê, e sem ela o buraco continuaria.

"Não é o autor" em vez de "é staff" foi decisão deliberada: é o mesmo critério
que o `_notify_other_party` já usa para decidir a quem notificar. Mesma
pergunta — há alguém do outro lado? —, uma só resposta no código. Cobre de
graça o admin que abre chamado interno e responde a si mesmo.

Mudança de status **não conta**, nem para `awaiting_client` manual. Se a
equipe atende por telefone, a fala tem que virar mensagem no chamado de
qualquer jeito — para o SLA e para o próximo técnico que pegar o caso.

Não olhar para status é o que torna a correção pré-requisito da Helô, e não
consequência dela: o chamado que nasce em `ai_handling` e nunca passa por
`open` funciona igual. E a mensagem da IA é excluída por dois filtros
independentes, `is_ai` e remetente nulo — o teste do remetente nulo já está no
repositório, antes de a Helô existir.

### Sem migration e sem backfill

A regra decide quando gravar; não reescreve o que já está gravado. Chamado
fechado mantém o valor, relatório antigo não muda, e chamado vivo se corrige
na próxima mensagem.

O backfill era possível — `chat_messages` tem `sender_id` e `created_at` — e
foi recusado por dois motivos. Migration roda sozinha no boot do container, e
um `UPDATE` varrendo `tickets × chat_messages` é a categoria de coisa que
derruba a API na subida, como o guard de CORS derrubou na véspera. E
**reescrever números que a equipe já viu em relatório é pior do que ter um
passado torto e datado**.

### O número vai piorar, e foi combinado antes

O card de violação de resposta sobe e o tempo médio sobe, porque o indicador
deixa de apagar violação atrasada e deixa de contar clique como conversa. Não
é regressão — é ele parando de mentir. Como o deploy é manual, a comunicação
com a equipe acontece no tempo de quem sobe.

### Fica na fila: a reabertura entrega metade do que anunciou

Conferido de passagem, e é contradição de verdade. O changelog do produto da
v1.4.0 diz que "reabrir um chamado devolve um prazo de atendimento novo, em
vez de trazê-lo de volta já vencido". O `reopen_ticket` renova só o prazo de
**resolução** — o de resposta fica no dia da abertura original.

Dá para ver na tela: o `TicketDetailPage` desenha dois chips lado a lado, e o
chamado reaberto volta com "Resolução" contando de novo e **"Resposta:
Vencido"**, permanentemente. Metade da promessa.

Não é conserto trivial, e por isso não entrou: renovar o prazo de resposta
obriga a decidir o que fazer com o `sla_first_response` do ciclo anterior —
zerá-lo apaga o único registro que existe dele, o que provavelmente pede um
campo por ciclo em vez de um campo por chamado. Decisão de produto própria.

### Testes

17 novos, nenhum dependendo do relógio: `now` é sempre injetado por parâmetro
e a função não chama `datetime.now()`. Dez sobre o núcleo puro (incluindo
resposta atrasada preservando a violação, pausa esticando o prazo e o
remetente nulo da Helô), dois nas rotas de chat e cinco de regressão — assumir,
cancelar e atribuir **não** marcam; resolver fora de `open` marca. Suíte
completa em 466 testes, cobertura 82,65%.

---

## 19/08/2026 (noite) — Terceira rodada da revisão

Um `/code-review` sobre 51 arquivos desde `154ec74` verificou token a token que
a reformatação do black (`57ca9d9`) é semanticamente idêntica e aprovou o
403→404, o `field_validator` do `APP_ENV`, o guard do
`EMAIL_VERIFICATION_ENABLED` e os testes novos do front. Sobraram três achados,
todos fechados aqui.

| Commit | O que foi feito |
|---|---|
| `a1bbd94` | `fix:` **o dummy do login dessincronizava de `BCRYPT_ROUNDS`** — a única piora que a rodada anterior introduziu, e ela veio justamente de consertar outra coisa |
| `b1ab978` | `fix:` **staff criava equipamento pertencente a staff** em `POST /equipment/my` |
| `3efb0cf` | `feat:` **seletor de dono na ProductsPage**, fechando o ciclo do `51a9cb8` |

### O knob vivo virou armadilha (`a1bbd94`)

Ligar `bcrypt_rounds` ao `pwd_context` (`b06228f`) tirou a configuração morta —
e criou uma pior: o dummy seguia fixado em 12 por literal. Medido antes de
corrigir, com `BCRYPT_ROUNDS=14`: **o e-mail desconhecido custava 486 ms e o
cadastrado 1777 ms**. O oráculo de tempo que o `f8e6013` fechou reabria maior
do que era originalmente (1 ms contra 250 ms).

O teste de paridade não pegava, e a razão importa: ele comparava o dummy com o
`pwd_context` **do processo que roda a suíte**, que nunca tem `BCRYPT_ROUNDS`
no ambiente. Afirmava 12 == 12 e passava verde enquanto produção divergia — um
teste verdadeiro sobre o ambiente errado.

Agora o import se encarrega: `_dummy_no_custo_do_contexto` compara o custo
embutido no literal com o do contexto e **só regera quando divergem**. No
caminho normal não paga bcrypt nenhum, que era o motivo de o hash ser fixo;
quem sobe os rounds paga um hash por processo, uma vez. O contrato de teste
passa a ser contra `settings.bcrypt_rounds`, não contra o contexto do processo.
Depois da correção: **1846 ms contra 1796 ms**.

### `/equipment/my` é do cliente, nos verbos que escrevem (`b1ab978`)

`POST /equipment/my` fazia `owner_id = actor.id` com qualquer perfil, então
técnico e admin criavam equipamento pertencente a staff — o mesmo estado que o
`_valida_dono` recusa com 400 nos endpoints de staff. Equipamento assim some da
listagem escopada e nunca vira chamado.

`POST`, `PATCH` e `DELETE` passam a exigir `authorize(UserRole.client)`. A
**leitura fica aberta de propósito**: se algum usuário virou staff depois de ter
sido cliente, o equipamento antigo continua existindo, e negar o `GET`
esconderia dele o que já era seu. Verificado antes que nenhuma tela quebra —
`/equipment` não tem `RoleGuard`, mas o link da sidebar é `roles: ["client"]` e
a `EquipmentPage` não ramifica por perfil; staff só chegava lá digitando a URL.

Efeito colateral saudável: o ramo de 403 para staff no `_check_equipment_owner`
virou código morto e saiu junto, com o teste que o cobria — ele passava, mas
por um motivo que deixou de existir.

### Seletor de dono (`3efb0cf`)

O `productService` omitia `owner_id` nos tipos de payload, então o backend
aceitava o campo desde `51a9cb8` e nenhum caller o enviava.

Entra um `SearchSelect` em `components/ui`, com **busca no servidor**. Um
dropdown pré-carregado não serve: `GET /users` tem `limit` máximo de 100 e
ordena por `created_at desc`, então quebraria em silêncio ao passar de 100
clientes — mostrando os 100 mais recentes, ordem que não ajuda a procurar um
nome. O componente não conhece a API (recebe `onSearch`), o que mantém `ui/`
apresentacional.

O campo aparece ao criar **e** ao editar, com "— Sem dono —": é o que conserta
os órfãos existentes um a um, sem migration. Sem backfill automático — o
sistema não tem como adivinhar dono.

Detalhe que só aparece implementando: o RED do service foi no **`tsc`**, não no
Vitest. O runtime já repassava o payload inteiro; quem barrava era o tipo.

### Fila desta rodada

- **Higiene de rota**: `/onboarding` está sob `AuthGuard` mas **fora** do
  `OnboardingGuard`, então staff consegue abrir a tela de onboarding digitando
  a URL. O bloqueio no backend (`b1ab978`) já fechou a porta que importava — a
  `OnboardingPage` chama `createMyEquipment` —, mas a rota em si continua
  aberta. Higiene, sem urgência.
- **Filtro "sem dono"** na listagem de equipamentos da ProductsPage, para o
  staff encontrar os órfãos remanescentes sem varrer página por página.

---

## 19/08/2026 — Push, ressurreição do CI e destrave do login

O push dos 24 commits da frente de segurança revelou que **o CI do main
estava vermelho desde 06/08** — e como o black rodava antes do pytest, **a
suíte do backend nunca rodava**: o gate de testes estava morto sem ninguém
perceber. Duas causas empilhadas, corrigidas em sequência, e um bug de
produção reportado pelo Rickelme no mesmo dia.

| Commit | Tipo | O que foi feito |
|---|---|---|
| `57ca9d9` | style | Reformata o backend com o black pinado (27 arquivos, zero lógica) — decisão do Rickelme; era a 1ª causa do CI vermelho |
| `4449ce2` | test | 2ª causa, revelada quando o pytest voltou a rodar: `keys/` é gitignored e o CI não tinha chaves JWT — 54 testes com `FileNotFoundError`. O conftest agora gera par RSA efêmero por sessão; `pytest` roda em máquina zerada |
| `1b3d355` | fix | **Login travado em produção** ("Confirme seu e-mail" sem e-mail chegar): a exigência era *inferida* de `SMTP_USER`/`SMTP_FROM_EMAIL` preenchidos — e o `.env.example` vem com os dois preenchidos (senha `CHANGE_ME`). Agora a adoção é explícita: `EMAIL_VERIFICATION_ENABLED` (default `false`) **e** SMTP presente; flag ligada sem SMTP recusa o boot em produção. Contas presas voltam a entrar sem mexer no banco |

Resultado: **CI verde de ponta a ponta no `4449ce2`** — o primeiro do main
desde antes de 06/08, com a suíte do backend (agora 435 testes, 82,35%)
rodando como gate de verdade.

**Fica na fila para quando o SMTP for adotado**: ligar
`EMAIL_VERIFICATION_ENABLED=true` no painel e decidir o que fazer com as
contas antigas criadas como não-verificadas (backfill ou reenvio de link).

**Aviso ao time**: a reformatação tocou 27 arquivos — trabalho local em
andamento terá conflitos cosméticos ao puxar (resolver com pull +
reaplicar `black .`). Código novo no backend deve passar pelo black antes
do commit, senão o CI volta a ficar vermelho.

### Segunda rodada da revisão (`51a9cb8` … `701df8e`)

Um segundo `/code-review`, agora sobre o diff completo contra o upstream (13
arquivos), confirmou o núcleo dos commits anteriores e trouxe seis achados mais
um fora do diff. Todos resolvidos nesta rodada.

| Commit | O que foi corrigido |
|---|---|
| `51a9cb8` | `feat:` **equipamento órfão** — staff criava equipamento sem `owner_id` e nenhum endpoint atribuía dono depois. Com o escopo por dono, esse equipamento ficava invisível ao cliente real *para sempre*: fora da listagem, barrado no `GET`, recusado no vínculo de chamado, e recadastrar batia no `409` do número de série. `owner_id` opcional entra nos endpoints de **staff**, validando que o dono existe e é cliente |
| `b06228f` | `fix:` **`BCRYPT_ROUNDS` era knob morto** — documentado no `.env.example`, lido pelo `Settings` e nunca passado ao `pwd_context`. Subir para `14` no painel não mudava nada, e a paridade de custo do hash descartável seguia dependendo de coincidência |
| `a06daa4` | `refactor:` **normalização do `APP_ENV` só existia em produção** — `is_development` e o rate limiter comparavam a string crua: `APP_ENV=Testing` num job de CI subia o limiter **ligado** contra o `redis_url`, e `Development` desligava o `/docs` calado. Vira `field_validator` no campo, com três propriedades irmãs lendo o valor já normalizado |
| `4d8fbbf` | `test:` **`_env_file=None` não isola do ambiente** — só do `.env`. Variável exportada vence o default do pydantic-settings, então quem tivesse `CORS_ORIGINS` no shell via os testes de default quebrarem. O helper passa a limpar as quatro sensíveis enquanto constrói |
| `637ad0f` | `fix:` **oráculo 403/404** — equipamento alheio devolvia `403` e inexistente `404`, o que dizia ao cliente quais ids existem. Ver a decisão revista abaixo |
| `701df8e` | `feat:` **`FORWARDED_ALLOW_IPS`** — o achado fora do diff. Ver o aviso de topologia abaixo |
| — | `docs:` este registro e o `Changelog.md`, com a entrada do escopo de equipamento movida de **Desempenho** para **Segurança**: o texto dela descreve vazamento de número de série entre clientes, e quem varresse o changelog atrás de mudanças de segurança antes de um deploy passaria batido |

O `owner_id` ficou em `EquipmentStaffCreate`/`EquipmentStaffUpdate`, herdados
dos schemas compartilhados, e **não** nos corpos aceitos pelos
`/equipment/my*`. Colocá-lo no schema comum daria ao cliente o controle do
dono, porque o `PATCH /equipment/my/{id}` aplica o corpo inteiro com `setattr`
— há dois testes só para acusar isso se alguém unificar os schemas mais tarde.
Falta a tela: o seletor de dono na `ProductsPage` não entrou nesta rodada, a
API veio primeiro.

#### Decisão revista: `404` no lugar do `403` para equipamento alheio

Na rodada anterior o `403` foi mantido por **consistência com o `403` dos
chamados**. A revisão apontou que isso deixa em pé um oráculo de existência
dentro da própria mudança feita para fechar oráculos, e o argumento novo vence:
distinguir "não é seu" de "não existe" não entrega nada ao usuário legítimo e
custa zero para fechar.

Agora, para o perfil **cliente**, a recusa sai como `404` com o mesmo texto de
um id inexistente — constante única, porque mensagens diferentes devolveriam
pelo detalhe o que o status parou de contar. Vale também para os
`/equipment/my*`. Para **staff** continua `403`: quem já enxerga o parque
inteiro pelo `GET /equipments/{id}` não ganha nada com o `404`, que ali seria
só uma resposta enganosa.

Os **chamados seguem como estão**. Aplicar o mesmo critério lá é refactor
maior, com mais call sites e mais perfis envolvidos — fica na fila.

> ⚠️ **TOPOLOGIA RESPONDIDA — a porta 8000 do backend ESTÁ PUBLICADA na
> internet** (confirmado pelo Rickelme em 19/08/2026). **Não definir
> `FORWARDED_ALLOW_IPS` enquanto isso for verdade.**
>
> O contexto: o `start.sh` sobe o uvicorn sem autorizar proxy nenhum, e o
> default do uvicorn (`FORWARDED_ALLOW_IPS=127.0.0.1`) faz o
> `get_remote_address` do rate limiter enxergar o IP do **proxy**, não o de
> quem chamou. Para o tráfego que entra pelo proxy, o
> `RATE_LIMIT_LOGIN=5/15minutes` é hoje **um balde único**: cinco senhas
> erradas de qualquer pessoa travam o login de todos os usuários.
>
> Ligar a variável resolveria isso — e, com a porta publicada, abriria coisa
> pior: quem chamasse a porta direto forjaria o `X-Forwarded-For` e **furaria o
> rate limit por completo**, uma chave por requisição. Trocar um limite fraco
> por nenhum limite não é troca.
>
> **Plano, nesta ordem — a ordem é a correção:**
>
> 1. **Fechar a publicação da porta 8000 no EasyPanel**, deixando só o proxy
>    alcançar o container. Conferir antes que nada legítimo dependa da porta
>    direta — o front chama a API pelo domínio, via proxy.
> 2. **Só então** definir `FORWARDED_ALLOW_IPS=*` no painel. Com a porta
>    fechada, o único que consegue mandar `X-Forwarded-For` é o próprio proxy,
>    e o rate limit passa a valer por IP real.
>
> Inverter os passos é o cenário ruim descrito acima. Enquanto o passo 1 não
> acontecer, o balde global fica — é o estado seguro dos dois.
>
> O passo 1 vale por si, além do rate limit: com a porta aberta, a API é
> alcançável passando por fora do proxy, e com ela tudo o que o proxy faz na
> frente.
>
> O `start.sh` de propósito não ganhou flag: o uvicorn já lê essa variável do
> ambiente, e uma flag criaria duas fontes que podem divergir. O boot em
> produção avisa no log enquanto a variável estiver vazia — o aviso é
> **esperado** até o passo 2, não é regressão.

### Rodada de testes do front (`0cd019a` … `3ae937c`)

Um test review do frontend (skill `help-test-review`) mapeou a suíte Vitest
contra o código e priorizou os gaps por risco. O review corrigiu de passagem
uma informação da própria skill: **Vitest RODA no CI** desde `1583b8b` — teste
de front quebrado bloqueia merge. O que segue fora do CI é só Playwright e k6.

| Commit | O que entrou |
|---|---|
| `0cd019a` | `test:` **interceptor do axios** (`api.ts`, era 0%) — o código que governa toda requisição: Bearer, refresh no 401, fila de chamadas concorrentes durante o refresh. 11 casos cobrindo os três guards anti-loop, os dois desfechos de logout forçado e a concorrência (dois 401 → UM refresh). Dois mutantes nos guards confirmaram que a suíte pega regressão |
| `f51685f` | `test:` **guards de rota** (`AuthGuard`, `RoleGuard`, `OnboardingGuard`, eram 0% e invisíveis) — `src/components/layout/` estava fora do `include` de cobertura do Vitest, então o relatório nem sabia que a camada existia. 10 casos + o include corrigido no `vite.config.ts` |
| `d792686` | `test:` **equipmentService** (era 0%) — superfície de front da mudança de dono de equipamento. Fixa o `product_id` na query do POST, o desempacote de `items`, o `is_active=false` na query e a limpeza de máscara do CNPJ/CEP |
| `2db8dfa` | `fix:` **"Equipment not found" sem tradução** — achado do review cruzando a mudança `637ad0f` do backend com o `TRANSLATIONS` do `apiError.ts`: desde o 403→404, essa é a mensagem que o cliente recebe para equipamento alheio, e o toast mostrava a string crua em inglês. A entrada antiga `Not your equipment` cobria o fluxo que deixou de existir |
| `6049181` | `test:` **toastError** (caminho de erro da aplicação inteira, era 0%) e os ramos de objeto/array do `cn` |
| `3ae937c` | `chore:` `frontend/coverage/` no `.gitignore` — o relatório do `test:coverage` ficava commitável e o eslint tropeçava nos js gerados |

Suíte do front: **192 → 229 testes** (30 arquivos), tudo verde; lint e
typecheck limpos (os 3 warnings restantes do eslint pré-existem em
`ChatPanel`, `ThemeContext` e `GroupsPage`). Cobertura da parte medida:
50,6% → 54,4% — com `api.ts`, os 3 guards, `equipmentService`, `toastError` e
`utils` em 100%.

**Deixado de fora de propósito:** os serviços 0% restantes (`groupService`,
`reportService`, `chatService`, `calendarService`, `auditService`,
`dashboardService`, `slaService`, `tagService`) são wrappers finos de
`api.get/post` — testá-los daria cobertura sem dar confiança; cobrir apenas
quando ganharem transformação (o padrão `withAvatarUrl` do `userService`).
Componentes de apresentação (`Alert`, `Avatar`, `Card`, `Textarea`) idem. Os
que têm lógica real e seguem descobertos: `FilterSelect`, `FormDropdown` e
`ThemeContext` — fila de prioridade baixa.

---

## 18/08/2026 — Auditoria de segurança, correções e CI

Primeira rodada com as skills do projeto: auditoria de segurança completa,
correção dos dois achados graves e primeira fase do reforço de testes no CI.

### Commits

| Commit | Tipo | O que foi feito |
|---|---|---|
| `1d6e766` | docs | 11 skills `help-*` em `.claude/skills/` — revisão de código, segurança, endpoints, migrations, env, testes, deploy, commit, PR, refactor e changelog (adicionadas via `git add -f`, pois `.claude/` é gitignored) |
| `0c7164f` | fix | 🟠 Fecha XSS armazenado na Base de Conhecimento — `frontend/src/lib/markdown.ts` sanitiza o HTML renderizado com DOMPurify; 7 testes provam a neutralização |
| `464d9be` | fix | 🟠 Liga rate limiting (slowapi, 5/15min) nos endpoints de autenticação — login, register, forgot-password e resend-confirmation; teste prova o 429 e que o limiter desligado (padrão em `APP_ENV=testing`) não afeta a suíte |
| `1583b8b` | ci | Vitest no job do frontend, entre o typecheck e o build (Fase 1 do plano de testes no CI) |
| `ec3a86b` | docs | Este registro de mudanças e o [Changelog.md](Changelog.md) do repositório |
| `724322f` | fix | 🟡 Fecha o achado #5 — `GET /products/{id}/equipments` e `GET /equipments/{id}` deixam de vazar equipamento (e número de série) entre clientes: listagem filtrada por dono e 403 no detalhe alheio. Escrito em TDD — os testes falharam antes da correção |
| `f8e6013` | fix | 🟡 Fecha o achado #3.2 — o login pulava o bcrypt para e-mail inexistente e o tempo de resposta (~1 ms contra ~250 ms) denunciava quais contas existem. Passa a verificar contra um hash descartável de 12 rounds |
| `8ab84c8` | fix | 🟡 Fecha o achado #4 — o boot em `APP_ENV=production` passa a exigir `CORS_ORIGINS` com domínio real e a recusar `*`, ao lado da validação que já existia para a `SECRET_KEY` |

### Auditoria (Passo 1)

Varredura estática dos 17 routers do backend:

- **Nenhuma rota desprotegida** — o padrão de alias enganava o grep, mas a
  verificação manual confirmou a cobertura de autenticação.
- **2 achados 🟠** (graves): XSS armazenado na KB e ausência de rate limiting
  na autenticação — ambos confirmados e corrigidos nesta mesma rodada.
- **2 achados 🟡** (médios) e **1 🔵** (informativo) — registrados na fila
  abaixo.
- Controles corretos reconhecidos: `/files/{token}` com JWT assinado e guarda
  de path traversal; escopo do client consistente; resposta neutra no
  login/forgot; anonimização LGPD preservando o AuditLog.

### Verificação

- Backend: **399 testes passando**, cobertura **81,90%** (gate de 80% mantido).
  `pytest` roda verde **sem variável de ambiente no comando** desde o
  `e4ec7f2`.
- Frontend: **192 testes passando**, `tsc` e `ruff` limpos.
- Todo conserto veio acompanhado do teste que o prova.

### Achado #5 — equipamento escopado por dono (`724322f`)

Fechado ainda nesta data, depois da rodada inicial, com o ciclo invertido a
pedido: **os testes vieram antes da correção e falharam** (`200` onde se
esperava `403`), provando que exercitavam a lacuna real.

- **Regra**: cliente vê apenas o próprio equipamento; equipamento **sem dono**
  também é negado (*fail closed*, mesmo critério do `/equipment/my`). Staff
  (admin e técnico) continua com acesso total, porque precisa para suporte.
- **403, não 404** — consistência com o `_check_ticket_access` de tickets e
  anexos. A preocupação de enumeração está registrada no #3 e será tratada lá.
- **Nenhuma tela mudou**: verificado antes de codificar que o cliente só usa
  `/equipment/my*`, que a `ProductsPage` (única consumidora da listagem) está
  sob `RoleGuard` de staff e que o GET singular não é consumido pelo front.
- `test_get_equipment` foi atualizado para ator staff: como cliente, ele
  afirmava justamente o acesso que esta correção fecha.

### Investigado e documentado (sem esconder)

- **`black --check .` reprova no main** — não é culpa do `auth.py`: com o
  `black==25.1.0` pinado, 24 arquivos reprovam. Causa: muitas linhas acima de
  100 caracteres que o black quebraria, e o ruff do projeto ignora `E501`
  (`pyproject.toml`) — então ruff passa e black não. Decisão de time pendente:
  reformatar tudo de uma vez ou alinhar ruff/black. Os arquivos novos desta
  rodada são black-limpos.

  **Resolvido em 19/08/2026 (`57ca9d9`)**: o primeiro push da frente revelou a
  gravidade real — **o CI do main estava vermelho desde 06/08** (seis runs
  seguidos), e como o black roda antes do pytest no job, **a suíte do backend
  nunca rodava no CI**: o gate de testes estava morto sem ninguém perceber.
  Decisão do Rickelme: reformatação mecânica com o black pinado — 27 arquivos,
  zero mudança de lógica, suíte verde (431/82,34%) e ruff limpo depois.

### Achados #3.2 e #4 — enumeração por tempo e CORS (`f8e6013`, `8ab84c8`)

Mesma disciplina do #5: investigação primeiro, aprovação, testes falhando
antes da correção.

**#3.2 — tempo de resposta do login.** A mensagem de erro já era neutra, mas o
relógio não: com e-mail inexistente o `or` curto-circuitava, o bcrypt nunca
rodava e a resposta voltava em ~1 ms contra ~250 ms de um e-mail cadastrado
(`BCRYPT_ROUNDS=12`). Agora a senha é conferida contra um hash descartável
(`DUMMY_PASSWORD_HASH`, 12 rounds, em `app/core/security.py`) e os dois
caminhos custam o mesmo. **O teste não cronometra nada** — medir tempo seria
instável; ele afirma que a verificação de senha roda também no caminho do
usuário inexistente, e falha se alguém reintroduzir o curto-circuito.

**#4 — CORS.** O boot em `app_env=production` passa a recusar `CORS_ORIGINS`
apontando para localhost/127.0.0.1 ou contendo `*`, ao lado da validação da
`SECRET_KEY`. O que motivou o rigor: o `frontend/nginx.conf` **não faz proxy**
para a API, então o navegador fala com outro domínio e o CORS é obrigatório —
com o default, o front ficaria bloqueado sem nenhum erro no backend.

> ⚠️ **Dependência de ambiente no deploy:** o boot de produção agora depende de
> **`CORS_ORIGINS`** (com o domínio real do front), de **`FRONTEND_URL`** e de
> **`APP_ENV`**. Hoje as duas primeiras existem no EasyPanel — confirmado antes
> da mudança —, mas **recriar o serviço sem elas derruba a API na subida**, com
> o container reiniciando em loop. Se algum dia o serviço for recriado do zero,
> configure-as antes do primeiro boot.
>
> Vale também para **migração avulsa**: `alembic/env.py` instancia `Settings`,
> então rodar `alembic upgrade` num shell de produção sem essas variáveis falha
> do mesmo jeito — não é só o boot da API.

Registrado como possibilidade futura, sem ação nesta rodada: o
`CORSMiddleware` usa `allow_credentials=True`, dispensável porque a
autenticação é por Bearer token no header, não por cookie. Remover reduziria
superfície, mas mexe em comportamento de rede.

### Correções da revisão de código (`e4ec7f2` … `53312aa`)

Um `/code-review` profundo sobre os commits locais confirmou que os fixes
funcionam como testados, mas achou bordas que valia fechar antes do push,
enquanto o histórico ainda era local.

| Commit | O que foi corrigido |
|---|---|
| `e4ec7f2` | `test:` **suíte dependia do `.env` local** — `pytest` na máquina de quem desenvolve pegava `APP_ENV=development` e subia o rate limiter **ligado**, fazendo os testes de login competirem com o limite de 5/15min. Verde no CI, intermitente local. Agora um `conftest.py` fixa o ambiente antes dos imports, e `pytest` sem env explícito roda verde |
| `72f31bc` | `fix:` **bcrypt no event loop** — o mais sério: `verify_password` é síncrono (~250 ms) e travava o loop, com todas as requisições em voo; o hash de custo igualado tinha estendido o bloqueio ao caminho do e-mail inexistente. Vai para `run_in_threadpool`, e os dois pontos de verificação viraram um |
| `ef636fe` | `fix:` **cinco bordas do guard de produção** — lista vazia passava (`any()` sobre lista vazia é falso); `APP_ENV=Production`/`prod` pulava **todas** as validações, inclusive a da `SECRET_KEY`; o formato JSON não fazia strip e estourava `JSONDecodeError` cru; `localhost` como substring barrava domínio legítimo e deixava passar `[::1]`/`0.0.0.0` (agora compara o host via `urlparse`); e `FRONTEND_URL` ganhou o mesmo guard |
| `9634d7e` | `test:` **paridade de custo do hash descartável** — os 12 rounds batiam por coincidência (`settings.bcrypt_rounds` nunca foi aplicado ao `pwd_context`). Se o dummy ficar mais barato, a enumeração por tempo reabre sem nenhum teste perceber; agora é contrato |
| `2ad773c` | `refactor:` **recusa de equipamento alheio unificada** — o check de dono estava inline em três endpoints, e o 403 mais novo divergia no texto. Vira `_check_equipment_owner`, no espírito do `_check_ticket_access`, sem ampliar permissão: `/equipment/my` segue estrito até para admin |
| `53312aa` | `test:` limpeza — harness duplicado que pagava dois bcrypts reais, e mock que decidia o retorno pela ordem das chamadas |
| `751bfeb` | `fix:` **bcrypt no event loop nos endpoints restantes** — o mesmo defeito do `72f31bc` nos pontos que sobraram: `register`, `reset-password`, `POST /users` e `change-password`. Cinco chamadas, quatro endpoints, todas para `run_in_threadpool` |

O `reset-password` não estava na lista da revisão: apareceu ao varrer todos os
call sites de bcrypt antes de corrigir, e entrou porque é o mesmo defeito. O
espião de thread virou utilitário no `conftest.py`, agora que três arquivos de
teste precisam dele.

### Fila para a próxima rodada

Decisões de produto levantadas pela revisão, registradas sem correção:

- **Unicidade global de número de série** — o `409` do `POST`/`PATCH
  /equipment/my` responde por seriais de qualquer dono, então serve de oráculo:
  dá para descobrir se um serial existe no sistema. Decidir primeiro a regra de
  negócio: serial é único global, ou a unicidade deve ser por dono?
- ~~**Equipamento sem dono fica órfão**~~ — **API resolvida em `51a9cb8`**
  (`owner_id` opcional nos endpoints de staff). Falta a **tela**: seletor de
  dono na `ProductsPage`, para o staff atribuir sem chamar a API na mão.
- **Oráculo de timing em `forgot-password`/`resend-verification`** — o envio de
  e-mail é síncrono e só acontece no ramo da conta existente, então o tempo de
  resposta vai denunciar quais e-mails têm conta **quando o SMTP entrar**.
  Correção natural: `BackgroundTasks`. Agrupar com a rodada do SMTP/#3.1.
- ~~`hash_password` e `verify_password` fora do login~~ — **resolvido em
  `751bfeb`** (aprovado depois de registrado aqui).

- 🟢 **#3.1 Register neutro — aprovado em desenho, aguardando SMTP em
  produção.** O SMTP ainda não está configurado, e sem ele a resposta neutra
  criaria um beco sem saída: o usuário legítimo que digitasse um e-mail já
  cadastrado ficaria sem conta e sem aviso, porque o e-mail de "você já tem
  conta" não sairia. O `409` do register fica como está por enquanto. Quando o
  SMTP entrar, a implementação **já está pré-autorizada** neste formato, sem
  rediscutir UX: resposta `201` neutra + tela "Falta um passo" (que já existe
  em `RegisterPage.tsx`) + e-mail "você já tem conta"; sai o bloco
  `if (status === 409)` do front.
- **Recusa por dono nos chamados** — o `403` de `_check_ticket_access` tem o
  mesmo formato de oráculo que o de equipamentos acabou de perder. Aplicar o
  mesmo critério lá é refactor maior, com mais call sites e mais perfis
  envolvidos; fica para uma rodada própria.
- **CI Fase 2/3** — Playwright em `e2e.yml` separado (workflow_dispatch +
  noturno) e k6 contra staging; proposta escrita, aguardando decisão de
  investir no ambiente.
