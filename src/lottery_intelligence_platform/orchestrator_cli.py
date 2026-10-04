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
from lottery_intelligence_platform.scheduler import enqueue_run, ensure_jobs, run_due


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("LOTTERY_DATABASE_HOST", "localhost"),
        port=int(os.environ.get("LOTTERY_DATABASE_PORT", "5432")),
        dbname=os.environ.get("LOTTERY_DATABASE_NAME", "lottery_platform"),
        user=os.environ.get("LOTTERY_DATABASE_USER", "directus"),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draw orchestration scheduler")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-due", help="claim and run all due job runs")
    run_job = sub.add_parser("run-job", help="enqueue and run one job now")
    run_job.add_argument("code")
    run_job.add_argument("--key", help="idempotency key for the run")
    sub.add_parser("health", help="print orchestrator health JSON")
    return parser


def main() -> int:
    args = _parser().parse_args()
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    with _connect() as connection:
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
