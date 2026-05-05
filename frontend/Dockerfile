# ============================================================
# HelpHS — Frontend Dockerfile
# Multi-stage: Node build + Nginx serve
# ============================================================

FROM node:20-alpine AS builder

WORKDIR /app

# Build-time variables (Vite embeds these into the JS bundle)
ARG VITE_API_URL
ARG VITE_WS_URL
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL

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
