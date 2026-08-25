---
name: help-env-check
description: Verifica variáveis de ambiente do HelpHS — pydantic-settings no backend, VITE_ no frontend (build args do Docker) e os docker-compose de dev e staging. Usar antes de deploy, ao alterar backend/app/core/config.py, ou quando a aplicação sobe apontando para o ambiente errado.
---

# Skill: Env Check — HelpHS

## Objetivo

Garantir que as variáveis estejam corretas em cada ambiente, sem valor de
desenvolvimento vazando para produção e sem segredo exposto.

Toda variável do backend nasce em `backend/app/core/config.py`
(pydantic-settings). O `.env.example` da **raiz** documenta o conjunto
completo (backend + `VITE_*`); `frontend/.env.example` só as `VITE_*`.

## O mapa de risco

`DATABASE_URL` é obrigatória sempre, e **fora de dev/testing o boot também
barra** SECRET_KEY curta, CORS de dev e FRONTEND_URL de localhost
(`model_post_init` em `config.py` — staging incluído no lado severo). O que
resta perigoso é o que ainda **sobe errado em silêncio**:

| Variável | Default | Risco se esquecida em produção |
|---|---|---|
| `APP_ENV` | `development` | liga `/docs` e `/redoc` públicos |
| `CORS_ORIGINS` | `localhost` | front de produção bloqueado — ou dev liberado |
| `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` | vazio (usa `keys/*.pem`) | container sem os arquivos não sobe |
| `SECRET_KEY` | vazio | validada (≥ 32 chars) fora de dev/testing — **dev** sobe com chave fraca sem reclamar |
| `SEED_ADMIN_PASSWORD` | ausente | regra invertida: **em produção não deve existir** (a ausência impede o seed de criar admin com senha conhecida); em dev, sem ela o admin local não nasce |
| `UPLOAD_DIR` | `/app/uploads` | sem **volume** montado, anexos e avatares somem a cada redeploy |
| `FRONTEND_URL` | `localhost:5173` | links de e-mail (reset de senha, confirmação) apontam para localhost |
| `SMTP_*` | vazio | **sem SMTP, o cadastro libera acesso sem confirmar e-mail** (`requires_email_verification`) — é comportamento intencional, mas precisa ser decisão, não esquecimento |

## O que verificar

### 1. A pegadinha do `VITE_`

`VITE_API_URL` é **build arg** no `frontend/Dockerfile` — embutida no bundle
durante o `npm run build`, e o build **falha cedo** se ela vier vazia
(fail-fast proposital). `VITE_WS_URL`, `VITE_APP_NAME` e `VITE_APP_VERSION`
foram removidas: nada as lê (o WS deriva do `VITE_API_URL` em
`chatService.ts`):

- Trocar a variável no painel do EasyPanel **não muda nada** sem rebuild da
  imagem — tem que ser build arg, e rebuildar
- **Nunca segredo em `VITE_*`** — fica legível no navegador
- Conferir o valor que ficou de fato no bundle:
  `grep -o "https\?://[^\"']*" dist/assets/*.js | sort -u`
- Em dev existe `VITE_DEV_API_TARGET` (lida só pelo `vite.config.ts`): muda o
  alvo do proxy do dev server — apontada para outra API, o front local fala
  com ela sem CORS. Não entra no bundle; conferi-la quando "o dev aponta para
  o ambiente errado"
- Os `.dockerignore` de front e back **já excluem `.env`** ✅ — manter assim;
  é a proteção contra o `.env` local disputar com o build arg

### 2. Chaves JWT (RS256)

- Dev: arquivos em `keys/` (gerados com `openssl genrsa`, ver README) —
  `keys/` está no `.gitignore` ✅, conferir que nenhum `.pem` foi commitado
- Produção: conteúdo PEM direto em `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY`
  (aceita `\n` escapado — `config.py` converte)
- Trocar o par de chaves **invalida todas as sessões ativas** — avisar antes

### 3. Vazamento entre ambientes

- `APP_ENV=development` em produção → ❌
- `CORS_ORIGINS` com `localhost` em produção → ❌
- `DATABASE_URL` de produção em dev/staging → ❌ risco de escrever em dado real
- SMTP real apontado no **staging** → ❌ dispara e-mail de verdade para
  cliente; o staging tem **Mailpit** (`docker-compose.staging.yml`) exatamente
  para isso

### 4. Ambientes e portas (dev)

- `backend/docker-compose.dev.yml` sobe a infra completa + backend na **8000**
  (pgAdmin 5050, RedisInsight 5540, MinIO 9001, Mailpit 8025, ClamAV 3310)
- O proxy do Vite, o Playwright e o k6 apontam para a **8001** — porta do
  uvicorn rodado localmente, fora do Docker. Quando "a API não responde",
  conferir primeiro **qual das duas** deveria estar de pé
- `backend/docker-compose.staging.yml` sobe **só a infra** (Postgres, Redis,
  MinIO, ClamAV, Mailpit) — a aplicação conecta nela

### 5. Configuração morta ou enganosa

- `MINIO_*`: legado — o storage passou a ser disco (`UPLOAD_DIR`); não
  configurar ambiente novo com base nelas
- `RATE_LIMIT_LOGIN`: **aplicada** por `app/core/rate_limit.py` (slowapi,
  storage no Redis, desligada sob `APP_ENV=testing`) — deixou de ser config
  morta; ver `help-security-audit`

### 6. Consistência com o `.env.example`

- Variável nova em `config.py` e ausente do `.env.example` da raiz → ⚠️ não
  documentada
- Variável no `.env.example` que o `config.py` não lê → ℹ️ pode remover
- Placeholders `CHANGE_ME_*` são o padrão do projeto — segredo real no
  `.env.example` é 🔴

## Formato de saída

```
ENV CHECK — HelpHS
==================
✅ Presença: DATABASE_URL e chaves JWT definidas no serviço
❌ Vazamento: APP_ENV=development no serviço de produção — /docs público
⚠️  Volume: UPLOAD_DIR sem volume montado — anexos somem no próximo redeploy
⚠️  Front: VITE_API_URL mudou mas a imagem não foi rebuildada — bundle ainda com o valor antigo
ℹ️  Doc: SMTP_REPLY_TO usada no código e ausente do .env.example
```

## Observações

- **Nunca logar o valor** de uma variável — só presença/ausência
- Ao reportar segredo exposto, citar caminho e linha, nunca o valor
- Deploy é manual no EasyPanel: variável do back muda com restart;
  `VITE_*` muda **só com rebuild** da imagem do front
- Ver [[help-deploy-check]] para o checklist completo e
  [[help-security-audit]] para o impacto de cada segredo
