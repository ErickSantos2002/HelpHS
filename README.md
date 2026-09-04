# HelpHS — Help Desk Health & Safety

[![CI](https://github.com/ErickSantos2002/HelpHS/actions/workflows/ci.yml/badge.svg)](https://github.com/ErickSantos2002/HelpHS/actions/workflows/ci.yml)

Sistema de Help Desk / Gestão de Chamados para organizações de Saúde & Segurança do Trabalho.

## Estrutura do Projeto

```
HelpHS/
├── backend/                    # API Python + FastAPI
│   └── docker-compose.dev.yml  # Infraestrutura de dev (PostgreSQL, Redis, MinIO, ClamAV...)
├── frontend/                   # App React + Vite + TypeScript + Tailwind
├── Documentação/               # Documentação do projeto (.docx)
├── schema.prisma               # Referência do schema original
└── .env.example
```

## Pré-requisitos

- Python 3.12+
- Node.js 20+
- Docker e Docker Compose
- Git

## Setup do Ambiente

### 1. Clonar o repositório

```bash
git clone https://github.com/ErickSantos2002/HelpHS.git
cd HelpHS
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Editar .env e preencher todos os valores CHANGE_ME_*
```

### 3. Gerar chaves JWT (RS256)

```bash
mkdir keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

### 4. Subir infraestrutura

```bash
docker-compose -f backend/docker-compose.dev.yml up -d
```

### 5. Interfaces de administração (dev)

| Serviço       | URL                     |
|---------------|-------------------------|
| pgAdmin       | http://localhost:5050   |
| RedisInsight  | http://localhost:5540   |
| Mailpit       | http://localhost:8025   |
| Swagger UI    | http://localhost:8001/docs |

### 6. Subir a aplicação

```bash
# backend — a porta 8001 é a que o proxy do Vite espera
cd backend && python -m uvicorn app.main:app --port 8001 --reload

# frontend, noutro terminal
cd frontend && npm ci && npm run dev     # http://localhost:5173
```

Login dos seeds: `admin@healthsafety.com`, com a senha vinda de
`SEED_ADMIN_PASSWORD` — exporte a variável **antes** de subir o backend, senão
o seed pula a criação do admin. Escolha a sua (mínimo 8 caracteres, com
maiúscula e número): os testes e2e não têm mais valor fixo, o workflow gera uma
senha por execução. Em produção a variável não deve existir.

Sem Docker na máquina? A receita alternativa (Postgres embutido, mini-Redis)
está em [desenvolvimento-local.md](desenvolvimento-local.md).

## Testes

```bash
cd backend  && pytest                # gate de 80% de cobertura
cd frontend && npm test              # Vitest
cd frontend && npx playwright test   # e2e — exige backend na 8001

python .github/scripts/verifica_dependencias.py   # auditoria de dependências
```

> As contagens de teste não ficam mais escritas aqui de propósito: número
> mantido à mão envelhece a cada teste novo. Duas vezes em 24 horas este README
> ficou desatualizado. Quem quiser o número corrente, roda o comando.

### Auditoria de dependências

O gate falha quando aparece vulnerabilidade **nova**, fora do baseline em
`.github/dependencias-conhecidas.toml`. Ele roda nos dois jobs do CI, sem
`continue-on-error`.

Quebrou o CI? A pergunta **não** é como fazer passar. É: *esse código é
alcançável no HelpHS?*

- **Alcançável** → conserte. Suba o pacote, ou mitigue na aplicação. Só entra no
  baseline depois, com a evidência.
- **Inalcançável** → acrescente ao baseline, e o `motivo` precisa citar o
  **comando** que provou. "Parece não usado" não passa — o script recusa entrada
  sem justificativa, e entrada obsoleta também derruba o CI, para o arquivo não
  virar lista que só cresce.

**Uma linha por advisory, não por pacote.** No backend a chave é o `id` do
pip-audit; no front é `pacote` + `advisory` (o GHSA). Indexar por pacote deixava
passar advisory **novo** num pacote já listado — justo o que o gate existe para
pegar — e fazia uma justificativa escrita para um aviso ser herdada por todos os
outros do mesmo pacote. Pacote sinalizado só por herança (`react-router-dom` →
`react-router`) não entra: o aviso é o do pacote de baixo, e o script imprime
esses nomes a cada rodada.

Ignore novo é aprovado no code review do PR que mexer no baseline. Os testes do
gate estão em `backend/tests/test_gate_dependencias.py` e rodam no `pytest`.

O `pytest` roda sem preparo: o `conftest.py` fixa o ambiente e gera chaves JWT
efêmeras. Cinco testes exercitam as agregações do dashboard contra **PostgreSQL
de verdade** — sobem um servidor efêmero via `pgserver`, sem Docker, e são
pulados limpo em quem não o tiver instalado. Os três primeiros comandos rodam no CI a cada push; o Playwright tem
workflow próprio (`e2e.yml`), acionado à mão.

## Stack

| Camada      | Tecnologia                                      |
|-------------|-------------------------------------------------|
| Backend     | Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic   |
| Banco       | PostgreSQL 15                                   |
| Cache       | Redis 7                                         |
| WebSocket   | Nativo do FastAPI (`starlette`), sem biblioteca |
| Frontend    | React, Vite, TypeScript, Tailwind CSS           |
| Storage     | Disco, em volume (`UPLOAD_DIR`)                 |
| Antivírus   | ClamAV                                          |
| Auth        | JWT RS256 (python-jose)                         |
| IA          | DeepSeek (provedor único, desligado)            |
| Deploy      | EasyPanel (backend e frontend separados)        |

Duas ressalvas que a tabela não conta: **não existe fila de tarefas** — o que
precisa rodar sozinho roda como task da própria API, por decisão registrada; e
o **MinIO** sobrevive só como configuração legada, já que os anexos passaram a
ser gravados em disco. Ambas no documento de decisões.

## Documentação

| Onde | O quê |
|---|---|
| [docs/decisoes-e-regras.md](docs/decisoes-e-regras.md) | **Comece por aqui.** As regras de negócio que não dá para deduzir do código: SLA, encerramento, permissões, equipamentos — e as pendências conhecidas |
| [desenvolvimento-local.md](desenvolvimento-local.md) | Subir o sistema na sua máquina, com e sem Docker, e as pegadinhas do caminho |
| [Changelog.md](Changelog.md) | Changelog técnico do repositório, por versão |
| [mudanças.md](mudanças.md) | Registro do trabalho por data, com o porquê de cada decisão |
| `frontend/src/data/changelog.ts` | O changelog que o **cliente** vê dentro do sistema |
| [docs/superpowers/specs/](docs/superpowers/specs/) | Desenhos e levantamentos: atendimento por IA, regra de primeira resposta do SLA, as duas fontes de verdade de empresa |
| [mudanças.md](mudanças.md) | Registro do trabalho por data — inclui a auditoria completa de agosto/2026 e as dívidas que ficaram registradas com o gatilho de quando revisitar |
| `Documentação/` | Dicionário de dados e requisitos originais (`.docx`, fora do Git) |
