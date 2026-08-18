---
name: help-security-audit
description: Auditoria de segurança do HelpHS — FastAPI/PostgreSQL no backend/ e React/Vite no frontend/, no mesmo repositório. Usar ao mexer em autenticação, criar router ou endpoint novo, alterar CORS/config/upload, mexer na renderização de markdown da KB, ou quando o usuário pedir auditoria. Também acionada pela help-code-review em arquivos críticos.
---

# Skill: Security Audit — HelpHS

## Objetivo

Encontrar vulnerabilidades antes que cheguem à produção. O HelpHS guarda trilha
de auditoria (`AuditLog` com IP e user-agent) e tem obrigações de **LGPD**
(consentimento e anonimização de usuário) — vazamento de dado pessoal ou
autoria falsificável aqui não é só bug, é incidente.

## Contexto do sistema

Monorepo — front e back no **mesmo repositório**, sob `frontend/` e `backend/`:

| | `backend/` | `frontend/` |
|---|---|---|
| Stack | FastAPI, SQLAlchemy 2.0 **async** (asyncpg), Pydantic 2 | React 19, Vite 6, TypeScript, Axios |
| Infra | PostgreSQL 15, Redis 7, ClamAV, SMTP, LLM (OpenAI + Anthropic) | Tailwind, token no `localStorage` |
| Auth | JWT **RS256** (par de chaves), refresh + blacklist no Redis | interceptor com refresh em `src/services/api.ts` |
| Deploy | EasyPanel, serviço próprio | EasyPanel, serviço próprio |

CI no GitHub Actions (`.github/workflows/ci.yml`) roda lint e pytest, mas
**o deploy continua sendo decisão manual** — achado corrigido só vale depois
que o serviço for subido no EasyPanel.

> ⚠️ Não aplicar checagens de Node/Express/MongoDB no back — não é a stack.
> E não confundir com o ChamadosHS: aqui **não há trava de rotas** no startup
> e o JWT é RS256 com par de chaves, não HS256 com `SECRET_KEY`.

## O ponto fraco estrutural: não há trava de rotas

Cada endpoint declara a própria proteção via `Depends(get_current_user)` ou
`authorize(...)` de `backend/app/core/security.py`. O `main.py` registra os
routers **sem** `dependencies=` — um endpoint esquecido **sobe aberto em
silêncio**, sem erro de inicialização. Por isso a varredura de superfície
(seção abaixo) é obrigatória em toda auditoria.

Rotas públicas por design: `/health`, `/api/v1/health` e, em
`backend/app/routers/auth.py`: login, register, refresh, recuperação de senha
e confirmação de e-mail. Qualquer outra rota respondendo sem token é 🔴.

## Categorias de análise

### 1. Autenticação e autorização

- **Endpoint sem `Depends(get_current_user)`** — ver ponto fraco acima.
- **Operação administrativa** sem `authorize(UserRole.admin, ...)` ou
  `require_admin()`. Esconder o botão no React não é controle de acesso.
- **Identidade vinda do cliente**: autoria tem que sair de `current_user`,
  nunca de `?user_id=` ou do body. Com `AuditLog` no sistema, autoria
  falsificável é 🔴.
- **Escopo do perfil `client`**: cliente só vê os próprios tickets (regra
  documentada no topo de `backend/app/routers/tickets.py`). Toda listagem ou
  consulta nova sobre tickets/anexos/notas precisa repetir esse filtro — o
  vazamento clássico aqui é endpoint novo devolvendo dado de outro cliente.
- **Rate limiting**: `RATE_LIMIT_LOGIN` existe em `app/core/config.py` mas
  **nada no código aplica** (não há slowapi/Limiter em uso). Brute force no
  `/auth/login` está livre — gap conhecido 🟠, reavaliar a cada auditoria.
- **Enumeração**: `/auth/register` devolve `409` "e-mail já cadastrado" —
  permite enumerar contas. Combinado com a ausência de rate limiting, sobe
  de severidade.

### 2. Chaves e segredos

- Par RS256: `keys/` está no `.gitignore` ✅ — mesmo assim, conferir que
  nenhum `.pem` foi commitado. Em produção a chave entra por variável
  (`JWT_PRIVATE_KEY`, conteúdo PEM). **Vazou a chave privada = qualquer token
  pode ser forjado.**
- `SECRET_KEY` mínimo de 32 chars só é validado quando `APP_ENV=production`
  (`config.py`, `model_post_init`) — staging e dev sobem com chave fraca sem
  reclamar.
- API keys de LLM e senha de SMTP: só no ambiente, nunca no código.

### 3. Injeção e XSS

- **SQL**: queries via ORM são parametrizadas. `text()` hoje só aparece com
  literal fixo (`date_trunc` em `app/routers/dashboard.py`) — o perigo é
  f-string ou concatenação com input do usuário dentro de `text()`.
- **XSS via markdown (o ponto quente do front)**: `KBArticlePage.tsx` e
  `KBFormPage.tsx` injetam `marked.parse(...)` com `dangerouslySetInnerHTML`
  **sem sanitização** — o `marked` não remove HTML embutido no markdown.
  Qualquer mudança na KB (artigos, comentários) passa por avaliar quem pode
  escrever o conteúdo e se ele é sanitizado (ex.: DOMPurify) antes de renderizar.
