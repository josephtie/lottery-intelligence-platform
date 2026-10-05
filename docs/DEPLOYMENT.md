# VPS deployment

Status: **prepared, not deployed**. These artifacts let the application tier
run on any Docker host, independent of the Mac. Nothing here is live until the
steps below are executed and verified.

## Architecture

Two stateless services built from the root `Dockerfile`
(`infrastructure/vps/compose.yaml`):

| Service | Command | Role |
|---|---|---|
| `scheduler` | `orchestrator_cli run-scheduler` | replaces the macOS crontab: enqueues cron-due jobs (`enqueue_due`, Africa/Abidjan) and drains `ops.job_runs` every 30 s |
| `api` | `lottery_intelligence_platform.api --host 0.0.0.0` | read-only API + console |

State stays outside the stack: **PostgreSQL** and the **S3/MinIO raw store**
are external dependencies (`LOTTERY_DATABASE_*`, `LOTTERY_S3_*`). Use a managed
Postgres or run it as a separate container — it must not be a sibling service
in this compose file, so a torn-down stack never takes the data with it.

## Prerequisites on the VPS

- Docker + compose plugin
- PostgreSQL ≥ 15 reachable from the containers, with all migrations applied
  (`apply_migrations`) — including ≥ `0020`
- S3/MinIO reachable, bucket `lottery-raw`
- Backups volume `lottery-backups` mounted for `backup_postgresql` dumps
- Reverse proxy (nginx/Caddy) in front of the API if exposed beyond loopback —
  `LOTTERY_API_TOKEN` is then mandatory

## Deploy

```bash
git clone <repo> && cd lottery-intelligence-platform
cp infrastructure/vps/.env.example infrastructure/vps/.env   # fill it in
docker compose -f infrastructure/vps/compose.yaml --env-file infrastructure/vps/.env build
docker compose -f infrastructure/vps/compose.yaml --env-file infrastructure/vps/.env up -d
```

## Verify

```bash
docker compose ... ps                                  # both services healthy
docker compose ... exec scheduler python -m lottery_intelligence_platform.orchestrator_cli health
curl -H "Authorization: Bearer $LOTTERY_API_TOKEN" http://127.0.0.1:8080/api/health
# within ~5 min: collect_results runs appear in ops.job_runs via `cron:` keys
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
