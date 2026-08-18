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

- Backend: **364 testes passando**, cobertura **80,94%** (gate de 80% mantido).
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

### Fila para a próxima rodada

- 🟡 **#3 Enumeração de usuários** — 409 no register e diferença de timing no
  login. **Vetado até aprovação explícita.**
- 🟡 **#4 CORS** — default aponta para localhost. **Vetado até aprovação
  explícita.**
- **CI Fase 2/3** — Playwright em `e2e.yml` separado (workflow_dispatch +
  noturno) e k6 contra staging; proposta escrita, aguardando decisão de
  investir no ambiente.
