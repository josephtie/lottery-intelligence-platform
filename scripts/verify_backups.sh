#!/usr/bin/env bash
# Verify that the latest backups exist, are non-empty and fresh (< 36h).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a

BACKUP_DIR="${LOTTERY_BACKUP_DIR:-./backups}"
MAX_AGE_SECONDS=$((36 * 3600))
NOW="$(date -u +%s)"
FAILED=0

check() {
  local dir="$1" pattern="$2" name="$3"
  local latest
  latest="$(ls -t "$dir"/$pattern 2>/dev/null | head -1 || true)"
  if [ -z "$latest" ]; then
    echo "MISSING: no $name backup found in $dir" >&2
    FAILED=1
    return
  fi
  if [ -f "$latest" ] && [ ! -s "$latest" ]; then
    echo "EMPTY: $latest" >&2; FAILED=1; return
  fi
  local mtime
  mtime="$(stat -f %m "$latest" 2>/dev/null || stat -c %Y "$latest")"
  if [ $((NOW - mtime)) -gt "$MAX_AGE_SECONDS" ]; then
    echo "STALE: $latest is older than ${MAX_AGE_SECONDS}s" >&2
    FAILED=1
    return
  fi
  echo "OK: $latest"
}

check "$BACKUP_DIR/postgres" 'lottery_*.dump' "PostgreSQL"
check "$BACKUP_DIR/raw" '*' "raw storage"
exit "$FAILED"
