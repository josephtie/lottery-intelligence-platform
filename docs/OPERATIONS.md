# Operations — runbook

Local-first deployment: PostgreSQL + MinIO (Docker Compose), cron-driven
jobs, stdlib read API. No Kubernetes — not justified at this scale.

## Components

| Component | Runs where | How |
|---|---|---|
| PostgreSQL | local compose | source of truth, port 5432 |
| MinIO | local compose (`raw-storage`) | raw payloads, ports 19000/19001 |
| Cron | host `crontab` | `infrastructure/cron/lottery.cron`, `CRON_TZ=Africa/Abidjan` |
| Scheduler | cron `run-due` every 5 min | claims due `ops.jobs` via `FOR UPDATE SKIP LOCKED` |
| Read API | on demand | `lottery-api --port 8080` (Bearer auth if `LOTTERY_API_TOKEN` set) |

## Backup & restore

| What | Job | Schedule | Output |
|---|---|---|---|
| PostgreSQL | `backup_postgresql` | daily 02:00 | `backups/postgres/lottery_*.dump` (pg_dump custom) |
| MinIO raw | `backup_raw_storage` | daily 02:30 | `backups/raw/` mirror (boto3 fallback) |
| Verification | `verify_backups` | daily 03:00 | checks newest dumps exist and are non-trivial |

**RPO**: 24 h (daily backups). **RTO**: minutes — `pg_restore` into a fresh
database; see below.

**Restore test — last executed 2026-10-04, PASS.** Procedure:

```bash
bash scripts/restore_postgresql.sh backups/postgres/<latest>.dump
```

Creates `lottery_restore_test`, restores, compares row counts of the
load-bearing tables (draws, versions, numbers, dataset members), drops the
scratch DB. Restored counts may lag live (the dump predates same-day writes);
core tables must never be empty.

**Raw storage recovery**: re-run `backup_raw_storage.sh` inverted (upload
`backups/raw/` mirror back to the bucket) or replay collection — every
payload's sha256 is in `ingestion.raw_objects` for integrity re-verification.

## Failure scenarios

| Failure | Behavior | Recovery |
|---|---|---|
| Collector down / source unreachable | job `FAILED`, retry ×3 (backoff 30s·2ⁿ), then `DEAD` + alert | fix cause, `run-job collect_results` |
| Draw expected but never published | stays `EXPECTED`; `audit_data_quality` alerts `MISSING_DRAWS` nightly | manual check on lonaci.ci |
| Source corrects a result | new draw_version, old `SUPERSEDED`, settlement re-runs | automatic |
| Prediction contamination | `LEAKAGE_DETECTED` alert, prediction `INVALID`, excluded from metrics | investigate dataset_version |
| Postgres restart | jobs resume via durable `job_runs` claim | automatic |
| Backup missing | `verify_backups` fails → alert | run backup scripts manually |

## Security posture

- Secrets in `.env` / `.pgpass` only — gitignored, never logged.
- API: read-only SQL views; Bearer token enforced when `LOTTERY_API_TOKEN`
  set; warns when binding non-loopback without a token.
- Append-only triggers on audit/events/coverage/artifacts — history cannot
  be rewritten even by a bug in new code.

## Monitoring

- `run-due` writes `ops.job_events` (append-only ledger) and `ops.alerts`
  (deduplicated, `acknowledged_at` workflow).
- `orchestrator_cli health` / `GET /api/health`: open alerts, run counts,
  last run timestamp, recent failures.
- `audit_data_quality` (23:45): per-type anomaly rollup + collection
  success/duplicate rates; alerts `MISSING_DRAWS` / `DRAW_QUALITY_ANOMALY`.
