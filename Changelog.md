# Changelog — HelpHS (repositório)

Changelog técnico, para desenvolvedores. O changelog do **produto** — o que o
cliente final vê dentro do sistema — vive em
`frontend/src/data/changelog.ts` e é mantido pela skill
`help-changelog-update`; este arquivo não o substitui.

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/).
Datas em DD/MM/AAAA.

## [Não publicado]

### Segurança
- **O SMTP passa a verificar o certificado do servidor** (`36bfc85`).
  `VALIDATE_CERTS` estava fixo em `False`: qualquer um que conseguisse
  responder no endereço configurado recebia **usuário e senha do SMTP** — a
  credencial de envio da empresa inteira. Sem chave de configuração para
  desligar: uma opção "não verifique o certificado" é o tipo de coisa que
  alguém liga para destravar um relay interno e nunca mais desliga.
- **`LLM_ENABLED` permite desligar a IA sem esvaziar as chaves** (`79ef715`).
  A única forma de parar de mandar conteúdo de chamado para OpenAI e Anthropic
  era **apagar** as chaves do painel — manobra que destrói a configuração e não
  tem volta. Padrão `true`, de propósito: desligar por padrão apagaria a
  classificação automática em produção no deploy seguinte sem ninguém pedir, e
  mudança silenciosa é o oposto do que uma flag de emergência deve fazer. ⚠️ A
  guarda ficou nas **quatro** entradas públicas, não só nos dois helpers de
  chamada: `suggest_reply`, `summarize_conversation` e `improve_message` montam
  as suas próprias requisições — são oito construções de `httpx.AsyncClient` no
  arquivo. Por isso o teste conta **construções de cliente HTTP**, não o
  retorno: é o que separa "não mandou" de "mandou e deu errado".
- **O upload deixa de materializar o arquivo antes de medir** (`ab791c3`). Os
  dois endpoints que recebem arquivo faziam `await file.read()` e só então
  mediam `len(data)`: mandar 2 GB fazia o processo alocar 2 GB **antes** de
  recusar, e não há middleware de tamanho de corpo na aplicação — o único
  middleware montado é o CORS. A leitura passa a ser por blocos de 64 KB,
  abortando no primeiro que cruza o limite, e a extensão é conferida antes de
  ler qualquer byte. ⚠️ O status muda de 422 para **413** — conferido antes: o
  `apiError.ts` já tem 413 no mapa de fallback e prefere o `detail`, então a
  mensagem do anexo passou de inglês (que dependia do mapa de tradução) para
  português direto.
- **Rascunho da base de conhecimento deixa de existir para quem não é da
  equipe** (`bdd1418`). O `GET` do artigo fazia a checagem certa — não-staff
  mais não-publicado vira 404 — e os três vizinhos não repetiam. Com o UUID de
  um rascunho na mão, o cliente confirmava que ele existe (feedback devolvia
  **204**), lia a discussão interna da equipe (comentários, **200**) e ainda
  comentava nele (**201**) — os três números são dos testes antes da correção.
  Em vez de um segundo helper de checagem, o próprio fetch passou a **exigir o
  ator**: não sobra caminho para carregar artigo sem passar pela guarda, e quem
  escrever o próximo endpoint não tem como esquecer a linha. Diferença
  proposital em relação ao `ensure_ticket_visible`: lá a regra é "é seu?" e a
  exceção de staff fica no call site; aqui o papel **é** a regra inteira. As
  duas recusas saem com a mesma frase, com teste de paridade nas três rotas.
- **Anonimizar conta de admin passa a ser privilégio de admin** (`45a1601`).
  Anonimizar é o único dos quatro endpoints de gestão de usuário que **não tem
  volta**: reescreve nome e e-mail, e não existe caminho de desfazer. Qualquer
  técnico podia fazer isso com a conta de um administrador. Guarda de **papel**,
  não de identidade — outro admin continua podendo. Mexi só neste: editar e
  desativar são reversíveis e fazem parte do dia a dia de uma equipe de dois
  técnicos, e excluir já é barrado pelas chaves estrangeiras. Sem técnico
  externo na empresa, o que resta é o clique errado e a conta comprometida — a
  segunda pesa mais aqui porque **não há MFA** no sistema.
- **O spec da API deixa de ser público fora de desenvolvimento** (`6e8f409`).
  `docs_url` e `redoc_url` já eram desligados, mas o `openapi_url` ficou no
  default: o `/openapi.json` seguia público em produção — e o spec é o mapa
  completo (toda rota, todo parâmetro, todo formato), que é o que alguém
  precisa para escolher o que atacar. Desligar o `/docs` e deixar o spec de pé
  fecha a porta e deixa a planta na calçada. **Não** criei flag própria, embora
  fosse uma opção: o spec *é* a documentação em outro formato, e duas chaves
  para "expor a API por escrito" seria mais uma configuração para alguém deixar
  ligada sem querer. ⚠️ O `zap-scan.yml` se alimenta desse endpoint — o
  cabeçalho e a descrição do input passam a dizer que o alvo precisa ser um
  ambiente com o spec exposto; apontar para produção agora dá 404 no passo do
  ZAP.
- **Ambiente que não é local para de escapar das validações de boot**
  (`e3cea9a`). O guard começava com `if not self.is_production: return`, e
  `is_production` só reconhece "production"/"prod" — então um `APP_ENV=staging`
  aceitava `SECRET_KEY` curta, `CORS_ORIGINS=*` e `FRONTEND_URL` de localhost.
  Staging exposto na internet com essas três é produção com outro nome, e é
  onde se testa com dado copiado do real. A lista de quem escapa passa a ser
  **fechada** — development e testing: um `APP_ENV` desconhecido, ou digitado
  errado, cai no lado severo. Antes um typo em "production" desligava todas as
  validações; agora um typo as liga. Apertar não promove: `is_production`
  continua False para staging, senão ele herdaria o `/docs` desligado e o seed
  de admin que não roda.
- **O link de confirmação de e-mail passa a ser de uso único** (`e8c642e`). O
  token de senha já era: carrega a impressão da senha vigente e morre quando
  ela muda. O de confirmação não carregava estado nenhum, então valia pelas
  24 h inteiras — um link vazado (e-mail encaminhado, histórico do navegador,
  log de proxy) seguia servindo depois de a conta já estar confirmada. Agora
  carrega o estado de verificação de quando foi emitido. Cuidei de não trocar
  segurança por atrito: clicar de novo num link já usado continua respondendo
  a frase amigável "já estava confirmado", e não um erro — a conta já está
  ativa, não há nada a conceder. Não embuti também a impressão do e-mail
  (a simetria mais completa) porque **não existe fluxo de troca de e-mail** no
  sistema: seria amarra que não guarda nada hoje.
- **O admin de seed deixa de nascer com senha do repositório** (`3478bae`,
  `b736114`). `start.sh` roda `python -m app.seeds` **a cada boot do
  container**, entre a migration e o uvicorn, **inclusive em produção**. Com a
  senha `Admin@123456` escrita em `seeds.py` e nenhuma guarda de ambiente, todo
  deploy criava — ou recriava, se alguém apagasse a linha — um administrador
  ativo com credencial publicada neste repositório. O `app.seeds_e2e` já tinha
  essa proteção e a docstring dele já explicava o porquê: o raciocínio tinha
  sido aplicado à conta de teste e não à de admin, que é a mais poderosa das
  duas. Passa a haver **duas defesas independentes** — `APP_ENV` de produção
  não cria a conta, e sem `SEED_ADMIN_PASSWORD` não cria a conta. A segunda não
  é redundância: `app_env` tem default `development`, então a primeira falha
  **aberta** se a variável faltar ou vier digitada errada; senha ausente é a
  correção, guarda de ambiente é só a defesa. **Nenhuma das duas levanta**, e é
  aí que esta regra difere da do módulo de e2e (que *deve* falhar ruidosamente,
  porque nada o chama em produção): `seed_admin` está no caminho do boot sob
  `set -e`, e levantar trocaria um vazamento de credencial por uma
  indisponibilidade. Produto e configuração de SLA continuam sendo semeados
  normalmente — são catálogo, não credencial. A idempotência permanece e
  protege quem já trocou a senha em produção; em contrapartida, **apagar o
  usuário deixa de ser forma de reiniciá-lo**. ⚠️ O workflow de e2e passa a
  definir `SEED_ADMIN_PASSWORD` (banco efêmero do job), e **quem sobe o
  ambiente local precisa exportá-la** — sem ela o seed avisa no log e pula a
  criação. ⚠️ **Isto não fecha o incidente:** falta verificar se a conta existe
  hoje no banco de produção e com que senha. Nada foi executado contra
  produção nesta rodada.

