#!/usr/bin/env bash
# RAW object storage (MinIO/S3) mirror backup.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

# Convention: LOTTERY_BACKUP_DIR is the backup ROOT; mirrors go under
# raw/<stamp>/ so verify_backups.sh sees the same layout everywhere.
BACKUP_DIR="${LOTTERY_BACKUP_DIR:-./backups}/raw"
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
  # boto3 fallback — project venv locally, system python in the container.
  PYBIN="$(command -v python || echo .venv/bin/python)"
  PYTHONPATH="${PYTHONPATH:-src}" "$PYBIN" - "$BUCKET" "$BACKUP_DIR/${STAMP}/" <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, "src")
from lottery_intelligence_platform.storage import s3_client_from_environment

bucket, dest = sys.argv[1], Path(sys.argv[2])
client = s3_client_from_environment()
count = 0
paginator = client.get_paginator("list_objects_v2")
for page in paginator.paginate(Bucket=bucket):
    for obj in page.get("Contents", []):
        target = dest / obj["Key"]
        target.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(bucket, obj["Key"], str(target))
        count += 1
print(f"{count} objects mirrored")
PY
fi
echo "raw backup written: $BACKUP_DIR/${STAMP}/"
