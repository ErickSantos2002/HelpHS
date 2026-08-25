---
name: help-test-review
description: Revisa testes do HelpHS e identifica cenários sem cobertura — pytest no backend/, Vitest + Testing Library no frontend/, Playwright em frontend/e2e/ e k6 na raiz. Usar após implementar feature ou endpoint, antes de refatorar, ou ao decidir em que nível (unidade, componente, e2e) testar algo.
---

# Skill: Test Review — HelpHS

## Objetivo

Analisar os testes de um módulo, apontar gaps e sugerir casos ausentes — sem
gerar código a menos que solicitado. Inclui decidir **em que nível** um cenário
deve ser testado.

## O que existe (e como funciona)

Diferente do ChamadosHS, aqui há suíte real nos dois lados. Quatro níveis:

| Nível | Onde | Como roda |
|---|---|---|
| Backend (unidade/rota) | `backend/tests/` | `pytest`, a partir de `backend/` |
| Front (unidade/componente) | `frontend/src/test/{components,contexts,lib,services}` | `npm test` (Vitest 4 + happy-dom) |
| E2E | `frontend/e2e/*.spec.ts` | `npm run e2e` (Playwright, chromium) |
| Carga | `k6/load-test.js`, `k6/stress-test.js` | `k6 run k6/load-test.js`, manual |

Padrões de cada suíte:

- **Backend**: `httpx.AsyncClient` com `ASGITransport` sobre o `app` real;
  banco e Redis **mockados** via `app.dependency_overrides` + `FakeRedis`
  (ver `backend/tests/test_auth.py`). O `conftest.py` fixa o ambiente antes
  de qualquer import de `app` (`APP_ENV=testing` → rate limiter desligado,
  chaves JWT efêmeras); as fixtures de app/banco vivem em cada arquivo.
  `asyncio_mode = "auto"` no `pyproject.toml`.
- **Cobertura mínima de 80% é gate**: `--cov-fail-under=80` no
  `pyproject.toml`. Código novo sem teste pode derrubar o pytest inteiro no CI
  mesmo com todos os testes passando.
- **Front**: serviços mockam o módulo `api` com `vi.mock` (não usa msw);
  componentes com Testing Library + `@testing-library/user-event`; setup em
  `frontend/src/test/setup.ts`. A cobertura do Vitest só mede
  `components/ui`, `lib`, `services` e `contexts` (ver `vite.config.ts`) —
  páginas inteiras ficam de fora por decisão.
- **E2E**: roda **sequencial de propósito** (`workers: 1`) porque o banco é
  compartilhado — não paralelizar. Sobe o dev server sozinho, mas exige o
  backend rodando na porta 8001 **com `SEED_ADMIN_PASSWORD` exportada**
  (sem ela o seed não cria o admin e todo login falha) e credenciais via
  `ADMIN_EMAIL`/`ADMIN_PASSWORD` etc. (ver `frontend/playwright.config.ts`).

## ⚠️ O que o CI roda — e o que não roda

O `.github/workflows/ci.yml` roda **pytest** (com o gate de 80%) no backend e,
no front, **ESLint + tsc + Vitest + build**. Ou seja:

- **Vitest roda no CI desde `1583b8b`** (entre o typecheck e o build): teste
  de front quebrado bloqueia o pipeline igual ao pytest.
- **E2E e k6 nunca rodam a cada push.** O e2e tem workflow próprio
  (`e2e.yml`, `workflow_dispatch`, banco efêmero do job com
  `SEED_ADMIN_PASSWORD` definido); o k6 é execução manual.

Ao revisar, se um cenário crítico só está coberto por e2e ou k6, dizer
explicitamente que ele está fora do gate do CI.

## Em que nível testar

- **Regra de negócio do back** (SLA em `app/utils/sla.py`, encerramento
  RN-005/RN-006 em `app/services/ticket_lifecycle.py`, protocolo, RBAC) →
  pytest. É o nível mais barato e o único com gate no CI.
- **Lógica pura do front** (`src/lib/`), **serviço de API**, **componente de
  ui reutilizável** → Vitest.
- **Fluxo completo** (login → abrir chamado → técnico resolve → cliente
  responde pesquisa) → Playwright. Caro e sequencial: reservar para o caminho
  que atravessa telas, não para variação de regra.
