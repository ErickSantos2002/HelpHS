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
| MinIO Console | http://localhost:9001   |
| Mailpit       | http://localhost:8025   |
| Swagger UI    | http://localhost:8000/docs |

## Stack

| Camada      | Tecnologia                                      |
|-------------|-------------------------------------------------|
| Backend     | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic   |
| Banco       | PostgreSQL 15                                   |
| Cache/Filas | Redis 7 + Celery                                |
| WebSocket   | python-socketio                                 |
| Frontend    | React, Vite, TypeScript, Tailwind CSS           |
| Storage     | MinIO (S3-compatible)                           |
| Antivírus   | ClamAV                                          |
| Auth        | JWT RS256 (python-jose)                         |
| IA          | OpenAI GPT-4o-mini + Anthropic (fallback)       |
| Deploy      | EasyPanel (backend e frontend separados)        |

## Documentação

Toda a documentação de negócio está em `Documentação/` (arquivos `.docx`).
