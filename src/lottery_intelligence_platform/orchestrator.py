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
from lottery_intelligence_platform.catalog import LotoBonheurCatalog, ensure_lotobonheur_catalog
from lottery_intelligence_platform.collectors.lotobonheur import (
    LotobonheurResultCollector,
    LotobonheurScheduleCollector,
    ResultValidationRules,
)
from lottery_intelligence_platform.draw_registry import DrawRegistry
from lottery_intelligence_platform.evidence_export import export_evidence
from lottery_intelligence_platform.prediction_generation import (
    ensure_default_cohort,
    generate_predictions,
)
from lottery_intelligence_platform.storage import raw_object_store_from_environment
from lottery_intelligence_platform.scheduler import (
    JobRun,
    emit_event,
    enqueue_run,
)
from lottery_intelligence_platform.settlement import settle_pending_draws

TZ = ZoneInfo("Africa/Abidjan")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_catalog(connection: Any, window: BackfillWindow):
    """Reuse the authoritative game_version (the one carrying the historical
    draws). A new version must only be created when the game's rules change —
    never as a function of the collection window."""
    row = connection.execute(
        """SELECT g.game_id, g.game_version_id, s.source_id,
                  COUNT(d.draw_id) AS draw_count
           FROM catalog.game_versions g
           JOIN ingestion.sources s ON s.code = 'lotobonheur_official'
           LEFT JOIN core.draws d ON d.game_version_id = g.game_version_id
           GROUP BY g.game_id, g.game_version_id, s.source_id
           ORDER BY draw_count DESC
           LIMIT 1"""
    ).fetchone()
    if row is not None and row[3] > 0:
        return LotoBonheurCatalog(
            source_id=row[2], game_id=row[0], game_version_id=row[1], version="canonical",
        )
    return ensure_lotobonheur_catalog(connection, data_coverage_start=window.start_date)


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

    catalog = _resolve_catalog(connection, window)
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


