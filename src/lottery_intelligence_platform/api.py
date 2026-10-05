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
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import psycopg

from lottery_intelligence_platform import lab_matrix
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
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
                f"""SELECT d.scheduled_date, n.number, n.position
                    FROM core.draws d
                    JOIN core.draw_versions v
                      ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
                    JOIN core.draw_numbers n
                      ON n.draw_version_id = v.draw_version_id
                     AND n.number_role = 'WINNING'
                    WHERE d.draw_type_id = %s {clause}
                    ORDER BY d.scheduled_date DESC, n.position""",
                params,
            ).fetchall()
        draw_dates = sorted({r[0] for r in rows}, reverse=True)
        draw_count = len(draw_dates)
        date_rank = {d: i for i, d in enumerate(draw_dates)}
        counts = {n: 0 for n in range(1, 91)}
        first_two = {n: 0 for n in range(1, 91)}
        last_rank = {n: None for n in range(1, 91)}
        last_date: dict[int, date | None] = {n: None for n in range(1, 91)}
        by_draw: dict[date, list[int]] = {}
        for draw_date, number, position in rows:
            counts[number] += 1
            if position is not None and position <= 2:
                first_two[number] += 1
            by_draw.setdefault(draw_date, []).append(number)
            rank = date_rank[draw_date]
            if last_rank[number] is None or rank < last_rank[number]:
                last_rank[number] = rank
                last_date[number] = draw_date
        # Most frequent unordered winning pairs within a draw
        pair_counts: dict[tuple[int, int], int] = {}
        pair_last: dict[tuple[int, int], date] = {}
        for draw_date, nums in by_draw.items():
            nums = sorted(set(nums))
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    pair = (nums[i], nums[j])
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
                    pair_last.setdefault(pair, draw_date)
        pairs = [
            {"pair": [a, b], "count": c, "last_date": pair_last[(a, b)].isoformat()}
            for (a, b), c in sorted(
                pair_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
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

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        url = urlparse(self.path)
        if not url.path.startswith("/api"):
            self._serve_static(url.path)
            return
        if self.token is not None:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {self.token}":
                self._send({"error": "unauthorized"}, 401)
                return
        try:
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
            if url.path == "/api/lab/candidates":
                self._send(self._lab_candidates(parse_qs(url.query)))
                return
            if url.path == "/api/lab/replay":
                self._send(self._lab_replay(parse_qs(url.query)))
                return
            if url.path == "/api/statistics":
                self._send(self._statistics(parse_qs(url.query)))
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
    ApiHandler.token = os.environ.get("LOTTERY_API_TOKEN") or None
    if ApiHandler.token is None and args.host != "127.0.0.1":
        print("warning: no LOTTERY_API_TOKEN set on a non-loopback bind",
              file=sys.stderr)
    server = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    print(f"listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
