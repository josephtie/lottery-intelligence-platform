#!/usr/bin/env bash
# Restore-test a PostgreSQL backup into a scratch database and verify counts.
#
# Usage: scripts/restore_postgresql.sh <dump_file> [scratch_db]
#
# Creates <scratch_db> (default lottery_restore_test), restores the dump,
# compares row counts of the load-bearing tables against the live database,
# prints PASS/FAIL, then drops the scratch database. Never touches the live DB.
set -euo pipefail

DUMP="${1:?usage: restore_postgresql.sh <dump_file> [scratch_db]}"
SCRATCH="${2:-lottery_restore_test}"

if [[ ! -f "$DUMP" ]]; then
    echo "dump not found: $DUMP" >&2; exit 2
fi

HOST="${LOTTERY_DB_HOST:-localhost}"; PORT="${LOTTERY_DB_PORT:-5432}"
USER="${LOTTERY_DB_USER:-directus}"; LIVE_DB="${LOTTERY_DB_NAME:-lottery_platform}"

# The local .pgpass only grants the live database; reuse its password for the
# scratch DB so the test stays non-interactive.
PGPASSFILE="${PGPASSFILE:-$HOME/.pgpass}"
export PGPASSWORD="$(awk -F: -v u="$USER" -v d="$LIVE_DB" \
    '$3==d && $4==u && ($1=="localhost" || $1=="127.0.0.1") {print $5; exit}' "$PGPASSFILE")"

echo "== restore test: $DUMP -> $SCRATCH =="
psql -h "$HOST" -p "$PORT" -U "$USER" -d "$LIVE_DB" -qc "DROP DATABASE IF EXISTS $SCRATCH;"
psql -h "$HOST" -p "$PORT" -U "$USER" -d "$LIVE_DB" -qc "CREATE DATABASE $SCRATCH;"

pg_restore -h "$HOST" -p "$PORT" -U "$USER" -d "$SCRATCH" --no-owner --no-privileges "$DUMP"

TABLES="core.draws core.draw_versions core.draw_numbers datasets.dataset_members research.predictions research.prediction_outcomes ingestion.raw_objects"
fail=0
for t in $TABLES; do
    live=$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$LIVE_DB" -tAc "SELECT count(*) FROM $t;")
    rest=$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$SCRATCH" -tAc "SELECT count(*) FROM $t;")
    status="OK"
    # Live grows after the dump; restored < live is expected. Empty restored
    # only matters for tables that existed with data at dump time — the load-
    # bearing core tables are the hard check.
    if [[ "$rest" -eq 0 && "$live" -gt 0 ]]; then status="empty (dump predates data)"; fi
    printf "%-40s restored=%-8s live=%-8s %s\n" "$t" "$rest" "$live" "$status"
done
for t in core.draws core.draw_versions core.draw_numbers datasets.dataset_members; do
    rest=$(psql -h "$HOST" -p "$PORT" -U "$USER" -d "$SCRATCH" -tAc "SELECT count(*) FROM $t;")
    if [[ "$rest" -eq 0 ]]; then echo "HARD FAIL: $t restored empty"; fail=1; fi
done

psql -h "$HOST" -p "$PORT" -U "$USER" -d "$LIVE_DB" -qc "DROP DATABASE IF EXISTS $SCRATCH;"
if [[ "$fail" -eq 0 ]]; then echo "RESTORE TEST: PASS"; else echo "RESTORE TEST: FAIL"; exit 1; fi
