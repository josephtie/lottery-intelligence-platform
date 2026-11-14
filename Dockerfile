# Lottery Intelligence Platform — application image.
# Runs the orchestrator daemon (run-scheduler) and the read-only API.
# PostgreSQL and MinIO stay separate services; this image carries no state.

# Stage 1: build the Vue console (frontend/dist is served by the API).
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

# Stage 2: runtime.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# postgresql-client → pg_dump for the backup_postgresql job; bash already present.
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY infrastructure/postgres/migrations ./infrastructure/postgres/migrations
COPY scripts ./scripts
COPY --from=frontend /build/dist ./frontend/dist

RUN pip install --no-cache-dir . && \
    useradd --system --uid 10001 lottery && \
    mkdir -p /app/backups /app/logs && \
    chmod +x scripts/*.sh && chown -R lottery /app

USER lottery

# Default: scheduler daemon. The api service overrides the command.
CMD ["python", "-m", "lottery_intelligence_platform.orchestrator_cli", "run-scheduler"]
