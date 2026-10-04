#!/usr/bin/env bash
# PostgreSQL backup. Cron-invoked via the backup_postgresql job.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

BACKUP_DIR="${LOTTERY_BACKUP_DIR:-./backups/postgres}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/lottery_${STAMP}.dump"

pg_dump \
  --host="${LOTTERY_DATABASE_HOST:-localhost}" \
  --port="${LOTTERY_DATABASE_PORT:-5432}" \
  --username="${LOTTERY_DATABASE_USER:-directus}" \
  --dbname="${LOTTERY_DATABASE_NAME:-lottery_platform}" \
  --format=custom --file="$OUT"

echo "backup written: $OUT ($(du -h "$OUT" | cut -f1))"
