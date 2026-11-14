"""Orchestrator entry point invoked by cron.

    python -m lottery_intelligence_platform.orchestrator_cli run-due
    python -m lottery_intelligence_platform.orchestrator_cli run-job collect_results
    python -m lottery_intelligence_platform.orchestrator_cli health
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from lottery_intelligence_platform.orchestrator import HANDLERS, orchestrator_health
from lottery_intelligence_platform.scheduler import (
    enqueue_due,
    enqueue_run,
    ensure_jobs,
    run_due,
)


def _connect(*, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("LOTTERY_DATABASE_HOST", "localhost"),
        port=int(os.environ.get("LOTTERY_DATABASE_PORT", "5432")),
        dbname=os.environ.get("LOTTERY_DATABASE_NAME", "lottery_platform"),
        user=os.environ.get("LOTTERY_DATABASE_USER", "directus"),
        autocommit=autocommit,
    )


def _run_scheduler(interval: int) -> int:
    """Daemon mode: enqueue cron-due jobs, then drain the queue, forever.

    Autocommit so each transaction() block in run_due commits independently;
    a crash mid-tick leaves claimed runs for the next tick to retry."""
    import time
    from datetime import datetime, timezone

    heartbeat = Path(os.environ.get(
        "LOTTERY_HEARTBEAT_FILE", "/tmp/scheduler_heartbeat"))
    connection = _connect(autocommit=True)
    ensure_jobs(connection)  # fresh database: register the default job specs
    while True:
        # Heartbeat before the tick: proves the loop is alive to the Docker
        # healthcheck even when the database is unreachable.
        try:
            heartbeat.write_text(datetime.now(timezone.utc).isoformat())
        except OSError:
            pass
        try:
            with connection.transaction():
                enqueued = enqueue_due(connection, datetime.now(timezone.utc))
            counts = run_due(connection, HANDLERS)
            if enqueued or any(counts.values()):
                print(json.dumps({"enqueued": enqueued, **counts}), flush=True)
        except Exception as exc:  # keep the daemon alive; next tick retries
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), flush=True)
            try:
                connection.rollback()
            except Exception:
                try:
                    connection.close()
                finally:
                    connection = _connect(autocommit=True)
        time.sleep(interval)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draw orchestration scheduler")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-due", help="claim and run all due job runs")
    sched = sub.add_parser("run-scheduler", help="loop run-due forever (service mode)")
    sched.add_argument("--interval", type=int, default=60,
                       help="seconds between ticks (default 60)")
    run_job = sub.add_parser("run-job", help="enqueue and run one job now")
    run_job.add_argument("code")
    run_job.add_argument("--key", help="idempotency key for the run")
    sub.add_parser("health", help="print orchestrator health JSON")
    sub.add_parser("register-lab-models",
                   help="register lab pickers and create the extended cohort version")
    sub.add_parser("migrate", help="apply pending SQL migrations")
    return parser


def main() -> int:
    args = _parser().parse_args()
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    if args.command == "run-scheduler":
        return _run_scheduler(args.interval)
    with _connect() as connection:
        if args.command == "migrate":
            from lottery_intelligence_platform.migrations import apply_migrations
            applied = apply_migrations(connection)
            connection.commit()
            print(json.dumps({"applied": applied}))
            return 0
        ensure_jobs(connection)
        connection.commit()
        if args.command == "run-due":
            counts = run_due(connection, HANDLERS)
            print(json.dumps(counts))
            return 0
        if args.command == "run-job":
            enqueue_run(
                connection, args.code,
                idempotency_key=args.key or f"manual-{args.code}-{os.getpid()}",
                details={"trigger": "manual"},
            )
            connection.commit()
            counts = run_due(connection, HANDLERS)
            print(json.dumps(counts))
            return 0
        if args.command == "health":
            print(json.dumps(orchestrator_health(connection), default=str, indent=2))
            return 0
        if args.command == "register-lab-models":
            from lottery_intelligence_platform.prediction_generation import (
                register_lab_cohort,
            )
            result = register_lab_cohort(connection)
            connection.commit()
            print(json.dumps(result, default=str))
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
