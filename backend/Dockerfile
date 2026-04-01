# ============================================================
# HelpHS — Backend Dockerfile
# Multi-stage: builder + runtime
# ============================================================

FROM python:3.13-slim AS builder

WORKDIR /app

# Dependências do sistema para compilar pacotes (asyncpg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Runtime ──────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Dependências de runtime apenas
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia pacotes instalados do builder
COPY --from=builder /install /usr/local

# Copia código da aplicação
COPY . .

# Usuário não-root por segurança
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
