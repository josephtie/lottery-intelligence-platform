from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.dataset_repository import workspace_code_version


class ResearchError(RuntimeError):
    pass


class ResearchConflict(ResearchError):
    pass


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Hypothesis:
    hypothesis_id: UUID
    code: str
    title: str
    statement: str
    status: str
    created: bool


@dataclass(frozen=True, slots=True)
class FeatureVersion:
    feature_version_id: UUID
    code: str
    version: int
    definition_sha256: str
    created: bool


@dataclass(frozen=True, slots=True)
class Experiment:
    experiment_id: UUID
    hypothesis_id: UUID
    dataset_version_id: UUID
    feature_version_id: UUID | None
    configuration_sha256: str
    code_version: str
    random_seed: int | None
    status: str
    created: bool


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    experiment_run_id: UUID
    experiment_id: UUID
    run_number: int
    scope: str
    status: str


def create_hypothesis(
    connection: Any,
    *,
    code: str,
    title: str,
    statement: str,
) -> Hypothesis:
    if not code.strip() or not title.strip() or not statement.strip():
        raise ValueError("hypothesis code, title and statement cannot be empty")
    hypothesis_id = uuid4()
    inserted = connection.execute(
        """INSERT INTO research.hypotheses (hypothesis_id, code, title, statement)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (code) DO NOTHING
           RETURNING hypothesis_id""",
        (hypothesis_id, code, title, statement),
    ).fetchone()
    if inserted:
        return Hypothesis(inserted[0], code, title, statement, "OPEN", True)
    existing = connection.execute(
        "SELECT hypothesis_id, title, statement, status FROM research.hypotheses WHERE code = %s",
        (code,),
    ).fetchone()
    if existing is None or existing[1] != title or existing[2] != statement:
        raise ResearchConflict("existing hypothesis code has a different title or statement")
    return Hypothesis(existing[0], code, title, statement, existing[3], False)


def register_feature_version(
    connection: Any,
    *,
    code: str,
    definition: Mapping[str, Any],
) -> FeatureVersion:
    if not code.strip():
        raise ValueError("feature code cannot be empty")
    if not isinstance(definition, Mapping):
        raise TypeError("feature definition must be a mapping")
    definition_sha = canonical_sha256(definition)
    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"feature:{code}",),
        )
        existing = connection.execute(
            """SELECT feature_version_id, version FROM research.feature_versions
               WHERE code = %s AND definition_sha256 = %s""",
            (code, definition_sha),
        ).fetchone()
        if existing:
            return FeatureVersion(existing[0], code, existing[1], definition_sha, False)
        version = connection.execute(
            """SELECT COALESCE(MAX(version), 0) + 1 FROM research.feature_versions
               WHERE code = %s""",
            (code,),
        ).fetchone()[0]
        feature_version_id = uuid4()
        connection.execute(
            """INSERT INTO research.feature_versions
               (feature_version_id, code, version, definition, definition_sha256)
               VALUES (%s, %s, %s, %s, %s)""",
            (feature_version_id, code, version, Jsonb(dict(definition)), definition_sha),
        )
        return FeatureVersion(feature_version_id, code, version, definition_sha, True)


