"""PostgreSQL-backed durable job queue.

Cron only *triggers* work; the actual pipeline is event-driven through
``ops.job_runs`` (claimable via SELECT ... FOR UPDATE SKIP LOCKED) and
``ops.job_events`` (append-only ledger of DRAW_DETECTED, SETTLED, ...).

Recovery model: a crashed run is retried from its first unfinished step —
handlers are idempotent so re-executing a stage is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

RETRY_BACKOFF_BASE_SECONDS = 30.0
DEFAULT_JOB_DEFS: tuple[dict[str, Any], ...] = (
    {
        "code": "collect_results",
        "kind": "COLLECT",
        "schedule_cron": "*/5 * * * *",
        "config": {"lookback_days": 7},
    },
    {
        "code": "settle_pending_draws",
        "kind": "PIPELINE",
        "schedule_cron": "*/5 * * * *",
        "config": {},
    },
    {
        "code": "generate_predictions",
        "kind": "PIPELINE",
        "schedule_cron": "15,45 * * * *",
        "config": {"stake": 100},
    },
    {
        "code": "daily_research_summary",
        "kind": "REPORT",
        "schedule_cron": "0 23 * * *",
        "config": {},
    },
    {
        "code": "weekly_research_report",
        "kind": "REPORT",
        "schedule_cron": "30 23 * * 0",
        "config": {},
    },
    {
        "code": "audit_data_quality",
        "kind": "MAINTENANCE",
        "schedule_cron": "45 23 * * *",
        "config": {},
    },
    {
        "code": "export_evidence",
        "kind": "MAINTENANCE",
        "schedule_cron": "10 * * * *",
        "config": {},
    },
    {
        "code": "backup_postgresql",
        "kind": "BACKUP",
        "schedule_cron": "0 2 * * *",
        "config": {},
    },
    {
        "code": "backup_raw_storage",
        "kind": "BACKUP",
        "schedule_cron": "30 2 * * *",
        "config": {},
    },
    {
        "code": "verify_backups",
        "kind": "BACKUP",
        "schedule_cron": "0 3 * * *",
        "config": {},
    },
)


@dataclass(frozen=True, slots=True)
class JobRun:
    job_run_id: UUID
    job_id: UUID
    code: str
    status: str
    retry_count: int
    details: Mapping[str, Any]


def ensure_jobs(connection: Any, defs: tuple[dict[str, Any], ...] = DEFAULT_JOB_DEFS) -> int:
    """Idempotently register the default job definitions."""
    count = 0
    for spec in defs:
        connection.execute(
            """INSERT INTO ops.jobs (job_id, code, kind, schedule_cron, config)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (code) DO NOTHING""",
            (uuid4(), spec["code"], spec["kind"], spec["schedule_cron"], Jsonb(spec["config"])),
        )
        count += 1
    return count


def enqueue_run(
    connection: Any,
    code: str,
    *,
    idempotency_key: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> tuple[UUID, bool]:
    """Enqueue a run for a job. Returns (job_run_id, created).

    Idempotent: the same ``idempotency_key`` never creates two runs.
    """
    job = connection.execute(
        "SELECT job_id FROM ops.jobs WHERE code = %s", (code,)
    ).fetchone()
    if job is None:
        raise KeyError(f"unknown job code: {code}")
    job_id = job[0]
    key = idempotency_key or str(uuid4())
    row = connection.execute(
        """INSERT INTO ops.job_runs
               (job_run_id, job_id, idempotency_key, details)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (idempotency_key) DO NOTHING
           RETURNING job_run_id""",
        (uuid4(), job_id, key, Jsonb(dict(details or {}))),
    ).fetchone()
    if row is not None:
        return row[0], True
    existing = connection.execute(
        "SELECT job_run_id FROM ops.job_runs WHERE idempotency_key = %s", (key,)
    ).fetchone()
    return existing[0], False


def emit_event(
    connection: Any,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    *,
    job_run_id: UUID | None = None,
) -> None:
    connection.execute(
        """INSERT INTO ops.job_events (job_event_id, job_run_id, event_type, payload)
           VALUES (%s, %s, %s, %s)""",
        (uuid4(), job_run_id, event_type, Jsonb(dict(payload or {}))),
    )


def claim_next_run(connection: Any, *, worker: str = "orchestrator") -> JobRun | None:
    """Atomically claim the oldest runnable run (SKIP LOCKED for workers)."""
    row = connection.execute(
        """UPDATE ops.job_runs jr
           SET status = 'RUNNING', started_at = CURRENT_TIMESTAMP, claimed_by = %s
           WHERE jr.job_run_id = (
               SELECT j.job_run_id FROM ops.job_runs j
               JOIN ops.jobs jb ON jb.job_id = j.job_id
               WHERE j.status = 'QUEUED'
                  OR (j.status = 'RETRY_REQUIRED' AND j.next_retry_at <= CURRENT_TIMESTAMP)
               ORDER BY j.created_at
               FOR UPDATE OF j SKIP LOCKED
               LIMIT 1
           )
           RETURNING jr.job_run_id, jr.job_id, jr.retry_count, jr.details,
                     (SELECT code FROM ops.jobs WHERE job_id = jr.job_id)""",
        (worker,),
    ).fetchone()
    if row is None:
        return None
    return JobRun(row[0], row[1], row[4], "RUNNING", row[2], row[3])


def complete_run(connection: Any, job_run_id: UUID, *, details: Mapping[str, Any] | None = None) -> None:
    connection.execute(
        """UPDATE ops.job_runs
           SET status = 'SUCCEEDED', finished_at = CURRENT_TIMESTAMP,
               details = details || %s
           WHERE job_run_id = %s""",
        (Jsonb(dict(details or {})), job_run_id),
    )


def _backoff_seconds(retry_count: int) -> float:
    return RETRY_BACKOFF_BASE_SECONDS * (2 ** retry_count)


def fail_run(connection: Any, job_run_id: UUID, error: BaseException | str) -> str:
    """Mark a run failed; schedule retry or declare it DEAD.

    Returns the resulting status ('RETRY_REQUIRED' or 'DEAD').
    """
    row = connection.execute(
        "SELECT retry_count, max_retries FROM ops.job_runs WHERE job_run_id = %s",
        (job_run_id,),
    ).fetchone()
    retry_count, max_retries = row
    message = str(error)[:2000]
    if retry_count < max_retries:
        next_at = datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(retry_count))
        connection.execute(
            """UPDATE ops.job_runs
               SET status = 'RETRY_REQUIRED', retry_count = retry_count + 1,
                   last_error = %s, next_retry_at = %s, finished_at = CURRENT_TIMESTAMP
               WHERE job_run_id = %s""",
            (message, next_at, job_run_id),
        )
        return "RETRY_REQUIRED"
    connection.execute(
        """UPDATE ops.job_runs
           SET status = 'DEAD', retry_count = retry_count + 1,
               last_error = %s, finished_at = CURRENT_TIMESTAMP
           WHERE job_run_id = %s""",
        (message, job_run_id),
    )
    return "DEAD"


def _cron_field_matches(field: str, value: int, lo: int, hi: int) -> bool:
    """Match one cron field: `*`, `*/n`, `a`, `a,b,c`, `a-b`, `a-b/n`."""
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            start, end = (int(x) for x in part.split("-", 1))
        else:
            start = end = int(part)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def cron_is_due(schedule: str, moment: datetime) -> bool:
    """True if a 5-field cron spec fires at `moment` (minute granularity)."""
    fields = schedule.split()
    if len(fields) != 5:
        raise ValueError(f"unsupported cron spec: {schedule!r}")
    minute, hour, dom, month, dow = fields
    # Cron convention: when both dom and dow are restricted, EITHER matches.
    dom_restricted, dow_restricted = dom != "*", dow != "*"
    day_ok = (
        _cron_field_matches(dom, moment.day, 1, 31) if dom_restricted else True
    ) and (
        _cron_field_matches(dow, (moment.weekday() + 1) % 7, 0, 7) if dow_restricted else True
    )
    if dom_restricted and dow_restricted:
        day_ok = _cron_field_matches(dom, moment.day, 1, 31) or _cron_field_matches(
            dow, (moment.weekday() + 1) % 7, 0, 7)
    return (
        _cron_field_matches(minute, moment.minute, 0, 59)
        and _cron_field_matches(hour, moment.hour, 0, 23)
        and _cron_field_matches(month, moment.month, 1, 12)
        and day_ok
    )


def enqueue_due(connection: Any, moment: datetime, *, tz: str = "Africa/Abidjan") -> int:
    """Enqueue one run for each job whose cron fires at `moment` (in `tz`).

    Idempotent via a `cron:<code>:<minute>` idempotency key — a daemon tick or
    a restart never double-enqueues the same minute.
    """
    local = moment.astimezone(ZoneInfo(tz)).replace(second=0, microsecond=0)
    enqueued = 0
    for code, schedule in connection.execute(
        "SELECT code, schedule_cron FROM ops.jobs"
    ).fetchall():
        if schedule and cron_is_due(schedule, local):
            _, created = enqueue_run(
                connection, code,
                idempotency_key=f"cron:{code}:{local.isoformat()}",
                details={"trigger": "cron", "fire_at": local.isoformat()},
            )
            enqueued += created
    return enqueued


def run_due(
    connection: Any,
    handlers: Mapping[str, Callable[[Any, JobRun], Mapping[str, Any] | None]],
    *,
    worker: str = "orchestrator",
    max_runs: int = 32,
) -> dict[str, int]:
    """Claim and execute runnable runs. Each run executes in its own
    transaction so a crash leaves prior stages intact."""
    counts = {"succeeded": 0, "failed": 0}
    for _ in range(max_runs):
        # Claim, handler execution and outcome recording use separate
        # transactions: a mid-handler crash must leave the claim intact so
        # the failure can be recorded and the run retried.
        with connection.transaction():
            run = claim_next_run(connection, worker=worker)
        if run is None:
            break
        handler = handlers.get(run.code)
        try:
            with connection.transaction():
                result = handler(connection, run) if handler else None
        except Exception as exc:  # noqa: BLE001 - job failure must not kill the worker
            with connection.transaction():
                status = fail_run(connection, run.job_run_id, exc)
                emit_event(connection, "JOB_FAILED", {"code": run.code, "status": status, "error": str(exc)})
            counts["failed"] += 1
            continue
        with connection.transaction():
            complete_run(connection, run.job_run_id, details=result or {})
        counts["succeeded"] += 1
    return counts
