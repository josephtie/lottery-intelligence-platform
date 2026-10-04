#!/usr/bin/env bash
# RAW object storage (MinIO/S3) mirror backup.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

BACKUP_DIR="${LOTTERY_BACKUP_DIR:-./backups/raw}"
mkdir -p "$BACKUP_DIR"
BUCKET="${LOTTERY_S3_BUCKET:?LOTTERY_S3_BUCKET must be set}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if command -v aws >/dev/null 2>&1; then
  ENDPOINT_ARGS=()
  [ -n "${LOTTERY_S3_ENDPOINT_URL:-}" ] && ENDPOINT_ARGS+=(--endpoint-url "$LOTTERY_S3_ENDPOINT_URL")
  aws s3 sync "s3://${BUCKET}/" "$BACKUP_DIR/${STAMP}/" "${ENDPOINT_ARGS[@]}"
elif command -v mc >/dev/null 2>&1; then
  mc mirror "local/${BUCKET}" "$BACKUP_DIR/${STAMP}/"
else
  echo "no s3 client available (aws or mc required)" >&2
  exit 1
fi
echo "raw backup written: $BACKUP_DIR/${STAMP}/"
