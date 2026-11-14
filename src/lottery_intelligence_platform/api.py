"""Read-only HTTP API over the platform's live views.

Stdlib-only (http.server): no web dependency, localhost bind by default.
Endpoints expose exactly what the research views expose — prospective
metrics, predictions, coverage, findings, outcomes, job health — never
write paths.

    PYTHONPATH=src python -m lottery_intelligence_platform.api --port 8090
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import psycopg

from lottery_intelligence_platform import (
    calling_image,
    digital_root_statistics,
    game_temporal,
    lab_matrix,
    meta_ensemble,
    structure_analysis,
    structure_map,
    turbo2_view,
)
from lottery_intelligence_platform.dependence import pair_dependence_tests
from lottery_intelligence_platform.lab_coverage import (
    CoverageRuleError, coverage_laboratory, resolve_payout_rule)
from lottery_intelligence_platform.lab_matrix import fdr_bh
from lottery_intelligence_platform.lab_simulation import simulate_bankroll
from lottery_intelligence_platform.prediction_generation import PICKERS
from lottery_intelligence_platform.settlement import (
    DEFAULT_TURBO_STAKE,
    _payout_multipliers,
    positional_hit_counts,
    turbo_settlement,
)
from lottery_intelligence_platform.stats import chi_square_sf

DEFAULT_DSN = "host=localhost port=5432 dbname=lottery_platform user=directus"


def _env_dsn() -> str:
    """Build the DSN from LOTTERY_DATABASE_* parts (libpq reads PGPASSWORD)."""
    if not os.environ.get("LOTTERY_DATABASE_HOST"):
        return DEFAULT_DSN
    parts = [
        f"host={os.environ.get('LOTTERY_DATABASE_HOST')}",
        f"port={os.environ.get('LOTTERY_DATABASE_PORT', '5432')}",
        f"dbname={os.environ.get('LOTTERY_DATABASE_NAME', 'lottery_platform')}",
        f"user={os.environ.get('LOTTERY_DATABASE_USER', 'directus')}",
    ]
    password = os.environ.get("LOTTERY_DATABASE_PASSWORD") or os.environ.get("PGPASSWORD")
    if password:
        parts.append(f"password={password}")
    return " ".join(parts)


def _default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"not JSON serializable: {type(obj)}")


ROUTES: dict[str, str] = {
    "/api/health": """
        SELECT
          (SELECT count(*) FROM ops.alerts WHERE acknowledged_at IS NULL) AS open_alerts,
          (SELECT count(*) FROM research.predictions WHERE status='PENDING') AS pending_predictions,
          (SELECT count(*) FROM research.predictions WHERE status='SCORED') AS scored_predictions,
          (SELECT count(*) FROM ops.job_runs
           WHERE finished_at > now() - interval '24 hours') AS runs_24h,
          (SELECT count(*) FROM ops.job_runs
           WHERE finished_at > now() - interval '24 hours' AND status='FAILED') AS failed_24h,
          (SELECT max(finished_at) FROM ops.job_runs) AS last_run
    """,
    "/api/prospective/metrics": """
        SELECT cohort_code, cohort_version, model_code, draw_type,
               eligible_pairs, generated, missing, failed, ineligible,
               absent_total, pending, locked, invalid, settled,
               settlement_rate, mean_hits,
               hits_first_1, hits_first_2, hits_first_3, hits_first_4, hits_first_5,
               turbo, historical_draws, low_power
        FROM research.prospective_metrics
        ORDER BY cohort_code, model_code, draw_type
    """,
    "/api/prospective/coverage": """
        SELECT status, reason, count(*) AS n
        FROM research.prediction_coverage
        GROUP BY status, reason ORDER BY status, n DESC
    """,
    "/api/power": """
        SELECT display_name AS draw_type, settled_draws, first_draw,
               meets_power_threshold
        FROM research.draw_type_power ORDER BY settled_draws DESC
    """,
    "/api/draws": """
        SELECT d.draw_id, dt.display_name AS draw_type, d.scheduled_date,
               d.status, v.validation_status,
               (SELECT jsonb_agg(n.number ORDER BY n.position)
                FROM core.draw_numbers n
                WHERE n.draw_version_id = v.draw_version_id
                  AND n.number_role = 'WINNING') AS winning_numbers
        FROM core.draws d
        JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
        LEFT JOIN LATERAL (
            SELECT draw_version_id, validation_status FROM core.draw_versions
            WHERE draw_id = d.draw_id ORDER BY version_number DESC LIMIT 1
        ) v ON true
        WHERE d.status IN ('FROZEN', 'SETTLED', 'EXPECTED')
        ORDER BY d.scheduled_date DESC LIMIT 100
    """,
    "/api/datasets": """
        SELECT d.code, dv.version_number, dv.cutoff_at,
               (SELECT count(*) FROM datasets.dataset_members m
                WHERE m.dataset_version_id = dv.dataset_version_id) AS members,
               dv.manifest_sha256
        FROM datasets.dataset_versions dv
        JOIN datasets.datasets d ON d.dataset_id = dv.dataset_id
        ORDER BY dv.created_at DESC
    """,
    "/api/models": """
        SELECT mv.code, mv.version, mv.family, mv.definition,
               (SELECT count(*) FROM research.predictions p
                WHERE p.model_version_id = mv.model_version_id) AS predictions,
               (SELECT count(*) FROM research.prediction_outcomes o
                JOIN research.predictions p ON p.prediction_id = o.prediction_id
                WHERE p.model_version_id = mv.model_version_id) AS settled
        FROM research.model_versions mv ORDER BY mv.code, mv.version
    """,
    "/api/hypotheses": """
        SELECT h.hypothesis_id, h.code, h.title, h.status, h.statement,
               h.created_at,
               count(f.finding_id) AS findings,
               max(f.created_at) AS last_finding,
               count(f.finding_id) FILTER (WHERE f.status = 'SUPPORTED') AS supported,
               count(f.finding_id) FILTER (WHERE f.status = 'REJECTED') AS rejected,
               count(f.finding_id) FILTER (WHERE f.status = 'INCONCLUSIVE') AS inconclusive
        FROM research.hypotheses h
        LEFT JOIN research.findings f ON f.hypothesis_id = h.hypothesis_id
        GROUP BY h.hypothesis_id, h.code, h.title, h.status, h.statement, h.created_at
        ORDER BY last_finding DESC NULLS LAST, h.created_at DESC
    """,
    "/api/findings": """
        SELECT f.finding_id, h.title AS hypothesis, f.status, f.conclusion,
               f.evidence, f.created_at
        FROM research.findings f
        JOIN research.hypotheses h ON h.hypothesis_id = f.hypothesis_id
        ORDER BY f.created_at DESC
    """,
    "/api/outcomes": """
        SELECT o.outcome_id, mv.code AS model_code, dt.display_name AS draw_type,
               p.scheduled_date, o.hit_count, o.positional_hits,
               o.metrics -> 'turbo' AS turbo, o.settled_at
        FROM research.prediction_outcomes o
        JOIN research.predictions p ON p.prediction_id = o.prediction_id
        JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
        JOIN core.draws d ON d.draw_id = o.draw_id
        JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
        ORDER BY o.settled_at DESC LIMIT 200
    """,
    "/api/overview": """
        SELECT
          (SELECT count(*) FROM core.draws WHERE status = 'SETTLED') AS settled_draws,
          (SELECT count(*) FROM core.draws) AS total_draws,
          (SELECT min(scheduled_date) FROM core.draws) AS first_draw,
          (SELECT max(scheduled_date) FROM core.draws WHERE status = 'SETTLED') AS last_draw,
          (SELECT count(DISTINCT draw_type_id) FROM core.draws WHERE status = 'SETTLED') AS draw_types,
          (SELECT count(*) FROM research.predictions) AS predictions_total,
          (SELECT count(*) FROM research.predictions WHERE status = 'PENDING') AS pending,
          (SELECT count(*) FROM research.predictions WHERE status = 'SCORED') AS scored,
          (SELECT count(*) FROM ops.alerts WHERE acknowledged_at IS NULL) AS open_alerts,
          (SELECT count(*) FROM ops.job_runs
           WHERE finished_at > now() - interval '24 hours' AND status = 'FAILED') AS failed_24h,
          (SELECT max(finished_at) FROM ops.job_runs) AS last_job_run
    """,
    "/api/jobs": """
        SELECT r.job_run_id, j.code, r.status, r.created_at, r.started_at,
               r.finished_at, r.details, r.last_error
        FROM ops.job_runs r JOIN ops.jobs j ON j.job_id = r.job_id
        ORDER BY r.created_at DESC LIMIT 100
    """,
    "/api/alerts": """
        SELECT alert_id, code, severity, entity_type, details, dedupe_key,
               raised_at, acknowledged_at
        FROM ops.alerts ORDER BY raised_at DESC LIMIT 200
    """,
    "/api/quality": """
        SELECT * FROM core.draw_quality_summary ORDER BY draw_type
    """,
    "/api/quality/anomalies": """
        SELECT draw_type, scheduled_date, draw_status, validation_status,
               missing_result, wrong_count, duplicate_number, number_out_of_range
        FROM core.draw_quality
        WHERE missing_result OR wrong_count OR duplicate_number OR number_out_of_range
        ORDER BY scheduled_date DESC LIMIT 200
    """,
    "/api/quality/collection": """
        SELECT * FROM ingestion.collection_quality ORDER BY day DESC LIMIT 60
    """,
    "/api/reconciliation": """
        SELECT c.comparison_id, c.outcome, o.draw_date, o.draw_name,
               c.primary_numbers, c.secondary_numbers, c.compared_at
        FROM ingestion.source_comparisons c
        JOIN ingestion.secondary_observations o ON o.observation_id = c.observation_id
        ORDER BY c.compared_at DESC LIMIT 200
    """,
    "/api/reconciliation/summary": """
        SELECT outcome, count(*) AS n, max(compared_at) AS latest
        FROM ingestion.source_comparisons GROUP BY outcome
    """,
    "/api/turbo/variants": """
        WITH flat AS (
            SELECT t.key AS variant,
                   (t.value ->> 'stake')::numeric AS stake,
                   (t.value ->> 'payout')::numeric AS payout,
                   (t.value ->> 'net')::numeric AS net,
                   (t.value ->> 'hit')::boolean AS hit,
                   (t.value ->> 'multiplier')::numeric AS multiplier
            FROM research.prediction_outcomes o, jsonb_each(o.metrics -> 'turbo') t
        )
        SELECT variant, multiplier,
               count(*) AS bets,
               count(*) FILTER (WHERE hit) AS wins,
               sum(stake) AS total_stake,
               sum(payout) AS gross_payout,
               sum(net) AS net,
               CASE WHEN sum(stake) > 0
                    THEN sum(net) / sum(stake) END AS roi
        FROM flat GROUP BY variant, multiplier ORDER BY variant
    """,
    "/api/turbo/summary": """
        SELECT count(*) AS evaluated,
               count(DISTINCT o.draw_id) AS draws,
               sum((o.metrics ->> 'stake')::numeric) AS total_stake,
               sum((t.value ->> 'payout')::numeric) AS gross_payout,
               sum((t.value ->> 'net')::numeric) AS net
        FROM research.prediction_outcomes o,
             jsonb_each(o.metrics -> 'turbo') t
        WHERE t.key = 'turbo_2'
    """,
    "/api/turbo/models": """
        WITH flat AS (
            SELECT mv.code AS model_code, t.key AS variant,
                   (t.value ->> 'hit')::boolean AS hit,
                   (t.value ->> 'stake')::numeric AS stake,
                   (t.value ->> 'net')::numeric AS net
            FROM research.prediction_outcomes o
            JOIN research.predictions p ON p.prediction_id = o.prediction_id
            JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id,
            jsonb_each(o.metrics -> 'turbo') t
        )
        SELECT model_code, variant, count(*) AS bets,
               count(*) FILTER (WHERE hit) AS wins,
               sum(stake) AS total_stake, sum(net) AS net,
               CASE WHEN sum(stake) > 0 THEN sum(net) / sum(stake) END AS roi
        FROM flat GROUP BY model_code, variant
        ORDER BY model_code, variant
    """,
    "/api/turbo/results": """
        SELECT o.outcome_id, d.scheduled_date, dt.display_name AS draw_type,
               mv.code AS model_code, o.predicted_numbers, o.winning_numbers,
               o.hit_count, o.positional_hits, o.metrics -> 'turbo' AS turbo,
               o.settled_at
        FROM research.prediction_outcomes o
        JOIN research.predictions p ON p.prediction_id = o.prediction_id
        JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
        JOIN core.draws d ON d.draw_id = o.draw_id
        JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
        ORDER BY d.scheduled_date DESC, mv.code
    """,
    "/api/turbo/next": """
        SELECT p.prediction_id, dt.display_name AS draw_type,
               COALESCE(d.scheduled_date, p.scheduled_date) AS scheduled_date,
               mv.code AS model_code, mv.version AS model_version,
               p.predicted_numbers, p.status, p.stake, p.created_at, p.locked_at
        FROM research.predictions p
        JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
        JOIN catalog.draw_types dt ON dt.draw_type_id = p.draw_type_id
        LEFT JOIN core.draws d ON d.draw_id = p.target_draw_id
        WHERE p.status IN ('PENDING', 'LOCKED')
        ORDER BY COALESCE(d.scheduled_date, p.scheduled_date), dt.display_name, mv.code
        LIMIT 500
    """,
    "/api/lab/draw-types": """
        SELECT DISTINCT ON (dt.display_name) dt.code, dt.display_name,
               (SELECT count(*) FROM core.draws d
                WHERE d.draw_type_id = dt.draw_type_id AND d.status = 'SETTLED') AS settled_draws,
               (SELECT max(d.scheduled_date) FROM core.draws d
                WHERE d.draw_type_id = dt.draw_type_id AND d.status = 'SETTLED') AS last_draw
        FROM catalog.draw_types dt
        ORDER BY dt.display_name, dt.draw_type_id
    """,
    "/api/lab/draw-types-on-date": """
        SELECT DISTINCT ON (dt.display_name) dt.code, dt.display_name,
               d.status AS draw_status
        FROM core.draws d
        JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
        WHERE d.scheduled_date = %(date)s
        ORDER BY dt.display_name, d.status DESC
    """,
    "/api/cohorts": """
        SELECT cv.cohort_version_id, c.code, c.display_name, cv.version,
               cv.definition, cv.effective_from, cv.created_at,
               (SELECT count(*) FROM research.prospective_cohort_members m
                WHERE m.cohort_version_id = cv.cohort_version_id) AS members
        FROM research.prospective_cohort_versions cv
        JOIN research.prospective_cohorts c ON c.cohort_id = cv.cohort_id
        ORDER BY cv.created_at DESC
    """,
    # AGENT SYSTEM ENDPOINTS
    "/api/agents": """
        SELECT * FROM edge_lab.agent_summary ORDER BY code
    """,
    "/api/agents/active": """
        SELECT * FROM edge_lab.agent_summary WHERE status = 'ACTIVE' ORDER BY code
    """,
    "/api/agents/performance": """
        SELECT * FROM edge_lab.agent_market_performance ORDER BY agent_code, draw_type
    """,
    "/api/agents/memory-summary": """
        SELECT * FROM edge_lab.agent_memory_summary ORDER BY agent_code
    """,
    "/api/agents/decisions": """
        SELECT ad.decision_id, a.code AS agent_code, dt.display_name AS draw_type,
               ad.decision_type, ad.selected_numbers, ad.stake_amount,
               ad.reasoning, ad.confidence_score, ad.created_at, ad.sealed_at,
               do.outcome_type, do.net_result, do.settled_at
        FROM edge_lab.agent_decisions ad
        JOIN edge_lab.agents a ON a.agent_id = ad.agent_id
        JOIN catalog.draw_types dt ON dt.draw_type_id = ad.draw_type_id
        LEFT JOIN edge_lab.decision_outcomes do ON do.decision_id = ad.decision_id
        ORDER BY ad.sealed_at DESC
        LIMIT 100
    """,
    "/api/agents/reflections": """
        SELECT ar.reflection_id, a.code AS agent_code, ar.reflection_type,
               ar.content, ar.context, ar.action_taken, ar.next_steps, ar.created_at
        FROM edge_lab.agent_reflections ar
        JOIN edge_lab.agents a ON a.agent_id = ar.agent_id
        ORDER BY ar.created_at DESC
        LIMIT 50
    """,
    "/api/collective/knowledge": """
        SELECT * FROM edge_lab.collective_summary ORDER BY knowledge_type, proof_level
    """,
    "/api/collective/knowledge-list": """
        SELECT ck.knowledge_id, ck.code, ck.title, ck.knowledge_type, ck.proof_level,
               a.code AS originating_agent, ck.validation_count, ck.rejection_count,
               ck.created_at, ck.updated_at
        FROM edge_lab.collective_knowledge ck
        JOIN edge_lab.agents a ON a.agent_id = ck.originating_agent_id
        ORDER BY ck.validation_count DESC, ck.updated_at DESC
        LIMIT 50
    """,
    # DIGITAL ROOT ANALYZER ENDPOINTS
    "/api/digital-root/relations": """
        SELECT relation_id, relation_type, source_root, target_root,
               status, discovery_date, total_observations, successful_predictions,
               current_success_rate, baseline_success_rate,
               observation_window_days, statistical_significance
        FROM research.digital_root_relations
        WHERE status IN ('OBSERVING', 'CONFIRMED_TEMPORARY')
        ORDER BY current_success_rate DESC, discovery_date DESC
        LIMIT 100
    """,
    "/api/digital-root/relations/history": """
        SELECT relation_id, relation_type, source_root, target_root,
               status, discovery_date, total_observations, successful_predictions,
               current_success_rate, last_validation_date
        FROM research.digital_root_relations
        ORDER BY discovery_date DESC
        LIMIT 200
    """,
    "/api/digital-root/predictions": """
        SELECT p.prediction_id, p.draw_id, p.draw_type_id, p.scheduled_date,
               p.predicted_roots, p.turbo_variant, p.predicted_numbers,
               p.used_relations_count, p.winning_numbers, p.hit_count,
               p.turbo_hit, p.stake, p.payout, p.net_profit, p.roi,
               p.created_at, p.settled_at
        FROM research.digital_root_predictions p
        ORDER BY p.created_at DESC
        LIMIT 100
    """,
    "/api/digital-root/validation": """
        SELECT validation_id, draw_type_id, start_date, end_date,
               training_window_days, test_window_days, turbo_variant,
               total_predictions, total_hits, hit_rate,
               turbo_hits, turbo_hit_rate, total_stake, total_payout,
               total_net_profit, average_roi,
               baseline_hit_rate, baseline_turbo_hit_rate, baseline_roi,
               hit_rate_improvement_percent, turbo_improvement_percent,
               roi_improvement, statistically_significant
        FROM research.digital_root_validation
        ORDER BY created_at DESC
        LIMIT 50
    """,
    "/api/digital-root/summary": """
        SELECT
          (SELECT COUNT(*) FROM research.digital_root_relations
           WHERE status IN ('OBSERVING', 'CONFIRMED_TEMPORARY')) AS active_relations,
          (SELECT COUNT(*) FROM research.digital_root_relations
           WHERE status = 'CANDIDATE') AS candidate_relations,
          (SELECT COUNT(*) FROM research.digital_root_relations
           WHERE status = 'EXPIRED') AS expired_relations,
          (SELECT COUNT(*) FROM research.digital_root_predictions) AS total_predictions,
          (SELECT COUNT(*) FROM research.digital_root_predictions
           WHERE settled_at IS NOT NULL) AS settled_predictions,
          (SELECT AVG(turbo_hit)::FLOAT FROM research.digital_root_predictions
           WHERE settled_at IS NOT NULL) AS avg_turbo_hit_rate,
          (SELECT AVG(roi)::FLOAT FROM research.digital_root_predictions
           WHERE settled_at IS NOT NULL) AS avg_roi
    """,
    # DIGITAL ROOT STATISTICS ENDPOINTS
    "/api/digital-root-stats/games": """
        SELECT dt.draw_type_id, dt.display_name AS game_name,
               (SELECT COUNT(*) FROM core.draws d
                WHERE d.draw_type_id = dt.draw_type_id AND d.status = 'SETTLED') AS total_draws
        FROM catalog.draw_types dt
        ORDER BY dt.display_name
    """,
}


PREDICTIONS_SQL = """
    SELECT p.prediction_id, mv.code AS model_code, dt.display_name AS draw_type,
           p.scheduled_date, p.predicted_numbers, p.status, p.stake,
           p.created_at, o.winning_numbers, o.hit_count, o.settled_at
    FROM research.predictions p
    JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
    JOIN catalog.draw_types dt ON dt.draw_type_id = p.draw_type_id
    LEFT JOIN research.prediction_outcomes o ON o.prediction_id = p.prediction_id
    WHERE (%(status)s::text IS NULL OR p.status = %(status)s)
      AND (%(date)s::date IS NULL OR p.scheduled_date = %(date)s)
      AND (%(from)s::date IS NULL OR p.scheduled_date >= %(from)s)
      AND (%(to)s::date IS NULL OR p.scheduled_date <= %(to)s)
    ORDER BY p.scheduled_date DESC, p.created_at DESC
    LIMIT %(limit)s