- **Número de série passa a ser único por dono, não no sistema inteiro**
  (`d5fa7a6`). A unicidade global recusava cadastro legítimo — empresas
  diferentes têm aparelhos de mesmo número — e era um oráculo: o `409` contava
  ao cliente que outra empresa tinha aquele serial. ⚠️ **Migration**
  (`u1p2q3r4s5t6`), roda no boot: troca o índice único global por um composto
  `(owner_id, serial_number)` mais um parcial `WHERE owner_id IS NULL` — em SQL,
  `NULL` não conflita com `NULL`, e sem o parcial dois órfãos iguais passariam.
  Upgrade seguro por construção (regra nova é mais fraca que a antiga), sem
  backfill; o **downgrade pode falhar** se houver o mesmo serial em donos
  distintos depois do upgrade. Testada em Postgres efêmero: upgrade, os quatro
  casos de conflito, downgrade e upgrade de novo. **Furo aceito, por decisão:**
  dois usuários da mesma empresa podem cadastrar o mesmo aparelho, cada um no
  próprio escopo; a evolução para CNPJ depende de normalizar o campo. O `PATCH`
  de staff valida o par final (dono, serial) — mover para um dono que já tem o
  serial dá `409`.
- **O envio de e-mail sai da frente da resposta em `forgot-password` e
  `resend-verification`** (`902d331`). O SMTP só é chamado no ramo da conta
  existente; enquanto o envio fosse aguardado dentro do handler, os dois ramos
  respondiam em tempos diferentes e o relógio dizia o que a mensagem cala — o
  oráculo de enumeração que o `f8e6013` fechou no login, renascendo ao lado.
  ⚠️ **Hoje isso não é mensurável em produção só porque não há SMTP
  configurado**: o oráculo nasceria pronto no dia em que ligassem. Com
  `BackgroundTasks` a resposta sai antes de o envio começar. O teste mede
  **ordem**, não relógio (mock de rede não tem latência e teste de tempo em CI
  compartilhado mediria o runner): pelo ASGI cru, o corpo da resposta precisa
  sair antes do envio. O `register` fica de fora de propósito — lá a resposta
  já difere por ramo (`409`), mas quando o **#3.1** o tornar neutro este
  tratamento precisa ir junto.
- **Chamado alheio deixa de denunciar que existe** (`7371bc7`). Para o cliente,
  o chamado de outra pessoa passa a responder `404`, com o mesmo texto de um id
  inexistente, em vez do `403` que confirmava a existência — com uma lista de
  UUIDs dava para enumerar o sistema sem ler um chamado sequer. Mesmo formato
  que os equipamentos ganharam no `637ad0f`. A regra estava copiada em **quatro
  arquivos sob três nomes** (`_check_ticket_access` nos anexos,
  `_get_ticket_or_403` no chat, mais quatro inlines em tickets e avaliações),
  doze pontos ao todo; passa a existir `ensure_ticket_visible` em `app/utils/`.
  O helper **não abre exceção para staff** — quem decide isso é o call site,
  pela mesma razão do `2ad773c`: um helper que "sabe" que admin passa vira
  passe-livre invisível no dia em que for chamado de um endpoint novo. Vale só
  para cliente: técnico e admin já listam tudo sem escopo, então `404` entre
  eles não fecharia nada e quebraria assumir/atender. Onde a recusa é de
  **papel** o `403` fica — técnico na observação do cliente, staff que não
  abriu o chamado na avaliação. Três achados que varredura de status HTTP não
  mostra: `GET /attachments/{id}` vazava **duas vezes** (id do anexo e id do
  chamado pai, três respostas distinguíveis) e agora responde sempre pelo
  **anexo**; o **WebSocket** tinha o mesmo oráculo em código de fechamento
  (`4003` contra `4004`) e passa a fechar `4004` nos dois casos com o mesmo
  motivo; e `"Attachment not found"` não tinha tradução em `apiError.ts`, o que
  entregaria ao cliente o toast cru em inglês — o bug que o `2db8dfa` consertou
  para equipamento. Sem migration, sem backfill. 471 → 490 testes no backend.
- O hash descartável do login passa a acompanhar `BCRYPT_ROUNDS` sozinho
  (`a1bbd94`). Ligar a variável ao `pwd_context` na v1.7.0 deixou o knob vivo e
  criou uma armadilha: o dummy seguia fixado em 12 por literal, então
  `BCRYPT_ROUNDS=14` no painel fazia o e-mail desconhecido custar 486 ms e o
  cadastrado 1777 ms — o oráculo de tempo reabria **maior** do que era antes de
  ser fechado. O teste de paridade não pegava porque comparava contra o
  contexto do processo de teste, que nunca tem a variável no ambiente. Agora o
  import compara o custo embutido no literal com o do contexto e só regera
  quando divergem: o caminho normal não paga bcrypt nenhum.
- `POST`, `PATCH` e `DELETE /equipment/my*` passam a exigir perfil `client`
  (`b1ab978`). Com qualquer autenticado, staff criava equipamento pertencente a
  staff — o mesmo estado que os endpoints de staff recusam com `400`, invisível
  a todo cliente e impossível de vincular a chamado. A **leitura** fica aberta
  de propósito, para não esconder equipamento legado de quem virou staff depois
  de ter sido cliente.

### Corrigido
- **O protocolo deixa de travar no 10.000º chamado do ano** (`32f07de`). A
  consulta do máximo ordenava `Ticket.protocol` como **texto**, e a sequência
  tem 4 dígitos: `'HS-2026-9999' > 'HS-2026-10000'` é verdade em ordenação de
  texto. O efeito não é um número fora de ordem — é **parada total**: o máximo
  volta a ser 9999 para sempre, o gerador propõe 10000 de novo, as cinco
  tentativas colidem no índice único e nenhum chamado novo pode ser aberto.
  Conserto mínimo: comprimento primeiro, texto depois — vale nos dois bancos e
  não levanta em nenhum (um CAST para inteiro seria mais direto de ler, mas
  estouraria no Postgres se uma linha com sufixo não-numérico entrasse por fora
  do gerador). A `SEQUENCE`, que resolveria também a corrida, fica registrada
  no docstring **com gatilho**: se colisão de protocolo aparecer no log, é hora.
- **O cadastro deixa de ficar pendurado no SMTP** (`36bfc85`). O `/register`
  era o único dos três fluxos de e-mail que **aguardava** o envio dentro do
  handler, sem timeout — servidor lento atrasava o cadastro, servidor que não
  responde o segurava até o timeout do proxy. Passa a `BackgroundTasks`, como
  os outros dois já faziam. O teste mede **ordem**, não relógio.
