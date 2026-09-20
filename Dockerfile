FROM node:22-alpine AS frontend
WORKDIR /build/frontend
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLIPO_DATABASE_URL=sqlite:////app/data/clipo.db
WORKDIR /app
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock \
    && useradd --create-home --uid 10001 clipo
COPY backend/ ./backend/
RUN pip install --no-cache-dir --no-deps ./backend \
    && mkdir -p /app/data \
    && chown -R clipo:clipo /app
COPY --from=frontend --chown=clipo:clipo /build/backend/app/static/ /app/backend/app/static/
COPY --chmod=755 deploy/entrypoint.sh /app/entrypoint.sh
ENV CLIPO_STATIC_PATH=/app/backend/app/static CLIPO_QUEUE_PATH=/app/data/huey.db
USER clipo
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"
ENTRYPOINT ["/app/entrypoint.sh"]
