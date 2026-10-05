# VPS deployment

Status: **prepared, not deployed**. These artifacts let the application tier
run on any Docker host, independent of the Mac. Nothing here is live until the
steps below are executed and verified.

## Architecture

Two stateless services built from the root `Dockerfile`
(`infrastructure/vps/compose.yaml`), plus a one-shot bootstrap:

| Service | Command | Role |
|---|---|---|
| `scheduler` | `orchestrator_cli run-scheduler` | replaces the macOS crontab entirely: `ensure_jobs` registers the 10 job specs on a fresh DB, `enqueue_due` fires them (collect_results + settle every 5 min, predictions ×2/h, daily/weekly summaries, audit, hourly evidence export, backups 02:00–03:00) and the loop drains `ops.job_runs` every 30 s |
| `api` | `lottery_intelligence_platform.api --host 0.0.0.0` | read-only API + Vue console (dist baked into the image) |
| `bootstrap` (profile) | `orchestrator_cli migrate` | one-shot: applies pending SQL migrations, exits |

The image carries everything the jobs need: `pg_dump` (postgresql-client),
`scripts/*.sh`, the built `frontend/dist`, and the installed Python package —
no venv paths, no host dependencies.

State stays outside the stack: **PostgreSQL** and the **S3/MinIO raw store**
are external dependencies (`LOTTERY_DATABASE_*`, `LOTTERY_S3_*`). Use a managed
Postgres or run it as a separate container — it must not be a sibling service
in this compose file, so a torn-down stack never takes the data with it.

## Prerequisites on the VPS

- Docker + compose plugin
- PostgreSQL ≥ 15 reachable from the containers — empty database is fine,
  migrations run via the `bootstrap` service (creates every schema/table)
- S3/MinIO reachable, bucket `lottery-raw`
- Reverse proxy (nginx/Caddy) in front of the API if exposed beyond loopback —
  `LOTTERY_API_TOKEN` is then mandatory

## Deploy

```bash
git clone <repo> && cd lottery-intelligence-platform
cp infrastructure/vps/.env.example infrastructure/vps/.env   # fill it in
COMPOSE="docker compose -f infrastructure/vps/compose.yaml --env-file infrastructure/vps/.env"

$COMPOSE build
# fresh database: apply all migrations first (no-op if already applied)
$COMPOSE --profile bootstrap run --rm bootstrap
$COMPOSE up -d
```

`run-scheduler` calls `ensure_jobs` at startup, so the job catalogue exists
even on a blank database; the first `collect_results` fires within 5 min.

## Cron coverage (what runs automatically)

| Job | Schedule | Role |
|---|---|---|
| `collect_results` | `*/5 * * * *` | collect LONACI/lotobonheur results |
| `settle_pending_draws` | `*/5 * * * *` | settle draws + score predictions |
| `generate_predictions` | `15,45 * * * *` | seal cohort predictions |
| `daily_research_summary` | `0 23 * * *` | daily research rollup |
| `weekly_research_report` | `30 23 * * 0` | weekly report |
| `audit_data_quality` | `45 23 * * *` | quality audit + alert auto-resolution |
| `export_evidence` | `10 * * * *` | NDJSON evidence export to S3 |
| `backup_postgresql` | `0 2 * * *` | pg_dump → `/app/backups` volume |
| `backup_raw_storage` | `30 2 * * *` | S3 mirror → `/app/backups` volume |
| `verify_backups` | `0 3 * * *` | freshness check (< 36 h) |

## Verify

```bash
$COMPOSE ps                                  # both services healthy
$COMPOSE exec scheduler python -m lottery_intelligence_platform.orchestrator_cli health
curl -H "Authorization: Bearer $LOTTERY_API_TOKEN" http://127.0.0.1:8090/api/health
# within ~5 min: collect_results runs appear in ops.job_runs via `cron:` keys
# after 02:00–03:00: dumps land in the lottery-backups volume
```

## Update

```bash
git pull && docker compose ... build && docker compose ... up -d
```
Pending `ops.job_runs` survive restarts — the queue is in Postgres, not the
container. Apply new migrations before starting the new image.

## Rollback

```bash
git checkout <previous-commit> && docker compose ... build && docker compose ... up -d
```
The code is stateless; only migrations are one-way. They are additive by
convention — do not ship a destructive migration without a paired backup.

## Cutover from the Mac

1. Deploy and verify on the VPS while the Mac cron keeps running — jobs are
   idempotent (`SKIP LOCKED`, dedupe keys), double execution is safe.
2. Confirm VPS `ops.job_runs` show `trigger: cron` runs succeeding.
3. Remove the Mac crontab. The local DB remains the live one until the DNS/DSN
   switch; the VPS services point wherever `LOTTERY_DATABASE_*` says.

## Backups / restore

Unchanged — `backup_postgresql`, `backup_raw_storage`, `verify_backups` run as
platform jobs (02:00–03:00) and write to the mounted volume. Restore with
`scripts/restore_postgresql.sh`; it was verified end-to-end (see OPERATIONS.md).
