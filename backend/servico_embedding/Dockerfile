# O serviço de embedding da Helô.
#
# Construído a partir de `backend/` (o contexto), mas NÃO é a API: só o pacote
# `servico_embedding` entra. Ver o README ao lado para o porquê da separação —
# resumo: a API roda com --workers 1, e cálculo de CPU no event loop já
# congelou esta API por 151 segundos uma vez.

FROM python:3.13-slim AS builder

WORKDIR /build
COPY servico_embedding/requirements.txt .
RUN pip install --upgrade pip && pip install --prefix=/install --no-cache-dir -r requirements.txt

# O MODELO BAIXA AQUI, no build. Baixar no start faria cada reinício depender
# da rede do servidor e do Hugging Face estarem de pé — um restart de
# madrugada viraria um contêiner que sobe e não funciona. Se o download falhar,
# o BUILD falha, que é o lugar certo para descobrir.
#
# O script confere revisão e SHA-256: modelo trocado sem aviso quebraria a
# comparabilidade dos 74 vetores já gravados, em silêncio.
COPY servico_embedding/baixa_modelo.py /build/baixa_modelo.py
RUN python /build/baixa_modelo.py /modelo

FROM python:3.13-slim AS runtime

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --from=builder /modelo /modelo
COPY servico_embedding /app/servico_embedding

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

ENV HELO_MODELO_DIR=/modelo \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# O /health responde 503 enquanto o modelo não carregou, então o healthcheck
# distingue "processo de pé" de "serviço servindo" — que é a distinção que
# importa aqui, porque o processo sobe mesmo com o modelo faltando.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health

# Um worker. O modelo são 864 MB residentes: dois workers seriam 1,7 GB para
# atender uma fila que hoje é de uma pergunta por vez.
CMD ["uvicorn", "servico_embedding.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
