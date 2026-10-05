# Cron schedule — Africa/Abidjan

File: `infrastructure/cron/lottery.cron` (set `REPO`/`PYTHON` before install).
All times are interpreted under `CRON_TZ=Africa/Abidjan` — never assume the
server clock matches the game's timezone.

| Cron | Job | Purpose |
|---|---|---|
| `*/5 * * * *` | `collect_results` | Fetch the trailing 7-day results window; store raw payloads; detect new draws |
| `*/5 * * * *` | `run-due` | Claim + run all due `ops.job_runs` (settlement, retries) |
| `0 23 * * *` | `daily_research_summary` | Daily counts: settled outcomes, pending/locked predictions, open alerts |
| `30 23 * * 0` | `weekly_research_report` | Per-model settled prediction performance, 7-day window |
| `0 2 * * *` | `backup_postgresql` | `pg_dump -Fc` into `backups/postgres/` |
| `30 2 * * *` | `backup_raw_storage` | Mirror `LOTTERY_S3_BUCKET` into `backups/raw/` |
| `0 3 * * *` | `verify_backups` | Latest backups exist, non-empty, < 36 h old |

## Scheduler-managed jobs (Docker deployment)

In the self-hosted stack the scheduler service (`run-scheduler`) owns the
job catalogue (`DEFAULT_JOB_DEFS`) — the host cron file is not used there.

| Cron | Job | Purpose |
|---|---|---|
| `*/5 * * * *` | `collect_results` | Result collection window |
| `*/5 * * * *` | `settle_pending_draws` | Settle newly frozen draws |
| `15,45 * * * *` | `generate_predictions` | Seal prospective predictions |
| `10 * * * *` | `export_evidence` | Export evidence tables to the raw store |
| `*/15 * * * *` | `check_job_freshness` | Watchdog: `JOB_FRESHNESS_STALE` alert if a critical job has no recent success; `JOB_RUNS_DEAD` on DEAD runs < 24 h |
| `0 23 * * *` | `daily_research_summary` | Daily counts |
| `30 23 * * 0` | `weekly_research_report` | Weekly report + conservative cohort suspension |
| `45 23 * * *` | `audit_data_quality` | Quality sweep + distribution drift |
| `0 2 * * *` | `backup_postgresql` | Nightly dump |
| `30 2 * * *` | `backup_raw_storage` | Raw-store mirror |
| `0 3 * * *` | `verify_backups` | Backup freshness check |

The scheduler service also writes a heartbeat file
(`/tmp/scheduler_heartbeat`, `LOTTERY_HEARTBEAT_FILE`) on every tick; the
Docker healthcheck fails when the file is older than 5 minutes, so a wedged
loop triggers a container restart — the layer the watchdog job cannot see
from inside.

## Design note

Cron is a *trigger mechanism only*. There is no fragile chained schedule —
each job enqueues idempotent work; a missed run simply runs late. The
collector looks back 7 days by default, so any outage shorter than a week
self-heals on the next tick.
