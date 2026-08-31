---
name: help-deploy-check
description: Checklist pré-deploy do HelpHS para EasyPanel + Docker — front (nginx) e back (FastAPI) em serviços separados, com migrations Alembic rodando sozinhas no boot. Usar antes de subir qualquer alteração para produção. Nunca executa o deploy.
---

# Skill: Deploy Check — HelpHS

## Objetivo

Rodar um checklist completo antes de subir para produção: código, ambiente,
banco, container e rollback.

> O deploy é **manual, feito pelo usuário, via EasyPanel** — front e back são
> serviços separados, cada um com sua imagem. O CI valida o código, mas
> **não sobe nada**. Nunca executar o deploy — apenas preparar e verificar.

## Infraestrutura

| | Front (`frontend/`) | Back (`backend/`) |
|---|---|---|
| Build | Node 20 alpine → `npm run build` | Python 3.13 slim, multi-stage |
| Runtime | nginx alpine (SPA fallback) | `start.sh`: **alembic upgrade head → seeds → uvicorn** (2 workers) |
| Porta | 80 | 8000 |
| Config | **build arg** `VITE_API_URL` (obrigatório — o build **falha** sem ele) | env vars em runtime (restart basta) |
| Healthcheck | não tem — validar abrindo a aplicação | `/health` no Dockerfile |
| Estado | — | volume em `/app/uploads` (anexos e avatares) |
| Usuário | — | `appuser` não-root ✅ |

## Sequência de verificação

### 1. Código e CI

- [ ] Branch correta e `git status` limpo
- [ ] **CI verde no commit que vai subir** (`ci.yml`: ruff, black, pytest com
      cobertura ≥ 80%, eslint, `tsc -b`, Vitest, build)
- [ ] O que o CI **não** cobre foi rodado se a mudança tocou no fluxo:
      `npm run e2e` (manual, ver `help-test-review`)
- [ ] Nenhum `console.log`/`print()` de debug esquecido

### 2. Variáveis de ambiente

> Executar `help-env-check` e incorporar o resultado aqui.

- [ ] `APP_ENV=production`, `CORS_ORIGINS` sem `localhost`
- [ ] Chaves JWT via `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` no serviço
- [ ] `FRONTEND_URL` com o domínio real (links dos e-mails dependem dele)
- [ ] `SEED_ADMIN_PASSWORD` **não** existe no serviço de produção — a
      ausência é o que impede o seed de criar admin com senha conhecida
- [ ] Mudou algo `VITE_*`? Então o front precisa de **rebuild**, não só restart

### 3. Banco de dados (o ponto de não-retorno)

A migration **roda sozinha** quando o container do back sobe (`start.sh`).
Não há passo manual — o que há é irreversibilidade:

> Executar `help-migration-check` para cada revision nova.

- [ ] Há revision nova? Testada com upgrade → downgrade → upgrade em
      local/staging?
- [ ] **Backup do banco antes de subir** — para migration destrutiva, é o
      único rollback de dado
- [ ] Migration quebrada = **API não sobe**; saber disso antes, não descobrir
      no healthcheck

### 4. Ordem de subida (dois serviços, um repositório)

O commit é um só, mas os serviços sobem separados — na janela entre um e
outro, os dois lados precisam conviver:

| Tipo de mudança | Ordem |
|---|---|
| Campo/endpoint novo na API (aditivo) | back → front |
| Campo removido ou renomeado no contrato | front → back |
| Só visual no front | front |
| **Mudança de autenticação/token** | **front primeiro** ⚠️ (senão o usuário logado é expulso sem saber renovar) |

- [ ] A ordem foi decidida? Se o back subir primeiro, o front no ar continua
      funcionando?

### 5. Container

- [ ] Imagem buildada do commit certo
- [ ] Back: `/health` respondendo e log de boot limpo — o log mostra as etapas
      do `start.sh` (migrations → seeds → uvicorn); erro em qualquer uma
      derruba o serviço. A **recusa do `seed_admin`** em produção é esperada
      no log — comportamento certo, não erro
- [ ] **Volume de `/app/uploads` montado** — sem ele os anexos somem no
      próximo redeploy
- [ ] Front: bundle com a URL certa
      (`grep -o "https\?://[^\"']*" dist/assets/*.js | sort -u`)

### 6. Verificação pós-deploy (smoke test)

- [ ] `GET /health` → 200 `{"status": "ok"}` (liveness: só diz que o
      processo subiu, não confere dependência nenhuma)
- [ ] `GET /api/v1/health` → 200 e `status: ok` (readiness: confere banco e
      Redis; **503 com `status: degraded`** se alguma faltar). Confira o
      `env` e o `auto_close.last_success` — `null` é o normal no primeiro
      minuto de cada worker, mas continuar `null` depois disso quer dizer
      que a rotina do RN-005 não está concluindo rodada. **Não** espere
      versão aqui: desde o `dcfc25f` ela não é exposta a **ninguém**. O
      `__version__` só alimenta o spec OpenAPI, e o spec está fechado em
      produção — `/openapi.json` e `/docs` respondem 404. Para saber qual
      commit está no ar, a fonte é o EasyPanel.
- [ ] Login funciona; rota protegida **sem** token → `401`
- [ ] Listagem de chamados carrega
- [ ] **Abrir um anexo existente** — prova que o volume sobreviveu ao deploy
- [ ] Abrir chamado de teste → notificação aparece
- [ ] Se mexeu em e-mail: disparar um reset de senha e conferir a chegada

### 7. Rollback

- [ ] Sabe qual imagem/commit anterior restaurar em cada serviço?
- [ ] Se subiu migration: o `downgrade` existe, mas dado apagado só volta com
      o **backup** do item 3
- [ ] Alguém usando o sistema agora? O restart do back derruba as requisições
      em voo — e o boot roda migration + seeds antes de aceitar tráfego

## Formato de resposta

Para cada seção: ✅ OK · ⚠️ Atenção — [detalhe] · ❌ Bloqueante — [não suba até resolver]

## Observações

- **Nunca executar o deploy** — quem sobe é o usuário, pelo EasyPanel
- Qualquer ❌ bloqueia o deploy
- Se front e back mudam juntos, dizer explicitamente a **ordem** e o motivo
- Ver [[help-env-check]], [[help-migration-check]] e, depois de subir,
  considerar o ZAP (`.github/workflows/zap-scan.yml`) se a superfície da API
  mudou