- **Performance** → k6, apenas quando a pergunta é de carga.

Regra prática: bug corrigido ganha teste no **nível mais barato que o
reproduz** — quase sempre pytest ou Vitest, quase nunca e2e.

## O que analisar

### 1. Cobertura de cenários, não de linhas

Casos de borda reais deste domínio:

- **Autenticação**: rota com e sem token, token expirado, refresh token usado
  como access, token na blacklist pós-logout, perfil errado → `403`
  (`test_rbac.py` é a referência)
- **Escopo do client**: cliente não pode ver/alterar ticket, anexo ou nota de
  outro cliente — o teste mais valioso do sistema; repetir para endpoint novo
- **SLA**: pausa nos status de espera, horário comercial 08:00–18:00, fuso
  `America/Sao_Paulo`, estouro de prazo (breach)
- **Encerramento (RN-005/RN-006)**: auto-close conta **dias úteis**; resolvido
  na sexta não pode fechar no domingo; reabertura dentro e fora do prazo
- **Upload**: extensão fora da allowlist, arquivo acima do limite, ClamAV
  indisponível
- **LLM**: timeout ou 500 do provider **não pode derrubar a criação do
  chamado**; fallback OpenAI → Anthropic
- **E-mail não configurado**: sem SMTP, o cadastro libera acesso na hora
  (`requires_email_verification` em `config.py`) — os dois caminhos precisam
  de teste

### 2. Tempo e fuso ⚠️

SLA e auto-close dependem de dias úteis e de `America/Sao_Paulo`, e o
container roda em UTC. Teste que usa "agora" real quebra sozinho com o passar
do tempo (ou numa sexta-feira). **Não há freezegun no projeto** — congelar o
relógio com `unittest.mock.patch` no módulo sob teste, ou propor adicionar
`freezegun` ao `requirements-dev.txt` se a dor se repetir.

### 3. O ponto cego da suíte do backend

Como o banco é 100% mockado, a suíte **não pega erro de query real** —
relacionamento errado, coluna renomeada sem migration, N+1. O que toca banco
de verdade é só o e2e. Ao revisar teste que mocka uma query complexa,
perguntar: o mock ainda descreve o que o banco faria?

### 4. Qualidade dos testes existentes

- Assertion vaga (`assert result`, `expect(x).toBeTruthy()`) não prova nada
- Teste dependente de ordem de execução (no e2e a ordem é intencional; fora
  dele, é defeito)
- Mock que esconde o comportamento em vez de isolá-lo
- Estado compartilhado sem limpeza — o padrão do projeto é limpar no início da
  fixture (`_fake_redis._store.clear()`) e `app.dependency_overrides.clear()`
  ao sair

### 5. Nomenclatura

Padrão atual do projeto: função de teste em inglês descritivo, docstring em
português quando precisa de contexto:

```
✅ async def test_client_cannot_see_other_clients_ticket()
✅ test("mostra erro quando o upload excede o limite", ...)
❌ def test_ticket()
```

O nome deve ler como documentação do comportamento — seguir o padrão do
arquivo em que o teste vai morar.

## Formato de resposta

```
TEST REVIEW — backend/app/services/ticket_lifecycle.py
======================================================
✅ Coberto: auto-close no prazo, reabertura pelo criador
❌ Ausente: resolvido na sexta (dias úteis), reopen após o prazo, intervalo=0 desliga a rotina
⚠️  Frágil: usa datetime.now real — quebra conforme o dia da semana
⚠️  Fora do CI: o fluxo de reabertura só está coberto no e2e (ticket-detail.spec.ts)
💡 Sugestão: fixture de ticket resolvido com data parametrizada
```

Ao final, perguntar: **"Quer que eu escreva os casos ausentes?"**

## Observações

- Não reescrever teste que funciona, só o que está incorreto
- Módulo sem teste nenhum: sugerir de 3 a 5 casos concretos, não uma suíte
  inteira de uma vez
- Os 80% são **piso do CI**, não alvo — cobertura de linha não substitui
  cenário de borda
- Ver [[help-refactor]]: refatoração sem teste é só reorganizar o risco — e
  [[help-security-audit]] para transformar achado de segurança em teste
