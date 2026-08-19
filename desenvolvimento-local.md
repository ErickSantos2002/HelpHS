# Desenvolvimento local — HelpHS

Como subir o sistema inteiro na sua máquina (`http://localhost:5173`).
Registrado em 19/08/2026 a partir de uma montagem real numa máquina Windows
**sem Docker** — se algo aqui estiver defasado, atualize este arquivo.

## O mapa

| Peça | Onde roda | Observação |
|---|---|---|
| Frontend (Vite) | `http://localhost:5173` | `npm run dev` em `frontend/` |
| Backend (FastAPI) | `http://localhost:8001` | ⚠️ o proxy do Vite aponta para **8001**, não 8000 (`frontend/vite.config.ts`) |
| PostgreSQL | `localhost:5432` (Docker) ou embutido | ver as duas rotas abaixo |
| Redis | `localhost:6379` | Docker, ou o mini-servidor em `backend/scripts/mini_redis.py` |

Login após os seeds: **`admin@healthsafety.com` / `Admin@123456`**.

## Rota A — com Docker (a padrão)

```bash
cd backend
docker compose -f docker-compose.dev.yml up -d   # postgres, redis, minio, clamav, mailpit
cp ../.env.example .env                          # ajuste DATABASE_URL/REDIS_URL para localhost
pip install -r requirements-dev.txt
python -m alembic upgrade head && python -m app.seeds
python -m uvicorn app.main:app --port 8001 --reload

cd ../frontend
npm ci && npm run dev                            # abre em localhost:5173
```

## Rota B — sem Docker (Windows, sem admin)

Usada quando a máquina não tem Docker nem acesso à senha do PostgreSQL nativo.

1. **Postgres embutido** (binário portátil via pip, dados em pasta local):

   ```bash
   pip install pgserver
   python -c "import pgserver; db = pgserver.get_server(r'C:\dev\helphs-pgdata', cleanup_mode=None); print(db.get_uri()); db.psql('CREATE DATABASE helpdesk_db;')"
   ```

   A URI impressa diz a porta (aleatória). O processo fica no ar sozinho.

2. **Mini-Redis**: `python backend/scripts/mini_redis.py` — implementa só o
   subconjunto que o auth usa (SETEX/GET/DEL/EXISTS). Suficiente para
   desenvolvimento; **não** suporta o rate limiter (que usa Lua) — por isso o
   passo 3 roda com `APP_ENV=testing`, que desliga o limiter.

3. **Backend** (ajuste a porta do Postgres pela URI do passo 1):

   ```bash
   cd backend
   export DATABASE_URL='postgresql+asyncpg://postgres:@127.0.0.1:<porta>/helpdesk_db'
   export APP_ENV=testing REDIS_URL='redis://127.0.0.1:6379/0' UPLOAD_DIR="$TMP/helphs-uploads"
   python -m alembic upgrade head && python -m app.seeds
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
   ```

4. **Frontend**: `cd frontend && npm ci && npm run dev` → `http://localhost:5173`.

## Pegadinhas conhecidas

- **Porta 8001**: o backend precisa subir em 8001 (ou mude o proxy no
  `vite.config.ts`). Subir em 8000 deixa o front com tela de login que nunca
  autentica.
- **Chaves JWT**: o runtime lê `backend/keys/private.pem` e `public.pem`
  (gitignored). Gere uma vez por máquina:
  `openssl genrsa -out keys/private.pem 2048 && openssl rsa -in keys/private.pem -pubout -out keys/public.pem`.
  (A **suíte de testes** não precisa disso — o `conftest.py` gera chaves
  efêmeras sozinho; `pytest` roda sem preparo nenhum.)
- **`APP_ENV=testing` vs `development`**: `testing` desliga o rate limiter
  (essencial na rota B, cujo mini-Redis não suporta os scripts Lua do
  limiter). `development` liga o limiter e o `/docs`, e exige Redis de
  verdade.
- **SMTP/confirmação de e-mail**: a exigência de confirmar e-mail é ligada
  pela flag `EMAIL_VERIFICATION_ENABLED` (default `false`) **e** SMTP
  presente. Preencher `SMTP_USER`/`SMTP_FROM_EMAIL` sozinho não liga nada —
  regra criada depois que esse par preenchido (seed do `.env.example`) travou
  login em produção.
- **PostgreSQL nativo na 5432**: se a máquina já tem um Postgres instalado
  cuja senha ninguém sabe, a rota B ignora ele por completo (porta própria).
- **`curl` no Vite**: o dev server ouve em `localhost` (IPv6 `::1`); teste
  com `http://localhost:5173`, não `http://127.0.0.1:5173`.

## Verificação rápida

```bash
curl http://localhost:8001/api/v1/health
# {"status":"ok",...}
curl -X POST http://localhost:5173/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@healthsafety.com","password":"Admin@123456"}'
# deve devolver access_token — prova o caminho front → proxy → API → banco
```
