from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.datasets import DatasetSnapshotManifest


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    dataset_id: UUID
    dataset_version_id: UUID
    version_number: int
    manifest: DatasetSnapshotManifest
    created: bool


class DatasetSnapshotError(RuntimeError):
    pass


def workspace_code_version(project_root: Path | None = None) -> str:
    root = project_root or Path(__file__).resolve().parents[2]
    commit_result = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = commit_result.stdout.strip() if commit_result.returncode == 0 else "no-git-commit"
    files = sorted((root / "src").rglob("*.py"))
    files += sorted((root / "infrastructure" / "postgres" / "migrations").glob("*.sql"))
    files.append(root / "pyproject.toml")
    digest = hashlib.sha256()
    for path in sorted(set(files)):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"git:{commit}+source-tree-sha256:{digest.hexdigest()}"


def latest_schema_version(connection: Any) -> str:
    row = connection.execute(
        "SELECT version FROM ops.schema_migrations ORDER BY version DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise DatasetSnapshotError("no PostgreSQL schema migration has been recorded")
    return row[0]


def create_dataset_snapshot(
    connection: Any,
    *,
    dataset_code: str,
    display_name: str,
    cutoff_at: datetime,
    code_version: str | None = None,
    schema_version: str | None = None,
) -> DatasetSnapshot:
    if not dataset_code.strip() or not display_name.strip():
        raise ValueError("dataset_code and display_name cannot be empty")
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("cutoff_at must be timezone-aware")
    cutoff = cutoff_at.astimezone(timezone.utc)
    code_version = code_version or workspace_code_version()

    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"dataset:{dataset_code}",),
        )
        resolved_schema_version = schema_version or latest_schema_version(connection)
        dataset_id = _ensure_dataset(connection, dataset_code, display_name)
        rows = connection.execute(
            """SELECT dv.draw_version_id, d.game_version_id, gv.rules, dt.rules
               FROM core.draws d
               JOIN core.draw_versions dv ON dv.draw_version_id = d.canonical_draw_version_id
               JOIN catalog.game_versions gv ON gv.game_version_id = d.game_version_id
               JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
               WHERE d.status IN ('FROZEN', 'SETTLED')
                 AND dv.validation_status = 'VALID'
                 AND dv.confirmed_at IS NOT NULL AND dv.confirmed_at <= %s
                 AND d.scheduled_date <= %s
               ORDER BY d.scheduled_date, d.game_id, d.draw_type_id, d.scheduled_sequence, d.draw_id""",
            (cutoff, cutoff.date()),
        ).fetchall()
        if not rows:
            raise DatasetSnapshotError("no canonical validated draws exist at the requested cutoff")

        game_version_ids = tuple(sorted({str(row[1]) for row in rows}))
        effectivity_statuses = set()
        eligibility_statuses = set()
        for _, _, game_rules, draw_type_rules in rows:
            effectivity_statuses.add(game_rules.get("historical_effectivity", "UNSPECIFIED"))
            eligibility_statuses.add(game_rules.get("model_eligibility", "UNSPECIFIED"))
            eligibility_statuses.add(draw_type_rules.get("modeling_eligibility", "UNSPECIFIED"))
        modeling_eligibility = (
            "EXPLORATORY_ONLY"
            if any(status != "VERIFIED" for status in effectivity_statuses)
            or any(status not in {"VERIFIED", "ELIGIBLE_FOR_RESEARCH"} for status in eligibility_statuses)
            else "RULES_VERIFIED"
        )
        manifest = DatasetSnapshotManifest(
            draw_version_ids=tuple(str(row[0]) for row in rows),
            game_version_ids=game_version_ids,
            cutoff_at=cutoff,
            schema_version=resolved_schema_version,
            code_version=code_version,
            historical_effectivity_statuses=tuple(effectivity_statuses),
            model_eligibility_statuses=tuple(eligibility_statuses),
            modeling_eligibility=modeling_eligibility,
        )
        existing = connection.execute(
            """SELECT dataset_version_id, version_number
               FROM datasets.dataset_versions
               WHERE dataset_id = %s AND manifest_sha256 = %s""",
            (dataset_id, manifest.sha256),
        ).fetchone()
        if existing:
            member_count = connection.execute(
                "SELECT count(*) FROM datasets.dataset_members WHERE dataset_version_id = %s",
                (existing[0],),
            ).fetchone()[0]
            if member_count != len(rows):
                raise DatasetSnapshotError("stored snapshot member count does not match its manifest")
            return DatasetSnapshot(dataset_id, existing[0], existing[1], manifest, False)

        version_number = connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM datasets.dataset_versions WHERE dataset_id = %s",
            (dataset_id,),
        ).fetchone()[0]
        dataset_version_id = uuid4()
        connection.execute(
            """INSERT INTO datasets.dataset_versions
               (dataset_version_id, dataset_id, version_number, cutoff_at, schema_version,
                code_version, manifest, manifest_sha256)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                dataset_version_id,
                dataset_id,
                version_number,
                cutoff,
                resolved_schema_version,
                code_version,
                Jsonb(manifest.to_dict()),
                manifest.sha256,
            ),
        )
        connection.cursor().executemany(
            """INSERT INTO datasets.dataset_members
               (dataset_version_id, draw_version_id, ordinal)
               VALUES (%s, %s, %s)""",
            [
                (dataset_version_id, row[0], ordinal)
                for ordinal, row in enumerate(rows, start=1)
            ],
        )
        return DatasetSnapshot(dataset_id, dataset_version_id, version_number, manifest, True)


def _ensure_dataset(connection: Any, code: str, display_name: str) -> UUID:
    proposed_id = uuid4()
    inserted = connection.execute(
        """INSERT INTO datasets.datasets (dataset_id, code, display_name)
           VALUES (%s, %s, %s)
           ON CONFLICT (code) DO NOTHING
           RETURNING dataset_id""",
        (proposed_id, code, display_name),
    ).fetchone()
    if inserted:
        return inserted[0]
    existing = connection.execute(
        "SELECT dataset_id, display_name FROM datasets.datasets WHERE code = %s FOR UPDATE",
        (code,),
    ).fetchone()
    if existing is None or existing[1] != display_name:
        raise DatasetSnapshotError("existing dataset code has a different display name")
    return existing[0]