- **`PATCH /sla-configs/{id}` deixa de devolver 500 em toda chamada**
  (`43c3238`). A linha de auditoria construía o `AuditLog` com três kwargs que
  o modelo não tem: `resource_type`, `resource_id` e `new_values`, quando os
  campos são `entity_type`, `entity_id` (UUID, não string) e `new_data`.
  Confirmado executando — o construtor levanta `TypeError`. Como isso acontece
  **depois** de aplicar as mudanças e antes do commit, o PATCH falhava em 100%
  das chamadas: **configurar prazo de SLA pela interface nunca funcionou**. ⚠️
  Sobreviveu porque o `test_sla.py` tinha 30 testes do motor de SLA e nenhum
  que batesse no endpoint — e porque o **mypy não pega**: modelo declarativo do
  SQLAlchemy não tem `__init__` conferido. A rede que faltava era teste de
  endpoint, e é o que entra: um afirma 200 e persistência, outro que a linha de
  auditoria nasce com `entity_type="sla_config"` e `entity_id` UUID, porque só
  afirmar o 200 deixaria passar um `AuditLog` com qualquer nome.
- **`DELETE /users/{id}` confere o que o banco recusa e explica o 409**
  (`52a3b7f`). A guarda contava só `Ticket.creator_id`: um técnico que nunca
  abriu chamado mas tem chamados **atribuídos** passava por ela e ia bater na
  chave estrangeira — e `assignee_id` não tem `ondelete`. Sem `except`, isso
  vira **500**, e um 500 num DELETE não diz ao admin o que fazer. Duas camadas:
  a contagem passa a cobrir as **onze** referências a `users.id` sem `ondelete`
  (levantadas uma a uma), e o `except IntegrityError` é rede para a tabela nova
  que nascer fora da lista. A mensagem diz o que fazer (anonimizar, com a rota)
  e o que segurou, com número e tipo. ⚠️ Como auditoria entra na lista, usuário
  que já agiu no sistema deixa de ser excluível e passa a ser caso de
  anonimização — que é o comportamento correto para a LGPD e já era a intenção
  do código; a diferença é que antes isso falhava com 500. Quem nunca agiu
  continua excluível.
- **As duas listagens sem paginação param de mentir o `limit`** (`8e03e05`).
  `GET /users/technicians` e `GET /products/my-equipment` respondiam
  `limit=100, offset=0` fixos sobre queries **sem** limit: com mais de 100
  registros o cliente leria "100 de N" e concluiria que há outra página, que
  não existe. Escolhi devolver os números reais em vez de paginar, pelo que as
  rotas **são**: uma alimenta o dropdown de responsável, a outra mostra os
  aparelhos do próprio usuário — as duas telas precisam do conjunto inteiro, e
  paginar esconderia opções atrás de uma página que a tela não sabe pedir.
  Conferido que o front lê só `items`.
- **O laço do fechamento automático sobrevive ao erro e diz que está vivo**
  (`9146dc2`). O `while True: await _run_once()` não tinha `try/except`: uma
  exceção encerrava a task e o RN-005 parava até o próximo restart, **calado**
  — a exceção só reapareceria no shutdown, onde o `suppress` cobre apenas
  `CancelledError`. E nem todo caminho de `_run_once` estava protegido por
  dentro: os imports tardios e o `get_settings()` ficam fora dos dois `try` de
  lá, justamente as linhas que ninguém imagina que levantam. Junto vem o
  carimbo que o readiness usa: o instante da última rodada sem erro, na memória
  de cada worker. Ceder a vez para outro worker **conta** (a rotina aconteceu;
  se não contasse, o worker que quase nunca pega o lock reportaria rotina
  parada para sempre); rodada pulada por Redis fora ou que levantou **não**
  conta. ⚠️ O teste de cancelamento prova que o laço termina no `cancel`, e só
  isso — verifiquei por mutação que trocar o tratamento por `except
  BaseException` o mantém verde, porque desde o 3.11 o asyncio re-entrega o
  cancelamento pendente no `await` seguinte.
- **O e-mail de notificação só sai depois do commit que o torna verdade**
  (`66f2569`). O `notify()` criava a task de envio na hora, e o docstring
  mandava chamá-lo **antes** do commit — então qualquer commit que falhasse
  depois mandava e-mail sobre algo que não aconteceu. O laço de protocolo do
  `create_ticket` era o caso visível (um e-mail por tentativa descartada, cada
  um anunciando um protocolo que não passou a existir), mas o furo valia para
  todo chamador. O `db.add(notif)` continua antes do commit — a notificação faz
  parte da transação; o que mudou foi o **disparo**. `notify()` registra o
  e-mail como pendência da sessão e `commit_e_notificar()` dispara depois do
  commit. ⚠️ Se alguém chamar `db.commit()` direto depois de um `notify()`, o
  e-mail não sai — é o lado seguro do erro: deixar de mandar um aviso é
  recuperável, mandar aviso de algo que não aconteceu não é.
- **O log de e-mail deixa de descartar o destinatário e o motivo** (`c615ad7`).
  Cinco chamadas usavam placeholder de `%`-formatting (`"%s"`), mas o loguru
  formata com `str.format()`: a linha saía com o literal `%s` e os argumentos
  eram jogados fora. O caso grave era o log de **falha de entrega**, que não
  dizia para quem nem por quê — exatamente o dado necessário quando alguém
  reclama que não recebeu. Passa a usar f-string, o estilo do resto do projeto
  (49 chamadas contra 1). Os testes capturam a linha já formatada e afirmam que
  destinatário e motivo aparecem nela.
- **Nenhum e-mail sairia com `SMTP_REPLY_TO` vazio** (`c53bb80`). Achado pelo
  teste do commit acima, não pela auditoria. O campo é opcional e nasce vazio;
  com ele vazio o `send_email` montava a mensagem com `reply_to=None`, e o
  `MessageSchema` do fastapi-mail recusa `None` ali — exige lista. A exceção
  estourava na **montagem**, antes de qualquer tentativa de entrega, e o
  `except` a engolia como se fosse falha de SMTP. ⚠️ Hoje está mascarado porque
  **não há SMTP em produção** e o `send_email` retorna antes, na guarda de "SMTP
  não configurado" — a falha apareceria inteira no dia em que o SMTP fosse
  ligado. O campo passa a receber lista vazia, que é o próprio default do
  fastapi-mail. O teste que já existia passava por coincidência: afirmava só
  `result is False`, verdade tanto pela falha simulada quanto por este erro.
- **As tags do artigo da KB deixam de ser uma lista compartilhada** (`e1985a4`).
  `default=[]` guarda **uma** lista, criada quando o módulo é importado, e o
  SQLAlchemy a reusa em toda inserção que não informe tags — quem mutasse o
  valor vindo dali contaminaria todos os artigos inseridos depois no mesmo
  processo. Com `default=list` cada linha nasce com a sua. Vale registrar o que
  o achado **não** era: default de coluna vale na inserção, não na construção
  (`KBArticle().tags` é `None`, não `[]`) — o risco é o compartilhamento entre
  inserções, não o clássico default mutável de argumento de função. Sem
  migration: default de Python não aparece no DDL.
- **A pesquisa de satisfação passa a cair junto com o ticket no ORM**
  (`a8de8c6`). Era o único filho de `Ticket` sem cascade no relationship. O
  banco já cobre pelo `ON DELETE CASCADE` da chave estrangeira, mas o ORM não
  sabe disso: um `db.delete(ticket)` faria o SQLAlchemy tentar orfanar a
  pesquisa, escrevendo `NULL` numa coluna `NOT NULL`. Latente — nenhuma rota
  apaga ticket pelo ORM hoje. O teste afirma a **regra inteira**, não a linha:
  todo filho `ONETOMANY` de `Ticket` precisa cascatear, então o próximo que
  alguém adicionar sem cascade também cai ali. Sem migration.
- **Limpar um campo da empresa passa a funcionar.** O `PUT` de empresa pulava
  todo valor `None`, então "enviado vazio" e "não enviado" eram
  indistinguíveis: o admin apagava o CNPJ na tela, salvava, e o valor velho
  voltava sem aviso nenhum — e valia para os sete campos, não só o CNPJ. A
  distinção agora vem do `model_fields_set` do pydantic, que diz o que o
  cliente **mandou**: ausente não mexe, enviado vazio limpa. `name` é a
  exceção, por causa do banco — a coluna é `NOT NULL`, então enviá-lo vazio
  devolve `422` com motivo, em vez do erro de servidor que "enviou, grava"
  produziria. O comportamento antigo estava preso por teste de caracterização
  desde o `470d56c`, escrito para que mudá-lo fosse decisão e não efeito
  colateral; as duas mutações (voltar a guarda antiga, tirar a guarda do nome)
  derrubam a suíte.
