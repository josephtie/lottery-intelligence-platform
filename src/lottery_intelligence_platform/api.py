"""Read-only HTTP API over the platform's live views.

Stdlib-only (http.server): no web dependency, localhost bind by default.
Endpoints expose exactly what the research views expose — prospective
metrics, predictions, coverage, findings, outcomes, job health — never
write paths.

    PYTHONPATH=src python -m lottery_intelligence_platform.api --port 8080
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

DEFAULT_DSN = "host=localhost port=5432 dbname=lottery_platform user=directus"


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
}


PREDICTIONS_SQL = """
    SELECT p.prediction_id, mv.code AS model_code, dt.display_name AS draw_type,
           p.scheduled_date, p.predicted_numbers, p.status, p.stake,
           p.created_at
    FROM research.predictions p
    JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
    JOIN catalog.draw_types dt ON dt.draw_type_id = p.draw_type_id
    WHERE (%(status)s IS NULL OR p.status = %(status)s)
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

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        url = urlparse(self.path)
        if self.token is not None:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {self.token}":
                self._send({"error": "unauthorized"}, 401)
                return
        try:
            if url.path in ("/", "/console"):
                html = (Path(__file__).with_name("console.html")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            if url.path == "/api/predictions":
                qs = parse_qs(url.query)
                status = (qs.get("status") or [None])[0]
                if status is not None and status not in ("PENDING", "LOCKED", "SCORED", "INVALID"):
                    self._send({"error": "invalid status"}, 400)
                    return
                limit = min(int((qs.get("limit") or ["100"])[0]), 500)
                self._send({"predictions": self._query(
                    PREDICTIONS_SQL, {"status": status, "limit": limit})})
                return
            sql = ROUTES.get(url.path)
            if sql is None:
                self._send({"error": "not found",
                            "routes": sorted(ROUTES) + ["/api/predictions?status=&limit="]}, 404)
                return
            rows = self._query(sql)
            self._send({"data": rows[0]} if url.path == "/api/health" else {"data": rows})
        except Exception as exc:  # noqa: BLE001 - surface as 500, keep serving
            self._send({"error": str(exc)[:300]}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Lottery platform read API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--dsn", default=os.environ.get("LOTTERY_DB_DSN", DEFAULT_DSN))
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
