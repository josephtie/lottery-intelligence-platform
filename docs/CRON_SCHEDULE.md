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

## Design note

Cron is a *trigger mechanism only*. There is no fragile chained schedule —
each job enqueues idempotent work; a missed run simply runs late. The
collector looks back 7 days by default, so any outage shorter than a week
self-heals on the next tick.