- **Criar empresa pela sugestão passa a vincular os clientes** (`abdee48`).
  `handleAddFromSuggestion` chamava só `createCompany`, e `create_company`
  nunca tocou em `User`: os clientes que geraram o card seguiam com
  `company_id` nulo, a sugestão reaparecia na abertura seguinte e clicar de
  novo criava **empresa duplicada**. O contador "3 clientes" era promessa que
  a ação não cumpria. Endpoint próprio
  (`POST /groups/{id}/companies/from-suggestion`) e não parâmetro no
  `create_company` — cadastro manual não pode ganhar efeito colateral de
  vínculo em massa; uma empresa criada à mão que, por coincidência de CNPJ,
  arrastasse clientes junto seria o **inverso** do defeito consertado aqui.
  Empresa com o mesmo CNPJ **no mesmo grupo** é reaproveitada em vez de
  duplicada; fora do grupo, cria — não é preferência, é que `Company.group_id`
  é `NOT NULL` e único, então "reusar" empresa de outro grupo seria mudá-la de
  grupo. O vínculo vai pela lista **explícita** de `client_ids` que a tela
  mostrou, com passo de confirmação exibindo nome e e-mail de cada um: vincular
  em massa sem ver quem é ação que ninguém desfaz. Cliente que mudou de estado
  entre a tela e o clique derruba tudo com `409` e **nada** é gravado, nem a
  empresa. O `key={s.company_name}` do React, que colidia quando duas sugestões
  compartilhavam o nome, passa a ser a tupla inteira. ⚠️ O agrupamento das
  sugestões **continua** pela tupla (endereço diferente ainda racha em duas):
  rechavear no CNPJ exige decidir qual nome vence quando os clientes discordam
  e o que fazer com quem tem `company_name` sem CNPJ — decisões de produto. O
  estrago acabou mesmo assim: com o reaproveitamento por CNPJ os dois cards
  caem na mesma empresa, e o defeito virou cosmético em vez de gerar duplicata.
- **A cobertura parava de contar depois do primeiro `await` no banco**
  (`e30968e`). O relatório subnotificava **todo** endpoint async que consulta o
  banco: contava a primeira linha do corpo e perdia o resto — em `groups.py`,
  `update_company` aparecia com a linha 280 coberta e 281-287 descobertas, o
  laço inteiro dado como não executado com teste passando por ele. A causa é o
  greenlet: o SQLAlchemy async atravessa `greenlet_spawn` a cada `await` de
  banco e o coverage perde o rastro na volta. `concurrency = ["thread",
  "greenlet"]` resolve. Não é cobertura nova, é a mesma medida direito —
  `groups.py` sai de 43% para 62% com exatamente os mesmos testes, e a suíte de
  84,48% para 85,20%. ⚠️ **Números anteriores a este commit estavam abaixo do
  real.** Descoberto por mutação: as linhas ditas descobertas derrubavam o
  teste quando mutadas, o que só podia significar que executavam.

- **CNPJ com pontuação deixa de chegar ao banco** (`62f022e`). O validador
  existia só no `OnboardingUpdate`; `UserUpdate`, `CompanyCreate` e
  `CompanyUpdate` aceitavam qualquer string até 18 caracteres, e o
  `placeholder` do front ensinava o admin a digitar com máscara. O resultado
  não era "nenhum lado normaliza", era **pior**: `users.cnpj` guardava 14
  dígitos crus e `companies.cnpj` guardava `11.222.333/0001-81` — normalizados
  em direções opostas, então comparar as duas colunas por string nunca dava
  igual, por construção. Foi esse o motivo real de a unicidade de série ter
  virado "por dono" em vez de "por empresa" (`d5fa7a6`), e está mapeado em
  `docs/superpowers/specs/2026-08-24-duas-fontes-de-verdade-empresa.md`.
  A regra passa a viajar no **tipo** (`CnpjOpcional` / `CnpjObrigatorio`, em
  `app/utils/documents.py`) e não num validador copiado por modelo: campo de
  CNPJ novo declarado com o tipo já nasce validado, que é exatamente o defeito
  que o `CompanyCreate` tinha. É `AfterValidator` e não `Before` para o valor
  chegar já coagido a `str` — com `Before`, um número viraria `AttributeError`
  em vez de `422`. **Opcional continua opcional:** `None` e string vazia viram
  `None`, porque limpar o campo no front manda `""` e não `null`, e recusar
  isso quebraria criar empresa sem CNPJ; já lixo com conteúdo (`"abc"`) vira
  erro e não `None` silencioso. No front o `placeholder` de empresa passa a
  pedir dígitos, a máscara volta só na **exibição** (`formatCnpj`) e a de
  digitação (`maskCnpjInput`) sai das duas cópias locais de `OnboardingPage` e
  `ProfilePage` para `lib/documents.ts`. A busca por CNPJ na tela de Grupos
  passa a comparar só dígitos — com a coluna normalizada, procurar com máscara
  pararia de achar. **Sem migration:** `String(18)` já comporta 14 dígitos.
  ⚠️ Um efeito colateral pequeno e assimétrico: campo enviado vazio agora vira
  `NULL` em vez da string `""`. Em `PATCH /users/*` isso limpa o CNPJ de
  verdade; no `PUT` de empresa o laço pula valor `None` (`groups.py:282`),
  então lá "vazio" passa a significar "não mexe" — o mesmo que `name`, `phone`
  e os outros cinco campos já faziam. Ou seja, limpar o CNPJ de uma empresa
  pela tela deixa de funcionar; era um caminho que gravava `""`, não `NULL`,
  e endireitá-lo é do Passo 3, junto com os testes de `groups.py`.

- **Chip de SLA deixa de dizer "Vencido" para resposta já dada** (`32fc736`).
  Chamado respondido no prazo e reaberto dias depois aparecia "Resposta:
  Vencido" em âmbar — cor certa, letra errada: o chip comparava o prazo do
  primeiro ciclo com o relógio sem saber que a resposta tinha sido dada, porque
  `sla_first_response` não era enviado ao front. Passa a ser exposto no
  `TicketResponse` (leitura, sem migration) e o `SlaChip` ganha `respondedAt`:
  preenchido, diz "Respondido" e para o relógio. **Não** silencia pelo
  `breached`: a flag só é recalculada em escrita, e um chamado vencido e
  intocado chega com ela falsa — a contagem ao vivo é o único lugar que conta a
  verdade sobre ele. O chip saiu da `TicketDetailPage` para `components/ui`,
  com testes verificados por mutação. A lista de chamados tinha o mesmo bug na
  barra de "1ª Resposta" (o chamado respondido pelo chat não sai de `open`) e
  recebeu o mesmo tratamento. Prazo próprio para o ciclo reaberto fica como
  melhoria futura.
- `/onboarding` deixa de abrir para quem não tem onboarding (`77a8e9c`). A rota
  estava sob o `AuthGuard` e fora do `OnboardingGuard`, então qualquer
  autenticado abria a tela digitando a URL: o staff, que não tem onboarding
  nenhum, e o cliente que já completou — para quem refazer significaria
  sobrescrever dados de cadastro já revisados. Ficar fora do `OnboardingGuard`
  era proposital (senão o redirecionamento apontaria para si mesmo); o que
  faltava era o par, `OnboardingOnlyRoute`. Higiene de rota, só no front — a
  porta que importava, o endpoint, já foi fechada no `b1ab978`.
