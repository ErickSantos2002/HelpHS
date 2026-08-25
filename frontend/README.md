# HelpHS — Frontend

App React + Vite + TypeScript + Tailwind do HelpHS. O setup geral do projeto
(backend, banco, variáveis da raiz) está no [README da raiz](../README.md).

## Requisitos

- Node.js 20 (o CI e o Docker usam 20 — `.nvmrc` na pasta)

## Desenvolvimento

```bash
npm ci
npm run dev        # Vite em http://localhost:5173
```

O backend local precisa estar de pé em **localhost:8001** — o proxy do Vite
(`vite.config.ts`) encaminha `/api` e o WebSocket para lá. Não é necessário
criar `.env` em dev; o fallback `/api/v1` + proxy é o caminho normal.
Ver `.env.example` para o caso de apontar para outra API.

## Scripts

| Script                               | O que faz                                           |
| ------------------------------------ | --------------------------------------------------- |
| `npm run dev`                        | dev server com HMR                                  |
| `npm run build`                      | typecheck (`tsc -b`) + build de produção em `dist/` |
| `npm run typecheck`                  | só o typecheck (mesmo comando do CI)                |
| `npm run lint`                       | ESLint                                              |
| `npm test` / `npm run test:coverage` | Vitest (unidade/componente)                         |
| `npm run e2e` / `npm run e2e:ui`     | Playwright (ver pré-requisitos abaixo)              |
| `npm run format`                     | Prettier em `src/` e `e2e/`                         |

## E2E (Playwright)

**Não roda no CI.** Requer, antes de `npm run e2e`:

1. Backend em `localhost:8001` com banco **local** semeado
   (`admin@healthsafety.com` / senha do seed — nunca rodar contra produção);
2. O dev server sobe sozinho via `webServer` do `playwright.config.ts`.

Credenciais podem ser sobrescritas por `ADMIN_EMAIL`/`ADMIN_PASSWORD` e
`CLIENT_EMAIL`/`CLIENT_PASSWORD`.

## Docker / produção

Multi-stage: Node 20 builda, nginx serve `dist/` na porta 80. O deploy é
manual via EasyPanel (front e back são serviços separados).

- **Build arg obrigatório:** `VITE_API_URL` (URL pública da API). O Vite
  embute o valor no bundle em **build-time** — trocar a URL exige _rebuild_
  do serviço, não restart. Sem o arg, o build falha de propósito.
- TLS/HSTS terminam no proxy do EasyPanel; o nginx daqui só serve estáticos.

```bash
docker build -t helphs-frontend --build-arg VITE_API_URL=https://api.exemplo.com/api/v1 .
```
