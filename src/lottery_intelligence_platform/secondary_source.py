"""Independent second-source import and reconciliation.

The platform's only live source is lotobonheur.ci; it can detect a *correction*
(payload changed) but never a *silent error* (wrong result, never fixed). A
second source closes that gap. Since no second URL is available, the channel is
a file import: an NDJSON file of observations exported from any independent
record (aggregator, published PDF, manual transcription). The file is stored
raw and content-addressed; each observation is reconciled against the canonical
registry. Conflicts are recorded and alerted — never auto-applied.

Input format (one JSON object per line):
    {"draw_date": "2026-10-05", "draw_name": "Fortune Thursday",
     "winning_numbers": [1, 2, 3, 4, 5], "machine_numbers": [..] (optional)}
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

import re
import unicodedata

from lottery_intelligence_platform.ingestion import ingest_payload
from lottery_intelligence_platform.raw import RawObjectStore
from lottery_intelligence_platform.raw_bucket import ensure_bucket
from lottery_intelligence_platform.storage import (
    raw_object_store_from_environment,
    s3_client_from_environment,
)

SOURCE_CODE = "lotobonheur_secondary"


def _code(draw_name: str) -> str:
    """Same normalization the registry uses to derive catalog codes."""
    normalized = unicodedata.normalize("NFKD", draw_name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")


def import_observations(
    connection: Any, store: RawObjectStore, path: Path
) -> dict[str, int]:
    """Store the file raw, then upsert each line as a secondary observation."""
    raw = path.read_bytes()
    source_id = connection.execute(
        "SELECT source_id FROM ingestion.sources WHERE code = %s", (SOURCE_CODE,)
    ).fetchone()[0]
    receipt = ingest_payload(
        connection, store,
        source_id=source_id,
        collector_name="secondary_file_import",
        collector_version="1.0.0",
        payload=raw,
        content_type="application/x-ndjson",
        external_identifiers={"file": path.name},
        request_metadata={"path": str(path)},
    )
    ref = receipt.raw_object
    raw_object_id = receipt.raw_object_id

    imported = skipped = 0
    for lineno, line in enumerate(raw.decode().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        try:
            draw_date = date.fromisoformat(record["draw_date"])
            draw_name = record["draw_name"]
            winning = list(record["winning_numbers"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{path.name}:{lineno}: invalid record") from exc
        machine = record.get("machine_numbers")
        cursor = connection.execute(
            """INSERT INTO ingestion.secondary_observations
                   (source_id, raw_object_id, draw_date, draw_name,
                    winning_numbers, machine_numbers, payload)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (source_id, draw_date, draw_name) DO NOTHING""",
            (source_id, raw_object_id, draw_date, draw_name,
             winning, list(machine) if machine else None, Jsonb(record)),
        )
        imported += cursor.rowcount
        skipped += 1 - cursor.rowcount
    return {"imported": imported, "skipped_existing": skipped,
            "raw_object": ref.object_key}


def reconcile(connection: Any) -> dict[str, int]:
    """Compare every secondary observation against the canonical registry.

    Outcomes: MATCH, MISMATCH (numbers differ), MISSING_PRIMARY (no canonical
    draw that day under that name), UNMATCHED_NAME (name maps to no draw type).
    Conflicts raise a SOURCE_CONFLICT alert — never overwrite the canonical row.
    """
    counts = {"MATCH": 0, "MISMATCH": 0, "MISSING_PRIMARY": 0, "UNMATCHED_NAME": 0}
    observations = connection.execute(
        """SELECT o.observation_id, o.draw_date, o.draw_name,
                  o.winning_numbers, o.machine_numbers
           FROM ingestion.secondary_observations o
           WHERE NOT EXISTS (
               SELECT 1 FROM ingestion.source_comparisons c
               WHERE c.observation_id = o.observation_id
                 AND c.outcome IN ('MATCH', 'MISMATCH'))
           ORDER BY o.draw_date"""
    ).fetchall()

    for obs_id, draw_date, draw_name, winning, machine in observations:
        canonical = connection.execute(
            """SELECT d.draw_id
               FROM core.draws d
               JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
               WHERE d.scheduled_date = %s AND dt.code = %s
               ORDER BY d.created_at DESC LIMIT 1""",
            (draw_date, _code(draw_name)),
        ).fetchone()

        if canonical is None:
            known = connection.execute(
                "SELECT 1 FROM catalog.draw_types WHERE code = %s",
                (_code(draw_name),),
            ).fetchone()
            outcome = "MISSING_PRIMARY" if known else "UNMATCHED_NAME"
            draw_id, primary = None, None
        else:
            draw_id = canonical[0]
            rows = connection.execute(
                """SELECT n.number FROM core.draw_numbers n
                   JOIN core.draws d2 ON d2.canonical_draw_version_id = n.draw_version_id
                   WHERE d2.draw_id = %s AND n.number_role = 'WINNING'
                   ORDER BY n.position""",
                (draw_id,),
            ).fetchall()
            primary = [r[0] for r in rows]
            outcome = "MATCH" if primary == list(winning) else "MISMATCH"

        counts[outcome] += 1
        connection.execute(
            """INSERT INTO ingestion.source_comparisons
                   (observation_id, draw_id, outcome, primary_numbers,
                    secondary_numbers, detail)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (obs_id, draw_id, outcome, primary, list(winning),
             Jsonb({"draw_name": draw_name})),
        )
        if outcome == "MISMATCH":
            _alert(connection, obs_id, draw_id, draw_date, draw_name,
                   primary, list(winning))
    return counts


def _alert(connection: Any, obs_id: UUID, draw_id: UUID, draw_date: date,
           draw_name: str, primary: list[int], secondary: list[int]) -> None:
    key = f"SOURCE_CONFLICT:{obs_id}"
    if connection.execute(
        "SELECT 1 FROM ops.alerts WHERE dedupe_key = %s", (key,)
    ).fetchone():
        return
    connection.execute(
        """INSERT INTO ops.alerts
               (alert_id, code, severity, entity_type, entity_id, details, dedupe_key)
           VALUES (%s, 'SOURCE_CONFLICT', 'CRITICAL', 'core.draws', %s, %s, %s)""",
        (uuid4(), draw_id,
         Jsonb({"draw_date": str(draw_date), "draw_name": draw_name,
                "primary": primary, "secondary": secondary,
                "observation_id": str(obs_id)}), key),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lottery-secondary-import",
        description="Import an independent-source NDJSON file and reconcile "
                    "it against the canonical registry.",
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--no-reconcile", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    load_dotenv()
    host = os.environ.get("LOTTERY_DATABASE_HOST", "localhost")
    port = int(os.environ.get("LOTTERY_DATABASE_PORT", "5432"))
    database = os.environ.get("LOTTERY_DATABASE_NAME", "lottery_platform")
    user = os.environ.get("LOTTERY_DATABASE_USER", "directus")
    bucket = os.environ.get("LOTTERY_S3_BUCKET", "").strip()
    if not bucket:
        raise SystemExit("LOTTERY_S3_BUCKET must be set in the environment")
    s3 = s3_client_from_environment()
    ensure_bucket(s3, bucket)
    store = raw_object_store_from_environment()
    with psycopg.connect(host=host, port=port, dbname=database, user=user) as connection:
        result = import_observations(connection, store, args.file)
        if not args.no_reconcile:
            result["reconciliation"] = reconcile(connection)
        connection.commit()
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
