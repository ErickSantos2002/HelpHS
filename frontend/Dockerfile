# ============================================================
# HelpHS — Frontend Dockerfile
# Multi-stage: Node build + Nginx serve
# ============================================================

FROM node:20-alpine AS builder

WORKDIR /app

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