"""

DRAWS_SQL = """
    SELECT d.draw_id, dt.display_name AS draw_type, d.scheduled_date,
           d.status, v.validation_status,
           (SELECT jsonb_agg(n.number ORDER BY n.position)
            FROM core.draw_numbers n
            WHERE n.draw_version_id = v.draw_version_id
              AND n.number_role = 'WINNING') AS winning_numbers
    FROM core.draws d
    JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
    LEFT JOIN LATERAL (
        SELECT draw_version_id, validation_status FROM core.draw_versions
        WHERE draw_id = d.draw_id ORDER BY version_number DESC LIMIT 1
    ) v ON true
    WHERE d.status IN ('FROZEN', 'SETTLED', 'EXPECTED')
      AND (%(date)s::date IS NULL OR d.scheduled_date = %(date)s)
      AND (%(from)s::date IS NULL OR d.scheduled_date >= %(from)s)
      AND (%(to)s::date IS NULL OR d.scheduled_date <= %(to)s)
      AND (%(type)s::text IS NULL OR dt.display_name = %(type)s)
      AND (%(status)s::text IS NULL OR d.status = %(status)s)
    ORDER BY d.scheduled_date DESC, dt.display_name
    LIMIT %(limit)s
"""


class ApiHandler(BaseHTTPRequestHandler):
    dsn: str = DEFAULT_DSN
    token: str | None = None  # when set, Bearer auth is required

    def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            cur = conn.execute(sql, params or {})
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _send(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=_default).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected mid-response (large research payloads,
            # browser timeouts) — nothing to recover, keep logs clean.
            self.close_connection = True

    def _lab_replay(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Re-run every cohort picker against one past draw, strict walk-forward:
        each picker only sees draws scheduled before the target date."""
        draw_type = (qs.get("draw_type") or [None])[0]
        target_raw = (qs.get("date") or [None])[0]
        if not draw_type or not target_raw:
            return {"error": "draw_type and date are required"}
        try:
            target = date.fromisoformat(target_raw)
        except ValueError:
            return {"error": "date must be YYYY-MM-DD"}
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            draw_type_id, display_name = dt_row
            draw = conn.execute(
                """SELECT d.draw_id, d.status,
                          (SELECT jsonb_agg(n.number ORDER BY n.position)
                           FROM core.draw_versions v
                           JOIN core.draw_numbers n
                             ON n.draw_version_id = v.draw_version_id
                            AND n.number_role = 'WINNING'
                           WHERE v.draw_id = d.draw_id
                             AND v.validation_status = 'VALID') AS winning
                   FROM core.draws d
                   WHERE d.draw_type_id = %s AND d.scheduled_date = %s
                   ORDER BY d.created_at DESC LIMIT 1""",
                (draw_type_id, target),
            ).fetchone()
            history = conn.execute(
                """SELECT count(*) FROM core.draws d
                   WHERE d.draw_type_id = %s AND d.scheduled_date < %s
                     AND d.status = 'SETTLED'""",
                (draw_type_id, target),
            ).fetchone()[0]
            members = conn.execute(
                """SELECT mv.code, mv.version, cm.parameters, cm.seed
                   FROM research.prospective_cohort_members cm
                   JOIN research.model_versions mv
                     ON mv.model_version_id = cm.model_version_id
                   JOIN research.prospective_cohort_versions cv
                     ON cv.cohort_version_id = cm.cohort_version_id
                   WHERE cv.cohort_version_id = (
                       SELECT cohort_version_id FROM research.prospective_cohort_versions
                       ORDER BY created_at DESC LIMIT 1)
                   ORDER BY mv.code""",
            ).fetchall()
            winning = draw[2] if draw else None
            multipliers = (
                _payout_multipliers(conn, None, draw[0]) if draw and winning else {}
            )
            models = []
            for code, version, params, seed in members:
                picker = PICKERS.get(code)
                if picker is None:
                    continue
                predicted = picker(conn, draw_type_id, target, params or {}, seed)
                predicted_5 = picker(
                    conn, draw_type_id, target,
                    {**dict(params or {}), "pick_count": 5}, seed)
                entry: dict[str, Any] = {
                    "model_code": code,
                    "model_version": version,
                    "predicted": predicted,
                    "predicted_5": predicted_5,
                }
                if winning:
                    entry["hit_numbers"] = sorted(set(predicted) & set(winning))
                    entry["hits"] = len(entry["hit_numbers"])
                    entry["hit_numbers_5"] = sorted(set(predicted_5) & set(winning))
                    entry["hits_5"] = len(entry["hit_numbers_5"])
                    entry["positional_hits"] = positional_hit_counts(predicted, winning)
                    if multipliers:
                        entry["turbo"] = turbo_settlement(
                            predicted, winning,
                            stake=DEFAULT_TURBO_STAKE, multipliers=multipliers,
                        )
                models.append(entry)
        return {
            "draw_type": display_name,
            "date": target.isoformat(),
            "draw_found": draw is not None,
            "draw_status": draw[1] if draw else None,
            "winning_numbers": winning,
            "history_draws": history,
            "models": models,
            "disclaimer": "Simulation walk-forward : chaque modèle ne voit que "
                          "l'historique antérieur au tirage. Pas un gain réel.",
        }

    def _statistics(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Per-number frequency / delay stats for one draw type."""
        draw_type = (qs.get("draw_type") or [None])[0]
        days = int((qs.get("days") or ["0"])[0])
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt_row = conn.execute(
                    """SELECT draw_type_id, display_name FROM catalog.draw_types
                       WHERE code = %s OR display_name = %s""",
                    (draw_type, draw_type),
                ).fetchone()
                if dt_row is None:
                    return {"error": f"unknown draw_type: {draw_type}"}
            else:
                dt_row = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                ).fetchone()
            draw_type_id, display_name = dt_row
            clause = "AND d.scheduled_date >= CURRENT_DATE - %s" if days > 0 else ""
            params: tuple[Any, ...] = (draw_type_id, days) if days > 0 else (draw_type_id,)
            rows = conn.execute(
                f"""SELECT d.scheduled_date, d.scheduled_sequence, n.number, n.position
                    FROM core.draws d
                    JOIN core.draw_versions v
                      ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                    JOIN core.draw_numbers n
                      ON n.draw_version_id = v.draw_version_id
                     AND n.number_role = 'WINNING'
                    WHERE d.draw_type_id = %s {clause}
                    ORDER BY d.scheduled_date DESC, d.scheduled_sequence, n.position""",
                params,
            ).fetchall()
        draw_keys = sorted({(r[0], r[1]) for r in rows}, reverse=True)
        draw_count = len(draw_keys)
        key_rank = {k: i for i, k in enumerate(draw_keys)}
        counts = {n: 0 for n in range(1, 91)}
        first_two = {n: 0 for n in range(1, 91)}
        last_rank = {n: None for n in range(1, 91)}
        last_date: dict[int, date | None] = {n: None for n in range(1, 91)}
        by_draw: dict[tuple[date, int], list[int]] = {}
        for draw_date, seq, number, position in rows:
            counts[number] += 1
            if position is not None and position <= 2:
                first_two[number] += 1
            by_draw.setdefault((draw_date, seq), []).append(number)
            rank = key_rank[(draw_date, seq)]
            if last_rank[number] is None or rank < last_rank[number]:
                last_rank[number] = rank
                last_date[number] = draw_date
        # M03 — pair co-occurrence vs chance expectation.
        # One-sided binomial right tail per pair; FDR (BH) over the full
        # C(90,2) = 4005 hypothesis space — pairs at/below expectation get
        # p = 1, which is what makes the correction honest.
        draw_sets = [set(nums) for nums in by_draw.values()]
        pair_last: dict[tuple[int, int], date] = {}
        pair_counts_all: dict[tuple[int, int], int] = {}
        for draw_key, nums in by_draw.items():
            nums = sorted(set(nums))
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    pair = (nums[i], nums[j])
                    pair_counts_all[pair] = pair_counts_all.get(pair, 0) + 1
                    pair_last.setdefault(pair, draw_key[0])
        tested = pair_dependence_tests(draw_sets)
        n_hypotheses = 90 * 89 // 2
        pvals = [r["p_value"] for r in tested] + [1.0] * (n_hypotheses - len(tested))
        qvals = fdr_bh(pvals)
        for entry, q in zip(tested, qvals):
            entry["q_fdr"] = q
            a, b = entry["pair"]
            entry["last_date"] = pair_last[(a, b)].isoformat()
        pairs = [
            {"pair": list(t["pair"]), "count": t["observed"],
             "expected": t["expected"], "lift": t["lift"],
             "p_value": t["p_value"], "q_fdr": t["q_fdr"],
             "last_date": t["last_date"]}
            for t in tested[:20]
        ]
        # fall back to raw top pairs when nothing exceeds expectation
        if not pairs:
            pairs = [
                {"pair": [a, b], "count": c, "expected": draw_count * 20 / 8010,
                 "lift": None, "p_value": None, "q_fdr": None,
                 "last_date": pair_last[(a, b)].isoformat()}
                for (a, b), c in sorted(
                    pair_counts_all.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
            ]
        first_two_ranked = [
            {"number": n, "count": c}
            for n, c in sorted(first_two.items(), key=lambda kv: (-kv[1], kv[0]))
            if c > 0
        ][:20]
        observed = [counts[n] for n in range(1, 91)]
        total = sum(observed)
        expected = total / 90 if total else 0.0
        chi2 = (sum((o - expected) ** 2 / expected for o in observed)
                if expected else 0.0)
        p_value = chi_square_sf(chi2, 89) if expected else None
        numbers = [
            {"number": n, "count": counts[n],
             "delay": last_rank[n] if last_rank[n] is not None else draw_count,
             "last_date": last_date[n].isoformat() if last_date[n] else None,
             "deviation": (counts[n] - expected) if expected else 0.0}
            for n in range(1, 91)
        ]
        by_count = sorted(numbers, key=lambda x: (-x["count"], x["number"]))
        return {
            "draw_type": display_name,
            "days": days or None,
            "draw_count": draw_count,
            "expected_per_number": expected,
            "chi_square": chi2,
            "df": 89,
            "p_value": p_value,
            "uniform": p_value is not None and p_value >= 0.05,
            "numbers": numbers,
            "hot": by_count[:10],
            "cold": by_count[-10:],
            "max_delay": max(numbers, key=lambda x: x["delay"]),
            "first_two": first_two_ranked,
            "first_two_expected": draw_count * 2 / 90 if draw_count else 0.0,
            "top_pairs": pairs,
        }

    def _root_statistics(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Per-root frequency / delay stats for one draw type (same format as _statistics)."""
        from lottery_intelligence_platform.digital_root import digital_root

        draw_type = (qs.get("draw_type") or [None])[0]
        days = int((qs.get("days") or ["0"])[0])
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt_row = conn.execute(
                    """SELECT draw_type_id, display_name FROM catalog.draw_types
                       WHERE code = %s OR display_name = %s""",
                    (draw_type, draw_type),
                ).fetchone()
                if dt_row is None:
                    return {"error": f"unknown draw_type: {draw_type}"}
            else:
                dt_row = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                ).fetchone()
            draw_type_id, display_name = dt_row
            clause = "AND d.scheduled_date >= CURRENT_DATE - %s" if days > 0 else ""
            params: tuple[Any, ...] = (draw_type_id, days) if days > 0 else (draw_type_id,)
            rows = conn.execute(
                f"""SELECT d.scheduled_date, d.scheduled_sequence, n.number, n.position
                    FROM core.draws d
                    JOIN core.draw_versions v
                      ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                    JOIN core.draw_numbers n
                      ON n.draw_version_id = v.draw_version_id
                     AND n.number_role = 'WINNING'
                    WHERE d.draw_type_id = %s {clause}
                    ORDER BY d.scheduled_date DESC, d.scheduled_sequence, n.position""",
                params,
            ).fetchall()
        draw_keys = sorted({(r[0], r[1]) for r in rows}, reverse=True)
        draw_count = len(draw_keys)
        key_rank = {k: i for i, k in enumerate(draw_keys)}
        counts = {r: 0 for r in range(9)}  # 0-8 (9 maps to 0)
        first_two = {r: 0 for r in range(9)}
        last_rank = {r: None for r in range(9)}
        last_date: dict[int, date | None] = {r: None for r in range(9)}
        by_draw: dict[tuple[date, int], list[int]] = {}
        for draw_date, seq, number, position in rows:
            root = digital_root(number)
            counts[root] += 1
            if position is not None and position <= 2:
                first_two[root] += 1
            by_draw.setdefault((draw_date, seq), []).append(root)
            rank = key_rank[(draw_date, seq)]
            if last_rank[root] is None or rank < last_rank[root]:
                last_rank[root] = rank
                last_date[root] = draw_date
        # Pair co-occurrence for roots (9 roots = 36 pairs)
        draw_sets = [set(nums) for nums in by_draw.values()]
        pair_last: dict[tuple[int, int], date] = {}
        pair_counts_all: dict[tuple[int, int], int] = {}
        for draw_key, nums in by_draw.items():
            nums = sorted(set(nums))
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    pair = (nums[i], nums[j])
                    pair_counts_all[pair] = pair_counts_all.get(pair, 0) + 1
                    pair_last.setdefault(pair, draw_key[0])
        # Statistical tests for root pairs
        from scipy.stats import binomtest
        n_hypotheses = 9 * 8 // 2  # 36 pairs
        tested = []
        for (a, b), observed in pair_counts_all.items():
            # Expected probability for a pair in 5-number draw from 9 roots
            # P(pair in draw) = sum(k=2 to 5) C(7, k-2) / C(9, k) ≈ 0.2778
            expected = draw_count * 0.2778
            if observed > expected:
                p_val = binomtest(observed, draw_count, 0.2778, alternative='greater').pvalue
                lift = observed / expected if expected else 0
                tested.append({
                    "pair": (a, b),
                    "observed": observed,
                    "expected": expected,
                    "lift": lift,
                    "p_value": p_val,
                })
        # FDR correction
        from statsmodels.stats.multitest import multipletests
        pvals = [r["p_value"] for r in tested] + [1.0] * (n_hypotheses - len(tested))
        qvals = multipletests(pvals, method='fdr_bh')[1]
        for entry, q in zip(tested, qvals):
            entry["q_fdr"] = q
            a, b = entry["pair"]
            entry["last_date"] = pair_last[(a, b)].isoformat()
        pairs = [
            {"pair": list(t["pair"]), "count": t["observed"],
             "expected": t["expected"], "lift": t["lift"],
             "p_value": t["p_value"], "q_fdr": t["q_fdr"],
             "last_date": t["last_date"]}
            for t in sorted(tested, key=lambda x: x["lift"], reverse=True)[:12]
        ]
        if not pairs:
            pairs = [
                {"pair": [a, b], "count": c, "expected": draw_count * 0.2778,
                 "lift": None, "p_value": None, "q_fdr": None,
                 "last_date": pair_last[(a, b)].isoformat()}
                for (a, b), c in sorted(
                    pair_counts_all.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
            ]
        first_two_ranked = [
            {"number": r, "count": c}
            for r, c in sorted(first_two.items(), key=lambda kv: (-kv[1], kv[0]))
            if c > 0
        ]
        observed = [counts[r] for r in range(9)]
        total = sum(observed)
        expected = total / 9 if total else 0.0
        chi2 = (sum((o - expected) ** 2 / expected for o in observed)
                if expected else 0.0)
        p_value = chi_square_sf(chi2, 8) if expected else None
        roots = [
            {"number": r, "count": counts[r],
             "delay": last_rank[r] if last_rank[r] is not None else draw_count,
             "last_date": last_date[r].isoformat() if last_date[r] else None,
             "deviation": (counts[r] - expected) if expected else 0.0}
            for r in range(9)
        ]
        by_count = sorted(roots, key=lambda x: (-x["count"], x["number"]))
        return {
            "draw_type": display_name,
            "days": days or None,
            "draw_count": draw_count,
            "expected_per_number": expected,
            "chi_square": chi2,
            "df": 8,
            "p_value": p_value,
            "uniform": p_value is not None and p_value >= 0.05,
            "numbers": roots,
            "hot": by_count[:5],
            "cold": by_count[-5:],
            "max_delay": max(roots, key=lambda x: x["delay"]),
            "first_two": first_two_ranked,
            "first_two_expected": draw_count * 2 / 9 if draw_count else 0.0,
            "top_pairs": pairs,
        }

    def _digital_root_statistics(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Digital root descriptive statistics (10/30/45/60/90 days) for one game."""
        draw_type = (qs.get("draw_type") or [None])[0]
        ref_str = (qs.get("reference_date") or [None])[0]
        if ref_str:
            try:
                reference = date.fromisoformat(ref_str)
            except ValueError:
                return {"error": f"invalid reference_date: {ref_str}"}
        else:
            reference = date.today()
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt_row = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       WHERE dt.code = %s OR dt.display_name = %s
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                    (draw_type, draw_type),
                ).fetchone()
                if dt_row is None:
                    return {"error": f"unknown draw_type: {draw_type}"}
            else:
                dt_row = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                ).fetchone()
            draw_type_id, display_name = dt_row
            return digital_root_statistics.compute_digital_root_statistics(
                conn, draw_type_id, display_name, reference)

    def _lab_structure(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """M04 + M05 + M06: null reference, serial dependence, change point
        for one draw type, computed on VALID draws in chronological order."""
        draw_type = (qs.get("draw_type") or [None])[0]
        if not draw_type:
            return {"error": "draw_type is required"}
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            draw_type_id, display_name = dt_row
            rows = conn.execute(
                """SELECT d.scheduled_date, d.scheduled_sequence,
                          jsonb_agg(n.number ORDER BY n.position) AS nums
                   FROM core.draws d
                   JOIN core.draw_versions v
                     ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                   JOIN core.draw_numbers n
                     ON n.draw_version_id = v.draw_version_id
                    AND n.number_role = 'WINNING'
                   WHERE d.draw_type_id = %s
                   GROUP BY d.scheduled_date, d.scheduled_sequence
                   ORDER BY d.scheduled_date, d.scheduled_sequence""",
                (draw_type_id,),
            ).fetchall()
        draws = [(r[0], set(r[2])) for r in rows]
        sets = [s for _, s in draws]
        seed = abs(hash(display_name)) % (2**31)
        return {
            "draw_type": display_name,
            "draws": len(sets),
            "null_reference": structure_analysis.null_reference(
                sets, simulations=199, seed=seed),
            "serial_dependence": structure_analysis.serial_dependence(
                sets, permutations=199, seed=seed),
            "change_point": structure_analysis.change_point(
                draws, permutations=199, seed=seed),
        }

    def _lab_simulation(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """M08 — Monte-Carlo bankroll simulation for a Turbo variant."""
        try:
            positions = int((qs.get("variant") or ["2"])[0])
            draws = min(int((qs.get("draws") or ["200"])[0]), 2000)
            paths = min(int((qs.get("paths") or ["500"])[0]), 2000)
            stake = float((qs.get("stake") or ["100"])[0])
            bankroll = float((qs.get("bankroll") or ["10000"])[0])
            lift = float((qs.get("lift") or ["1.0"])[0])
        except ValueError:
            return {"error": "numeric parameters expected"}
        try:
            return simulate_bankroll(
                positions=positions, stake=stake, draws=draws,
                paths=paths, bankroll=bankroll, hit_lift=lift)
        except ValueError as exc:
            return {"error": str(exc)}

    def _lab_coverage(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """M10 — Coverage Laboratory: optimized vs random portfolios, exact/MC
        P(at least one win), economics from catalog.payout_rule_versions."""
        try:
            budget = float(qs["budget"][0]) if qs.get("budget") else None
            tickets_raw = qs.get("tickets")
            tickets = min(int(tickets_raw[0]), 500) if tickets_raw else None
            stake = float((qs.get("stake") or ["100"])[0])
            pick_size = int((qs.get("pick_size") or ["2"])[0])
            seed = int((qs.get("seed") or ["0"])[0])
            baselines = min(int((qs.get("baselines") or ["100"])[0]), 300)
            mc_sims = min(int((qs.get("mc_sims") or ["20000"])[0]), 100_000)
        except ValueError:
            return {"error": "numeric parameters expected"}
        variant = (qs.get("variant") or ["turbo_2"])[0]
        rule_version = (qs.get("rule_version") or [None])[0]
        try:
            with psycopg.connect(self.dsn, autocommit=True) as conn:
                rule = resolve_payout_rule(conn, rule_version)
            return coverage_laboratory(
                rule=rule, budget_fcfa=budget, tickets=tickets, stake=stake,
                pick_size=pick_size, variant=variant, seed=seed,
                baselines=baselines, mc_sims=mc_sims)
        except (CoverageRuleError, ValueError) as exc:
            return {"error": str(exc)}

    _matrix_cache: dict[str, dict[str, Any]] = {}

    def _lab_matrix(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        draw_type = (qs.get("draw_type") or [None])[0]
        if not draw_type:
            return {"error": "draw_type is required"}
        cache_key = draw_type
        if cache_key in self._matrix_cache:
            return self._matrix_cache[cache_key]
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            result = lab_matrix.evaluate_game(conn, dt_row[0], dt_row[1])
            if result is None:
                return {"error": "not enough settled draws",
                        "minimum": lab_matrix.MIN_DRAWS + lab_matrix.MIN_WF}
            result["candidate"] = lab_matrix.candidate_for(result)
            for name, entry in result["models"].items():
                entry["stage"] = lab_matrix.stage_of(entry)
                entry["robustness"] = lab_matrix.robustness_score(entry)[0]
        self._matrix_cache[cache_key] = result
        return result

    _calling_image_cache: dict[str, dict[str, Any]] = {}

    def _lab_calling_image(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """CALLING_IMAGE family — H1..H4 directional edge study for one
        draw type. Associations vs theoretical + permutation nulls, FDR per
        horizon, OOS replication. An anomaly is a candidate, never a verdict."""
        draw_type = (qs.get("draw_type") or [None])[0]
        if not draw_type:
            return {"error": "draw_type is required"}
        try:
            permutations = min(int((qs.get("permutations") or ["99"])[0]), 499)
        except ValueError:
            return {"error": "permutations must be numeric"}
        cache_key = f"{draw_type}:{permutations}"
        if cache_key in self._calling_image_cache:
            return self._calling_image_cache[cache_key]
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            draw_type_id, display_name = dt_row
            from lottery_intelligence_platform.prediction_generation import (
                _history,
            )
            hist = _history(conn, draw_type_id, date(2100, 1, 1))
        if len(hist) < lab_matrix.MIN_DRAWS + lab_matrix.MIN_WF:
            return {"error": "not enough settled draws",
                    "minimum": lab_matrix.MIN_DRAWS + lab_matrix.MIN_WF}
        result = calling_image.evaluate_family(
            hist,
            permutations=permutations,
            seed=calling_image._stable_seed("api", display_name),
        )
        result["draw_type"] = display_name
        self._calling_image_cache[cache_key] = result
        return result

    _consensus_cache: dict[str, dict[str, Any]] = {}

    def _lab_consensus(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Meta-ensemble — deterministic consensus of the lab pickers for
        one draw type. `date` (YYYY-MM-DD) replays the consensus computed
        strictly from draws before that date (as-of view, no look-ahead);
        omit for the next-draw consensus on full history."""
        draw_type = (qs.get("draw_type") or [None])[0]
        if not draw_type:
            return {"error": "draw_type is required"}
        try:
            k = min(int((qs.get("k") or ["5"])[0]), 10)
            d_to = (date.fromisoformat(v) if (v := (qs.get("date") or [""])[0])
                    else date(2100, 1, 1))
        except ValueError:
            return {"error": "k must be numeric; date must be YYYY-MM-DD"}
        cache_key = f"{draw_type}:{k}:{d_to}"
        if cache_key in self._consensus_cache:
            return self._consensus_cache[cache_key]
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            draw_type_id, display_name = dt_row
            from lottery_intelligence_platform.prediction_generation import (
                _history,
            )
            hist = _history(conn, draw_type_id, d_to)
        if len(hist) < 20:
            return {"error": "not enough settled draws", "minimum": 20}
        result = meta_ensemble.detail(hist, k)
        result["draw_type"] = display_name
        result["as_of"] = d_to.isoformat() if d_to.year < 2100 else "next"
        self._consensus_cache[cache_key] = result
        return result

    _structure_map_cache: dict[str, dict[str, Any]] = {}

    def _lab_structure_map(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Structure Map — full audit of one draw process: frequency
        windows, autocorrelation, unconstrained 90x90 transitions,
        positional structure, runs/delay, change point, seasonality,
        calling/image — each vs its declared null, FDR + OOS holdout.
        light=1 skips the full transition matrix."""
        draw_type = (qs.get("draw_type") or [None])[0]
        if not draw_type:
            return {"error": "draw_type is required"}
        try:
            permutations = min(int((qs.get("permutations") or ["200"])[0]),
                               499)
            d_from = (date.fromisoformat(v) if (v := (qs.get("from") or [""])[0])
                      else None)
            d_to = (date.fromisoformat(v) if (v := (qs.get("to") or [""])[0])
                    else None)
        except ValueError:
            return {"error": "permutations must be numeric; "
                             "from/to must be YYYY-MM-DD"}
        light = (qs.get("light") or ["0"])[0] in ("1", "true")
        cache_key = f"{draw_type}:{permutations}:{light}:{d_from}:{d_to}"
        if cache_key in self._structure_map_cache:
            return self._structure_map_cache[cache_key]
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            draw_type_id, display_name = dt_row
            dated = game_temporal.dated_history(
                conn, draw_type_id, d_to or date(2100, 1, 1))
        if d_from is not None:
            dated = [(d, nums) for d, nums in dated if d >= d_from]
        hist = [nums for _, nums in dated]
        if len(hist) < 60:
            return {"error": "not enough settled draws", "minimum": 60}
        result = structure_map.build_structure_map(
            hist, dated=dated, permutations=permutations,
            seed=calling_image._stable_seed("structure-map", display_name),
            light=light)
        result["draw_type"] = display_name
        result["date_range"] = {
            "from": str(d_from) if d_from else str(dated[0][0]),
            "to": str(d_to) if d_to else str(dated[-1][0]),
        }
        self._structure_map_cache[cache_key] = result
        return result

    _cross_game_cache: dict[str, dict[str, Any]] = {}

    def _lab_cross_game(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Cross-game structure: ordered intra-day transitions X -> Y
        (adjacent games by scheduled_sequence), overlap vs NULL B
        permutation and calling-edge density. min_days guards thin pairs."""
        try:
            permutations = min(int((qs.get("permutations") or ["300"])[0]),
                               999)
            days = int((qs.get("days") or ["0"])[0])
        except ValueError:
            return {"error": "permutations/days must be numeric"}
        cache_key = f"cross:{permutations}:{days}"
        if cache_key in self._cross_game_cache:
            return self._cross_game_cache[cache_key]
        clause = ("AND d.scheduled_date >= CURRENT_DATE - %s"
                  if days > 0 else "")
        params: tuple[Any, ...] = (days,) if days > 0 else ()
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            rows = conn.execute(
                f"""SELECT d.scheduled_date, d.scheduled_sequence,
                           dt.display_name, n.number
                    FROM core.draws d
                    JOIN catalog.draw_types dt
                      ON dt.draw_type_id = d.draw_type_id
                    JOIN core.draw_versions v
                      ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                    JOIN core.draw_numbers n
                      ON n.draw_version_id = v.draw_version_id
                     AND n.number_role = 'WINNING'
                    WHERE 1=1 {clause}
                    ORDER BY d.scheduled_date, d.scheduled_sequence,
                             n.position""",
                params,
            ).fetchall()
        day_games: dict[Any, dict[str, tuple[int, list[int]]]] = {}
        for draw_date, seq, game, number in rows:
            day = day_games.setdefault(draw_date, {})
            entry = day.setdefault(game, (seq, []))
            entry[1].append(number)
        flat = {
            day: [(seq, game, nums)
                  for game, (seq, nums) in games.items()]
            for day, games in day_games.items()
        }
        result = structure_map.cross_game(
            flat, permutations=permutations,
            seed=calling_image._stable_seed("cross-game"))
        result["n_days"] = len(flat)
        self._cross_game_cache[cache_key] = result
        return result

    _game_profiles_cache: dict[str, dict[str, Any]] = {}

    def _lab_game_profiles(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Temporal Intelligence layer — JEU × MODÈLE walk-forward profiles.
        Read-only observation; never touches predictions or settlement."""
        draw_type = (qs.get("draw_type") or [None])[0]
        if not draw_type:
            return {"error": "draw_type is required"}
        as_of_raw = (qs.get("as_of") or [None])[0]
        try:
            as_of = date.fromisoformat(as_of_raw) if as_of_raw else date.today()
        except ValueError:
            return {"error": "as_of must be YYYY-MM-DD"}
        cache_key = f"{draw_type}:{as_of.isoformat()}"
        if cache_key in self._game_profiles_cache:
            return self._game_profiles_cache[cache_key]
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            result = game_temporal.game_profile(
                conn, dt_row[0], dt_row[1], as_of=as_of)
        self._game_profiles_cache[cache_key] = result
        return result

    def _lab_game_matrix(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Cross-game matrix from sealed prospective outcomes — real stats,
        sparse cells labelled, never invented."""
        as_of_raw = (qs.get("as_of") or [None])[0]
        try:
            as_of = date.fromisoformat(as_of_raw) if as_of_raw else date.today()
        except ValueError:
            return {"error": "as_of must be YYYY-MM-DD"}
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            return game_temporal.prospective_matrix(conn, as_of)

    _game_cards_cache: dict[str, Any] = {}

    def _lab_game_cards(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """One card per game — windowed walk-forward summary. Cached."""
        as_of_raw = (qs.get("as_of") or [None])[0]
        try:
            as_of = date.fromisoformat(as_of_raw) if as_of_raw else date.today()
        except ValueError:
            return {"error": "as_of must be YYYY-MM-DD"}
        key = as_of.isoformat()
        if key in self._game_cards_cache:
            return self._game_cards_cache[key]
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            cards = game_temporal.game_cards(conn, as_of)
        result = {"as_of": key,
                  "card_window": game_temporal.CARD_WINDOW,
                  "cards": cards}
        self._game_cards_cache[key] = result
        return result

    def _lab_turbo2_history(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Turbo 2 sealed history for ONE game — reads metrics already
        computed by the settlement engine; never recomputes."""
        draw_type = (qs.get("draw_type") or [None])[0]
        if not draw_type:
            return {"error": "draw_type is required"}
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            dt_row = conn.execute(
                """SELECT draw_type_id, display_name FROM catalog.draw_types
                   WHERE code = %s OR display_name = %s""",
                (draw_type, draw_type),
            ).fetchone()
            if dt_row is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            return turbo2_view.turbo2_history(conn, dt_row[0])

    def _lab_candidates(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        top = min(int((qs.get("top") or ["8"])[0]), 30)
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            games = conn.execute(
                """SELECT DISTINCT ON (dt.display_name) dt.draw_type_id, dt.display_name
                   FROM catalog.draw_types dt
                   JOIN core.draws d ON d.draw_type_id = dt.draw_type_id
                     AND d.status = 'SETTLED'
                   GROUP BY dt.display_name, dt.draw_type_id
                   HAVING count(d.draw_id) >= %s
                   ORDER BY dt.display_name, count(d.draw_id) DESC
                   LIMIT %s""",
                (lab_matrix.MIN_DRAWS + lab_matrix.MIN_WF, top),
            ).fetchall()
            rows = []
            for draw_type_id, display_name in games:
                cached = self._matrix_cache.get(display_name)
                result = cached or lab_matrix.evaluate_game(
                    conn, draw_type_id, display_name)
                if result is None:
                    continue
                self._matrix_cache.setdefault(display_name, result)
                rows.append(lab_matrix.candidate_for(result))
        return {"games_evaluated": len(rows), "candidates": rows}

    @staticmethod
    def _dist_dir() -> Path:
        override = os.environ.get("LOTTERY_FRONTEND_DIST")
        if override:
            return Path(override)
        # Source checkout: <repo>/src/<pkg>/api.py → <repo>/frontend/dist
        repo = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        if repo.is_dir():
            return repo
        return Path("/app/frontend/dist")  # installed image layout

    def _serve_static(self, path: str) -> None:
        if path == "/console":
            self._send_file(Path(__file__).with_name("console.html"))
            return
        dist = self._dist_dir()
        if not dist.is_dir():
            self._send_file(Path(__file__).with_name("console.html"))
            return
        target = (dist / path.lstrip("/")).resolve()
        # SPA history-mode fallback: unknown paths get index.html; block traversal
        if path != "/" and target.is_file() and target.is_relative_to(dist.resolve()):
            self._send_file(target)
        else:
            self._send_file(dist / "index.html")

    def _digital_root_stats(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Digital root statistics for a game and time window.

        Provides descriptive statistics without predictive claims.
        """
        from lottery_intelligence_platform.digital_root_statistics import DigitalRootStatistics

        draw_type = (qs.get("draw_type") or [None])[0]
        window_days_str = (qs.get("window_days") or ["30"])[0]
        reference_date_str = (qs.get("reference_date") or [None])[0]

        try:
            window_days = int(window_days_str)
        except ValueError:
            return {"error": "window_days must be an integer"}

        if window_days not in [10, 30, 45, 60, 90]:
            return {"error": "window_days must be one of: 10, 30, 45, 60, 90"}

        if reference_date_str:
            try:
                reference_date = date.fromisoformat(reference_date_str)
            except ValueError:
                return {"error": "reference_date must be YYYY-MM-DD format"}
        else:
            reference_date = date.today()

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt = conn.execute(
                    "SELECT draw_type_id, display_name FROM catalog.draw_types "
                    "WHERE code = %s OR display_name = %s",
                    (draw_type, draw_type),
                ).fetchone()
            else:
                dt = conn.execute(
                    "SELECT dt.draw_type_id, dt.display_name FROM catalog.draw_types dt "
                    "ORDER BY (SELECT count(*) FROM core.draws d "
                    "WHERE d.draw_type_id = dt.draw_type_id) DESC LIMIT 1",
                ).fetchone()

            if dt is None:
                return {"error": f"unknown draw_type: {draw_type}"}

            draw_type_id, display_name = dt

            # Calculate statistics
            analyzer = DigitalRootStatistics()
            game_stats = analyzer.calculate_game_statistics(
                conn,
                draw_type_id,
                reference_date,
            )

            window_stats = game_stats.windows.get(window_days)
            if not window_stats:
                return {"error": f"No data for {window_days}-day window"}

            # Convert to JSON-serializable format
            result = {
                "game_id": str(game_stats.game_id),
                "game_name": game_stats.game_name,
                "reference_date": str(game_stats.reference_date),
                "window_days": window_days,
                "start_date": str(window_stats.start_date),
                "end_date": str(window_stats.end_date),
                "draw_count": window_stats.draw_count,
                "total_numbers_analyzed": window_stats.total_numbers_analyzed,
                "data_quality_score": window_stats.data_quality_score,
                "has_duplicate_draws": window_stats.has_duplicate_draws,
                "has_missing_dates": window_stats.has_missing_dates,
                "global_distribution": [
                    {
                        "root": d.root,
                        "occurrences": d.occurrences,
                        "percentage": round(d.percentage, 2),
                        "draws_containing": d.draws_containing,
                        "deviation_from_reference": round(d.deviation_from_reference, 2),
                    }
                    for d in window_stats.global_distribution
                ],
                "position_distributions": {
                    str(pos): {
                        "root_counts": dist.root_counts,
                        "root_percentages": {str(k): round(v, 2) for k, v in dist.root_percentages.items()},
                        "most_frequent_root": dist.most_frequent_root,
                        "sample_size": dist.sample_size,
                    }
                    for pos, dist in window_stats.position_distributions.items()
                },
                "draw_signatures": [
                    {
                        "draw_id": str(s.draw_id),
                        "scheduled_date": str(s.scheduled_date),
                        "original_numbers": s.original_numbers,
                        "root_sequence": s.root_sequence,
                        "distinct_roots": s.distinct_roots,
                        "root_repetitions": {str(k): v for k, v in s.root_repetitions.items()},
                    }
                    for s in window_stats.draw_signatures[:20]  # Last 20 draws
                ],
                "family_frequencies": {
                    str(root): {
                        "root": f.family_frequencies[root].root,
                        "family_numbers": f.family_frequencies[root].family_numbers,
                        "total_occurrences": f.family_frequencies[root].total_occurrences,
                        "frequency_by_position": {
                            str(k): round(v, 2) for k, v in f.family_frequencies[root].frequency_by_position.items()
                        },
                    }
                    for root, f in window_stats.family_frequencies.items()
                },
                "temporal_changes": [
                    {
                        "root": c.root,
                        "window_from": c.window_from,
                        "window_to": c.window_to,
                        "percentage_change": round(c.percentage_change, 2),
                        "trend": c.trend,
                        "sample_size_from": c.sample_size_from,
                        "sample_size_to": c.sample_size_to,
                    }
                    for c in game_stats.temporal_changes
                    if c.window_to == window_days or c.window_from == window_days
                ],
                "transition_matrices": {
                    str(source): {
                        "source_root": tm.source_root,
                        "target_counts": tm.target_counts,
                        "conditional_probabilities": {
                            str(k): round(v, 4) for k, v in tm.conditional_probabilities.items()
                        },
                        "total_observations": tm.total_observations,
                    }
                    for source, tm in game_stats.transition_matrices.items()
                },
                "warning": (
                    "Insufficient sample size" if window_stats.draw_count < 10 else None
                ),
            }

            return result

    def _digital_root_turbo_predictions(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Digital root Turbo predictions for games (Turbo 2 and Turbo 5)."""
        from lottery_intelligence_platform.digital_root_analyzer import DigitalRootTurboAnalyzer
        from lottery_intelligence_platform.betting_formulas import TURBO_FORMULAS

        draw_type = (qs.get("draw_type") or [None])[0]
        date_str = (qs.get("date") or [None])[0]
        variant = (qs.get("variant") or ["turbo_2"])[0]

        if date_str:
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                return {"error": f"invalid date: {date_str}"}
        else:
            target_date = date.today()

        if variant not in ["turbo_2", "turbo_5"]:
            return {"error": "variant must be turbo_2 or turbo_5"}

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt = conn.execute(
                    """SELECT draw_type_id, display_name FROM catalog.draw_types
                       WHERE code = %s OR display_name = %s""",
                    (draw_type, draw_type),
                ).fetchone()
            else:
                dt = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                ).fetchone()

            if dt is None:
                return {"error": f"unknown draw_type: {draw_type}"}

            draw_type_id, display_name = dt

            # Generate prediction using Digital Root Turbo Analyzer
            analyzer = DigitalRootTurboAnalyzer(
                observation_window_days=3,
                min_observations=5,
                default_turbo_variant=variant,
            )

            try:
                prediction = analyzer.predict(
                    conn,
                    draw_type_id,
                    target_date,
                    turbo_variant=variant,
                    top_roots=5,
                    candidates_per_root=10,
                )
            except Exception as e:
                return {"error": f"prediction failed: {str(e)[:200]}"}

            # Get Turbo formula for numbers required
            formula = TURBO_FORMULAS.get(f"TURBO_{variant.replace('turbo_', '').upper()}")
            numbers_required = formula.numbers_required if formula else 2

            # Format output
            return {
                "draw_type": display_name,
                "target_date": str(target_date),
                "variant": variant,
                "numbers_required": numbers_required,
                "predicted_roots": [
                    {
                        "root": p.root,
                        "confidence": p.confidence,
                        "uncertainty_level": p.uncertainty_level,
                        "observation_window_days": p.observation_window_days,
                        "comparison_to_random": p.comparison_to_random,
                    }
                    for p in prediction.predicted_roots
                ],
                "turbo_candidates": [
                    {
                        "number": c.number,
                        "root": c.root,
                        "rank_in_family": c.rank_in_family,
                        "historical_frequency": c.historical_frequency,
                        "adjusted_score": c.adjusted_score,
                    }
                    for c in prediction.turbo_candidates
                ],
                "final_selection": prediction.get_final_selection(numbers_required),
                "metadata": prediction.metadata,
            }

    def _digital_root_turbo_daily(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Daily digital root Turbo predictions for all games with official results."""
        from lottery_intelligence_platform.digital_root_analyzer import DigitalRootTurboAnalyzer
        from lottery_intelligence_platform.betting_formulas import TURBO_FORMULAS
        from lottery_intelligence_platform.digital_root import digital_root

        date_str = (qs.get("date") or [None])[0]
        if date_str:
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                return {"error": f"invalid date: {date_str}"}
        else:
            target_date = date.today()

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Get all draw types
            draw_types = conn.execute(
                """SELECT dt.draw_type_id, dt.display_name, dt.code
                   FROM catalog.draw_types dt
                   ORDER BY dt.display_name"""
            ).fetchall()

            # Get draws for the target date
            draws = conn.execute(
                """SELECT d.draw_id, d.draw_type_id, d.scheduled_date, d.status,
                          dv.validation_status, dv.version_number, dv.draw_version_id
                   FROM core.draws d
                   LEFT JOIN core.draw_versions dv
                     ON dv.draw_id = d.draw_id
                    AND dv.version_number = (
                        SELECT MAX(version_number) FROM core.draw_versions v2
                        WHERE v2.draw_id = d.draw_id
                    )
                   WHERE d.scheduled_date = %s
                   ORDER BY d.scheduled_sequence""",
                (target_date,),
            ).fetchall()

            # Get winning numbers for settled draws
            draw_ids = [d[0] for d in draws]
            winning_numbers = {}
            if draw_ids:
                win_rows = conn.execute(
                    """SELECT dv.draw_version_id, dn.number, dn.position
                       FROM core.draw_numbers dn
                       JOIN core.draw_versions dv ON dv.draw_version_id = dn.draw_version_id
                       WHERE dv.validation_status = 'VALID'
                         AND dn.number_role = 'WINNING'
                         AND dv.draw_id = ANY(%s)
                       ORDER BY dv.draw_id, dn.position""",
                    (draw_ids,),
                ).fetchall()
                for dv_id, number, position in win_rows:
                    if dv_id not in winning_numbers:
                        winning_numbers[dv_id] = []
                    winning_numbers[dv_id].append(number)

            analyzer = DigitalRootTurboAnalyzer(
                observation_window_days=3,
                min_observations=5,
            )

            daily_predictions = []
            for draw_id, draw_type_id, scheduled_date, status, validation_status, version_number, dv_id in draws:
                draw_type = next((dt for dt in draw_types if dt[0] == draw_type_id), None)
                if not draw_type:
                    continue

                draw_type_id, display_name, code = draw_type

                # Get winning numbers if available
                actual_numbers = None
                actual_roots = None
                if status == 'SETTLED' and validation_status == 'VALID' and dv_id:
                    actual_numbers = winning_numbers.get(dv_id, [])
                    actual_roots = [digital_root(n) for n in actual_numbers] if actual_numbers else None

                # Generate predictions for Turbo 2 and Turbo 5
                predictions = {}
                for variant in ["turbo_2", "turbo_5"]:
                    try:
                        pred = analyzer.predict(
                            conn,
                            draw_type_id,
                            target_date,
                            turbo_variant=variant,
                            top_roots=5,
                            candidates_per_root=10,
                        )
                        formula = TURBO_FORMULAS.get(f"TURBO_{variant.replace('turbo_', '').upper()}")
                        numbers_required = formula.numbers_required if formula else 2

                        predictions[variant] = {
                            "predicted_roots": [p.root for p in pred.predicted_roots],
                            "final_selection": pred.get_final_selection(numbers_required),
                            "numbers_required": numbers_required,
                        }
                    except Exception as e:
                        predictions[variant] = {"error": str(e)[:100]}

                # Generate adaptive root prediction
                from lottery_intelligence_platform.adaptive_root_predictor import AdaptiveRootPredictor
                try:
                    adaptive_predictor = AdaptiveRootPredictor(min_observations=5)
                    # Load historical data for adaptive predictor
                    historical_draws = conn.execute(
                        """SELECT d.scheduled_date, dn.number
                           FROM core.draws d
                           JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
                           JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
                           WHERE d.draw_type_id = %s
                             AND dv.validation_status = 'VALID'
                             AND dn.number_role = 'WINNING'
                             AND d.scheduled_date < %s
                           ORDER BY d.scheduled_date DESC, d.scheduled_sequence, dn.position
                           LIMIT 200""",
                        (draw_type_id, target_date),
                    ).fetchall()

                    # Group by draw
                    draws_dict = {}
                    for scheduled_date, number in historical_draws:
                        if scheduled_date not in draws_dict:
                            draws_dict[scheduled_date] = []
                        draws_dict[scheduled_date].append(number)

                    draw_records = [
                        {"scheduled_date": d, "numbers": nums}
                        for d, nums in draws_dict.items()
                    ]

                    adaptive_predictor.learn_from_history(draw_records)

                    # Extract hour from target_date
                    draw_hour = target_date.hour if isinstance(target_date, datetime) else 7

                    adaptive_pred = adaptive_predictor.predict_adaptive(
                        target_date=target_date,
                        draw_type=display_name,
                        target_hour=draw_hour,
                        top_roots=5,
                    )

                    predictions["adaptive"] = {
                        "predicted_roots": adaptive_pred.predicted_roots,
                        "confidence": adaptive_pred.confidence,
                        "reasoning": adaptive_pred.reasoning,
                    }
                except Exception as e:
                    predictions["adaptive"] = {"error": str(e)[:100]}

                daily_predictions.append({
                    "draw_id": str(draw_id),
                    "draw_type": display_name,
                    "draw_type_code": code,
                    "scheduled_date": str(scheduled_date),
                    "status": status,
                    "validation_status": validation_status,
                    "actual_numbers": actual_numbers,
                    "actual_roots": actual_roots,
                    "predictions": predictions,
                })

            return {
                "date": str(target_date),
                "total_games": len(daily_predictions),
                "predictions": daily_predictions,
            }

    def _digital_root_turbo_range(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Digital root Turbo predictions for a date range with optional game filter."""
        from lottery_intelligence_platform.digital_root_analyzer import DigitalRootTurboAnalyzer
        from lottery_intelligence_platform.betting_formulas import TURBO_FORMULAS
        from lottery_intelligence_platform.digital_root import digital_root

        start_date_str = (qs.get("start_date") or [None])[0]
        end_date_str = (qs.get("end_date") or [None])[0]
        draw_type = (qs.get("draw_type") or [None])[0]

        if start_date_str:
            try:
                start_date = date.fromisoformat(start_date_str)
            except ValueError:
                return {"error": f"invalid start_date: {start_date_str}"}
        else:
            start_date = date.today() - timedelta(days=7)

        if end_date_str:
            try:
                end_date = date.fromisoformat(end_date_str)
            except ValueError:
                return {"error": f"invalid end_date: {end_date_str}"}
        else:
            end_date = date.today()

        if start_date > end_date:
            return {"error": "start_date must be before or equal to end_date"}

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Get draw type filter
            draw_type_filter = ""
            draw_type_params = []
            if draw_type:
                draw_type_filter = "AND (dt.code = %s OR dt.display_name = %s)"
                draw_type_params = [draw_type, draw_type]

            # Get draws for the date range
            draws = conn.execute(
                f"""SELECT d.draw_id, d.draw_type_id, d.scheduled_date, d.status,
                          dv.validation_status, dv.version_number, dv.draw_version_id,
                          dt.display_name, dt.code
                   FROM core.draws d
                   LEFT JOIN core.draw_versions dv
                     ON dv.draw_id = d.draw_id
                    AND dv.version_number = (
                        SELECT MAX(version_number) FROM core.draw_versions v2
                        WHERE v2.draw_id = d.draw_id
                    )
                   JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
                   WHERE d.scheduled_date BETWEEN %s AND %s
                   {draw_type_filter}
                   ORDER BY d.scheduled_date, d.scheduled_sequence""",
                (start_date, end_date, *draw_type_params),
            ).fetchall()

            # Get winning numbers for settled draws
            draw_ids = [d[0] for d in draws]
            winning_numbers = {}
            if draw_ids:
                win_rows = conn.execute(
                    """SELECT dv.draw_version_id, dn.number, dn.position
                       FROM core.draw_numbers dn
                       JOIN core.draw_versions dv ON dv.draw_version_id = dn.draw_version_id
                       WHERE dv.validation_status = 'VALID'
                         AND dn.number_role = 'WINNING'
                         AND dv.draw_id = ANY(%s)
                       ORDER BY dv.draw_id, dn.position""",
                    (draw_ids,),
                ).fetchall()
                for dv_id, number, position in win_rows:
                    if dv_id not in winning_numbers:
                        winning_numbers[dv_id] = []
                    winning_numbers[dv_id].append(number)

            analyzer = DigitalRootTurboAnalyzer(
                observation_window_days=3,
                min_observations=5,
            )

            daily_predictions = []
            for draw_id, draw_type_id, scheduled_date, status, validation_status, version_number, dv_id, display_name, code in draws:
                # Get winning numbers if available
                actual_numbers = None
                actual_roots = None
                if status == 'SETTLED' and validation_status == 'VALID' and dv_id:
                    actual_numbers = winning_numbers.get(dv_id, [])
                    actual_roots = [digital_root(n) for n in actual_numbers] if actual_numbers else None

                # Generate predictions for Turbo 2 and Turbo 5
                predictions = {}
                for variant in ["turbo_2", "turbo_5"]:
                    try:
                        pred = analyzer.predict(
                            conn,
                            draw_type_id,
                            scheduled_date,
                            turbo_variant=variant,
                            top_roots=5,
                            candidates_per_root=10,
                        )
                        formula = TURBO_FORMULAS.get(f"TURBO_{variant.replace('turbo_', '').upper()}")
                        numbers_required = formula.numbers_required if formula else 2

                        predictions[variant] = {
                            "predicted_roots": [p.root for p in pred.predicted_roots],
                            "final_selection": pred.get_final_selection(numbers_required),
                            "numbers_required": numbers_required,
                        }
                    except Exception as e:
                        predictions[variant] = {"error": str(e)[:100]}

                # Generate adaptive root prediction
                from lottery_intelligence_platform.adaptive_root_predictor import AdaptiveRootPredictor
                try:
                    adaptive_predictor = AdaptiveRootPredictor(min_observations=5)
                    # Load historical data for adaptive predictor
                    historical_draws = conn.execute(
                        """SELECT d.scheduled_date, dn.number
                           FROM core.draws d
                           JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
                           JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
                           WHERE d.draw_type_id = %s
                             AND dv.validation_status = 'VALID'
                             AND dn.number_role = 'WINNING'
                             AND d.scheduled_date < %s
                           ORDER BY d.scheduled_date DESC, d.scheduled_sequence, dn.position
                           LIMIT 200""",
                        (draw_type_id, scheduled_date),
                    ).fetchall()

                    # Group by draw
                    draws_dict = {}
                    for scheduled_date, number in historical_draws:
                        if scheduled_date not in draws_dict:
                            draws_dict[scheduled_date] = []
                        draws_dict[scheduled_date].append(number)

                    draw_records = [
                        {"scheduled_date": d, "numbers": nums}
                        for d, nums in draws_dict.items()
                    ]

                    adaptive_predictor.learn_from_history(draw_records)

                    # Extract hour from scheduled_date
                    draw_hour = scheduled_date.hour if isinstance(scheduled_date, datetime) else 7

                    adaptive_pred = adaptive_predictor.predict_adaptive(
                        target_date=scheduled_date,
                        draw_type=display_name,
                        target_hour=draw_hour,
                        top_roots=5,
                    )

                    predictions["adaptive"] = {
                        "predicted_roots": adaptive_pred.predicted_roots,
                        "confidence": adaptive_pred.confidence,
                        "reasoning": adaptive_pred.reasoning,
                    }
                except Exception as e:
                    predictions["adaptive"] = {"error": str(e)[:100]}

                daily_predictions.append({
                    "draw_id": str(draw_id),
                    "draw_type": display_name,
                    "draw_type_code": code,
                    "scheduled_date": str(scheduled_date),
                    "status": status,
                    "validation_status": validation_status,
                    "actual_numbers": actual_numbers,
                    "actual_roots": actual_roots,
                    "predictions": predictions,
                })

            return {
                "start_date": str(start_date),
                "end_date": str(end_date),
                "total_games": len(daily_predictions),
                "predictions": daily_predictions,
            }

    def _adaptive_root_predict(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Generate adaptive root prediction using machine learning."""
        from lottery_intelligence_platform.adaptive_root_predictor import AdaptiveRootPredictor
        from lottery_intelligence_platform.digital_root import digital_root

        draw_type = (qs.get("draw_type") or [None])[0]
        date_str = (qs.get("date") or [None])[0]
        hour_str = (qs.get("hour") or [None])[0]
        top_roots = int((qs.get("top_roots") or ["5"])[0])

        if date_str:
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                return {"error": f"invalid date: {date_str}"}
        else:
            target_date = date.today()

        target_hour = int(hour_str) if hour_str else None

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # Load historical data for training
            if draw_type:
                dt = conn.execute(
                    """SELECT draw_type_id, display_name FROM catalog.draw_types
                       WHERE code = %s OR display_name = %s""",
                    (draw_type, draw_type),
                ).fetchone()
            else:
                dt = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                ).fetchone()

            if dt is None:
                return {"error": f"unknown draw_type: {draw_type}"}

            draw_type_id, display_name = dt

            # Load historical draws
            draws = conn.execute(
                """SELECT d.scheduled_date, dn.number
                   FROM core.draws d
                   JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
                   JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
                   WHERE d.draw_type_id = %s
                     AND dv.validation_status = 'VALID'
                     AND dn.number_role = 'WINNING'
                     AND d.scheduled_date < %s
                   ORDER BY d.scheduled_date DESC, d.scheduled_sequence, dn.position
                   LIMIT 200""",
                (draw_type_id, target_date),
            ).fetchall()

            # Group by draw
            draws_dict = {}
            for scheduled_date, number in draws:
                if scheduled_date not in draws_dict:
                    draws_dict[scheduled_date] = []
                draws_dict[scheduled_date].append(number)

            # Convert to list of dicts
            draw_records = [
                {"scheduled_date": d, "numbers": nums}
                for d, nums in draws_dict.items()
            ]

            # Create and train predictor
            predictor = AdaptiveRootPredictor(min_observations=5)
            predictor.learn_from_history(draw_records)

            # Generate prediction
            prediction = predictor.predict_adaptive(
                target_date=target_date,
                draw_type=display_name,
                target_hour=target_hour,
                top_roots=top_roots,
            )

            return {
                "draw_type": display_name,
                "target_date": str(target_date),
                "target_hour": target_hour,
                "predicted_roots": prediction.predicted_roots,
                "confidence": prediction.confidence,
                "reasoning": prediction.reasoning,
                "adaptive_factors": prediction.adaptive_factors,
            }

    def _adaptive_root_train(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Train the adaptive predictor on historical data."""
        from lottery_intelligence_platform.adaptive_root_predictor import AdaptiveRootPredictor
        from lottery_intelligence_platform.digital_root import digital_root

        draw_type = (qs.get("draw_type") or [None])[0]
        days_back = int((qs.get("days_back") or ["30"])[0])

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt = conn.execute(
                    """SELECT draw_type_id, display_name FROM catalog.draw_types
                       WHERE code = %s OR display_name = %s""",
                    (draw_type, draw_type),
                ).fetchone()
            else:
                dt = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                ).fetchone()

            if dt is None:
                return {"error": f"unknown draw_type: {draw_type}"}

            draw_type_id, display_name = dt

            # Load historical draws
            cutoff_date = date.today() - timedelta(days=days_back)
            draws = conn.execute(
                """SELECT d.scheduled_date, dn.number
                   FROM core.draws d
                   JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
                   JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
                   WHERE d.draw_type_id = %s
                     AND dv.validation_status = 'VALID'
                     AND dn.number_role = 'WINNING'
                     AND d.scheduled_date >= %s
                   ORDER BY d.scheduled_date, d.scheduled_sequence, dn.position""",
                (draw_type_id, cutoff_date),
            ).fetchall()

            # Group by draw
            draws_dict = {}
            for scheduled_date, number in draws:
                if scheduled_date not in draws_dict:
                    draws_dict[scheduled_date] = []
                draws_dict[scheduled_date].append(number)

            # Convert to list of dicts
            draw_records = [
                {"scheduled_date": d, "numbers": nums}
                for d, nums in draws_dict.items()
            ]

            # Create and train predictor
            predictor = AdaptiveRootPredictor(min_observations=5)
            predictor.learn_from_history(draw_records)

            return {
                "draw_type": display_name,
                "training_period_days": days_back,
                "draws_trained_on": len(draw_records),
                "statistics": predictor.get_statistics(),
            }

    def _adaptive_root_stats(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Get current adaptive predictor statistics."""
        from lottery_intelligence_platform.adaptive_root_predictor import AdaptiveRootPredictor

        draw_type = (qs.get("draw_type") or [None])[0]

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt = conn.execute(
                    """SELECT draw_type_id, display_name FROM catalog.draw_types
                       WHERE code = %s OR display_name = %s""",
                    (draw_type, draw_type),
                ).fetchone()
            else:
                dt = conn.execute(
                    """SELECT dt.draw_type_id, dt.display_name
                       FROM catalog.draw_types dt
                       ORDER BY (SELECT count(*) FROM core.draws d
                                 WHERE d.draw_type_id = dt.draw_type_id) DESC
                       LIMIT 1""",
                ).fetchone()

            if dt is None:
                return {"error": f"unknown draw_type: {draw_type}"}

            draw_type_id, display_name = dt

            # Load historical draws
            draws = conn.execute(
                """SELECT d.scheduled_date, dn.number
                   FROM core.draws d
                   JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
                   JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
                   WHERE d.draw_type_id = %s
                     AND dv.validation_status = 'VALID'
                     AND dn.number_role = 'WINNING'
                   ORDER BY d.scheduled_date DESC, d.scheduled_sequence, dn.position
                   LIMIT 200""",
                (draw_type_id,),
            ).fetchall()

            # Group by draw
            draws_dict = {}
            for scheduled_date, number in draws:
                if scheduled_date not in draws_dict:
                    draws_dict[scheduled_date] = []
                draws_dict[scheduled_date].append(number)

            # Convert to list of dicts
            draw_records = [
                {"scheduled_date": d, "numbers": nums}
                for d, nums in draws_dict.items()
            ]

            # Create and train predictor
            predictor = AdaptiveRootPredictor(min_observations=5)
            predictor.learn_from_history(draw_records)

            return {
                "draw_type": display_name,
                "statistics": predictor.get_statistics(),
            }

    def _fusion_agents(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Decisions of the virtual fusion betting agents for one draw type.

        Strict walk-forward: each agent only sees the settled history already
        present, never the future. Read-only — nothing is persisted or sealed.
        """
        from collections import OrderedDict
        import random as _random

        from lottery_intelligence_platform import fusion_agents as fa

        draw_type = (qs.get("draw_type") or [None])[0]
        target_date = (qs.get("date") or [None])[0]
        status_filter = (qs.get("status") or [None])[0]
        
        from datetime import date as _date
        
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt = conn.execute(
                    "SELECT draw_type_id, display_name FROM catalog.draw_types "
                    "WHERE code = %s OR display_name = %s "
                    "ORDER BY (SELECT count(*) FROM core.draws d "
                    "WHERE d.draw_type_id = catalog.draw_types.draw_type_id) DESC LIMIT 1",
                    (draw_type, draw_type),
                ).fetchone()
            else:
                dt = conn.execute(
                    "SELECT dt.draw_type_id, dt.display_name FROM catalog.draw_types dt "
                    "ORDER BY (SELECT count(*) FROM core.draws d "
                    "WHERE d.draw_type_id = dt.draw_type_id) DESC LIMIT 1",
                ).fetchone()
            if dt is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            draw_type_id, display_name = dt
            
            # Build history for predictions (always use full history for predictions)
            history_rows = conn.execute(
                """SELECT d.scheduled_date, d.scheduled_sequence, n.number
                   FROM core.draws d
                   JOIN core.draw_versions v
                     ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                   JOIN core.draw_numbers n
                     ON n.draw_version_id = v.draw_version_id AND n.number_role = 'WINNING'
                   WHERE d.draw_type_id = %s AND d.status = 'SETTLED'
                   ORDER BY d.scheduled_date, d.scheduled_sequence, n.position""",
                (draw_type_id,),
            ).fetchall()
            
            draws: "OrderedDict[tuple[Any, Any], list[int]]" = OrderedDict()
            for d, seq, num in history_rows:
                draws.setdefault((d, seq), []).append(num)
            history = [list(nums) for nums in draws.values()]
            draw_dates = [str(k[0]) for k in draws.keys()]
            
            # Get target draw if specified
            target_draw = None
            target_draw_date = None
            target_draw_id = None
            target_status = "EXPECTED"
            if target_date:
                target_draw_rows = conn.execute(
                    """SELECT d.draw_id, d.scheduled_date, d.status
                       FROM core.draws d
                       WHERE d.draw_type_id = %s AND d.scheduled_date = %s""",
                    (draw_type_id, target_date),
                ).fetchall()
                if target_draw_rows:
                    target_draw_id, target_draw_date, target_status = target_draw_rows[0]
            
            # Get last draw date for display
            last_draw_date = draw_dates[-1] if draw_dates else None
            last_draw = history[-1] if history else []
            last_target = _date.fromisoformat(last_draw_date) if last_draw_date else None

            rng = _random.Random(len(history))
            decisions = []
            for profile in fa.FUSION_AGENT_PROFILES:
                if profile.strategy == "digital_root_turbo":
                    with psycopg.connect(self.dsn, autocommit=True) as conn2:
                        d = fa.decide(profile, history, rng, k=5, connection=conn2,
                                      draw_type_id=draw_type_id, target=last_target)
                else:
                    d = fa.decide(profile, history, rng, k=5)
                
                # Calculate hits if target draw is settled
                hits = 0
                outcome = "PENDING"
                net_result = 0
                if target_draw_date and target_status == "SETTLED":
                    # Get winning numbers for target draw
                    winning_rows = conn.execute(
                        """SELECT n.number
                           FROM core.draws d
                           JOIN core.draw_versions v ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                           JOIN core.draw_numbers n ON n.draw_version_id = v.draw_version_id AND n.number_role = 'WINNING'
                           WHERE d.draw_id = %s""",
                        (target_draw_id,),
                    ).fetchall()
                    winning_numbers = [r[0] for r in winning_rows]
                    hits = len(set(d["selected_numbers"]) & set(winning_numbers))
                    outcome = "WIN" if hits > 0 else "LOSS"
                    net_result = hits * 1000 if hits > 0 else -500  # Simple example scoring
                
                decisions.append({
                    "code": d["code"],
                    "display_name": d["display_name"],
                    "strategy": d["strategy"],
                    "bet_type": d["bet_type"],
                    "selected_numbers": d["selected_numbers"],
                    "stake_amount": str(d["stake_amount"]),
                    "confidence_score": d["confidence_score"],
                    "reasoning": d["reasoning"],
                    "hits": hits,
                    "outcome": outcome,
                    "net_result": net_result,
                    "target_date": target_draw_date,
                })
            
            # Get winning numbers for target draw if settled
            target_draw_numbers = []
            if target_draw_id and target_status == "SETTLED":
                winning_rows = conn.execute(
                    """SELECT n.number
                       FROM core.draws d
                       JOIN core.draw_versions v ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                       JOIN core.draw_numbers n ON n.draw_version_id = v.draw_version_id AND n.number_role = 'WINNING'
                       WHERE d.draw_id = %s""",
                    (target_draw_id,),
                ).fetchall()
                target_draw_numbers = [r[0] for r in winning_rows]
            
            # capital virtuel persisté (edge_lab) si les agents ont été backfillés
            try:
                cap_rows = conn.execute(
                    "SELECT a.code, c.current_capital, c.net_profit, c.total_bets, "
                    "c.winning_bets, c.roi FROM edge_lab.agents a "
                    "JOIN edge_lab.agent_capital c ON c.agent_id = a.agent_id"
                ).fetchall()
            except Exception:
                cap_rows = []
            cap = {r[0]: {"persisted_capital": float(r[1]), "persisted_profit": float(r[2]),
                          "persisted_bets": r[3], "persisted_wins": r[4],
                          "persisted_roi": float(r[5]) if r[5] is not None else None}
                   for r in cap_rows}
            for dec in decisions:
                if dec["code"] in cap:
                    dec.update(cap[dec["code"]])
            
            return {
                "draw_type": display_name,
                "n_draws": len(history),
                "target_date": target_draw_date,
                "target_status": target_status if target_date else "EXPECTED",
                "target_draw_numbers": target_draw_numbers,
                "agents": decisions,
            }
        # capital virtuel persisté (edge_lab) si les agents ont été backfillés
        try:
            with psycopg.connect(self.dsn, autocommit=True) as conn2:
                cap_rows = conn2.execute(
                    "SELECT a.code, c.current_capital, c.net_profit, c.total_bets, "
                    "c.winning_bets, c.roi FROM edge_lab.agents a "
                    "JOIN edge_lab.agent_capital c ON c.agent_id = a.agent_id"
                ).fetchall()
        except Exception:
            cap_rows = []
        cap = {r[0]: {"persisted_capital": float(r[1]), "persisted_profit": float(r[2]),
                      "persisted_bets": r[3], "persisted_wins": r[4],
                      "persisted_roi": float(r[5]) if r[5] is not None else None}
               for r in cap_rows}
        for dec in decisions:
            if dec["code"] in cap:
                dec.update(cap[dec["code"]])
        
        # Get winning numbers for target draw if settled
        target_draw_numbers = []
        if target_draw_id and target_status == "SETTLED":
            winning_rows = conn.execute(
                """SELECT n.number
                   FROM core.draws d
                   JOIN core.draw_versions v ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                   JOIN core.draw_numbers n ON n.draw_version_id = v.draw_version_id AND n.number_role = 'WINNING'
                   WHERE d.draw_id = %s""",
                (target_draw_id,),
            ).fetchall()
            target_draw_numbers = [r[0] for r in winning_rows]
        
        return {
            "draw_type": display_name,
            "n_draws": len(history),
            "target_date": target_draw_date,
            "target_status": target_status if target_date else "EXPECTED",
            "target_draw_numbers": target_draw_numbers,
            "agents": decisions,
        }

    def _fusion_agent_detail(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Walk-forward detail (capital, profit, bets, versions) for ONE agent."""
        from collections import OrderedDict
        import random as _random

        from lottery_intelligence_platform import fusion_agents as fa

        code = (qs.get("code") or [None])[0]
        draw_type = (qs.get("draw_type") or [None])[0]
        window = min(int((qs.get("window") or ["20"])[0]), 100)
        profile = fa.get_profile(code) if code else None
        if profile is None:
            return {"error": f"unknown agent code: {code}"}

        with psycopg.connect(self.dsn, autocommit=True) as conn:
            if draw_type:
                dt = conn.execute(
                    "SELECT draw_type_id, display_name FROM catalog.draw_types "
                    "WHERE code = %s OR display_name = %s "
                    "ORDER BY (SELECT count(*) FROM core.draws d "
                    "WHERE d.draw_type_id = catalog.draw_types.draw_type_id) DESC LIMIT 1",
                    (draw_type, draw_type),
                ).fetchone()
            else:
                dt = conn.execute(
                    "SELECT dt.draw_type_id, dt.display_name FROM catalog.draw_types dt "
                    "ORDER BY (SELECT count(*) FROM core.draws d "
                    "WHERE d.draw_type_id = dt.draw_type_id) DESC LIMIT 1",
                ).fetchone()
            if dt is None:
                return {"error": f"unknown draw_type: {draw_type}"}
            draw_type_id, display_name = dt
            rows = conn.execute(
                """SELECT d.scheduled_date, d.scheduled_sequence, n.number
                   FROM core.draws d
                   JOIN core.draw_versions v
                     ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                   JOIN core.draw_numbers n
                     ON n.draw_version_id = v.draw_version_id AND n.number_role = 'WINNING'
                   WHERE d.draw_type_id = %s AND d.status = 'SETTLED'
                   ORDER BY d.scheduled_date, d.scheduled_sequence, n.position""",
                (draw_type_id,),
            ).fetchall()
        draws: "OrderedDict[tuple[Any, Any], list[int]]" = OrderedDict()
        for d, seq, num in rows:
            draws.setdefault((d, seq), []).append(num)
        history = [list(nums) for nums in draws.values()]
        draw_dates = [str(k[0]) for k in draws.keys()]

        rng = _random.Random(len(history))
        with psycopg.connect(self.dsn, autocommit=True) as conn2:
            detail = fa.walkforward_detail(profile, history, window=window, rng=rng,
                                           dates=draw_dates, connection=conn2,
                                           draw_type_id=draw_type_id)
        detail["draw_type"] = display_name
        detail["n_draws"] = len(history)
        return detail

    def _draws_by_date(self, qs: dict[str, list[str]]) -> dict[str, Any]:
        """Get all draw types for a specific date."""
        date = (qs.get("date") or [None])[0]
        if not date:
            return {"error": "date parameter required"}
        
        try:
            from datetime import date as _date
            _date.fromisoformat(date)
        except ValueError:
            return {"error": "date must be YYYY-MM-DD"}
        
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            rows = conn.execute(
                """SELECT DISTINCT dt.draw_type_id, dt.code, dt.display_name, d.status, d.scheduled_date
                   FROM catalog.draw_types dt
                   JOIN core.draws d ON d.draw_type_id = dt.draw_type_id
                   WHERE d.scheduled_date = %s
                   ORDER BY dt.display_name""",
                (date,),
            ).fetchall()
        
        return {
            "data": [
                {
                    "draw_type_id": r[0],
                    "code": r[1],
                    "display_name": r[2],
                    "status": r[3],
                    "scheduled_date": str(r[4])
                }
                for r in rows
            ]
        }

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        url = urlparse(self.path)
        if not url.path.startswith("/api"):
            self._serve_static(url.path)
            return
        if self.token is not None and self.token != "":
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {self.token}":
                self._send({"error": "unauthorized"}, 401)
                return
        try:
            if url.path == "/api/draws":
                qs = parse_qs(url.query)
                day = (qs.get("date") or [None])[0]
                date_from = (qs.get("from") or [None])[0]
                date_to = (qs.get("to") or [None])[0]
                for raw in (day, date_from, date_to):
                    if raw is not None:
                        try:
                            date.fromisoformat(raw)
                        except ValueError:
                            self._send({"error": "dates must be YYYY-MM-DD"}, 400)
                            return
                status = (qs.get("status") or [None])[0]
                if status is not None and status not in ("SETTLED", "FROZEN", "EXPECTED"):
                    self._send({"error": "invalid status"}, 400)
                    return
                limit = min(int((qs.get("limit") or ["100"])[0]), 2000)
                self._send({"data": self._query(DRAWS_SQL, {
                    "date": day, "from": date_from, "to": date_to,
                    "type": (qs.get("type") or [None])[0],
                    "status": status, "limit": limit})})
                return
            if url.path == "/api/predictions":
                qs = parse_qs(url.query)
                status = (qs.get("status") or [None])[0]
                if status is not None and status not in ("PENDING", "LOCKED", "SCORED", "INVALID"):
                    self._send({"error": "invalid status"}, 400)
                    return
                date_from = (qs.get("from") or [None])[0]
                date_to = (qs.get("to") or [None])[0]
                day = (qs.get("date") or [None])[0]
                for raw in (day, date_from, date_to):
                    if raw is not None:
                        try:
                            date.fromisoformat(raw)
                        except ValueError:
                            self._send({"error": "dates must be YYYY-MM-DD"}, 400)
                            return
                limit = min(int((qs.get("limit") or ["100"])[0]), 500)
                self._send({"predictions": self._query(
                    PREDICTIONS_SQL, {
                        "status": status, "date": day,
                        "from": date_from, "to": date_to, "limit": limit})})
                return
            if url.path == "/api/lab/draw-types-on-date":
                day = (parse_qs(url.query).get("date") or [None])[0]
                if day is None:
                    self._send({"error": "date is required"}, 400)
                    return
                try:
                    date.fromisoformat(day)
                except ValueError:
                    self._send({"error": "date must be YYYY-MM-DD"}, 400)
                    return
                self._send({"data": self._query(
                    ROUTES["/api/lab/draw-types-on-date"], {"date": day})})
                return
            if url.path == "/api/lab/matrix":
                self._send(self._lab_matrix(parse_qs(url.query)))
                return
            if url.path == "/api/digital-root-stats/summary":
                self._send(self._digital_root_stats(parse_qs(url.query)))
                return
            if url.path == "/api/lab/calling-image":
                self._send(self._lab_calling_image(parse_qs(url.query)))
                return
            if url.path == "/api/lab/consensus":
                self._send(self._lab_consensus(parse_qs(url.query)))
                return
            if url.path == "/api/lab/structure-map":
                self._send(self._lab_structure_map(parse_qs(url.query)))
                return
            if url.path == "/api/lab/cross-game":
                self._send(self._lab_cross_game(parse_qs(url.query)))
                return
            if url.path == "/api/lab/candidates":
                self._send(self._lab_candidates(parse_qs(url.query)))
                return
            if url.path == "/api/lab/replay":
                self._send(self._lab_replay(parse_qs(url.query)))
                return
            if url.path == "/api/statistics":
                self._send(self._statistics(parse_qs(url.query)))
                return
            if url.path == "/api/root-statistics":
                self._send(self._root_statistics(parse_qs(url.query)))
                return
            if url.path == "/api/digital-root-statistics":
                self._send(self._digital_root_statistics(parse_qs(url.query)))
                return
            if url.path == "/api/lab/structure":
                self._send(self._lab_structure(parse_qs(url.query)))
                return
            if url.path == "/api/lab/simulation":
                self._send(self._lab_simulation(parse_qs(url.query)))
                return
            if url.path == "/api/lab/coverage":
                self._send(self._lab_coverage(parse_qs(url.query)))
                return
            if url.path == "/api/lab/game-profiles":
                self._send(self._lab_game_profiles(parse_qs(url.query)))
                return
            if url.path == "/api/lab/game-matrix":
                self._send(self._lab_game_matrix(parse_qs(url.query)))
                return
            if url.path == "/api/lab/game-cards":
                self._send(self._lab_game_cards(parse_qs(url.query)))
                return
            if url.path == "/api/lab/turbo2-history":
                self._send(self._lab_turbo2_history(parse_qs(url.query)))
                return
            if url.path == "/api/fusion/agents":
                self._send(self._fusion_agents(parse_qs(url.query)))
                return
            if url.path == "/api/digital-root-stats/summary":
                self._send(self._digital_root_stats(parse_qs(url.query)))
                return
            if url.path == "/api/digital-root-turbo/predictions":
                self._send(self._digital_root_turbo_predictions(parse_qs(url.query)))
                return
            if url.path == "/api/digital-root-turbo/daily":
                self._send(self._digital_root_turbo_daily(parse_qs(url.query)))
                return
            if url.path == "/api/digital-root-turbo/range":
                self._send(self._digital_root_turbo_range(parse_qs(url.query)))
                return
            if url.path == "/api/adaptive-root/predict":
                self._send(self._adaptive_root_predict(parse_qs(url.query)))
                return
            if url.path == "/api/adaptive-root/train":
                self._send(self._adaptive_root_train(parse_qs(url.query)))
                return
            if url.path == "/api/adaptive-root/stats":
                self._send(self._adaptive_root_stats(parse_qs(url.query)))
                return
            if url.path == "/api/fusion/agent-detail":
                self._send(self._fusion_agent_detail(parse_qs(url.query)))
                return
            if url.path == "/api/lab/draws-by-date":
                self._send(self._draws_by_date(parse_qs(url.query)))
                return
            sql = ROUTES.get(url.path)
            if sql is None:
                self._send({"error": "not found",
                            "routes": sorted(ROUTES) + [
                                "/api/predictions?status=&limit=",
                                "/api/lab/replay?draw_type=&date=",
                                "/api/statistics?draw_type=&days="]}, 404)
                return
            rows = self._query(sql)
            if url.path in ("/api/health", "/api/overview", "/api/turbo/summary"):
                self._send({"data": rows[0]})
            else:
                self._send({"data": rows})
        except Exception as exc:  # noqa: BLE001 - surface as 500, keep serving
            self._send({"error": str(exc)[:300]}, 500)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self._send({"error": "not found"}, 404)
            return
        ctype = ("text/html" if path.suffix == ".html"
                 else "text/css" if path.suffix == ".css"
                 else "text/javascript" if path.suffix == ".js"
                 else "image/svg+xml" if path.suffix == ".svg"
                 else "application/octet-stream")
        if path.suffix == ".html":
            ctype += "; charset=utf-8"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Lottery platform read API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--dsn", default=os.environ.get("LOTTERY_DB_DSN") or _env_dsn())
    args = parser.parse_args()
    ApiHandler.dsn = args.dsn
    ApiHandler.token = os.environ.get("LOTTERY_API_TOKEN") or ""
    if ApiHandler.token == "" and args.host != "127.0.0.1":
        print("warning: no LOTTERY_API_TOKEN set on a non-loopback bind",
              file=sys.stderr)
    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
