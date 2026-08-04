# Ajustes do feedback do cliente — HelpHS v1.0.0

**Data:** 04/08/2026
**Origem:** rodada de testes do cliente sobre a v1.0.0

Sete frentes de trabalho, independentes entre si. Cada uma pode ser implementada,
revisada e entregue isoladamente.

---

## Frente 1 — Técnico pode excluir comentários da Base de Conhecimento

**Problema:** só admin exclui comentário de terceiro. Técnico que modera a KB não
consegue remover comentário inadequado de cliente.

**Backend** — `backend/app/routers/kb.py`, `delete_comment`:

A regra atual é `is_admin or is_own`. Passa a ser:

```python
is_privileged = actor.role in (UserRole.admin, UserRole.technician)
is_own = comment.author_id == actor.id
if not is_privileged and not is_own:
    raise HTTPException(403, detail="Você não tem permissão para excluir este comentário.")
```

Quando o comentário tem respostas aninhadas, elas são excluídas junto (a relação
já é `cascade`). A exclusão continua sendo permanente.

**Frontend** — `frontend/src/pages/kb/KBArticlePage.tsx`: o botão de excluir passa
a aparecer quando `role === "admin" || role === "technician" || comentário é do usuário`.

**Teste:** técnico exclui comentário de cliente (204); cliente tenta excluir
comentário de outro cliente (403 com a mensagem em português).

---

## Frente 2 — Agenda: paleta fixa de 15 cores e remoção da legenda

**Problema:** o seletor de cor livre (`<input type="color">`) gera cores fora do
padrão visual. O cliente quer escolher entre cores prontas. A legenda de tipos no
rodapé do calendário deve sair.

**Arquivo:** `frontend/src/pages/calendar/CalendarPage.tsx`

1. Nova constante `EVENT_COLOR_PALETTE` com 15 cores, incluindo as 5 já usadas por
   tipo de evento (`#6366f1`, `#3b82f6`, `#10b981`, `#f59e0b`, `#ef4444`) mais 10
   tons complementares da mesma família Tailwind.
2. O campo "Cor" do modal vira uma grade 5×3 de botões quadrados. O selecionado
   recebe anel de destaque e `aria-pressed`. Cada botão tem `aria-label` com o nome
   da cor.
3. O comportamento de `colorOverride` é preservado: trocar o tipo do evento
   atualiza a cor sugerida até o usuário escolher uma manualmente.
4. Remover o bloco de legenda no rodapé do calendário. O tipo do evento continua
   visível na lista "Próximos eventos".

**Compatibilidade:** eventos já salvos com cor fora da paleta continuam
renderizando com a cor gravada. Ao editar, nenhum swatch aparece selecionado até
que o usuário escolha um.

---

## Frente 3 — Varredura ortográfica

**Escopo:** todo texto em português exibido ao usuário — páginas e componentes do
frontend, mensagens de erro e de e-mail do backend, textos de notificação, títulos
de coluna, placeholders e labels. Fora do escopo: comentários de código, nomes de
variável e docstrings.

**Erros já identificados** — pluralização concatenada errado:

| Arquivo | Linha | Renderiza |
|---|---|---|
| `frontend/src/pages/reports/ReportsPage.tsx` | 745 | `violaçãoões` |
| `frontend/src/pages/reports/ReportsPage.tsx` | 478 | `avaliaçãoões` |
| `frontend/src/pages/reports/ReportsPage.tsx` | 749 | `avaliaçãoões` |
| `frontend/src/pages/kb/KBArticlePage.tsx` | 394 | `visualizaçãoões` |

O padrão `` `${n} violação${n !== 1 ? "ões" : ""}` `` concatena em vez de trocar a
terminação. Correção: escolher a palavra inteira — `` `${n} ${n === 1 ? "violação" : "violações"}` ``.

Para evitar a repetição do erro, criar em `frontend/src/lib/utils.ts`:

```ts
export function plural(n: number, singular: string, plural: string): string
```

**Entrega:** ao final, uma lista de todas as correções aplicadas (arquivo, texto
antes, texto depois) para conferência.

---

## Frente 4 — Mensagens de erro descritivas

