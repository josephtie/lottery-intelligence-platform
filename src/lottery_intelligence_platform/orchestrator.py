"""Job handlers for the draw orchestration pipeline.

Cron only enqueues/executes job runs; the chain DRAW_DETECTED -> FREEZE ->
SETTLEMENT -> METRICS is driven by draw/job state, so a provider delay or a
crash cannot break the pipeline — unfinished work is simply retried.
"""

from __future__ import annotations

import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from lottery_intelligence_platform.backfill import BackfillWindow, collect_result_window
from lottery_intelligence_platform.catalog import ensure_lotobonheur_catalog
from lottery_intelligence_platform.collectors.lotobonheur import (
    LotobonheurResultCollector,
    ResultValidationRules,
)
from lottery_intelligence_platform.draw_registry import DrawRegistry
from lottery_intelligence_platform.storage import raw_object_store_from_environment
from lottery_intelligence_platform.scheduler import (
    JobRun,
    emit_event,
    enqueue_run,
)
from lottery_intelligence_platform.settlement import settle_pending_draws

TZ = ZoneInfo("Africa/Abidjan")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _alert(connection: Any, code: str, severity: str, details: Mapping[str, Any]) -> None:
    from lottery_intelligence_platform.settlement import _raise_alert

    _raise_alert(connection, code=code, severity=severity, details=details)


def handle_collect_results(connection: Any, run: JobRun) -> Mapping[str, Any]:
    """Collect the recent results window and register any new draws.

    Emits DRAW_DETECTED / NO_NEW_DRAW, DRAW_VALIDATED, DRAW_FROZEN events and
    enqueues a settlement run for each newly frozen draw.
    """
    lookback = int(run.details.get("lookback_days") or 7)
    end = date.today()
    window = BackfillWindow(end - timedelta(days=lookback), end)

    catalog = ensure_lotobonheur_catalog(connection, data_coverage_start=window.start_date)
    rules = ResultValidationRules.from_game_version(connection, catalog.game_version_id)
    collector = LotobonheurResultCollector(rules=rules)
    raw_store = raw_object_store_from_environment()
    registry = DrawRegistry(
        connection,
        game_id=catalog.game_id,
        game_version_id=catalog.game_version_id,
        source_id=catalog.source_id,
        auto_create_draw_types=True,
    )
    result = collect_result_window(
        collector, connection, raw_store,
        source_id=catalog.source_id, window=window,
        draw_registry=registry, pause_seconds=0,
    )

    new_draws: list[str] = []
    for _, registrations in result.registrations:
        for registration in registrations:
            payload = {
                "draw_id": str(registration.draw_id),
                "status": registration.status,
                "window": [window.start_date.isoformat(), window.end_date.isoformat()],
            }
            if registration.status == "FROZEN":
                new_draws.append(str(registration.draw_id))
                for event_type in ("DRAW_DETECTED", "DRAW_VALIDATED", "DRAW_FROZEN"):
                    emit_event(connection, event_type, payload, job_run_id=run.job_run_id)
                enqueue_run(
                    connection, "settle_pending_draws",
                    idempotency_key=f"settle-draw-{registration.draw_id}",
                    details={"trigger": "DRAW_FROZEN", "draw_id": str(registration.draw_id)},
                )
            elif registration.status == "CONFLICT":
                emit_event(connection, "DATA_CONFLICT", payload, job_run_id=run.job_run_id)
                _alert(connection, "DATA_CONFLICT", "CRITICAL", payload)

    for failure in result.failures:
        _alert(
            connection, "COLLECT_FAILURE", "WARNING",
            {"month_year": failure.month_year, "error_type": failure.error_type},
        )
    if not new_draws:
        emit_event(
            connection, "NO_NEW_DRAW",
            {"window": [window.start_date.isoformat(), window.end_date.isoformat()]},
            job_run_id=run.job_run_id,
        )
    return {
        "window": [window.start_date.isoformat(), window.end_date.isoformat()],
        "observations": len(result.observations),
        "new_draws": new_draws,
        "conflicts": len(result.conflicting_observations),
        "failures": len(result.failures),
    }


def handle_settle_pending_draws(connection: Any, run: JobRun) -> Mapping[str, Any]:
    counts = settle_pending_draws(connection, job_run_id=run.job_run_id)
    if counts["settled"] == 0 and counts["skipped"] == 0:
        emit_event(connection, "NOTHING_TO_SETTLE", {}, job_run_id=run.job_run_id)
    return counts


