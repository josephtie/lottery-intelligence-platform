# Recovery

## Failure model

Every stage is either idempotent or transactional:

| Failure point | State left | Recovery |
|---|---|---|
| After raw fetch, before registration | `collection_runs` + `raw_objects` + `collection_events` persisted | Next collect re-registers (payload hash dedupe → `UNCHANGED`) |
| During registration | transaction rolled back | Observations re-registered on next collect |
| After freeze, before settlement | draw `FROZEN`, predictions `PENDING` | `settle_pending_draws` picks the draw up |
| Mid-settlement | whole transaction rolled back | `settle_draw` retries; already-locked predictions stay `LOCKED` and resume at scoring |
| After settlement | draw `SETTLED` | second call returns `ALREADY_SETTLED` |
| Job crash | run `FAILED → RETRY_REQUIRED` (`next_retry_at`, backoff 30s·2ⁿ) | `run-due` re-claims after backoff; `DEAD` after `max_retries` |

## Sweeping stuck runs

A run claimed but never finished stays `RUNNING`. To requeue crashed work
(operator action, audited):

```sql
UPDATE ops.job_runs
SET status = 'RETRY_REQUIRED', next_retry_at = CURRENT_TIMESTAMP
WHERE status = 'RUNNING' AND started_at < CURRENT_TIMESTAMP - interval '30 minutes';
```

## Backups

- `backup_postgresql` → `backups/postgres/lottery_<utc>.dump` (custom format, restore with `pg_restore`)
- `backup_raw_storage` → mirror of the raw-object bucket
- `verify_backups` → fails (alert `BACKUP_FAILED`) if the latest backup is missing, empty, or older than 36 h

Restore drill: `pg_restore --clean --if-exists -d lottery_platform <dump>`
then `apply_migrations()` to verify the schema chain end-to-end.
