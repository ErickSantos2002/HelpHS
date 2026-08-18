---
name: help-endpoint-review
description: Revisão de endpoints FastAPI do HelpHS — contrato Pydantic, status codes, autenticação, escopo por perfil, paginação, N+1 e sincronia com os services do frontend. Usar ao criar ou alterar endpoint em backend/app/routers/, ou quando front e back divergem no contrato.
---

# Skill: Endpoint Review — HelpHS

## Objetivo

Revisar endpoints verificando design, segurança e **consistência com o que o
front consome**. Como é monorepo, contrato divergente não é fatalidade de
sincronização — é erro dentro do próprio PR, e dá para pegar na revisão.

## Contexto

- Routers por recurso em `backend/app/routers/`, registrados em `main.py` sob
  `/api/v1` (`settings.api_prefix`)
- Contratos em `backend/app/schemas/` (Pydantic), models em
  `backend/app/models/models.py` (arquivo único)
- Regra de negócio em `backend/app/services/` e `backend/app/utils/` (SLA,
  ciclo de vida do ticket, protocolo `HS-AAAA-NNNN`)
- Consumidor: os services de `frontend/src/services/*Service.ts`, um por recurso
- OpenAPI em `/openapi.json` (`/docs` só em development)

## O que analisar

### 1. Autenticação e escopo (bloqueante)

**Não há trava de startup** — cada endpoint declara a própria proteção:

- Todo endpoint tem `Depends(get_current_user)` (direto ou via `authorize`)?
  Endpoint esquecido sobe aberto em silêncio — ver `help-security-audit`
- Operação administrativa usa `authorize(UserRole.admin, ...)` /
  `require_admin()`
- **Escopo do `client`**: cliente só acessa os próprios tickets/anexos/notas.
  O padrão está em `app/routers/tickets.py` — endpoint novo sobre recurso do
  cliente repete o filtro, senão vaza dado entre clientes
- Autoria vem de `current_user`, **nunca** de `?user_id=` ou do body — o
  `AuditLog` depende disso

### 2. Alinhamento com o front

Ao alterar um endpoint, abrir o service correspondente no front **no mesmo PR**:

- A interface TypeScript do service bate campo a campo com o schema Pydantic?
- Campo `| None` no back está `?`/`| null` no TS?
- **Listagens devolvem envelope** — `items` + `total` + `limit` (ver
  `TicketListResponse` em `app/schemas/ticket.py`). Endpoint novo de listagem
  segue esse formato, não array puro
- Não há versionamento além do `/v1`: mudança de campo é breaking na prática,
  mas como o front muda junto no monorepo, o custo real é **lembrar dos dois
  lados no mesmo commit**

### 3. Design e nomenclatura

- Recurso no plural, em inglês: `/tickets`, `/users`, `/quick-replies` ✅
- Verbos:
  - `GET` leitura sem efeito colateral
  - `POST` criação e ação (`/tickets/{id}/reopen`)
  - `PATCH` atualização parcial e mudança de estado
    (`/tickets/{id}/status`, `/{id}/assign`)
  - `DELETE` remoção — em tickets é **cancelamento**, não apaga o registro
- Ação de estado como sub-recurso é o padrão do projeto — manter consistente

### 4. Status codes

| Código | Quando |
|---|---|
| `200` | sucesso com body |
| `201` | criação — `status_code=status.HTTP_201_CREATED` (padrão já seguido em `/auth/register`) |
| `204` | sucesso sem body |
| `400` | erro de requisição |
| `401` | não autenticado |
| `403` | autenticado sem permissão (perfil errado, conta inativa) |
| `404` | não encontrado — usar `get_or_404` de `app/utils/crud.py` |
| `409` | conflito — **já em uso**: e-mail duplicado no cadastro |
| `422` | validação Pydantic (automático) |

No `409`, o `detail` deve dizer **por quê**, em português, pronto para o front
exibir — as mensagens de erro deste projeto são voltadas ao usuário final.

### 5. Paginação

O padrão do projeto é `offset`/`limit` com teto declarado no `Query`
(`le=500` na listagem de tickets, `le=200` no histórico) e o total no
envelope de resposta.

- Endpoint novo que pode crescer tem `offset`/`limit` com `ge`/`le`?
- O teto faz sentido para o volume esperado?
- O front pagina usando `total`, ou assume que veio tudo?

### 6. Performance

- **N+1**: listagem que acessa relacionamento (`ticket.creator`,
  `.assignee`, `.tags`, `.equipments`) sem `selectinload` dispara uma query
  por registro — com `limit=500`, são milhares. O padrão do projeto é
  `selectinload` (ver `list_tickets` em `tickets.py`)
- `await` esquecido em query — SQLAlchemy async falha silenciosamente
- Campo pesado (`description`, corpo de artigo da KB) devolvido em listagem
  que só monta card
- Verificação de SLA/breach por item dentro de loop de listagem

## Formato de resposta

```
ENDPOINT REVIEW — POST /api/v1/tickets/
=======================================
✅ Autenticação: Depends(get_current_user)
✅ Autoria: creator_id sai de current_user.id
❌ Escopo: GET novo não filtra por creator quando role=client — vaza ticket de outro cliente
❌ Status code: retorna 200 na criação — deveria ser 201
⚠️  Contrato: `equipment_ids` é lista aqui, mas ticketService.ts ainda manda `equipment_id`
💡 Performance: sem selectinload em tags — N+1 na listagem
🔗 Front: frontend/src/services/ticketService.ts precisa mudar no mesmo PR
```

## Observações

- Revisar **todos os endpoints do mesmo recurso juntos** — inconsistência
  entre irmãos é o defeito mais comum
- Toda mudança de contrato deve listar o que muda no front, arquivo e linha —
  e conferir se o teste do service (`src/test/services/`) acompanhou
- Endpoint novo sem teste em `backend/tests/` pode derrubar o gate de 80% de
  cobertura do CI — ver `help-test-review`
- Deploy é manual via EasyPanel: mudança de contrato exige subir **os dois
  serviços**, back primeiro em mudança aditiva
