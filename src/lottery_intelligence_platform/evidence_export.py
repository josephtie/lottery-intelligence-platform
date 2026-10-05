"""Incremental evidence export to the raw object store.

Prospective predictions are the platform's scarcest asset: a lost PENDING
prediction is lost *proof* that cannot be re-collected from the source. A
daily pg_dump leaves a 24 h hole; this job ships the evidence tables
(predictions, outcomes, coverage, job events, alerts, findings) as NDJSON to
the content-addressed store every hour.

Idempotent by construction: identical bytes hash to the same sha256, so a
no-change export costs nothing.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.raw import RawObjectStore
from lottery_intelligence_platform.scheduler import emit_event

EVIDENCE_TABLES: tuple[str, ...] = (
    "research.predictions",
    "research.prediction_outcomes",
    "research.prediction_coverage",
    "research.prospective_cohort_members",
    "research.prospective_cohort_versions",
    "ops.job_events",
    "ops.alerts",
    "research.findings",
)


def _default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (dict, list)):
        return obj
    return str(obj)


def export_evidence(connection: Any, store: RawObjectStore) -> dict[str, Any]:
    """Serialize evidence tables to NDJSON and store them content-addressed.

    Returns a manifest {tables, sha256, bytes, skipped_unchanged}.
    """
    lines: list[str] = []
    counts: dict[str, int] = {}
    for table in EVIDENCE_TABLES:
        cur = connection.execute(f"SELECT * FROM {table}")  # noqa: S608 - fixed list
        cols = [d.name for d in cur.description]
        n = 0
        for row in cur.fetchall():
            lines.append(json.dumps(
                {"table": table, "row": dict(zip(cols, row))},
                default=_default, sort_keys=True,
            ))
            n += 1
        counts[table] = n
    payload = ("\n".join(lines) + "\n").encode()
    ref = store.put(payload, "application/x-ndjson")
    connection.execute(
        """INSERT INTO ops.audit_events
               (audit_event_id, actor, action, entity_type, entity_id,
                attempted_value, outcome)
           VALUES (gen_random_uuid(), 'export_evidence', 'EVIDENCE_EXPORTED',
                   'raw_object', gen_random_uuid(), %s, 'ALLOWED')""",
        (Jsonb({"object_key": ref.object_key}),),
    )
    emit_event(
        connection, "EVIDENCE_EXPORTED",
        {"sha256": ref.sha256, "byte_size": ref.byte_size, "tables": counts},
    )
    return {
        "tables": counts,
        "rows": sum(counts.values()),
        "sha256": ref.sha256,
        "byte_size": ref.byte_size,
        "object_key": ref.object_key,
    }
