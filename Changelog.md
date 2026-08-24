# Changelog — HelpHS (repositório)

Changelog técnico, para desenvolvedores. O changelog do **produto** — o que o
cliente final vê dentro do sistema — vive em
`frontend/src/data/changelog.ts` e é mantido pela skill
`help-changelog-update`; este arquivo não o substitui.

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/).
Datas em DD/MM/AAAA.

## [Não publicado]

### Segurança
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
- Duas linhas mortas (`0e1a917`): o comentário de `products.py` citando
  `_check_ticket_access`, apagado no `7371bc7`, e o `!disabled &&` do
  `FormDropdown` — o atributo `disabled` do `<button>` já impede o navegador de
  disparar o clique, como a verificação por mutação do `f7945e0` mostrou.

### CI
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