- **A primeira resposta do SLA passa a exigir uma fala ao cliente** (`230d670`).
  `sla_first_response` era carimbado sob `old_status == open`, então "primeira
  resposta" queria dizer "o chamado saiu do estado inicial" — e, como o mapa de
  transições só permite `open → in_progress` e `open → cancelled`, na prática
  "alguém assumiu ou cancelou". Duas distorções opostas conviviam: o técnico que
  respondia pelo chat sem mexer no status não registrava resposta nenhuma
  (`chat.py` não tocava no SLA), enquanto atribuir, assumir ou **cancelar** um
  chamado registrava resposta sem uma palavra ter sido dita. O card de violação
  de resposta e o tempo médio de primeira resposta mediam o tempo até alguém
  clicar. A regra nova não olha para status nenhum: marca a primeira mensagem de
  chat de quem **não é o autor** do chamado — o mesmo critério que o
  `_notify_other_party` já usa para decidir a quem notificar — e a resolução como
  rede de segurança, já que a nota de resolução é texto que o cliente lê. Sem
  migration e **sem backfill**: a regra decide quando gravar, não reescreve o que
  já está gravado. Desenho e levantamento dos 13 caminhos em
  `docs/superpowers/specs/2026-08-20-primeira-resposta-sla-design.md`.
  ⚠️ **O indicador piora no dia do deploy, e essa é a intenção.**
- Violação de primeira resposta que se apagava sozinha (`230d670`). Nos três
  pontos, o carimbo vinha antes do `check_breaches`, que só avalia o prazo
  enquanto `sla_first_response` é nulo — o chamado atendido com três dias de
  atraso saía com `sla_response_breach = False`, e a condição viva do dashboard,
  que também exige o campo nulo, perdia a violação do outro lado.
  `register_first_response` avalia antes de carimbar.

### Alterado
- **O uvicorn sobe com um worker enquanto o chat depender da memória do
  processo** (`9175752`). O `ConnectionManager` guarda as conexões WebSocket
  num dicionário **do processo**. Com dois workers, duas pessoas no mesmo
  chamado caem em processos diferentes com probabilidade alta, cada uma numa
  sala que o outro não enxerga: ficam conectadas, sem erro nenhum, e não
  recebem a mensagem uma da outra. ⚠️ O **lock no Redis** do fechamento
  automático **fica**, mesmo sendo desnecessário com um worker só: voltar a
  dois é mudar um número, e sem o lock essa volta duplicaria histórico e
  notificação de cada chamado fechado — calada, do mesmo jeito. O backplane
  (Redis pub/sub reemitindo as mensagens entre workers) fica como dívida **com
  gatilho**: é o pré-requisito para voltar a mais de um. Três comentários que
  afirmavam `--workers 2` foram corrigidos para não depender do número.
- **A versão da API ganha fonte única e sai da resposta pública** (`dcfc25f`).
  Estava escrita à mão em dois pontos do `main.py`, e as duas cópias
  congelaram em `"1.0.0"` enquanto o produto seguiu para v1.8.0; agora vive em
  `app/__init__.py` e um literal novo derruba o teste. E some do
  `/api/v1/health`, que **responde sem autenticação** — a release exata
  entregue a qualquer um só ajuda quem quer casar versão com vulnerabilidade
  conhecida, e quem chama health check quer saber se a API está de pé. A versão
  continua no metadado do FastAPI, visível no `/docs`, desligado em produção.
  Nada quebra: o front mostra a versão a partir do próprio `changelog.ts`, e os
  `HEALTHCHECK` do Dockerfile e dos compose batem em `/health`, intocado. O
  teste antigo fixava `data["version"] == "1.0.0"` — travava a correção do
  próprio valor que estava errado.
- **`tags.py` deixa de anotar usuário como `object` e de mentir na permissão**
  (`21e8b22`). Os cinco `Depends` estavam anotados como `object`, e o código
  faz `actor.id` em cima disso — enquanto o mypy não está ligado ninguém
  reclama; no dia em que ligar, o erro aparece longe dali. O resto do projeto
  já usa `Annotated[User, ...]`. O docstring dizia que `PATCH` e `DELETE` são
  "admin", mas o código sempre chamou `authorize(admin, technician)`: corrigido
  o **docstring**, não o código — técnico mexer em etiqueta é coerente com o
  resto do sistema, onde ele já cria etiqueta e vincula etiqueta a chamado.
- **O `.dockerignore` do backend passa a excluir `.coverage` e `uploads/`**
  (`4e975b7`). Os dois estão no `.gitignore` desde sempre, mas o
  `.dockerignore` ficou para trás — e o Dockerfile copia com `COPY . .`. O
  `.coverage` existia na árvore com 69 KB e entrava em toda imagem; `uploads/`
  é onde os anexos são gravados, e um build a partir de uma cópia local levaria
  arquivo de chamado para dentro da imagem.
- **O tema segue a preferência do sistema operacional na primeira visita**
  (`8542183`). Quem nunca escolheu recebia escuro fixo; agora vale
  `prefers-color-scheme`. Escolha salva continua mandando, contra o sistema
  inclusive. Duas consequências que a regra arrasta: a gravação saiu do efeito
  de montagem para o `toggleTheme` — gravar ao montar congelaria o valor do SO
  daquele dia e "seguir o sistema" valeria por uma visita só; e o script
  anti-flash do `index.html`, que roda antes do bundle, teve de repetir a regra
  nova à mão, senão quem usa o SO no claro veria flash escuro em toda visita.
  Valor salvo estragado deixa de contar como escolha; sem `matchMedia` no
  ambiente, o escuro segue sendo o padrão.

### Adicionado
- **Revarredura de anexos e aviso de antivírus fora do ar** (`8ff214c`),
  preparando a subida do ClamAV. `scripts/revarre_anexos.py` é avulso, no molde
  do `normaliza_cnpj`: dry-run por padrão, `--aplicar` para gravar. Varre os
  anexos com `virus_scanned=False` — os que entraram enquanto o antivírus não
  existia, já que o upload trata `unavailable` como aprovado. **Não apaga
  nada**, nem infectado: anexo é prova de um chamado, e script de limpeza que
  descarta o que não entende é pior que o problema. A recusa que importa está
  na tradução da resposta: `unavailable` e `error:` **não** viram exame —
  marcar como examinado o que o ClamAV não conseguiu ler seria inventar
  resultado. No boot, fora de dev/teste, um `ping` (que exige `PONG`, porque
  abrir e fechar a conexão faria qualquer porta ocupada passar por antivírus no
  ar) avisa quando o serviço não responde. ⚠️ A **política não mudou**: o
  upload continua aceitando sem varrer, porque bloquear derrubaria o anexo
  inteiro por causa de um serviço auxiliar. O que mudou é o estado deixar de
  ser invisível.
- **`/api/v1/health` vira readiness de verdade; `/health` segue intocado**
  (`ec533c4`). A rota respondia `{"status": "ok"}` sem conferir nada — pior que
  rota nenhuma, porque dá a quem observa a certeza de que está tudo bem
  exatamente quando não está. Os dois conceitos ficam separados: `/health`
  (liveness) **não mudou**, e um teste novo trava isso — é o alvo do
  `HEALTHCHECK` do Dockerfile e dos compose, e se passasse a depender do banco
  uma oscilação do Postgres reiniciaria o container da API, trocando uma
  indisponibilidade parcial por uma total. `/api/v1/health` (readiness) confere
  banco (`SELECT 1`) e Redis, os dois com timeout de 2 s, em paralelo; alguma
  faltou responde **503** com `status: degraded` e o culpado em `checks`. Redis
  conta porque dele dependem a blacklist de token e o lock do fechamento
  automático. O carimbo do auto-close aparece em `auto_close.last_success`,
  **reportado e não usado para derrubar**: é `null` nos primeiros 60 s de cada
  worker, e derrubar por isso daria 503 em todo boot. Deu para mudar o status
  code porque **nada consome a rota programaticamente** — `HEALTHCHECK`, os
  dois compose, o k6, o `e2e.yml` e o `zap-scan` batem todos em `/health`.
