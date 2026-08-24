# ============================================================
# HelpHS — Frontend Dockerfile
# Multi-stage: Node build + Nginx serve
# ============================================================

FROM node:20-alpine AS builder

WORKDIR /app

# O Vite embute VITE_API_URL no bundle em build-time. Sem valor, o app
# subiria com o fallback /api/v1 e o nginx devolveria o próprio index.html
# para toda chamada de API — por isso o build falha cedo aqui.
ARG VITE_API_URL
RUN test -n "$VITE_API_URL" || (echo "ERRO: build arg VITE_API_URL é obrigatório" && exit 1)
ENV VITE_API_URL=$VITE_API_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Runtime ──────────────────────────────────────────────────
FROM nginx:alpine AS runtime

# SPA config: unknown routes fallback to index.html
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