**Problema:** o cliente recebeu "Não foi possível atribuir o ticket." sem saber o
motivo. Trata-se do texto de fallback — o backend devolveu um `detail` genérico
(ou em inglês, ou nenhum).

### 4a. Backend — `detail` explicativo em português

Revisar os `raise HTTPException` dos routers e substituir mensagens genéricas por
mensagens que digam o motivo e o caminho de solução. Exemplos:

| Antes | Depois |
|---|---|
| `"Access denied"` | `"Apenas o técnico responsável pelo ticket pode alterá-lo."` |
| `"Assignee not found"` | `"O técnico selecionado não existe mais no sistema."` |
| `"Ticket not found"` | `"Ticket não encontrado. Ele pode ter sido excluído."` |

### 4b. Frontend — `getApiError` mais robusto

`frontend/src/lib/apiError.ts` hoje lê apenas `response.data.detail` como string.
Passa a tratar:

- `detail` como lista (erro de validação do FastAPI) — hoje renderizaria
  `[object Object]`. Extrair `msg` do primeiro item e o campo em `loc`.
- ausência de `response` (rede caiu, backend fora do ar, timeout) —
  "Não foi possível falar com o servidor. Verifique sua conexão."
- HTTP 500 sem `detail` — "Erro interno no servidor. Tente novamente em instantes."
- HTTP 403/404/409 sem `detail` — mensagens padrão por status.

Nova função `getApiErrorParts(err, fallback): { title, description }` para que o
toast mostre título curto + motivo detalhado (`toast.error(title, { description })`,
suportado pelo `sonner` já em uso).

### 4c. Causa raiz do erro de reatribuição

`backend/app/routers/tickets.py`, `assign_ticket` — o endpoint hoje:

- não valida se o usuário destino é técnico ou admin (é possível atribuir a um cliente);
- não bloqueia atribuição em ticket `closed`/`cancelled`;
- chama `_auto_transition` e `notify`, que podem falhar e devolver 500 sem `detail`.

Reproduzir o cenário do print (reatribuir um ticket com SLA) antes de corrigir,
seguindo depuração sistemática — a hipótese acima precisa ser confirmada, não
presumida. Ao corrigir, adicionar as validações com mensagens explicativas.

---

## Frente 5 — Respostas rápidas no chat + página de gestão

**Objetivo:** o técnico digita `/` no chat do ticket e escolhe uma mensagem pronta,
como no WhatsApp Business. As mensagens são **globais** (uma lista só para toda a
equipe) e gerenciadas por **admin e técnico**.

### Banco

Nova tabela `quick_replies`:

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | UUID | PK |
| `shortcut` | String(50) | único, minúsculo, sem espaço — o que vem depois da `/` |
| `title` | String(120) | rótulo exibido na lista |
| `content` | Text | o texto inserido no chat |
| `is_active` | Boolean | default `true`; inativa não aparece no chat |
| `created_by` | UUID | FK `users.id` |
| `created_at` / `updated_at` | timestamptz | |

Migration Alembic nova em `backend/alembic/versions/`.

### API — `backend/app/routers/quick_replies.py`

Mesmo padrão de `tags.py`:

| Rota | Permissão |
|---|---|
| `GET /quick-replies` | admin, technician |
| `POST /quick-replies` | admin, technician |
| `PATCH /quick-replies/{id}` | admin, technician |
| `DELETE /quick-replies/{id}` | admin, technician |

`shortcut` duplicado devolve 409 com mensagem explicativa. Registrar no router em
`main.py`.

### Chat — `frontend/src/components/chat/ChatPanel.tsx`

- Ao digitar `/` como primeiro caractere da mensagem, abre um painel acima do input
  com a lista de respostas ativas.
- Continuar digitando filtra por `shortcut` e por `title` (`/bomdia`).
- `↑`/`↓` navegam, `Enter` ou clique insere o `content` no input (substituindo o
  comando digitado), `Esc` fecha. `Enter` com o painel aberto **não** envia mensagem.
- Visível apenas para admin e técnico. Cliente digitando `/` não vê nada.
- As respostas são carregadas uma vez ao montar o painel e ficam em memória.

### Gestão — nova página