def handle_daily_research_summary(connection: Any, run: JobRun) -> Mapping[str, Any]:
    row = connection.execute(
        """SELECT
             (SELECT COUNT(*) FROM research.prediction_outcomes
              WHERE settled_at::date = CURRENT_DATE) AS settled_today,
             (SELECT COUNT(*) FROM core.draws
              WHERE status = 'SETTLED'
                AND EXISTS (SELECT 1 FROM ops.job_events e
                            WHERE e.payload->>'draw_id' = draws.draw_id::text
                              AND e.event_type = 'PREDICTIONS_SETTLED'
                              AND e.occurred_at::date = CURRENT_DATE)) AS draws_settled_today,
             (SELECT COUNT(*) FROM research.predictions WHERE status = 'PENDING') AS pending_predictions,
             (SELECT COUNT(*) FROM research.predictions WHERE status = 'LOCKED') AS locked_predictions,
             (SELECT COUNT(*) FROM ops.alerts WHERE acknowledged_at IS NULL) AS open_alerts"""
    ).fetchone()
    summary = {
        "settled_today": row[0], "draws_settled_today": row[1],
        "pending_predictions": row[2], "locked_predictions": row[3],
        "open_alerts": row[4],
    }
    emit_event(connection, "RESEARCH_SUMMARY", summary, job_run_id=run.job_run_id)
    return summary


def handle_weekly_research_report(connection: Any, run: JobRun) -> Mapping[str, Any]:
    rows = connection.execute(
        """SELECT mv.model_code, COUNT(*) AS settled,
                  AVG(o.hit_count) AS mean_hits
           FROM research.prediction_outcomes o
           JOIN research.predictions p ON p.prediction_id = o.prediction_id
           JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
           WHERE o.settled_at > CURRENT_TIMESTAMP - interval '7 days'
           GROUP BY mv.model_code"""
    ).fetchall()
    report = {
        "models": [
            {"model_code": r[0], "settled": r[1], "mean_hits": float(r[2])} for r in rows
        ],
    }
    emit_event(connection, "WEEKLY_REPORT", report, job_run_id=run.job_run_id)
    return report


def _run_script(connection: Any, run: JobRun, script: str) -> Mapping[str, Any]:
    completed = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / script)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600,
    )
    emit_event(
        connection,
        "BACKUP_FAILED" if completed.returncode else "BACKUP_DONE",
        {"script": script, "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]},
        job_run_id=run.job_run_id,
    )
    if completed.returncode:
        _alert(connection, "BACKUP_FAILED", "CRITICAL", {"script": script, "stderr": completed.stderr[-1000:]})
        raise RuntimeError(f"{script} failed with exit code {completed.returncode}")
    return {"script": script, "stdout": completed.stdout[-2000:]}


def handle_backup_postgresql(connection: Any, run: JobRun) -> Mapping[str, Any]:
    return _run_script(connection, run, "backup_postgresql.sh")


def handle_backup_raw_storage(connection: Any, run: JobRun) -> Mapping[str, Any]:
    return _run_script(connection, run, "backup_raw_storage.sh")


def handle_verify_backups(connection: Any, run: JobRun) -> Mapping[str, Any]:
    return _run_script(connection, run, "verify_backups.sh")


HANDLERS: dict[str, Callable[[Any, JobRun], Mapping[str, Any] | None]] = {
    "collect_results": handle_collect_results,
    "settle_pending_draws": handle_settle_pending_draws,
    "daily_research_summary": handle_daily_research_summary,
    "weekly_research_report": handle_weekly_research_report,
    "backup_postgresql": handle_backup_postgresql,
    "backup_raw_storage": handle_backup_raw_storage,
    "verify_backups": handle_verify_backups,
}


def orchestrator_health(connection: Any) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM ops.orchestrator_health").fetchone()
    columns = [d.name for d in connection.description]
    health = dict(zip(columns, row, strict=True))
    health["recent_failures"] = [
        {"code": r[0], "error": r[1], "at": r[2].isoformat() if r[2] else None}
        for r in connection.execute(
            """SELECT j.code, jr.last_error, jr.finished_at
               FROM ops.job_runs jr JOIN ops.jobs j ON j.job_id = jr.job_id
               WHERE jr.status IN ('FAILED', 'DEAD', 'RETRY_REQUIRED')
               ORDER BY jr.finished_at DESC NULLS LAST LIMIT 10"""
        ).fetchall()
    ]
    return health