- **Script de backfill de CNPJ** (`62f022e`, `backend/scripts/normaliza_cnpj.py`).
  O validador cuida do futuro; este script cuida do passado — sobretudo de
  `companies.cnpj`, que nasceu texto livre. **Avulso e rodado à mão, nunca em
  migration**, que é a regra do projeto: dado histórico se corrige em script,
  regra nova é prospectiva. Dry-run por padrão (`--aplicar` grava), e importa a
  mesma normalização do validador de propósito — cópia própria da regra
  gravaria linha que a API recusaria depois. Linha que não soma 14 dígitos é
  **relatada e deixada como está**, nunca apagada: script de limpeza que
  descarta o que não entende é pior que o problema que veio consertar.
  Verificado ponta a ponta em Postgres efêmero — dry-run não grava, `--aplicar`
  normaliza, linha torta sobrevive, segunda rodada não faz nada. ⚠️ **Ainda não
  foi rodado em produção**; o `backend/.env` local aponta para o banco real,
  então quem roda é o Rickelme, quando quiser.

- **Filtro de equipamentos sem dono** na listagem de Produtos (`3f3af90`),
  fechando o outro lado do `3efb0cf`: atribuir dono já era possível, achar o
  órfão para atribuir não era. Precisou ser parâmetro novo do endpoint
  (`without_owner` em `GET /products/{id}/equipments`) e não filtro de tela —
  a listagem é paginada no servidor, então peneirar o array recebido acharia só
  o órfão que por acaso caiu na página aberta. A forma é um booleano e não um
  filtro de dono genérico porque as duas coisas são ortogonais: "sem dono" é a
  **ausência** de `owner_id` e não caberia num `owner_id=<uuid>` sem inventar um
  valor sentinela; um filtro por dono específico, se fizer falta, entra ao lado
  sem renegociar este contrato. O filtro **soma** ao escopo por dono do cliente
  e nunca o substitui — cliente pedindo `without_owner=true` recebe lista vazia
  em vez do parque órfão inteiro, e há teste para isso.
- Seletor de dono no cadastro de equipamento pela tela de Produtos
  (`3efb0cf`), fechando o ciclo do `51a9cb8`: o backend aceitava `owner_id`
  desde então, mas o `productService` omitia o campo e o equipamento continuava
  nascendo órfão. Novo componente `SearchSelect` com busca no servidor — um
  dropdown pré-carregado quebraria em silêncio ao passar de 100 clientes, que é
  o teto de `GET /users`. O campo aparece ao criar **e** ao editar, com
  "— Sem dono —", o que também conserta os órfãos existentes um a um.

### Removido
- **Sete configurações que não alimentavam código nenhum** (`b30f75e`), todas
  com uso zero fora da própria definição: `llm_primary_provider` e
  `llm_fallback_provider` (o `llm.py` escolhe provedor por caminho de código
  explícito), `openai_max_tokens` e `anthropic_max_tokens` (o `llm.py` fixa
  `max_tokens` por tarefa — 256, 512, 400; um número só não serviria para as
  três), `llm_max_retries` (não há laço de retry que o leia),
  `clamav_max_file_size_mb` (quem barra arquivo grande é
  `upload_max_file_size_mb`) e `rate_limit_default` (o `Limiter` sobe sem
  `default_limits`; `rate_limit_login` segue em uso). Saem também do
  `.env.example`, senão a mentira apenas mudaria de arquivo. Remover campo do
  `Settings` é seguro aqui porque o `model_config` usa `extra="ignore"`: se a
  variável continuar setada no EasyPanel, o boot ignora em vez de quebrar.
- **O bloco SLA do `config.py`, que nunca alimentou o motor** (`3cf63d2`). Era o
  mais perigoso: o `config.py` anunciava `SLA_BUSINESS_HOURS_END=18:00`
  enquanto o `utils/sla.py` calcula com `_WORK_END = 17` — e o `sla.py` **não
  importa `Settings`**. O código está certo: 08:00–17:00, 9 h/dia, confirmado
  com o cliente em 05/08/2026 (RN-013). ⚠️ Quem um dia decidisse "consertar a
  divergência" ligando a configuração ao motor **mudaria o prazo de todos os
  chamados de uma vez**. Por isso remover era a única opção segura, e por isso
  veio em commit separado do de cima: ali a escolha entre remover e ligar era
  de gosto, aqui não era. Saíram os quatro campos, não só os dois do horário —
  `sla_business_days` e `sla_timezone` estavam igualmente mortos e são a mesma
  armadilha. A proteção real ficou no próprio `sla.py`: um comentário nas
  constantes explica por que são constantes e aponta para o documento de
  decisões, porque comentário de commit ninguém lê daqui a um ano.
- **O pacote `app/worker/` e o Celery, que nunca executaram nada** (`3c4b433`).
  Não havia uma única chamada `.delay(` ou `.apply_async(` no repositório,
  nenhum processo Celery no `start.sh`, nenhum `beat_schedule`; as duas tarefas
  de negócio devolviam `{"status": "queued"}` sem fazer coisa alguma. Um
  esqueleto que responde "queued" é pior que ausência — alguém acaba chamando
  acreditando que funciona. Havia inclusive uma colisão esperando acontecer:
  `tasks.classify_ticket` era um stub vazio enquanto o `classify_ticket` do
  `services/llm.py`, de mesmo nome, é o que de fato roda. Sai junto tudo que só
  existia por causa dele — `celery` do `requirements.txt` (o **`redis` fica**:
  cache, blacklist de token e o lock da rotina de fechamento), o bloco
  `CELERY_*` do `config.py` e do `.env.example`, o omit de cobertura e o
  override de mypy no `pyproject.toml`. Nos documentos, a rotina periódica
  dentro da API deixa de aparecer como consequência de uma falta e passa a
  constar como **decisão**, com o motivo.
- Duas linhas mortas (`0e1a917`): o comentário de `products.py` citando
  `_check_ticket_access`, apagado no `7371bc7`, e o `!disabled &&` do
  `FormDropdown` — o atributo `disabled` do `<button>` já impede o navegador de
  disparar o clique, como a verificação por mutação do `f7945e0` mostrou.

### Desempenho
- **As três listagens administrativas param de consultar por item** (`d765587`).
  `/dashboard/reports/technicians` fazia 2 consultas por técnico,
  `/groups` uma por grupo, e `/groups/{id}` mais `/groups/{id}/companies` duas
  por empresa. Com 15 técnicos eram 31 consultas numa tela; com 40 empresas,
  81. Agora são 3 e 3, com o mesmo padrão que o `list_tickets` já usava:
  agregação com `GROUP BY` para a página inteira. Quem não tem filho nenhum não
  volta do `GROUP BY` — por isso toda leitura é `.get(id, 0)`. Os caminhos de
  item único seguem com os helpers individuais, onde não há N+1 a evitar. O
  teste não prende um número fixo de consultas (esse muda quando alguém
  acrescenta um campo) e sim a propriedade: **dobrar a lista não pode dobrar as
  consultas**.

### CI
- **mypy zerado e ligado** (`846c6c4`). 28 erros em 12 arquivos viraram zero, e
  o CI passa a rodar `mypy app` depois do black — a ferramenta já estava no
  `requirements-dev` desde sempre e nunca tinha sido executada. Nenhum dos
  erros escondia bug vivo: os dois mais suspeitos são benignos (o
  `_record_history` faz `str()` antes de gravar; o CSV só reusava o nome `c` em
  dois laços de tipos diferentes). O resto é anotação faltando, tipo estreito
  demais e limitação de biblioteca. Um achado saiu do meio disso e **não era
  bug**: `schemas/tag.py` passava `strip_whitespace=True` ao `Field`, que não é
  parâmetro do `Field` no pydantic v2 — chegava como kwarg extra e não fazia
  nada; o strip real vem do `str_strip_whitespace` do `AppBaseModel`, herdado.
  Decoração morta com o comportamento certo por outro caminho. De quebra sumiu
  a deprecation que sujava toda rodada de teste.
