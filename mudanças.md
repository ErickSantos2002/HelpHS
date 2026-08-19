# Mudanças — Rickelme David

Registro do trabalho feito por **Rickelme David** neste repositório, por data.
O changelog do produto (o que o cliente vê) fica em
`frontend/src/data/changelog.ts`; o changelog do repositório, para devs, é o
[Changelog.md](Changelog.md).

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