- Rota `/respostas-rapidas`, com `RoleGuard roles={["admin", "technician"]}`.
- Item "Respostas Rápidas" no grupo **Gestão** da sidebar.
- Tabela com atalho, título, prévia do conteúdo e status; modal de criar/editar;
  confirmação para excluir. Segue o padrão visual da página de Etiquetas.
- Serviço `frontend/src/services/quickReplyService.ts`.

### Fora de escopo

Variáveis dinâmicas (`{{nome_do_cliente}}`), anexos nas respostas, respostas
pessoais por técnico e categorias/pastas. Ficam para uma rodada futura.

---

## Frente 6 — CNPJ e CEP obrigatórios no cadastro do cliente

**Onboarding** (`frontend/src/pages/onboarding/OnboardingPage.tsx`) — CNPJ e CEP
deixam de ser opcionais:

- CNPJ: 14 dígitos **com validação de dígito verificador**. Formato inválido
  bloqueia o envio com mensagem no campo.
- CEP: 8 dígitos.
- O preenchimento automático já existente (`/auth/cnpj/{cnpj}` e busca de CEP)
  continua funcionando; falha na consulta externa não impede o cadastro manual.

**Backend** (`backend/app/schemas/user.py`, `OnboardingUpdate`) — `cnpj` e
`company_cep` passam a ser obrigatórios, com validador de formato, para que a
regra não seja contornável pela API. Mensagens de erro em português.

**Clientes já cadastrados:** não são bloqueados. Quem tiver `cnpj` ou
`company_cep` vazio vê um aviso no topo do perfil pedindo para completar o
cadastro. Ao salvar o perfil, se o usuário preencher um dos campos, valem as
mesmas validações de formato.

**Migration:** nenhuma. As colunas continuam `nullable` no banco por causa dos
registros existentes; a obrigatoriedade é de aplicação.

---

## Frente 7 — Unificar a escala CSAT em 1–10

**Problema:** o cliente avalia de 1 a 10, mas o resto do sistema assume 1 a 5.
Daí o card "Média CSAT — 10 / 5" do print. Pior: avaliações de 6 a 10 desaparecem
do gráfico de distribuição.

**Estado atual, inconsistente:**

| Local | Escala assumida |
|---|---|
| `TicketDetailPage.tsx` — `ScoreRating` | 1–10 (coleta real) |
| `backend/app/schemas/survey.py` — `SurveyCreate` | 1–10 |
| `backend/app/models/models.py` — comentário | "1 a 5" |
| `backend/app/routers/surveys.py` — filtro `rating` | `le=5` |
| `backend/app/routers/dashboard.py` — `csat_distribution` | `range(1, 6)` |
| `ReportsPage.tsx` / `AdminDashboard.tsx` / `TechnicianDashboard.tsx` | `x / 5` |
| `ReportsPage.tsx` — `CSAT_COLORS` | 5 cores |

**Decisão:** padronizar em **1–10**, preservando todas as avaliações já feitas.

**Mudanças:**

- `dashboard.py`: `range(1, 11)` na distribuição.
- `surveys.py`: filtro `rating` com `le=10`.
- `models.py`: corrigir o comentário para "1 a 10".
- Frontend: `x / 10` nos cards; `CSAT_COLORS` com 10 cores em gradiente
  vermelho → verde; rótulo do gráfico "Distribuição CSAT (1–10)"; tooltips e
  eixos coerentes.
- Exportações CSV e PDF em `dashboard.py`: rótulos e faixas.

**Teste:** avaliação com nota 8 aparece no gráfico de distribuição, entra na média
e é exportada corretamente.

---

## Ordem de implementação

1. Frente 3 (ortografia) e Frente 7 (CSAT) — rápidas e imediatamente visíveis
2. Frente 1 (KB), Frente 2 (Agenda), Frente 6 (CNPJ/CEP)
3. Frente 4 (mensagens de erro, com a depuração da reatribuição)
4. Frente 5 (respostas rápidas) — única que mexe no banco

## Verificação

Cada frente entrega com `npm run lint`, `npm run build` e `npm test` passando no
frontend, e `pytest` no backend quando houver mudança lá. As frentes 1, 5, 6 e 7
ganham teste automatizado da regra nova. O changelog em
`frontend/src/data/changelog.ts` recebe uma entrada de versão nova ao final do
pacote.
