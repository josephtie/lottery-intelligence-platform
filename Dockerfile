# Lottery Intelligence Platform — application image.
# Runs the orchestrator daemon (run-scheduler) and the read-only API.
# PostgreSQL and MinIO stay separate services; this image carries no state.

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY infrastructure/postgres/migrations ./infrastructure/postgres/migrations

RUN pip install --no-cache-dir . && \
    useradd --system --uid 10001 lottery && \
    mkdir -p /app/backups /app/logs && chown -R lottery /app

USER lottery

# Default: scheduler daemon. The api service overrides the command.
CMD ["python", "-m", "lottery_intelligence_platform.orchestrator_cli", "run-scheduler"]