- **Upload**: extensão validada contra allowlist, tamanho máximo e ClamAV
  (`app/routers/attachments.py`, `app/services/antivirus.py`). Nome de arquivo
  do usuário nunca vira caminho no disco diretamente — conferir em mudança no
  `storage.py`.

### 4. Exposição de dados

- `response_model` ausente devolve o objeto ORM inteiro — conferir se
  `password` ou campo interno vaza no schema de resposta.
- `/docs` e `/redoc` já ficam desligados fora de `development`
  (`main.py`) — não reverter isso.
- `HTTPException(detail=str(e))` vazando erro interno — os handlers globais
  estão em `app/core/exceptions.py`, mas o vazamento pontual em router
  continua possível.
- Log (loguru) com payload de dado pessoal — o `AuditLog` já guarda IP e
  user-agent de forma controlada; não duplicar isso em log comum.
- **LGPD**: existe ação de anonimização na trilha de auditoria — mudança em
  usuários/exclusão precisa preservá-la, não contorná-la.

### 5. Integrações externas

- `/auth/cnpj` e `/auth/cep` chamam BrasilAPI/ViaCEP com input do usuário —
  hoje o input é reduzido a dígitos e há timeout; manter esse padrão.
- `classify_ticket` (`app/services/llm.py`) envia o texto do chamado para
  OpenAI/Anthropic — **dado do cliente saindo do sistema**. Falha ou timeout
  do LLM não pode derrubar a criação do chamado.
- E-mails de reset/confirmação: validade dos tokens vem de `config.py`
  (`PASSWORD_RESET_TOKEN_HOURS=1`) — não aumentar sem motivo.

### 6. Configuração

- `CORS_ORIGINS` tem padrão `localhost` — em produção, se a variável não for
  definida, **sobe com valor de dev em silêncio**. E `allow_credentials=True`
  com `"*"` nunca.
- `APP_ENV=development` em produção liga o `/docs` público — conferir.
- **CORS não é proteção de API** — `curl` ignora. Nunca tratar como controle
  de acesso.

### 7. Front-end

- **Segredo em `VITE_*`**: embutido no bundle no build, legível no navegador.
  🔴 se houver token ou chave.
- Tokens em `localStorage` (`helphs_access_token` / `helphs_refresh_token`,
  em `src/services/api.ts`): vulnerável a XSS. Com o ponto do markdown da
  seção 3, esse é o encadeamento mais provável do sistema — XSS na KB →
  roubo de token. `httpOnly cookie` é mudança de arquitetura: 🔵 enquanto não
  houver XSS real, 🔴 se houver.
- Regra de permissão só no front, sem contrapartida no back.

### 8. Dependências e ferramentas já disponíveis

- Back: `pip-audit` (**não** `npm audit`). Front: `npm audit` — esse sim.
- **CodeQL** já roda no CI (`.github/workflows/codeql.yml`) — conferir alertas
  abertos antes de declarar a auditoria limpa.
- **OWASP ZAP** DAST manual (`.github/workflows/zap-scan.yml`) contra ambiente
  vivo — sugerir rodar após mudança grande de superfície da API.

## Procedimento: varredura de superfície

Sem trava de rotas, este é o único teste objetivo de "a API está protegida?":

1. Baixar a superfície: `GET /openapi.json`
2. Chamar cada rota **sem** header `Authorization`
3. Esperado: `401` em tudo, exceto as rotas públicas listadas acima

Qualquer rota devolvendo `200` sem token é 🔴. Só leitura — pode rodar contra
qualquer ambiente. Complementar com `pytest backend/tests/test_rbac.py
backend/tests/test_auth.py`, que cobrem parte disso no nível de código.

## Severidade

- 🔴 **Crítico** — exploração direta, autenticação ausente, dado pessoal exposto, auditoria falsificável
- 🟠 **Alto** — requer encadeamento mas tem impacto real
- 🟡 **Médio** — configuração ruim, boa prática violada
- 🔵 **Informativo** — sugestão de hardening

## Formato de saída

```
SECURITY AUDIT — HelpHS
=======================
🔴 CRÍTICO: GET /api/v1/reports responde 200 sem token — backend/app/routers/reports.py:41
   → adicionar Depends(get_current_user) no endpoint
🔴 CRÍTICO: listagem nova de anexos não filtra por dono — client vê arquivo de outro cliente
   → backend/app/routers/attachments.py — repetir o filtro de escopo de tickets.py
🟠 ALTO: sem rate limiting em /auth/login — config existe, nada aplica
🟡 MÉDIO: CORS_ORIGINS não definido no serviço de produção — subiu com localhost
🔵 INFO: markdown da KB sem sanitização — avaliar DOMPurify antes de abrir escrita a mais perfis
```

## Observações

- **Não corrija automaticamente** — liste, explique, decisão é do usuário
- Para cada 🔴, incluir o trecho de código da correção
- Nunca imprimir valor de secret ou conteúdo de chave no relatório, só o caminho
- Monorepo: front e back mudam no **mesmo commit/PR** — não há "repositório
  irmão" para sincronizar, mas os serviços no EasyPanel sobem separados; dizer
  qual precisa subir
- Ver [[help-code-review]] para revisão geral, [[help-env-check]] para
  variáveis de ambiente e [[help-test-review]] para cobrir o achado com teste
