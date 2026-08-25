---
name: help-migration-check
description: Revisa migrations Alembic do HelpHS (backend/alembic/versions/). Usar ao criar ou alterar uma revision, ao mudar backend/app/models/models.py, ou antes de um deploy que inclua migration — elas rodam sozinhas no boot do container.
---

# Skill: Migration Check — HelpHS

## Objetivo

Garantir que uma alteração de schema seja segura, num projeto onde a migration
**roda automaticamente**: o `backend/start.sh` executa `alembic upgrade head`
e depois `python -m app.seeds` **a cada boot do container**. Ninguém aplica
SQL à mão — e migration quebrada **impede a API de subir**.

## Fontes de verdade (e o que não é)

- **Models**: `backend/app/models/models.py` (arquivo único) — o que o código
  espera do banco
- **Migrations**: `backend/alembic/versions/` — como o banco chega lá; o
  `env.py` aponta `target_metadata = Base.metadata`, então o `autogenerate`
  funciona
- **`schema.prisma` na raiz NÃO é fonte de verdade.** O próprio arquivo se
  declara "REFERÊNCIA — NÃO UTILIZADO EM PRODUÇÃO". Mudar ali não muda nada
  no banco; se uma mudança de schema for pedida "no prisma", redirecionar para
  model + revision Alembic. Não gastar esforço mantendo-o sincronizado a menos
  que o usuário peça

## Convenções do projeto

Olhar `q7l8m9n0o1p2_add_email_verification.py` como referência:

- **Revision IDs são manuais e sequenciais** (`p6k7l8m9n0o1` → `q7l8m9n0o1p2`),
  não hashes gerados — seguir o padrão da cadeia
- Docstring com o **porquê** em português, incluindo a decisão de dado
  (ex.: "quem já usa o sistema entra como verificado")
- `downgrade()` **real e escrito** — é o padrão do repositório, não opcional
- Coluna `NOT NULL` em tabela populada entra com `server_default` e, se
  preciso, backfill via `op.execute(...)`

## O que verificar

### 1. A cadeia

- `down_revision` aponta para o head atual? Duas revisions com o mesmo pai
  criam branch e o `upgrade head` falha — como roda no boot, **a API não sobe**
- `alembic history` conta uma história linear?

### 2. Autogenerate vs manual

`alembic revision --autogenerate` é o ponto de partida, nunca o ponto final:

- **Rename** de coluna/tabela vira `drop` + `add` no autogenerate — perde o
  dado; escrever `op.alter_column`/`op.rename_table` à mão
- **Mudança de enum** (novo valor em `AuditAction`, `TicketStatus`...) não sai
  no autogenerate — precisa de `ALTER TYPE ... ADD VALUE` manual
- `server_default` e constraints com nome costumam divergir — conferir

### 3. Segurança do dado existente

- `ADD COLUMN NOT NULL` sem `server_default` **falha** com tabela populada
- `DROP COLUMN` e mudança de tipo destrutiva: exigir confirmação explícita
  antes de sequer detalhar
- `op.execute` com `UPDATE` — conferir o `WHERE` duas vezes
- O `downgrade` devolve o schema, mas **não devolve dado apagado** — para
  migration destrutiva, o rollback real é o backup

### 4. Sincronia com o model

Coluna nova em `models.py` sem revision correspondente (ou vice-versa) não
aparece nos testes — **a suíte mocka o banco** (ver `help-test-review`) — e
explode só em runtime, depois do deploy. Conferir tipo, `nullable` e default
batendo dos dois lados.

### 5. Seeds

`app/seeds.py` roda **todo boot**, depois das migrations — qualquer mudança
nele precisa ser idempotente (rodar duas vezes sem duplicar nem falhar) e
**não pode levantar exceção** (o `start.sh` tem `set -e`; levantar derruba o
boot). O `seed_admin` recusa rodar em produção e exige `SEED_ADMIN_PASSWORD`
— a recusa logada é esperada; produtos e SLA seguem sendo semeados.

## Sequência antes de subir migration para produção

1. [ ] Rodar num banco local/staging: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`
2. [ ] **Backup do banco de produção** — para destrutiva, é o único rollback de dado
3. [ ] Cadeia linear, sem branch
4. [ ] Model e migration sincronizados
5. [ ] Lembrar: o deploy no EasyPanel **aplica a migration sozinho** no boot —
       não há passo manual, o que há é ponto de não-retorno

## Formato de resposta

```
MIGRATION CHECK — backend/alembic/versions/r8m9n0o1p2q3_add_x.py
================================================================
❌ Cadeia: down_revision aponta para p6k7... mas o head é q7l8... — branch, boot vai falhar
⚠️  Dado: NOT NULL sem server_default — falha com a tabela populada
⚠️  Model: coluna existe na revision mas falta em app/models/models.py
✅ Downgrade: escrito e simétrico
📋 Antes do deploy: backup → conferir upgrade/downgrade em staging
```

## Observações

- **Nunca editar revision já aplicada em produção** — criar uma nova por cima
- **Nunca rodar migration contra produção pela máquina local** — quem aplica é
  o `start.sh` no deploy
- Migration destrutiva: pedir confirmação explícita, e backup antes, sempre
- Ver [[help-deploy-check]] para o checklist completo de subida
