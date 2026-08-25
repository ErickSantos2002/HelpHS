---
name: help-code-review
description: Revisão de código do HelpHS — React/TypeScript em frontend/ e FastAPI/Python em backend/, no mesmo repositório. Usar ao revisar arquivo, função ou alteração antes de commitar. Delega para help-security-audit, help-endpoint-review, help-migration-check, help-env-check e help-test-review conforme o tipo de arquivo.
---

# Skill: Code Review — HelpHS

## Objetivo

Revisão detalhada e contextualizada, aproveitando o histórico da sessão para
não repetir sugestão já discutida nem contrariar decisão já tomada.

## Contexto do monorepo

| | `frontend/` | `backend/` |
|---|---|---|
| Linguagem | TypeScript / React 19 | Python 3.12+ / FastAPI |
| Estado | Context API (`AuthContext`, `ThemeContext`) — **não usa React Query** | — |
| HTTP | Axios com interceptors de refresh em `src/services/api.ts` | — |
| Camadas | `pages` → `contexts`/`services` → API | `routers` → `services`/`utils` → `models` |
| Formulários | react-hook-form + zod | validação nos schemas Pydantic |
| Banco | — | SQLAlchemy 2.0 **async** + Alembic |

Convenções do projeto:

- **Identificadores em inglês** (`Ticket`, `assignee`, `reopenTicket`);
  **português** em docstrings, comentários, mensagens de commit e todo texto
  de UI/erro que o usuário vê. Não misturar no mesmo nível: variável em
  português no meio de código em inglês é fuga do padrão (o inverso do
  ChamadosHS — não confundir)
- Toda chamada à API passa por um service de `src/services/*Service.ts` —
  componente **nunca** chama `axios`/`api` direto
- Tailwind com `darkMode: "class"` e tokens semânticos
  (`background-surface`, `border`, `primary`, `danger`...) definidos em
  `tailwind.config.js` — cor nova crua (`gray-100` sem variante `dark:`) é
  regressão de tema
- Erro para o usuário via toast (`sonner`), com `src/lib/toastError.ts` — erro
  que morre no `console.error` não aconteceu para o usuário

## Como executar

### 1. Contexto da sessão

Antes de revisar, considerar o que já foi estabelecido: decisões de
arquitetura, padrões acordados, itens que o usuário já decidiu não tratar.

### 2. Delegação por tipo de arquivo

| Arquivo | Delegar para |
|---|---|
| `backend/app/routers/*.py` | `help-endpoint-review` |
| `security.py`, `config.py`, `main.py`, `auth.py`, `storage.py`, KB com markdown | `help-security-audit` |
| `backend/alembic/versions/*`, `app/models/models.py` | `help-migration-check` |
| `.env*`, `Dockerfile*`, `docker-compose*.yml` | `help-env-check` |
| `backend/tests/`, `src/test/`, `frontend/e2e/` | `help-test-review` |

Incorporar o resultado na seção correspondente em vez de duplicar a análise.

### 3. Categorias de análise

**Qualidade**
- O código faz o que se propõe?
- Lógica duplicada que caberia extrair (`src/lib/` no front,
  `app/services/`/`app/utils/` no back)?
- Nomes comunicam intenção, no idioma certo (ver convenções acima)?

**Front-end especificamente**
- `useEffect` sem array de dependência correto, ou faltando cleanup
- Estado derivado guardado em `useState` quando poderia ser calculado
- Chamada à API dentro de componente sem passar pelo service
- Formulário novo montado à mão em vez de react-hook-form + zod
- Toda cor nova usa token semântico e funciona no dark mode?
- Lista sem `key` estável (índice de array não conta)
- Arquivos já grandes (`TicketDetailPage.tsx` ~1700 linhas, `GroupsPage.tsx`
  e `ReportsPage.tsx` passam de 1100) — evitar engordar mais sem necessidade

**Back-end especificamente**
- Sessão do banco obtida fora do `Depends(get_db)`
- **`await` esquecido** em chamada async (SQLAlchemy async falha de formas
  silenciosas — `MissingGreenlet`, coroutine nunca executada)
- N+1 em listagem — o padrão do projeto é `selectinload` (ver
  `app/routers/tickets.py`)
- `commit()` sem `rollback()` no caminho de erro; `except Exception: pass`
- `HTTPException(detail=str(e))` vazando erro interno
- `response_model` ausente, devolvendo o objeto ORM inteiro
- Regra de negócio no router em vez de `app/services/` ou `app/utils/`
- Datas: armazenar em UTC (`datetime.now(UTC)`); prazo de SLA e dias úteis
  **sempre** via `app/utils/sla.py` (fuso `America/Sao_Paulo`), nunca
  aritmética de `timedelta` na mão
- Mudou model? Precisa de revisão Alembic junto — ver `help-migration-check`

**Contrato (a vantagem do monorepo)**
- Schema Pydantic mudou → o tipo no front (`src/types/`, interfaces nos
  services) muda **no mesmo commit/PR**. Não existe "repositório irmão" para
  sincronizar depois — divergência de contrato dentro de um PR é erro de
  revisão, não fatalidade
- Apontar arquivo e linha do lado que falta

**Segurança**
- Ver delegação. Nunca aprovar endpoint novo sem verificar autenticação e o
  filtro de escopo do perfil `client`

**Manutenibilidade**
- Segue o padrão do restante do projeto?
- Tem teste? Código novo no backend sem teste pode derrubar o gate de
  cobertura de 80% do CI (ver `help-test-review`)

### 4. O que o CI vai cobrar

Antes de aprovar, lembrar o que o `.github/workflows/ci.yml` roda:

- Back: `ruff check .`, `black --check .`, `pytest` (cobertura ≥ 80%)
- Front: `npm run lint`, `npm run typecheck` (`tsc -b` — **nunca**
  `tsc --noEmit`, que com o solution file termina verde sem checar nada),
  `npm test` (Vitest) e `npm run build`

Sugerir rodar localmente o que for relevante à mudança — o typecheck do front
já quebrou build por ter ficado sem rodar (commit `882662b`).

### 5. Formato da resposta

1. **Resumo geral** — 1 a 2 linhas
2. **Pontos críticos** — precisa corrigir
3. **Sugestões** — recomendado, não obrigatório
4. **Positivos** — o que está bem feito (não pular)

## Observações

- Direto, mas construtivo
- Sempre incluir exemplo de correção quando aplicável
- O CI valida, mas **não sobe nada**: o deploy é manual via EasyPanel, com
  front e back em serviços separados — dizer qual serviço precisa subir
- Não sugerir bibliotecas novas sem necessidade real; o front é
  deliberadamente enxuto (sem React Query, sem state manager externo)
