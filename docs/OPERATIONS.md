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
| Read API | on demand | `lottery-api --port 8090` (Bearer auth if `LOTTERY_API_TOKEN` set) |

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

## Evidence export (`export_evidence`, hourly at :10)

Ships the irreplaceable evidence tables — predictions, outcomes, coverage,
cohort versions, job events, alerts, findings — as one NDJSON object to the
content-addressed raw store. Hourly granularity caps evidence loss at ~1 h
instead of the 24 h pg_dump RPO; a lost prediction is lost *proof* that cannot
be re-collected. Idempotent by construction: unchanged content hashes to the
same `raw/sha256/...` key, so a quiet hour costs nothing. Each export writes
an `EVIDENCE_EXPORTED` audit + job event carrying the sha256.

## Secondary source reconciliation

An independent check against the single-source blind spot (silent source
error, never corrected). Channel: file import — an NDJSON file from any
independent record (aggregator export, published PDF, manual transcription):

```json
{"draw_date": "2026-10-05", "draw_name": "Fortune Thursday", "winning_numbers": [1,2,3,4,5]}
```

```bash
lottery-secondary-import path/to/observations.ndjson
```

The file is preserved raw and content-addressed; each observation is compared
to the canonical registry → `MATCH`, `MISMATCH` (+ `SOURCE_CONFLICT` alert,
severity CRITICAL), `MISSING_PRIMARY`, or `UNMATCHED_NAME`. Conflicts are
recorded in `ingestion.source_comparisons` — the canonical row is **never**
auto-corrected; arbitration stays human.

## Dedicated test database

Integration tests require `LOTTERY_TEST_DATABASE_URL` and skip without it —
there is no fallback to the live DSN. The test DB is a template clone
(`createdb -T lottery_platform lottery_platform_test`, ~15.7k draws) with all
migrations applied. Refresh by re-cloning when the schema or fixture needs
current data; drop stale `cron:` job runs is unnecessary (append-only, they
expire unclaimed).
