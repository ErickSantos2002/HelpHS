---
name: help-refactor
description: Propõe refatorações no HelpHS (React/TypeScript em frontend/ e FastAPI/Python em backend/) com foco em legibilidade e manutenção. Usar em código que funciona mas é difícil de entender, ou antes de adicionar feature sobre código problemático. Nunca altera sem aprovação.
---

# Skill: Refactor — HelpHS

## Objetivo

Identificar e propor melhorias estruturais sem alterar comportamento externo.
Mais fácil de ler, testar e manter — não apenas mais "elegante".

## Princípio fundamental

> Refatoração sem teste é apenas reorganizar o risco.

Este projeto **tem** suíte (ver `help-test-review`) — então o primeiro passo
de qualquer proposta é **conferir se o alvo está coberto**, não assumir:

1. Alvo coberto por pytest/Vitest → refatorar com a rede existente; o gate de
   80% do CI segura regressão de cobertura no back
2. Alvo sem teste (páginas inteiras do front ficam fora da cobertura por
   decisão) → escrever teste de caracterização antes, ou fatiar em passos
   pequenos e verificáveis, um commit por passo
3. **Atenção ao ponto cego**: o pytest mocka o banco — refatoração que mexe em
   query real (joins, `selectinload`) não é protegida pela suíte; validar
   manualmente ou via e2e

Nunca propor refatoração grande e sem rede em SLA (`app/utils/sla.py`),
ciclo de encerramento (`app/services/ticket_lifecycle.py`) ou autenticação
(`app/core/security.py`) — é onde mora a regra sutil.

## Alvos conhecidos

Os maiores arquivos, concentrando tela + estado + lógica:

| Arquivo | Linhas |
|---|---|
| `frontend/src/pages/tickets/TicketDetailPage.tsx` | ~1690 |
| `frontend/src/pages/groups/GroupsPage.tsx` | ~1230 |
| `frontend/src/pages/reports/ReportsPage.tsx` | ~1130 |
| `backend/app/routers/tickets.py` | ~1100 |
| `backend/app/routers/dashboard.py` | ~1030 |
| `backend/app/models/models.py` | ~820 (arquivo único, por decisão) |

Não são urgentes. Valem refatoração **quando já houver motivo para mexer
neles** — não como projeto isolado.

## O que analisar

### Camadas
- Regra de negócio dentro do router em vez de `app/services/`/`app/utils/`
  (`tickets.py` mistura transporte, histórico, SLA e notificação — o precedente
  bom é `ticket_lifecycle.py`, que extraiu o encerramento)
- Componente chamando `api` direto em vez do service de `src/services/`
- Página lendo `localStorage` direto em vez de usar `AuthContext`/`tokenStorage`

### Duplicação
- Bloco de escrita de histórico/auditoria repetido entre endpoints
- Validação "existe?" repetida — `get_or_404` de `app/utils/crud.py` já existe,
  usar
- Formatação de status/prioridade/data copiada entre telas — candidata a
  `src/lib/` (padrão: `ticketConstants.ts`, `colors.ts`)
- Modais de cadastro com a mesma estrutura entre páginas

### Complexidade
- Componente acumulando muitos `useState` — sinal de `useReducer` ou de
  extrair sub-componente com estado próprio
- Função com mais de ~30 linhas fazendo mais de uma coisa
- Condicional aninhada além de 3 níveis; JSX com regra de negócio no markup
- Endpoint com muitos parâmetros de query — a listagem de tickets já tem 9;
  crescer mais pede objeto de filtro
- Query dentro de loop (N+1) — quase sempre vira `selectinload` ou `IN`

### Nomenclatura
- Variável `data`, `result`, `temp`, `item` sem contexto
- Identificadores em inglês, textos de UI em português — mistura no mesmo
  nível é fuga do padrão (ver `help-code-review`)
- Booleano sem prefixo `is/has/can/should`

### Específico deste projeto
- `datetime.now()` sem `UTC`, ou aritmética de prazo fora de `app/utils/sla.py`
- Cor crua em vez de token semântico do Tailwind, ou sem variante `dark:`
- Formulário montado à mão em vez de react-hook-form + zod
- `except Exception` genérico escondendo erro real

## Formato de resposta

```
📍 frontend/src/pages/tickets/TicketDetailPage.tsx — bloco do chat + pesquisa (≈400 linhas)
🔍 Problema: fetch, estado local, permissões e render misturados no mesmo componente
💡 Sugestão: extrair <TicketSurveyCard /> com estado próprio; ChatPanel já existe como precedente
⚠️  Pré-requisito: página fora da cobertura do Vitest — fatiar em 3 commits verificáveis
📊 Impacto: alto (arquivo mais alterado do front)
```

Ao final, perguntar: **"Por qual quer começar?"**

## Regras

- **Nunca alterar código diretamente** — propor, explicar, aguardar aprovação
- Priorizar por impacto: complexidade alta em código frequentemente alterado
- Nada por gosto estético — todo item precisa de justificativa objetiva
- Refatoração que muda schema Pydantic **muda o contrato**: front acompanha no
  mesmo PR (ver `help-endpoint-review`)
- Refatoração que renomeia coluna/model exige migration Alembic pensada
  (rename, não drop+add) — ver `help-migration-check`
- Usar o contexto da sessão para não repropor o que já foi descartado