- **Playwright em workflow separado, `e2e.yml`** (`d361e78`), acionado à mão
  por enquanto; o agendamento noturno está comentado no arquivo e entra depois
  de duas execuções manuais verdes. Sobe Postgres e Redis como services, roda
  migrations e seeds, levanta o backend na 8001 e roda os 46 specs; relatório
  sempre como artefato, log do backend quando falha. `APP_ENV=testing` porque a
  suíte faz ~16 logins do mesmo IP contra o rate limit de 5/15 min; chaves JWT
  efêmeras geradas no job — nenhum segredo do repositório. **As contas do e2e
  não entram em `app.seeds`**, que roda no boot de produção: vivem em
  `app.seeds_e2e`, que se recusa a rodar em produção antes de abrir sessão, com
  teste provando que `app.seeds` não cria conta de teste nenhuma. A credencial
  de técnico saiu do `helpers.ts` — nenhum spec a usava. k6 (Fase 3) segue
  aguardando staging.

### Testes
- **O domínio de empresa em `groups.py` sai do descoberto** (`470d56c`).
  Nenhum teste da suíte referenciava `Company`, `company_id` ou qualquer
  endpoint `/groups` — os únicos "company" em `tests/` eram `company_name` e
  `company_cep`, colunas de onboarding do `User`. São testes de
  **caracterização**: prendem o que o código faz hoje para que a próxima
  mudança seja decisão e não descoberta. Dois entram justamente porque são
  silenciosos e ninguém os escolheu — o `PUT` que ignora `None` (limpar CNPJ
  pela tela não funciona, e trocar a guarda mexe em sete campos de uma vez) e
  a exclusão de empresa, que desvincula cliente sem avisar. **Banco de
  verdade, não mock**: a exclusão não dá para provar com mock — quem
  desvincula é o SQLAlchemy com a FK `ON DELETE SET NULL` por baixo, e um mock
  afirmaria que `db.delete` foi chamado e passaria mesmo com a regra
  invertida. SQLite em memória reproduz o mesmo resultado do Postgres efêmero
  do levantamento e roda no CI sem subir serviço; `create_all` vai só no
  subconjunto de tabelas porque `kb_articles` tem `ARRAY`, que o SQLite não
  compila. Como passaram de primeira, foram verificados por **mutação** —
  e uma asserção não sobreviveu: `resp.content == b""` era tautológica (o
  `204` já garante corpo vazio) e foi trocada pelo status, que cai se a
  exclusão virar bloqueante ou informativa.

- `FilterSelect`, `FormDropdown` e `ThemeContext` saem do descoberto
  (`f7945e0`). Os três tinham lógica real e nenhum teste; como o Vitest é gate
  do CI desde `1583b8b`, a ausência não aparecia como risco, aparecia como
  silêncio. Cobrem o que um `<select>` nativo daria de graça e aqui é código
  nosso — o painel em portal do `FilterSelect`, que precisa fechar sozinho em
  clique fora, scroll e resize e reancorar quando abriria fora da janela — e o
  ciclo escolher/sair/voltar do tema, que é onde a classe `dark` no `<html>` e a
  chave `helphs-theme` divergiriam. Fica registrado no teste que o padrão é o
  escuro e **não** `prefers-color-scheme`: o app não lê a preferência do sistema
  operacional. Cada arquivo foi verificado por mutação.

### Documentação
- O checklist de deploy (`help-deploy-check`) descrevia `GET /api/v1/health`
  como "versão e env certos" — a versão saíra na rodada anterior e o readiness
  mudou o contrato de novo. Agora descreve os dois contratos e o que um
  `auto_close.last_success` parado quer dizer.
- Guia de desenvolvimento local (`f27f38c`, `3485092`) e mini-Redis de dev em
  `backend/scripts/` (`5fc7562`); skill de test review atualizada sobre o
  Vitest no CI (`b1f10b7`).

## [v1.7.0] — 19/08/2026

Fechada com o deploy de 19/08 (backend e frontend). Versão correspondente no
changelog do produto: `docs: changelog da v1.7.0` (`1c0399d`).

### Segurança
- Sanitização com DOMPurify do markdown renderizado da Base de Conhecimento,
  fechando XSS armazenado (`0c7164f`).
- Rate limiting com slowapi (5 tentativas / 15 min) nos endpoints de
  autenticação: login, register, forgot-password e resend-confirmation
  (`464d9be`). Desligado por padrão sob `APP_ENV=testing`.
- Login deixa de vazar, pelo tempo de resposta, quais e-mails têm conta
  (`f8e6013`): e-mail inexistente passa a ser conferido contra um hash
  descartável de 12 rounds, igualando o custo dos dois caminhos.
- Boot em `APP_ENV=production` passa a exigir `CORS_ORIGINS` com o domínio real
  do front e a recusar `*` (`8ab84c8`) — antes, a ausência da variável fazia a
  API subir em silêncio com origem de desenvolvimento. **Recriar o serviço sem
  `CORS_ORIGINS`, `FRONTEND_URL` e `APP_ENV` impede o boot** (vale também para
  `alembic upgrade` avulso, que instancia as mesmas configurações).
- Guard de produção endurecido (`ef636fe`): lista de origens vazia passava a
  valer como configuração válida; `APP_ENV=Production`/`prod` desligava **todas**
  as validações, inclusive a da `SECRET_KEY`; `[::1]` e `0.0.0.0` escapavam do
  filtro de loopback enquanto um domínio legítimo contendo "localhost" era
  barrado; `FRONTEND_URL` — que monta os links dos e-mails — passou a ser
  validada igual.
- Paridade de custo do hash descartável do login virou contrato de teste
  (`9634d7e`): se ele ficar mais barato que os hashes reais, a enumeração por
  tempo reabre.
- Equipamentos escopados por dono para o perfil cliente (`724322f`):
  `GET /products/{id}/equipments` passa a filtrar por `owner_id` e
  `GET /equipments/{id}` recusa equipamento de outro dono — ou sem dono
  (*fail closed*). Antes, qualquer autenticado lia o número de série do
  equipamento de qualquer cliente. Staff mantém acesso total.
- A recusa acima deixa de denunciar o que existe (`637ad0f`): para o cliente
  ela sai como `404`, com o mesmo texto de um id inexistente, em vez do `403`
  que confirmava a existência do equipamento. Vale também para os
  `/equipment/my*`. Para staff continua `403`, que já enxerga o parque inteiro.
- `BCRYPT_ROUNDS` deixou de ser configuração morta (`b06228f`): a variável
  estava documentada e lida, mas nunca chegava ao `pwd_context` — quem subisse
  com `14` no painel não mudava nada. O teste de paridade do hash descartável
  passou a comparar contra o custo efetivo, então subir os rounds sem regerar
  o dummy fica vermelho na suíte.
- `FORWARDED_ALLOW_IPS` passa a existir como configuração explícita
  (`701df8e`), com aviso no boot de produção quando está vazia. Sem ela, atrás
  de um proxy o rate limit de login enxerga sempre o IP do proxy e vira um
  limite único para todos os usuários. **Ligar exige confirmar a topologia
  antes** — ver `mudanças.md`.
- `APP_ENV` normalizado na origem (`a06daa4`): a tolerância a caixa e espaço
  valia só no ramo de produção, então `APP_ENV=Testing` num job de CI subia o
  rate limiter ligado contra o Redis e `Development` desligava o `/docs` em
  silêncio.

