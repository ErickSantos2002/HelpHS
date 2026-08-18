# Mudanças — Rickelme David

Registro do trabalho feito por **Rickelme David** neste repositório, por data.
O changelog do produto (o que o cliente vê) fica em
`frontend/src/data/changelog.ts`; o changelog do repositório, para devs, é o
[Changelog.md](Changelog.md).

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
- **Equipamento sem dono fica órfão** — staff cria equipamento sem `owner_id` e
  nenhum schema permite atribuí-lo depois; com o escopo por dono, ele fica
  invisível ao cliente real. Precisa de endpoint e tela de atribuição — é
  feature, não correção.
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
- **CI Fase 2/3** — Playwright em `e2e.yml` separado (workflow_dispatch +
  noturno) e k6 contra staging; proposta escrita, aguardando decisão de
  investir no ambiente.
