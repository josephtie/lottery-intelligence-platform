# Orchestration — temporal proof pipeline

## Principle

```
PREDICTION → LOCK → DRAW → VALIDATION → FREEZE → SETTLEMENT → PERFORMANCE → KNOWLEDGE
```

A prediction must exist **before** the result is known. The pipeline is
event-driven: cron only *triggers* work; each stage is driven by explicit
state and is idempotent, so a provider delay or a crash cannot break the
chain — unfinished work is retried, never restarted from scratch.

## Components

| Layer | Implementation |
|---|---|
| Scheduler | `ops.jobs` + `ops.job_runs` (durable queue, `SKIP LOCKED` claim), `ops.job_events` (append-only ledger) — `scheduler.py` |
| Collect | `collect_results` job → `LotobonheurResultCollector` + `BackfillWindow` (trailing N days) — `orchestrator.py` |
| Detect/Validate/Freeze | `DrawRegistry.register_result_batch` — dedupe by payload hash, `CONFLICT` versions, `draw_corrections`, `FROZEN` status |
| Lock | `settle_draw` lock stage: `PENDING → LOCKED` (or `INVALID` if created after `result_observed_at`, or `LEAKAGE_DETECTED`) — `settlement.py` |
| Settle | `research.prediction_outcomes` (hits + positional hits + Turbo variants), `research.prediction_scores` (compat) |
| Strategy | `research.strategy_settlements` per Turbo variant, scope `REALIZED` |
| Health | `ops.orchestrator_health` view + `orchestrator_cli.py health` |
| Alerts | `ops.alerts` (deduped), `ops.audit_events` |

## Event flow

```
collect_results (cron */5)
    │  raw payload stored (ingestion.raw_objects + collection_runs)
    ▼
DRAW_DETECTED ──(dedupe: same payload → UNCHANGED)── NO_NEW_DRAW
    ▼
DrawRegistry: validate → CONFIRMED → FROZEN        (conflict → draw_corrections + DATA_CONFLICT alert)
    ▼
settle_pending_draws enqueued (idempotency key per draw)
    ▼
settle_draw(draw)  [single transaction, FOR UPDATE on draw]
    ├─ PENDING preds → LOCKED (created_at < result_observed_at)
    │                → INVALID + audit (late / leakage)
    ├─ LOCKED preds  → prediction_outcomes + scores → SCORED
    ├─ strategy_version_id → strategy_settlements (4 turbo variants)
    └─ draw → SETTLED, events PREDICTIONS_SETTLED
```

## Recovery

- `job_runs.status`: `QUEUED → RUNNING → SUCCEEDED|FAILED|RETRY_REQUIRED|DEAD`
- `fail_run` schedules `next_retry_at` with exponential backoff (30s·2ⁿ, max 3 retries → `DEAD`).
- A crash inside `run_due` leaves the run `RUNNING`; the claim is re-done on
  next invocation only after manual reset or a stale-claim sweep (the run's
  handler is idempotent — re-execution is a no-op for completed stages).
- Per-draw settlement runs in its own transaction: one bad draw cannot
  poison the batch.

## Immutability

`research.guard_prediction_update()` (trigger): all content fields are
frozen at insert; `target_draw_id`/`locked_at` may be set during `PENDING`
only; status transitions are whitelisted. Violations raise
`IMMUTABLE_PREDICTION_VIOLATION`; the controlled amendment path
(`attempt_prediction_amendment`) converts them into `REJECTED` audit
events + alerts.

## Commands

```
python -m lottery_intelligence_platform.orchestrator_cli run-due          # claim + run due jobs
python -m lottery_intelligence_platform.orchestrator_cli run-job <code>   # enqueue + run one job
python -m lottery_intelligence_platform.orchestrator_cli health           # health screen JSON
```