### Adicionado
- Staff pode atribuir o dono do equipamento (`51a9cb8`): `owner_id` opcional no
  `POST /products/{id}/equipments` e no `PATCH /equipments/{id}`, recusando com
  `400` quem não existe ou não é cliente. Sem isso o equipamento cadastrado
  pela tela de Produtos nascia órfão e ficava assim — invisível ao cliente
  real, sem poder virar chamado e sem poder ser recadastrado, porque o número
  de série já estava tomado. O campo **não** existe nos corpos aceitos pelos
  `/equipment/my*`. Falta a tela (seletor de dono na ProductsPage).

### Desempenho

- Login não bloqueia mais o event loop (`72f31bc`): o bcrypt, síncrono e de
  ~250 ms, passou a rodar em thread separada — antes, cada tentativa de login
  travava todas as requisições em voo, e a defesa contra enumeração por tempo
  havia estendido esse custo ao caminho do e-mail inexistente.
- Mesma correção nos demais endpoints que mexem com senha (`751bfeb`):
  cadastro, redefinição de senha por e-mail, criação de usuário pelo staff e
  troca de senha — nenhum deles trava mais a API enquanto calcula o hash.

### CI
- Vitest passou a rodar no job do frontend, entre o typecheck e o build
  (`1583b8b`).
- Backend reformatado com o black pinado (`57ca9d9`), devolvendo o CI ao verde:
  o Black format check reprovava no main desde 06/08 e, por rodar antes do
  pytest, impedia a suíte do backend de rodar — o gate de testes estava morto
  sem ninguém perceber. Reformatação mecânica, sem mudança de lógica.
- Chaves JWT efêmeras geradas pelo conftest (`4449ce2`): com o pytest de volta
  no CI, 54 testes que assinam RS256 morriam com `FileNotFoundError` porque
  `keys/` é gitignored e nada as gerava. Par RSA por sessão em diretório
  temporário — `pytest` roda em máquina zerada, e a suíte nunca toca as chaves
  reais do dev. Primeiro CI verde de ponta a ponta desde antes de 06/08.
- Suíte do backend deixou de depender do `.env` local (`e4ec7f2`): um
  `conftest.py` fixa `APP_ENV=testing` antes dos imports, então `pytest` roda
  verde sem variável no comando. Antes, quem rodasse localmente subia o rate
  limiter ligado e via falhas que o CI não tinha.
- Testes de configuração deixaram de depender das variáveis exportadas no
  shell (`4d8fbbf`): o `_env_file=None` calava o `.env`, mas não o ambiente —
  quem tivesse `CORS_ORIGINS` exportado, o caso de dentro dos containers de dev
  e staging, via os testes de default quebrarem sem ter mexido em nada.
- Suíte do front reforçada nos pontos de maior risco (`0cd019a` … `6049181`,
  192 → 229 testes): o interceptor do axios — refresh no 401, guards anti-loop
  e fila de chamadas concorrentes — saiu de 0% para 100%, junto com os três
  guards de rota (`AuthGuard`/`RoleGuard`/`OnboardingGuard`), o
  `equipmentService`, o `toastError` e os ramos restantes do `cn`.
  `src/components/layout/` entrou no `include` de cobertura do Vitest, que não
  enxergava a camada; `frontend/coverage/` entrou no `.gitignore` (`3ae937c`).

### Corrigido
- Build do frontend quebrado por typecheck que não checava nada (`882662b`).
- Toast em inglês para o cliente ao tentar equipamento alheio ou inexistente
  (`2db8dfa`): com a recusa por dono virando `404` (`637ad0f`), a mensagem que
  chega é "Equipment not found" — e ela não estava no dicionário de traduções
  do `apiError.ts`. A entrada antiga cobria o fluxo que deixou de existir.
- Login travava com "Confirme seu e-mail" sem nenhum e-mail chegar (`1b3d355`):
  a exigência de confirmação era inferida de `SMTP_USER`/`SMTP_FROM_EMAIL`
  preenchidos — e o `.env.example` vem com os dois preenchidos. A adoção agora
  é explícita via `EMAIL_VERIFICATION_ENABLED` (default `false`) junto do SMTP;
  em produção, flag ligada sem SMTP recusa o boot. Contas criadas presas voltam
  a entrar sem intervenção no banco.

### Documentação
- 11 skills `help-*` de revisão, segurança e deploy em `.claude/skills/`
  (`1d6e766`).
- Desenho do atendimento por IA (Helo) em 3 fases (`9f0aec1`).

## [v1.6.0] — 10/08/2026

### Adicionado
- Vários equipamentos por chamado: N:N entre ticket e equipamentos, com busca
  pelo número de série de qualquer aparelho vinculado e sugestão de artigos
  considerando todos os produtos envolvidos (`b58bfd8`).

## [v1.5.0] — 07/08/2026

### Adicionado
- Pergunta de recomendação (1 a 10) na pesquisa de satisfação e card
  Recomendação nos relatórios (`58f6773`).

## [v1.4.0] — 07/08/2026

### Adicionado
- Ciclo de encerramento do chamado (RN-005 e RN-006): reabertura pelo cliente
  em até 5 dias úteis e fechamento automático após 3 dias úteis sem
  manifestação, com prazo de SLA renovado na reabertura (`0e00a31`).

### Corrigido
- Chat espremido quando a pesquisa de satisfação aparecia no chamado.
- Tempo médio de resolução contava os dias de espera até o fechamento.
- Convite de avaliação era enviado duas vezes ao resolver o chamado.

## [v1.3.0] — 06/08/2026

### Adicionado
- Confirmação de e-mail no cadastro e recuperação de senha, com tokens,
  e-mails transacionais e telas próprias (`79469a6`, `b1a15e4`, `03830df`).
- Armazenamento de anexos e avatares em disco com volume, substituindo o
  MinIO (`8f93b37`).
- Visualização de anexo no navegador sem download (`84be869`).
- Produto e equipamento visíveis no ticket (`04e01c2`); busca de tickets pelo
  número de série (`3b0cd45`).

### Corrigido
- Anexos escolhidos na abertura do chamado eram descartados (`d44351d`).
- Base de conhecimento quebrava quando a API não mandava `products`
  (`6f7440c`).

## [v1.2.0] — 05/08/2026

### Adicionado
- Base de conhecimento por produto: vínculo artigo–produto, sugestões por
  produto/categoria do ticket, aba de KB no chamado e filtro por produto
  (`d752431`).
- Qualquer técnico pode concluir e responder qualquer ticket (`986d48d`).
- 16ª cor na paleta da agenda (`0d16819`).

### Corrigido
- Etiquetas do ticket legíveis e sem vazar da coluna (`49e6986`).

## [v1.1.0] — 04/08/2026

### Adicionado
- Respostas rápidas no chat com atalho `/` e página de gestão (`9f60877`).
- Técnico pode excluir comentários na base de conhecimento (`bfebbfc`).
- CNPJ e CEP obrigatórios no cadastro do cliente, com validação (`eb08065`).
- Paleta fixa de cores na agenda (`2a300e4`); mensagens de erro explicativas
  (`639bc2d`).

### Corrigido
- Escala do CSAT unificada em 1 a 10 (`d8fd1a2`).
- Ortografia, encoding corrompido e bug de hooks na KB (`b88ac2d`).
- Suíte do backend recuperada: 37 falhas → 0 (`fae7b95`); pipeline devolvido
  ao verde com ruff e cobertura de 80% (`98fd0e6`).

## [v1.0.0] — 20/05/2026

- Acesso completo de técnicos a Grupos, Usuários, Produtos e Etiquetas;
  interface responsiva para mobile e tablet; detalhes de equipamentos; audit
  logs adaptados para tablet.

## [v0.9.0] — 01/05/2026

- Módulo de Audit Logs; SLA por prioridade com alertas; etiquetas coloridas;
  performance do dashboard; correção de notificações no Safari.

## [v0.8.0] — 15/04/2026

- Base de Conhecimento com busca; gestão de grupos e empresas; modo
  escuro/claro; relatórios com gráficos.
