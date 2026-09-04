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

Login após os seeds: **`admin@healthsafety.com`**, com a senha que você mesmo
definiu em `SEED_ADMIN_PASSWORD` — veja abaixo. Não há senha padrão: sem a
variável o seed não cria admin nenhum, e é assim de propósito.

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
   # Sem esta variável o seed NÃO cria o admin e não há como logar. A senha
   # saiu do código de propósito (ver decisoes-e-regras.md), e não há valor
   # padrão para cair: ESCOLHA A SUA. Mínimo 8 caracteres, com maiúscula e
   # número.
   #
   # Guarde-a em `backend/.env.local`, que o .gitignore cobre, e carregue a
   # cada sessão do terminal com a linha abaixo. Não use `backend/.env` para
   # isto: aquele arquivo é lido sozinho pelo app e pode estar apontando para o
   # banco de produção (ver a seção de diagnóstico no fim deste documento).
   #
   #     echo "SEED_ADMIN_PASSWORD=<a sua senha>" >> .env.local
   set -a; . ./.env.local; set +a
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
- **Subiu e o login do admin não funciona**: provavelmente `SEED_ADMIN_PASSWORD`
  não estava definida quando você rodou `python -m app.seeds`. O seed avisa no
  log e **pula** a criação em vez de usar uma senha conhecida. Defina a
  variável e rode o seed de novo — ele é idempotente.
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

## Apontando o localhost para o banco de produção (diagnóstico)

Às vezes é útil rodar o app local **lendo os dados reais** (investigar um
chamado, reproduzir um bug com dado de verdade). O procedimento:

1. Crie `backend/.env` (é **gitignored** — credencial nunca vai para o repo)
   com o `DATABASE_URL` de produção (`postgresql+asyncpg://usuario:senha@host:porta/banco`
   — as credenciais são as mesmas do DBeaver; peça a quem administra).
   Mantenha `APP_ENV=testing` e o `REDIS_URL` local — os tokens de sessão
   ficam só na sua máquina.
2. Suba o backend normalmente (porta 8001). O login passa a ser com as
   **contas reais**; o admin de seed local não existe lá.

⚠️ **Regras de sobrevivência nesse modo:**

- **Toda escrita é real.** Criar/editar/fechar chamado no localhost aparece
  para os clientes. Use para *ler e diagnosticar*; para experimentar, volte
  ao banco local.
- **Nunca rode `alembic upgrade` nem `python -m app.seeds`** apontando para
  produção — o seed criaria usuário de teste no banco real, e migration fora
  do deploy quebra o contrato de que elas rodam no boot do container.
- **O worker de fechamento automático roda na sua instância também** e
  escreve no banco (fecha chamados resolvidos há 3+ dias úteis, checando a
  cada hora). O efeito é idêntico ao do servidor, mas sua máquina passa a
  executá-lo junto enquanto o backend local estiver no ar.
- Terminou o diagnóstico? Volte o `DATABASE_URL` do `.env` para o banco
  local — não deixe o backend apontado para produção sem necessidade.

## Verificação rápida

```bash
curl http://localhost:8001/api/v1/health
# {"status":"ok",...}
# A senha vem da variável, nunca escrita aqui — aspas DUPLAS no -d para o
# shell expandir. Se der "senha inválida", confira se a variável está no
# terminal: `echo "${SEED_ADMIN_PASSWORD:?nao definida}"`.
curl -X POST http://localhost:5173/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@healthsafety.com\",\"password\":\"$SEED_ADMIN_PASSWORD\"}"
# deve devolver access_token — prova o caminho front → proxy → API → banco
```