def create_experiment(
    connection: Any,
    *,
    hypothesis_id: UUID | str,
    dataset_version_id: UUID | str,
    configuration: Mapping[str, Any],
    random_seed: int | None = None,
    feature_version_id: UUID | str | None = None,
    model_version_id: UUID | str | None = None,
    model_version: str | None = None,
    strategy_version: str | None = None,
    code_version: str | None = None,
) -> Experiment:
    if not isinstance(configuration, Mapping):
        raise TypeError("experiment configuration must be a mapping")
    code_version = code_version or workspace_code_version()
    configuration_sha = canonical_sha256(configuration)

    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"experiment:{hypothesis_id}",),
        )
        existing = connection.execute(
            """SELECT experiment_id, feature_version_id, random_seed, status
               FROM research.experiments
               WHERE hypothesis_id = %s AND dataset_version_id = %s
                 AND configuration_sha256 = %s AND code_version = %s
                 AND random_seed IS NOT DISTINCT FROM %s
                 AND feature_version_id IS NOT DISTINCT FROM %s
                 AND model_version_id IS NOT DISTINCT FROM %s
                 AND model_version IS NOT DISTINCT FROM %s
                 AND strategy_version IS NOT DISTINCT FROM %s""",
            (
                hypothesis_id, dataset_version_id, configuration_sha, code_version,
                random_seed, feature_version_id, model_version_id, model_version, strategy_version,
            ),
        ).fetchone()
        if existing:
            return Experiment(
                existing[0], UUID(str(hypothesis_id)), UUID(str(dataset_version_id)),
                existing[1], configuration_sha, code_version, existing[2], existing[3], False,
            )
        dataset_exists = connection.execute(
            "SELECT 1 FROM datasets.dataset_versions WHERE dataset_version_id = %s",
            (dataset_version_id,),
        ).fetchone()
        if dataset_exists is None:
            raise ResearchError("dataset_version_id does not reference a dataset version")
        experiment_id = uuid4()
        connection.execute(
            """INSERT INTO research.experiments
               (experiment_id, hypothesis_id, dataset_version_id, feature_version_id,
                model_version_id, model_version, strategy_version, code_version, configuration,
                configuration_sha256, random_seed)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                experiment_id, hypothesis_id, dataset_version_id, feature_version_id,
                model_version_id, model_version, strategy_version, code_version,
                Jsonb(dict(configuration)), configuration_sha, random_seed,
            ),
        )
        connection.execute(
            "UPDATE research.hypotheses SET status = 'TESTING' WHERE hypothesis_id = %s AND status = 'OPEN'",
            (hypothesis_id,),
        )
        return Experiment(
            experiment_id, UUID(str(hypothesis_id)), UUID(str(dataset_version_id)),
            UUID(str(feature_version_id)) if feature_version_id else None,
            configuration_sha, code_version, random_seed, "DESIGNED", True,
        )


def start_run(
    connection: Any,
    *,
    experiment_id: UUID | str,
    scope: str,
    cutoff_at: datetime | None = None,
    details: Mapping[str, Any] | None = None,
) -> ExperimentRun:
    valid_scopes = {"TRAIN", "VALIDATION", "OUT_OF_SAMPLE", "PROSPECTIVE", "GLOBAL"}
    if scope not in valid_scopes:
        raise ValueError(f"scope must be one of {sorted(valid_scopes)}")
    with connection.transaction():
        experiment = connection.execute(
            "SELECT status FROM research.experiments WHERE experiment_id = %s FOR UPDATE",
            (experiment_id,),
        ).fetchone()
        if experiment is None:
            raise ResearchError("experiment_id does not reference an experiment")
        run_number = connection.execute(
            """SELECT COALESCE(MAX(run_number), 0) + 1 FROM research.experiment_runs
               WHERE experiment_id = %s""",
            (experiment_id,),
        ).fetchone()[0]
        run_id = uuid4()
        connection.execute(
            """INSERT INTO research.experiment_runs
               (experiment_run_id, experiment_id, run_number, scope, cutoff_at, details)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (run_id, experiment_id, run_number, scope, cutoff_at, Jsonb(dict(details or {}))),
        )
        connection.execute(
            "UPDATE research.experiments SET status = 'RUNNING' WHERE experiment_id = %s AND status = 'DESIGNED'",
            (experiment_id,),
        )
    return ExperimentRun(run_id, UUID(str(experiment_id)), run_number, scope, "RUNNING")


def finish_run(
    connection: Any,
    *,
    experiment_run_id: UUID | str,
    status: str = "COMPLETED",
    details: Mapping[str, Any] | None = None,
) -> None:
    if status not in {"COMPLETED", "FAILED"}:
        raise ValueError("status must be COMPLETED or FAILED")
    updated = connection.execute(
        """UPDATE research.experiment_runs
           SET status = %s, finished_at = CURRENT_TIMESTAMP,
               details = details || %s::JSONB
           WHERE experiment_run_id = %s AND status = 'RUNNING'""",
        (status, Jsonb(dict(details or {})), experiment_run_id),
    ).rowcount
    if updated != 1:
        raise ResearchError("run is not running or does not exist")


def complete_experiment(connection: Any, *, experiment_id: UUID | str) -> None:
    open_runs = connection.execute(
        """SELECT count(*) FROM research.experiment_runs
           WHERE experiment_id = %s AND status = 'RUNNING'""",
        (experiment_id,),
    ).fetchone()[0]
    if open_runs:
        raise ResearchError("experiment still has running runs")
    updated = connection.execute(
        """UPDATE research.experiments
           SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
           WHERE experiment_id = %s AND status IN ('DESIGNED', 'RUNNING')""",
        (experiment_id,),
    ).rowcount
    if updated != 1:
        raise ResearchError("experiment cannot be completed from its current status")


def record_metric(
    connection: Any,
    *,
    experiment_id: UUID | str,
    metric_name: str,
    metric_scope: str,
    metric_value: float | None,
    experiment_run_id: UUID | str | None = None,
    details: Mapping[str, Any] | None = None,
) -> UUID:
    if not metric_name.strip():
        raise ValueError("metric_name cannot be empty")
    metric_id = uuid4()
    connection.execute(
        """INSERT INTO research.experiment_metrics
           (experiment_metric_id, experiment_id, experiment_run_id, metric_name,
            metric_scope, metric_value, details)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            metric_id, experiment_id, experiment_run_id, metric_name,
            metric_scope, metric_value, Jsonb(dict(details or {})),
        ),
    )
    return metric_id


def record_finding(
    connection: Any,
    *,
    hypothesis_id: UUID | str,
    conclusion: str,
    status: str,
    evidence: Mapping[str, Any] | None = None,
    experiment_id: UUID | str | None = None,
) -> UUID:
    if not conclusion.strip():
        raise ValueError("conclusion cannot be empty")
    if status not in {"SUPPORTED", "REJECTED", "INCONCLUSIVE"}:
        raise ValueError("status must be SUPPORTED, REJECTED or INCONCLUSIVE")
    with connection.transaction():
        finding_id = uuid4()
        connection.execute(
            """INSERT INTO research.findings
               (finding_id, hypothesis_id, experiment_id, conclusion, status, evidence)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (finding_id, hypothesis_id, experiment_id, conclusion, status, Jsonb(dict(evidence or {}))),
        )
        connection.execute(
            "UPDATE research.hypotheses SET status = %s WHERE hypothesis_id = %s",
            (status, hypothesis_id),
        )
    return finding_id