def handle_generate_predictions(connection: Any, run: JobRun) -> Mapping[str, Any]:
    """Record prospective predictions for upcoming draws.

    Best effort: tries to refresh the official schedule first so predictions
    target real EXPECTED draws; falls back to recently active draw types.
    """
    catalog = _resolve_catalog(connection, BackfillWindow.trailing_months(1))
    try:
        raw_store = raw_object_store_from_environment()
        schedule_collector = LotobonheurScheduleCollector()
        batch = schedule_collector.collect(connection, raw_store, source_id=catalog.source_id)
        registry = DrawRegistry(
            connection,
            game_id=catalog.game_id,
            game_version_id=catalog.game_version_id,
            source_id=catalog.source_id,
            auto_create_draw_types=True,
        )
        registry.register_schedule_batch(batch)
        emit_event(connection, "SCHEDULE_COLLECTED", {"observations": len(batch.validation.observations)}, job_run_id=run.job_run_id)
    except Exception as exc:  # noqa: BLE001 - schedule is a best-effort input
        emit_event(connection, "SCHEDULE_COLLECT_FAILED", {"error": str(exc)[:500]}, job_run_id=run.job_run_id)
        _alert(connection, "SCHEDULE_COLLECT_FAILED", "WARNING", {"error": str(exc)[:500]})

    ensure_default_cohort(connection)
    result = generate_predictions(connection)
    emit_event(
        connection, "PREDICTIONS_GENERATED",
        {"targets": result.targets, "created": result.created,
         "reused": result.reused, "failed": result.failed,
         "by_model": result.by_model},
        job_run_id=run.job_run_id,
    )
    return {
        "targets": result.targets, "created": result.created,
        "reused": result.reused, "failed": result.failed,
        "ineligible": result.ineligible,
    }


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
    """Prospective-only report built from the cohort metrics view.

    Denominators (eligible_pairs, generated, settled) come from the coverage
    ledger; economics from outcomes settled under the payout-rule version in
    force at settlement. Backtest/walk-forward metrics are never mixed in.
    """
    rows = connection.execute(
        """SELECT cohort_code, cohort_version, model_code, draw_type,
                  eligible_pairs, generated, absent_total, settled,
                  settlement_rate, mean_hits, hits_first_2, turbo
           FROM research.prospective_metrics
           ORDER BY cohort_code, model_code, draw_type"""
    ).fetchall()
    report = {
        "scope": "PROSPECTIVE",
        "cells": [
            {
                "cohort": r[0], "cohort_version": r[1],
                "model_code": r[2], "draw_type": r[3],
                "eligible_pairs": r[4], "generated": r[5],
                "absent": r[6], "settled": r[7],
                "settlement_rate": float(r[8]) if r[8] is not None else None,
                "mean_hits": float(r[9]) if r[9] is not None else None,
                "turbo_2_hits": r[10],
                "turbo": r[11],
            }
            for r in rows
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


def handle_audit_data_quality(connection: Any, run: JobRun) -> Mapping[str, Any]:
    """Daily data-quality sweep: anomaly rollup + collection success rate.

    Alerts on missing results (EXPECTED draws past their date without a valid
    version) and on structural anomalies (wrong count, duplicates, range).
    """
    # Stale pending predictions: projected target dates that never became real
    # draws would stay PENDING forever and inflate denominators. Past a 2-day
    # grace (collection lag) with no draw row, mark INVALID + audit.
    stale = connection.execute(
        """UPDATE research.predictions p SET status = 'INVALID'
           WHERE p.status = 'PENDING'
             AND p.scheduled_date < CURRENT_DATE - 2
             AND NOT EXISTS (
                 SELECT 1 FROM core.draws d
                 WHERE d.draw_type_id = p.draw_type_id
                   AND d.scheduled_date = p.scheduled_date)
           RETURNING p.prediction_id"""
    ).fetchall()
    if stale:
        emit_event(
            connection, "STALE_PREDICTIONS_INVALIDATED",
            {"count": len(stale),
             "prediction_ids": [str(r[0]) for r in stale]},
            job_run_id=run.job_run_id,
        )
        _alert(connection, "STALE_PREDICTIONS", "WARNING",
               {"count": len(stale)})
    anomalies = connection.execute(
        """SELECT draw_type, draws, missing_result, wrong_count,
                  duplicate_number, number_out_of_range, anomalous
           FROM core.draw_quality_summary WHERE anomalous > 0"""
    ).fetchall()
    missing = sum(r[2] for r in anomalies)
    structural = sum(r[6] - r[2] for r in anomalies)
    coll = connection.execute(
        """SELECT source, day, runs, succeeded, success_rate, duplicate_rate
           FROM ingestion.collection_quality
           WHERE day >= CURRENT_DATE - 1 ORDER BY day DESC"""
    ).fetchall()
    report = {
        "anomalous_draw_types": len(anomalies),
        "missing_results": missing,
        "structural_anomalies": structural,
        "stale_invalidated": len(stale),
        "collection_days": [
            {"source": r[0], "day": str(r[1]), "runs": r[2],
             "succeeded": r[3], "success_rate": float(r[4] or 0),
             "duplicate_rate": float(r[5] or 0)}
            for r in coll
        ],
    }
    emit_event(connection, "DATA_QUALITY_REPORT", report, job_run_id=run.job_run_id)
    if missing:
        _alert(connection, "MISSING_DRAWS", "WARNING",
               {"count": missing, "draw_types": [r[0] for r in anomalies if r[2]]})
    else:
        _auto_resolve(connection, run, "MISSING_DRAWS")
    if structural:
        _alert(connection, "DRAW_QUALITY_ANOMALY", "WARNING",
               {"count": structural,
                "detail": [
                    {"draw_type": r[0], "wrong_count": r[3],
                     "duplicate": r[4], "out_of_range": r[5]}
                    for r in anomalies if r[6] - r[2] > 0
                ]})
    else:
        _auto_resolve(connection, run, "DRAW_QUALITY_ANOMALY")
    return report


def _auto_resolve(connection: Any, run: JobRun, code: str) -> None:
    """Acknowledge open alerts of `code` once the condition has cleared.

    Alert content is immutable; `acknowledged_at` is the resolution marker.
    An event preserves which alerts were auto-resolved and by which run."""
    resolved = connection.execute(
        """UPDATE ops.alerts SET acknowledged_at = CURRENT_TIMESTAMP
           WHERE code = %s AND acknowledged_at IS NULL
           RETURNING alert_id""",
        (code,),
    ).fetchall()
    if resolved:
        emit_event(
            connection, "ALERT_AUTO_RESOLVED",
            {"code": code, "alert_ids": [str(r[0]) for r in resolved]},
            job_run_id=run.job_run_id,
        )


def handle_export_evidence(connection: Any, run: JobRun) -> Mapping[str, Any]:
    """Ship evidence tables to the raw store (hourly). Idempotent:
    unchanged content hashes to the same object key."""
    store = raw_object_store_from_environment()
    return export_evidence(connection, store)


def handle_backup_postgresql(connection: Any, run: JobRun) -> Mapping[str, Any]:
    return _run_script(connection, run, "backup_postgresql.sh")


def handle_backup_raw_storage(connection: Any, run: JobRun) -> Mapping[str, Any]:
    return _run_script(connection, run, "backup_raw_storage.sh")


def handle_verify_backups(connection: Any, run: JobRun) -> Mapping[str, Any]:
    return _run_script(connection, run, "verify_backups.sh")


HANDLERS: dict[str, Callable[[Any, JobRun], Mapping[str, Any] | None]] = {
    "collect_results": handle_collect_results,
    "settle_pending_draws": handle_settle_pending_draws,
    "generate_predictions": handle_generate_predictions,
    "daily_research_summary": handle_daily_research_summary,
    "weekly_research_report": handle_weekly_research_report,
    "audit_data_quality": handle_audit_data_quality,
    "export_evidence": handle_export_evidence,
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
